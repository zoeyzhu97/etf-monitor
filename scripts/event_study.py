# -*- coding: utf-8 -*-
"""事件研究: 对样本库中每个买入干预日计算前瞻收益、干预后最大回撤、
至市场底天数, 并用 bootstrap 随机日期基准对比。
输出 data/event_study_results.json 供前端"历史规律"页展示。

核心计算函数均为纯函数, 离线可测。指数日线需先由 fetch_index_daily.py 回补。
统计口径声明(会随结果一并写入前端):
  样本量小(约20次), 干预内生于暴跌(选择偏差), 机制随时间演变,
  所有结论只报告分布/区间, 不构成投资建议。"""
import random
import sys

from utils import load_json, save_json

HORIZONS = [20, 60, 120, 250]
N_BOOTSTRAP = 1000


def _index_map(rows):
    dates = [r["date"] for r in rows]
    closes = [r["close"] for r in rows]
    return dates, closes


def _locate(dates, date_str, tolerance_days=15):
    """返回 >= date_str 的第一个交易日下标; 数据未覆盖该日期
    (越界或定位日距事件日超过tolerance_days)返回None, 防止把
    早于数据起点的事件错误映射到数据首日。"""
    import datetime as _dt
    target = _dt.date.fromisoformat(date_str)
    for i, d in enumerate(dates):
        if d >= date_str:
            gap = (_dt.date.fromisoformat(d) - target).days
            return i if gap <= tolerance_days else None
    return None


def forward_return(dates, closes, date_str, horizon):
    i = _locate(dates, date_str)
    if i is None or i + horizon >= len(closes):
        return None
    return round(closes[i + horizon] / closes[i] - 1, 4)


def max_drawdown_after(dates, closes, date_str, window=250):
    """干预日后window个交易日内, 相对干预日收盘的最大回撤(负数)与见底天数"""
    i = _locate(dates, date_str)
    if i is None:
        return None, None
    end = min(i + window, len(closes) - 1)
    seg = closes[i:end + 1]
    if not seg:
        return None, None
    trough = min(seg)
    return round(trough / seg[0] - 1, 4), seg.index(trough)


def random_baseline(dates, closes, horizon, n=N_BOOTSTRAP, seed=42):
    """随机日期同持有期收益分布: 返回 (中位数, 5分位, 95分位, 胜率)"""
    rng = random.Random(seed)
    max_i = len(closes) - horizon - 1
    if max_i <= 0:
        return None
    rets = []
    for _ in range(n):
        i = rng.randint(0, max_i)
        rets.append(closes[i + horizon] / closes[i] - 1)
    rets.sort()
    win = sum(1 for r in rets if r > 0) / len(rets)
    q = lambda p: rets[int(p * (len(rets) - 1))]
    return {"median": round(q(0.5), 4), "p05": round(q(0.05), 4),
            "p95": round(q(0.95), 4), "win_rate": round(win, 3)}


def run(samples, index_data):
    results = {"buy_events": [], "baselines": {}, "summary": {},
               "caveats": "样本量小且干预内生于暴跌，机制随时间演变；"
                          "本页仅报告历史条件分布，不构成投资建议。"}
    per_horizon_wins = {h: [] for h in HORIZONS}
    for s in samples:
        if s.get("kind") not in ("buy", "policy"):
            continue
        rows = index_data.get(s["index_code"])
        if not rows:
            continue
        dates, closes = _index_map(rows)
        item = {"date": s["date_policy"], "market": s["market"],
                "note": s.get("note", ""), "verify": s.get("verify", False),
                "returns": {}}
        for h in HORIZONS:
            r = forward_return(dates, closes, s["date_policy"], h)
            item["returns"][str(h)] = r
            if r is not None:
                per_horizon_wins[h].append(r > 0)
        dd, days = max_drawdown_after(dates, closes, s["date_policy"])
        item["max_drawdown"], item["days_to_trough"] = dd, days
        if dd is None and all(v is None for v in item["returns"].values()):
            continue  # 指数数据未覆盖该事件日期, 跳过
        results["buy_events"].append(item)
    for code, rows in index_data.items():
        dates, closes = _index_map(rows)
        results["baselines"][code] = {
            str(h): random_baseline(dates, closes, h) for h in HORIZONS}
    for h in HORIZONS:
        wins = per_horizon_wins[h]
        results["summary"][str(h)] = {
            "n": len(wins),
            "win_rate": round(sum(wins) / len(wins), 3) if wins else None}
    return results


def main():
    samples = load_json("intervention_samples.json")["samples"]
    index_data = {}
    for code in ("000001", "399001", "000688", "TWII", "HSI"):
        rows = load_json(f"index/{code}.json")
        if rows:
            index_data[code] = rows
    if not index_data:
        print("指数日线为空, 请先运行 fetch_index_daily.py 回补", file=sys.stderr)
        return 2
    save_json("event_study_results.json", run(samples, index_data))
    print("事件研究结果已写入 data/event_study_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
