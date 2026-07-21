# -*- coding: utf-8 -*-
"""指数日线抓取与回补: A股三指数 + TWII / HSI。

首次运行(回补): 优先 akshare (pip install akshare), 拉取2005年至今日线;
此后每日增量: 只补最近缺失的交易日。
存储: data/index/{code}.json -> [{"date": "YYYY-MM-DD", "close": float}, ...]

2026-07-20 实测 akshare 1.18.64:
  - stock_zh_index_daily(symbol="sh000001") 可用，列名为
    date/open/high/low/close/volume；index_zh_a_hist 当日连接被上游关闭。
  - stock_hk_index_daily_sina(symbol="HSI") 仅从 2013 年开始，不足以
    覆盖 1998 年事件，故 TWII/HSI 改用实测可回溯至 1997/1990 的
    Yahoo Chart JSON:
    https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?period1=631152000&period2=1784678400&interval=1d&events=history
"""
import datetime
import sys

import requests

from utils import load_json, save_json

MAINLAND_INDEXES = {
    "000001": ("sh000001", "2005-01-01"),
    "399001": ("sz399001", "2005-01-01"),
    "000688": ("sh000688", "2020-07-01"),
}
GLOBAL_INDEXES = {"TWII": "^TWII", "HSI": "^HSI"}
# 与 event_study.INCLUDE_MARKETS 联动: 当前统计口径仅中国大陆,
# 停止境外指数的每日抓取; 如需恢复参照样本改为 True。
FETCH_GLOBAL_INDEXES = False
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def backfill_with_akshare(code: str, symbol: str, start_date: str):
    import akshare as ak  # noqa: 延迟导入, 未安装时报错清晰
    df = ak.stock_zh_index_daily(symbol=symbol)
    required = {"date", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"akshare 列名变更: {list(df.columns)}")
    rows = [{"date": str(r["date"])[:10], "close": round(float(r["close"]), 2)}
            for _, r in df.iterrows() if str(r["date"])[:10] >= start_date]
    if not rows:
        raise ValueError("返回空日线")
    rows.sort(key=lambda r: r["date"])
    save_json(f"index/{code}.json", rows)
    print(f"{code}: 回补 {len(rows)} 条 ({rows[0]['date']}..{rows[-1]['date']})")
    if code == "000001" and "low" in df.columns:
        for anchor in ("2024-02-05", "2024-09-18"):
            hit = df[df["date"].astype(str).str[:10] == anchor]
            if not hit.empty:
                print(f"  锚点 {anchor} 最低 {float(hit.iloc[0]['low']):.2f}")


def backfill_with_yahoo(code: str, symbol: str):
    start = int(datetime.datetime(1990, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
    end = int(datetime.datetime.combine(
        datetime.date.today() + datetime.timedelta(days=2), datetime.time.min,
        tzinfo=datetime.timezone.utc).timestamp())
    r = requests.get(YAHOO_CHART_URL.format(symbol=requests.utils.quote(symbol, safe="")),
                     params={"period1": start, "period2": end, "interval": "1d",
                             "events": "history"}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    chart = (r.json() or {}).get("chart") or {}
    if chart.get("error"):
        raise ValueError(chart["error"])
    result = (chart.get("result") or [None])[0]
    if not result:
        raise ValueError("返回空图表")
    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    rows = []
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        day = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).date().isoformat()
        rows.append({"date": day, "close": round(float(close), 2)})
    if not rows:
        raise ValueError("返回空日线")
    rows.sort(key=lambda item: item["date"])
    save_json(f"index/{code}.json", rows)
    print(f"{code}: 回补 {len(rows)} 条 ({rows[0]['date']}..{rows[-1]['date']})")


def main():
    failures = 0
    for code, (symbol, start_date) in MAINLAND_INDEXES.items():
        existing = load_json(f"index/{code}.json", default=[])
        try:
            backfill_with_akshare(code, symbol, start_date)
        except Exception as e:
            print(f"[失败] {code}: {e} (已有{len(existing)}条, 保持不变)", file=sys.stderr)
            failures += 1
    for code, symbol in (GLOBAL_INDEXES.items() if FETCH_GLOBAL_INDEXES else ()):
        existing = load_json(f"index/{code}.json", default=[])
        try:
            backfill_with_yahoo(code, symbol)
        except Exception as e:
            print(f"[失败] {code}: {e} (已有{len(existing)}条, 保持不变)", file=sys.stderr)
            failures += 1
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
