# -*- coding: utf-8 -*-
"""每日抓取 ETF 最新总份额并写入 data/history/{code}.json。

数据源优先级：
  1) 上交所/深交所官方披露。查询最近 7 天并使用实际披露日期；
  2) 东方财富 f84，仅在官方源失败时兜底，记录一律 verified=False。

上交所 ETFGM 披露的是每日总份额（万份），直接换算为亿份；旧的
CKLSGM 规模/净值反推路径只在直接份额接口不可用时兜底。
任何来源都不允许把空值或 0 写入历史。
"""
import datetime
import functools
import math
import re
import sys
import time

import requests

from utils import load_json, append_history, gap_to_baseline, is_trading_day

EASTMONEY_URLS = (
    "https://push2.eastmoney.com/api/qt/stock/get",
    "https://push2delay.eastmoney.com/api/qt/stock/get",
)
EASTMONEY_NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
SSE_SCALE_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_SHARES_SQL_ID = "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L"
SZSE_REPORT_URL = "https://www.szse.cn/api/report/ShowReport/data"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
}
SSE_HEADERS = {**HEADERS, "Referer": "https://etf.sse.com.cn/"}
SZSE_HEADERS = {**HEADERS, "Referer": "https://fund.szse.cn/marketdata/fundslist/index.html"}
SANITY_MIN_YI, SANITY_MAX_YI = 0.1, 5000.0
OFFICIAL_LOOKBACK_DAYS = 7
RETRIES, BACKOFF = 3, 0.8


def _as_date(value):
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def _get_json(url, params, headers, timeout=20):
    """带短退避的 JSON GET；最终失败时把原始异常交给调用方处理。"""
    last_error = None
    for attempt in range(RETRIES):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt + 1 < RETRIES:
                time.sleep(BACKOFF * (2 ** attempt))
    raise last_error


def fetch_eastmoney(code: str, exchange: str):
    """官方源失败时的兜底；f84 可能滞后，调用方必须标记未核验。"""
    market = "1" if exchange == "SH" else "0"
    params = {
        "secid": f"{market}.{code}",
        "fields": "f57,f58,f84,f85,f116,f117,f124,f297",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "invt": "2",
        "fltt": "2",
    }
    for url in EASTMONEY_URLS:
        try:
            payload = _get_json(url, params, HEADERS)
            data = (payload or {}).get("data") or {}
            raw = data.get("f84")
            if raw in (None, "-", 0, "0"):
                raise ValueError(f"f84 空值: {data}")
            shares_yi = float(raw) / 1e8
            if not (SANITY_MIN_YI <= shares_yi <= SANITY_MAX_YI):
                raise ValueError(f"份额超出合理区间: {shares_yi} 亿份")
            return shares_yi
        except (requests.RequestException, ValueError, TypeError) as exc:
            message = re.sub(r"\s+", " ", str(exc)).strip()
            print(f"  [东财兜底不可用] {code} {url.split('/')[2]}: {message}", file=sys.stderr)
    return None


def fetch_eastmoney_navs(code: str, start_date, end_date):
    """实测的东方财富历史单位净值接口，返回 {日期: 单位净值}。"""
    start_date, end_date = _as_date(start_date), _as_date(end_date)
    headers = {**HEADERS, "Referer": f"https://fundf10.eastmoney.com/jjjz_{code}.html"}
    base_params = {
        "fundCode": code,
        "pageSize": 20,
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
    }
    first = _get_json(EASTMONEY_NAV_URL, {**base_params, "pageIndex": 1}, headers)
    total = int(first.get("TotalCount") or 0)
    page_size = int(first.get("PageSize") or 20)
    page_count = math.ceil(total / page_size) if total else 0
    payloads = [first]
    for page_no in range(2, page_count + 1):
        payloads.append(_get_json(
            EASTMONEY_NAV_URL, {**base_params, "pageIndex": page_no}, headers))
    navs = {}
    for payload in payloads:
        for row in ((payload.get("Data") or {}).get("LSJZList") or []):
            day, raw_nav = row.get("FSRQ"), row.get("DWJZ")
            if not day or raw_nav in (None, "", "-"):
                continue
            nav = float(raw_nav)
            if nav > 0:
                navs[day] = nav
    return navs


def fetch_eastmoney_closes(code: str, exchange: str, start_date, end_date):
    """净值缺失时的未复权收盘价兜底，返回 {日期: 收盘价}。"""
    start_date, end_date = _as_date(start_date), _as_date(end_date)
    market = "1" if exchange == "SH" else "0"
    params = {
        "secid": f"{market}.{code}",
        "klt": 101,
        "fqt": 0,
        "lmt": 1000,
        "beg": start_date.strftime("%Y%m%d"),
        "end": end_date.strftime("%Y%m%d"),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    payload = _get_json(EASTMONEY_KLINE_URL, params, HEADERS)
    closes = {}
    for line in ((payload.get("data") or {}).get("klines") or []):
        parts = line.split(",")
        if len(parts) >= 3 and parts[2] not in ("", "-"):
            closes[parts[0]] = float(parts[2])
    return closes


def fetch_sse_scale_rows(code: str, start_date, end_date):
    """上交所参考历史规模 CKLSGM，SCALE 单位为亿元。"""
    start_date, end_date = _as_date(start_date), _as_date(end_date)
    params = {
        "isPagination": "true",
        "sqlId": "COMMON_JJZWZ_JJLB_JJXQ_JJGM_CKLSGM_L",
        "pageHelp.cacheSize": 1,
        "pageHelp.pageSize": 500,
        "pageHelp.pageNo": 1,
        "pageHelp.beginPage": 1,
        "pageHelp.endPage": 1,
        "FUND_CODE": code,
        "START_DATE": start_date.strftime("%Y%m%d"),
        "END_DATE": end_date.strftime("%Y%m%d"),
    }
    payload = _get_json(SSE_SCALE_URL, params, SSE_HEADERS)
    rows = []
    for row in payload.get("result") or []:
        if str(row.get("FUND_CODE", "")).strip() != code:
            continue
        day, raw_scale = row.get("TRADE_DATE"), row.get("SCALE")
        if day and raw_scale not in (None, "", "-"):
            rows.append({"date": day, "scale_yi_yuan": float(str(raw_scale).replace(",", ""))})
    return sorted(rows, key=lambda item: item["date"])


def _parse_sse_share_payload(payload, codes=None):
    """解析上交所 ETF 总份额报表；TOT_VOL 单位为万份。"""
    wanted = set(codes or [])
    rows = []
    for row in (payload or {}).get("result") or []:
        code = str(row.get("SEC_CODE", "")).strip()
        if wanted and code not in wanted:
            continue
        day, raw_volume = row.get("STAT_DATE"), row.get("TOT_VOL")
        if not code or not day or raw_volume in (None, "", "-", 0, "0"):
            continue
        shares_yi = float(str(raw_volume).replace(",", "")) / 1e4
        if SANITY_MIN_YI <= shares_yi <= SANITY_MAX_YI:
            rows.append({
                "code": code,
                "date": day,
                "total_shares_yi": shares_yi,
                "source": "sse_official_shares",
                "verified": True,
            })
    return sorted(rows, key=lambda item: (item["date"], item["code"]))


@functools.lru_cache(maxsize=64)
def _fetch_sse_share_payload_for_date(day_iso):
    params = {
        "isPagination": "true",
        "sqlId": SSE_SHARES_SQL_ID,
        "pageHelp.cacheSize": 1,
        "pageHelp.pageSize": 2000,
        "pageHelp.pageNo": 1,
        "pageHelp.beginPage": 1,
        "pageHelp.endPage": 1,
        "STAT_DATE": day_iso,
    }
    return _get_json(SSE_SCALE_URL, params, SSE_HEADERS)


def fetch_sse_share_rows_for_date(as_of, codes=None):
    """读取某日上交所全部 ETF 的直接总份额，再按代码筛选。"""
    day = _as_date(as_of).isoformat()
    return _parse_sse_share_payload(
        _fetch_sse_share_payload_for_date(day), codes=codes)


def fetch_szse_share_rows(code: str, start_date, end_date):
    """深交所基金规模报表，current_size 单位为万份。"""
    start_date, end_date = _as_date(start_date), _as_date(end_date)
    base_params = {
        "SHOWTYPE": "JSON",
        "CATALOGID": "fund_jjgm",
        "TABKEY": "tab1",
        "txtDm": code,
        "txtStart": start_date.isoformat(),
        "txtEnd": end_date.isoformat(),
    }
    first = _get_json(SZSE_REPORT_URL, {**base_params, "PAGENO": 1}, SZSE_HEADERS)
    first_tab = next((tab for tab in first
                      if tab.get("metadata", {}).get("tabkey") == "tab1"), None)
    if not first_tab:
        return []
    page_count = int(first_tab.get("metadata", {}).get("pagecount") or 1)
    tabs = [first_tab]
    for page_no in range(2, page_count + 1):
        payload = _get_json(
            SZSE_REPORT_URL, {**base_params, "PAGENO": page_no}, SZSE_HEADERS)
        tab = next((item for item in payload
                    if item.get("metadata", {}).get("tabkey") == "tab1"), None)
        if tab:
            tabs.append(tab)
    rows = []
    for tab in tabs:
        for row in tab.get("data") or []:
            if str(row.get("fund_code", "")).strip() != code:
                continue
            day, raw_size = row.get("size_date"), row.get("current_size")
            if day and raw_size not in (None, "", "-"):
                shares_yi = float(str(raw_size).replace(",", "")) / 1e4
                rows.append({
                    "date": day,
                    "total_shares_yi": shares_yi,
                    "source": "szse_official",
                    "verified": True,
                })
    deduped = {row["date"]: row for row in rows}
    return sorted(deduped.values(), key=lambda item: item["date"])


def derive_sse_share_rows(code: str, scale_rows):
    """用单位净值优先、收盘价兜底，将上交所亿元规模反推为亿份。"""
    if not scale_rows:
        return []
    start_date, end_date = scale_rows[0]["date"], scale_rows[-1]["date"]
    try:
        navs = fetch_eastmoney_navs(code, start_date, end_date)
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        print(f"  [净值源不可用] {code}: {exc}", file=sys.stderr)
        navs = {}
    missing_nav = any(row["date"] not in navs for row in scale_rows)
    closes = {}
    if missing_nav:
        try:
            closes = fetch_eastmoney_closes(code, "SH", start_date, end_date)
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            print(f"  [收盘价兜底不可用] {code}: {exc}", file=sys.stderr)
    derived = []
    for row in scale_rows:
        day = row["date"]
        denominator = navs.get(day)
        source = "sse_official_derived_nav"
        if not denominator:
            denominator = closes.get(day)
            source = "sse_official_derived_px"
        if not denominator or denominator <= 0:
            print(f"  [跳过] {code} {day}: 无单位净值或收盘价", file=sys.stderr)
            continue
        shares_yi = row["scale_yi_yuan"] / denominator
        if SANITY_MIN_YI <= shares_yi <= SANITY_MAX_YI:
            derived.append({
                "date": day,
                "total_shares_yi": shares_yi,
                "source": source,
                "verified": True,
            })
    return derived


def fetch_official(code: str, exchange: str, as_of=None):
    """查询 [as_of-7天, as_of] 并返回最新官方记录的值、来源、实际日期。

    深交所实测请求：
    https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=fund_jjgm&TABKEY=tab1&PAGENO=1&txtDm=159919&txtStart=2026-07-14&txtEnd=2026-07-21

    上交所实测请求（TOT_VOL 为万份）：
    https://query.sse.com.cn/commonQuery.do?isPagination=true&sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L&pageHelp.pageSize=2000&pageHelp.pageNo=1&STAT_DATE=2026-07-20
    """
    end_date = _as_date(as_of or datetime.date.today())
    start_date = end_date - datetime.timedelta(days=OFFICIAL_LOOKBACK_DAYS)
    try:
        if exchange == "SZ":
            rows = fetch_szse_share_rows(code, start_date, end_date)
        else:
            # 直接份额报表按单日查询；倒序命中最近披露日后即可停止。
            rows = []
            for offset in range(OFFICIAL_LOOKBACK_DAYS + 1):
                day = end_date - datetime.timedelta(days=offset)
                if day.weekday() >= 5:
                    continue
                rows = fetch_sse_share_rows_for_date(day, codes=[code])
                if rows:
                    break
            # 旧规模接口保留为官方兜底，避免交易所直接接口短时故障。
            if not rows:
                scales = fetch_sse_scale_rows(code, start_date, end_date)
                rows = derive_sse_share_rows(code, scales)
        if not rows:
            return None, None, None
        latest = max(rows, key=lambda item: item["date"])
        return latest["total_shares_yi"], latest["source"], latest["date"]
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        message = re.sub(r"\s+", " ", str(exc)).strip()
        print(f"  [官方源不可用] {code}: {message}", file=sys.stderr)
        return None, None, None


def main():
    today = datetime.date.today()
    if not is_trading_day(today):
        print(f"{today} 非交易日, 跳过")
        return 0
    conf = load_json("baselines.json")
    failures = 0
    for etf in conf["etfs"]:
        code, exchange, name = etf["code"], etf["exchange"], etf["name"]
        baseline = etf["huijin_shares_yi"]

        # 官方源始终优先；只有官方源完全失败才访问东财 f84。
        shares, source, actual_date = fetch_official(code, exchange, today)
        verified = shares is not None
        if shares is None:
            shares = fetch_eastmoney(code, exchange)
            source, actual_date, verified = "eastmoney_f84", today.isoformat(), False
            if shares is not None:
                print(f"  [仅东财兜底，未核验] {name}")
        if shares is None:
            print(f"[失败] {name}({code}) 全部数据源不可用", file=sys.stderr)
            failures += 1
            continue

        append_history(code, actual_date, shares, source, verified)
        gap, inverted = gap_to_baseline(shares, baseline)
        flag = f" 倒挂! 减持下限{abs(gap):.1f}亿份" if inverted else ""
        print(f"{name:<14}{shares:>10.2f} 亿份 [{actual_date} {source}]{flag}")
        time.sleep(0.2)
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
