# -*- coding: utf-8 -*-
"""公共工具: 路径、JSON读写、交易日判断、历史快照读写。全部离线可测。"""
import json
import os
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def load_json(rel_path, default=None):
    path = os.path.join(DATA, rel_path)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(rel_path, obj):
    path = os.path.join(DATA, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def is_trading_day(d: datetime.date) -> bool:
    """周一至周五且不在节假日表中。节假日表 data/holidays.json 需每年更新,
    或改用 chinese_calendar 库(见 requirements 可选项)。"""
    if d.weekday() >= 5:
        return False
    holidays = load_json("holidays.json", default=[])
    return d.isoformat() not in holidays


def gap_to_baseline(total_shares_yi, baseline_yi):
    """返回 (差额, 是否倒挂)。差额<0 即倒挂, 其绝对值为减持下限。"""
    if baseline_yi is None or total_shares_yi is None:
        return None, False
    gap = round(total_shares_yi - baseline_yi, 2)
    return gap, gap < 0


def load_history(code):
    return load_json(f"history/{code}.json", default=[])


def append_history(code, date_str, shares_yi, source, verified):
    """追加一条快照; 同日重复运行则覆盖当日记录。"""
    rows = [r for r in load_history(code) if r["date"] != date_str]
    rows.append({"date": date_str, "total_shares_yi": round(shares_yi, 2),
                 "source": source, "verified": bool(verified)})
    rows.sort(key=lambda r: r["date"])
    save_json(f"history/{code}.json", rows)
    return rows
