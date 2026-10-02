# -*- coding: utf-8 -*-
"""从上交所年度休市安排同步 A 股非周末休市日。"""
import argparse
import datetime
from html.parser import HTMLParser
import os
import re
import sys

import requests

from utils import is_trading_day, load_json, save_json

SSE_CALENDAR_URL = "https://www.sse.com.cn/disclosure/dealinstruc/closed/"
YEAR_PATTERN = re.compile(r"<strong>\s*(\d{4})年休市安排\s*</strong>")
RANGE_PATTERN = re.compile(
    r"(\d{1,2})月(\d{1,2})日[^，。]*?至(?:(\d{1,2})月)?"
    r"(\d{1,2})日[^，。]*?休市"
)


class TableCells(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.current is not None:
            self.cells.append("".join(self.current).strip())
            self.current = None


def parse_sse_holidays(html, expected_year):
    """只接受当前年度的完整官方表，避免误读往年或公告链接。"""
    match = YEAR_PATTERN.search(html)
    if not match or int(match.group(1)) != expected_year:
        raise ValueError(f"上交所页面没有 {expected_year} 年年度休市安排")
    table = html[match.end():].split("</table>", 1)[0]
    parser = TableCells()
    parser.feed(table)
    holidays = set()
    ranges = 0
    for cell in parser.cells:
        main = cell.split("另外", 1)[0]
        match = RANGE_PATTERN.search(main)
        if not match:
            continue
        start_month, start_day = int(match.group(1)), int(match.group(2))
        end_month = int(match.group(3) or start_month)
        end_day = int(match.group(4))
        start = datetime.date(expected_year, start_month, start_day)
        end = datetime.date(expected_year, end_month, end_day)
        if end < start or (end - start).days > 14:
            raise ValueError(f"无法解析休市区间：{cell}")
        ranges += 1
        day = start
        while day <= end:
            if day.weekday() < 5:
                holidays.add(day.isoformat())
            day += datetime.timedelta(days=1)
    if ranges < 5 or len(holidays) < 10:
        raise ValueError("上交所年度休市表解析不完整")
    return sorted(holidays)


def sync(as_of):
    year = as_of.year
    existing = set(load_json("holidays.json", default=[]))
    try:
        response = requests.get(
            SSE_CALENDAR_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        # 上交所页面声明 UTF-8，但响应头没有 charset；requests 会误用 Latin-1。
        official = parse_sse_holidays(response.content.decode("utf-8"), year)
    except (requests.RequestException, ValueError) as exc:
        # 已核验的本地年度表允许交易所网站短时不可达；新年度没有表时
        # 必须明确失败，不能把所有周一至周五误认成交易日。
        if any(date.startswith(f"{year}-") for date in existing):
            print(f"[休市表] 官方同步暂不可用，沿用本地 {year} 年表：{exc}")
            return
        raise RuntimeError(f"{year} 年休市表缺失且官方同步失败：{exc}") from exc
    updated = sorted(
        {date for date in existing if not date.startswith(f"{year}-")}
        | set(official)
    )
    if updated != sorted(existing):
        save_json("holidays.json", updated)
        print(f"[休市表] 已同步上交所 {year} 年 {len(official)} 个工作日休市日期")
    else:
        print(f"[休市表] 上交所 {year} 年休市日期已是最新")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=datetime.date.fromisoformat,
                        default=datetime.datetime.now(datetime.timezone.utc).date())
    args = parser.parse_args()
    try:
        sync(args.as_of)
    except RuntimeError as exc:
        print(f"[休市表错误] {exc}", file=sys.stderr)
        return 1
    trading_day = is_trading_day(args.as_of)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"trading_day={str(trading_day).lower()}\n")
    if not trading_day:
        print(f"[休市表] {args.as_of} 非交易日，跳过行情更新与发布")
    return 0


if __name__ == "__main__":
    sys.exit(main())
