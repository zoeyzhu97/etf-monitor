# -*- coding: utf-8 -*-
"""回补本轮中央汇金公开 ETF 操作期内的每日总份额。

监测起点取 2023-10-23（汇金公开宣布当日买入 ETF），不是 ETF 成立日。
上交所按交易日一次查询全部目标 ETF 的直接总份额；深交所按短区间查询，
避免其报表接口在日期范围过大时返回空结果。
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import sys

from fetch_etf_shares import (
    fetch_sse_share_rows_for_date,
    fetch_szse_share_rows,
)
from utils import load_json, save_json

START_DATE = datetime.date(2023, 10, 23)
SZSE_CHUNK_DAYS = 80
SSE_WORKERS = 4


def _merge_history(code, backfilled):
    existing = load_json(f"history/{code}.json", default=[])
    # 份额图围绕国家队公开 ETF 操作周期，而不是基金成立以来的全寿命。
    merged = {row["date"]: row for row in existing
              if row["date"] >= START_DATE.isoformat()}
    for row in backfilled:
        merged[row["date"]] = {
            "date": row["date"],
            "total_shares_yi": round(float(row["total_shares_yi"]), 2),
            "source": row["source"],
            "verified": bool(row["verified"]),
        }
    rows = sorted(merged.values(), key=lambda item: item["date"])
    save_json(f"history/{code}.json", rows)
    return rows


def _date_chunks(start_date, end_date, chunk_days=SZSE_CHUNK_DAYS):
    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(cursor + datetime.timedelta(days=chunk_days - 1), end_date)
        yield cursor, chunk_end
        cursor = chunk_end + datetime.timedelta(days=1)


def _trading_dates(start_date, end_date):
    rows = load_json("index/000001.json", default=[])
    dates = [row["date"] for row in rows
             if start_date.isoformat() <= row["date"] <= end_date.isoformat()]
    if dates:
        return dates
    # 指数数据缺失时的保守兜底；节假日会返回空报表，不会写入伪记录。
    days = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor += datetime.timedelta(days=1)
    return days


def _backfill_sse(etfs, start_date, end_date):
    codes = [etf["code"] for etf in etfs]
    by_code = {code: [] for code in codes}
    dates = _trading_dates(start_date, end_date)
    failures = []
    with ThreadPoolExecutor(max_workers=SSE_WORKERS) as pool:
        futures = {
            pool.submit(fetch_sse_share_rows_for_date, day, codes): day
            for day in dates
        }
        for future in as_completed(futures):
            day = futures[future]
            try:
                for row in future.result():
                    by_code[row["code"]].append(row)
            except Exception as exc:
                failures.append((day, str(exc)))
    if failures:
        sample = "; ".join(f"{d}: {e}" for d, e in failures[:3])
        raise RuntimeError(f"上交所 {len(failures)} 个交易日查询失败；{sample}")
    for rows in by_code.values():
        rows.sort(key=lambda item: item["date"])
    return by_code


def _backfill_szse(code, start_date, end_date):
    rows = []
    for chunk_start, chunk_end in _date_chunks(start_date, end_date):
        rows.extend(fetch_szse_share_rows(code, chunk_start, chunk_end))
    deduped = {row["date"]: row for row in rows}
    return sorted(deduped.values(), key=lambda item: item["date"])


def main():
    end_date = datetime.date.today()
    conf = load_json("baselines.json")
    failures = 0
    sse_etfs = [etf for etf in conf["etfs"] if etf["exchange"] == "SH"]
    try:
        print(f"上交所：读取 {START_DATE}..{end_date} 的直接总份额…", flush=True)
        sse_rows = _backfill_sse(sse_etfs, START_DATE, end_date)
    except Exception as exc:
        print(f"[失败] 上交所批量回补: {exc}", file=sys.stderr)
        sse_rows = {}
        failures += len(sse_etfs)

    for etf in conf["etfs"]:
        code, exchange, name = etf["code"], etf["exchange"], etf["name"]
        try:
            if exchange == "SZ":
                backfilled = _backfill_szse(code, START_DATE, end_date)
            else:
                if not sse_rows:
                    continue
                backfilled = sse_rows.get(code, [])
            if not backfilled:
                raise ValueError("官方区间查询返回空记录")
            rows = _merge_history(code, backfilled)
            print(
                f"{name}({code}): 回补{len(backfilled)}条 "
                f"{backfilled[0]['date']}..{backfilled[-1]['date']} "
                f"[{backfilled[-1]['source']}]，历史共{len(rows)}条")
        except Exception as exc:
            print(f"[失败] {name}({code}): {exc}", file=sys.stderr)
            failures += 1
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
