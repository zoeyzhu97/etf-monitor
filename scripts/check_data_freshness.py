# -*- coding: utf-8 -*-
"""检查ETF历史文件是否已到达最新应有交易日。

工作流每次抓取后都调用；滞后时退出码1。早期尝试据此显示状态，
北京次日02:17的最终重试据此发送告警并让任务失败；不删除已有数据。
"""
import argparse
import datetime
import os
import math

from utils import is_trading_day, load_history, load_json, market_data_date


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


def quality_errors(etfs, histories, expected):
    """日期齐全不等于可信：校验近期连续官方份额及数值。"""
    errors = []
    if not etfs:
        return ["ETF配置为空"]
    end = datetime.date.fromisoformat(expected)
    required = [(end - datetime.timedelta(days=i)).isoformat()
                for i in range(8) if is_trading_day(end - datetime.timedelta(days=i))]
    for etf in etfs:
        code = etf["code"]
        rows = histories.get(code) or []
        by_date = {r.get("date"): r for r in rows}
        if len(by_date) != len(rows):
            errors.append(f"{code}存在重复日期")
        if any(r.get("date", "") > expected for r in rows):
            errors.append(f"{code}存在超出基准日的记录")
        for day in required:
            row = by_date.get(day, {})
            value = row.get("total_shares_yi")
            valid_number = (isinstance(value, (int, float)) and not isinstance(value, bool)
                            and math.isfinite(value) and 0.1 <= value <= 5000)
            if (row.get("verified") is not True or
                    row.get("source") not in {"sse_official_shares", "szse_official"} or
                    not valid_number):
                errors.append(f"{code} {day}缺少有效的已核验官方份额")
    return errors


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
        default=None,
        help="指定检查基准日；默认按北京时间收盘界限确定，15点前检查前一日。",
    )
    parser.add_argument("--snapshot", action="store_true",
                        help="发布校验：以现有评估所属日检查快照，允许保留已核验旧站点。")
    args = parser.parse_args(argv)
    expected = expected_trading_date(args.as_of or market_data_date())
    if args.snapshot:
        expected = load_json("daily_assessment.json", default={}).get("as_of")
        if not expected:
            print("[失败] 缺少评估日期")
            return 1
    conf = load_json("baselines.json", default={})
    etfs = conf.get("etfs", [])
    histories = {etf["code"]: load_history(etf["code"]) for etf in etfs}
    stale = find_stale_etfs(etfs, histories, expected)
    errors = quality_errors(etfs, histories, expected)
    if stale or errors:
        details = "、".join(
            f'{item["name"]}({item["code"]})最新{item["latest_date"]}'
            for item in stale
        )
        message = f"ETF份额校验失败，基准日{expected}：{details}；" + "；".join(errors)
        print(f"[滞后] {message}")
        _write_github_output(message)
        return 1
    message = f"全部{len(etfs)}只ETF已更新至{expected}。"
    print(f"[正常] {message}")
    _write_github_output(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
