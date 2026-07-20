# -*- coding: utf-8 -*-
"""回补 2026-01-23 至今的 ETF 每日总份额历史。"""
import datetime
import sys

from fetch_etf_shares import (
    derive_sse_share_rows,
    fetch_sse_scale_rows,
    fetch_szse_share_rows,
)
from utils import load_json, save_json

START_DATE = datetime.date(2026, 1, 23)


def _merge_history(code, backfilled):
    existing = load_json(f"history/{code}.json", default=[])
    merged = {row["date"]: row for row in existing}
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


def main():
    end_date = datetime.date.today()
    conf = load_json("baselines.json")
    failures = 0
    for etf in conf["etfs"]:
        code, exchange, name = etf["code"], etf["exchange"], etf["name"]
        try:
            if exchange == "SZ":
                backfilled = fetch_szse_share_rows(code, START_DATE, end_date)
            else:
                scales = fetch_sse_scale_rows(code, START_DATE, end_date)
                backfilled = derive_sse_share_rows(code, scales)
            if not backfilled:
                raise ValueError("官方区间查询返回空记录")
            rows = _merge_history(code, backfilled)
            nav_count = sum(r["source"] == "sse_official_derived_nav" for r in backfilled)
            px_count = sum(r["source"] == "sse_official_derived_px" for r in backfilled)
            print(
                f"{name}({code}): 回补{len(backfilled)}条 "
                f"{backfilled[0]['date']}..{backfilled[-1]['date']} "
                f"[净值反推{nav_count}/价格兜底{px_count}]，历史共{len(rows)}条")
        except Exception as exc:
            print(f"[失败] {name}({code}): {exc}", file=sys.stderr)
            failures += 1
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
