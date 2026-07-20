# -*- coding: utf-8 -*-
"""规则引擎生成每日中文解读, 写入 data/comments/{date}.md。
核心函数 build_comment() 为纯函数, 离线可测。
可选增强: 设置环境变量 LLM_API_KEY 后可将摘要交给大模型润色(未实现,
失败必须回退到规则文本)。"""
import datetime
import os
import sys

from utils import load_json, load_history, gap_to_baseline

SIG_PCT, SIG_ABS_YI, TREND_DAYS = 0.015, 5.0, 5
DISCLAIMER = "\n以上由规则引擎自动生成，仅为公开数据的机械描述，不构成投资建议。"


def _delta(rows, n=1):
    """最近一条与向前第n条的份额差及两条记录的自然日间隔;
    数据不足返回 (None, None)。调用方必须根据间隔判断是否为'单日'变动。"""
    if len(rows) < n + 1:
        return None, None
    a, b = rows[-1 - n], rows[-1]
    gap_days = (datetime.date.fromisoformat(b["date"]) -
                datetime.date.fromisoformat(a["date"])).days
    return round(b["total_shares_yi"] - a["total_shares_yi"], 2), gap_days


def _trend(rows, days=TREND_DAYS):
    """最近days个变动是否同向: 返回 'in'/'out'/None。
    要求参与判断的记录日期基本连续(相邻间隔≤4自然日, 容周末/短假),
    否则稀疏数据不判定趋势。"""
    if len(rows) < days + 1:
        return None
    seg = rows[-(days + 1):]
    for a, b in zip(seg, seg[1:]):
        gap = (datetime.date.fromisoformat(b["date"]) -
               datetime.date.fromisoformat(a["date"])).days
        if gap > 4:
            return None
    diffs = [seg[i + 1]["total_shares_yi"] - seg[i]["total_shares_yi"]
             for i in range(days)]
    if all(d > 0 for d in diffs):
        return "in"
    if all(d < 0 for d in diffs):
        return "out"
    return None


def build_comment(date_str, etfs, histories):
    """etfs: baselines.json里的列表; histories: {code: rows}。返回markdown文本。"""
    lines = [f"# {date_str} 解读", ""]
    findings, inversions = [], []
    covered = 0
    for etf in etfs:
        code, name, baseline = etf["code"], etf["name"], etf["huijin_shares_yi"]
        rows = histories.get(code) or []
        if not rows or rows[-1]["date"] != date_str:
            continue
        covered += 1
        latest = rows[-1]["total_shares_yi"]
        gap, inverted = gap_to_baseline(latest, baseline)
        if inverted:
            was_inverted = (len(rows) > 1 and
                            gap_to_baseline(rows[-2]["total_shares_yi"], baseline)[1])
            tag = "持续倒挂" if was_inverted else "新出现倒挂"
            inversions.append(
                f"{name}总份额{latest:.2f}亿份，低于汇金基线{baseline:.2f}亿份"
                f"（{tag}，确认减持下限{abs(gap):.1f}亿份）")
        d1, gap_days = _delta(rows, 1)
        if d1 is not None and (abs(d1) >= SIG_ABS_YI or
                               abs(d1) / max(latest, 1e-9) >= SIG_PCT):
            verb = "净申购" if d1 > 0 else "净赎回"
            if gap_days is not None and gap_days <= 4:
                findings.append(f"{name}单日{verb}{abs(d1):.1f}亿份")
            else:
                findings.append(
                    f"{name}较上次记录（{gap_days}个自然日前）累计{verb}"
                    f"{abs(d1):.1f}亿份，期间数据缺失，非单日变动")
        t = _trend(rows)
        if t:
            findings.append(f"{name}已连续{TREND_DAYS}日净{'流入' if t=='in' else '流出'}")
    if inversions:
        lines += ["**倒挂/减持确认**", ""] + [f"- {x}" for x in inversions] + [""]
    if findings:
        lines += ["**份额异动**", ""] + [f"- {x}" for x in findings] + [""]
    if covered == 0:
        lines += ["今日暂无份额数据（抓取脚本未运行或数据源失败），不作判断。", ""]
    elif not inversions and not findings:
        lines += ["监控标的份额无显著变化，国家队层面无可观测动作。", ""]
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def main():
    conf = load_json("baselines.json")
    histories = {e["code"]: load_history(e["code"]) for e in conf["etfs"]}
    # 交易所T+1披露: 解读绑定"最新有数据的日期"而非运行日,
    # 避免每日解读长期显示"暂无数据"。无任何历史数据时才落到今天。
    latest_dates = [rows[-1]["date"] for rows in histories.values() if rows]
    date_str = max(latest_dates) if latest_dates else datetime.date.today().isoformat()
    text = build_comment(date_str, conf["etfs"], histories)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "comments", f"{date_str}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    manifest = load_json("comments/manifest.json", default=[])
    if date_str not in manifest:
        manifest.append(date_str)
        manifest.sort(reverse=True)
        from utils import save_json
        save_json("comments/manifest.json", manifest)
    print(f"解读已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
