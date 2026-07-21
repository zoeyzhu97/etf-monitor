# -*- coding: utf-8 -*-
"""检查ETF历史文件是否已到达最新应有交易日。

工作流只在北京时间22:00的最终重试及手动运行时调用。
滞后时退出码1，供 GitHub Actions 发送告警；不删除已有数据。
"""
import argparse
import datetime
import os

from utils import is_trading_day, load_history, load_json


def expected_trading_date(as_of):
    """返回 as_of 当日或之前最近的A股交易日。"""
    day = as_of
    while not is_trading_day(day):
        day -= datetime.timedelta(days=1)
    return day.isoformat()


def find_stale_etfs(etfs, histories, expected_date):
    """返回缺失 expected_date 的ETF及其最新日期。"""
    stale = []
    for etf in etfs:
        code = etf["code"]
        rows = histories.get(code) or []
        latest = max((row.get("date", "") for row in rows), default="")
        if latest < expected_date:
            stale.append({
                "code": code,
                "name": etf.get("name", code),
                "latest_date": latest or "无数据",
            })
    return stale


def _write_github_output(message):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        safe = message.replace("\r", " ").replace("\n", " ")
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"message={safe}\n")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of",
        type=datetime.date.fromisoformat,
        default=datetime.date.today(),
        help="按 UTC 日期检查，默认为运行日。",
    )
    args = parser.parse_args(argv)
    expected = expected_trading_date(args.as_of)
    conf = load_json("baselines.json", default={})
    etfs = conf.get("etfs", [])
    histories = {etf["code"]: load_history(etf["code"]) for etf in etfs}
    stale = find_stale_etfs(etfs, histories, expected)
    if stale:
        details = "、".join(
            f'{item["name"]}({item["code"]})最新{item["latest_date"]}'
            for item in stale
        )
        message = f"期望ETF份额日期为{expected}，但仍滞后：{details}。"
        print(f"[滞后] {message}")
        _write_github_output(message)
        return 1
    message = f"全部{len(etfs)}只ETF已更新至{expected}。"
    print(f"[正常] {message}")
    _write_github_output(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
