# -*- coding: utf-8 -*-
"""规则引擎生成每日中文解读, 写入 data/comments/{date}.md。

解读把ETF份额、三大指数趋势、恐慌压力和历史样本放在一起，明确区分
“数据发生了什么”和“可以怎样理解”。核心函数 build_comment() 保持纯函数，
离线可测；任何判断都必须能回溯到仓库里的公开数据。
"""
import datetime
import os
import sys

from utils import load_json, load_history, gap_to_baseline

SIG_PCT, SIG_ABS_YI, TREND_DAYS = 0.015, 5.0, 5
DISCLAIMER = "\n以上由规则引擎根据公开数据生成，不构成投资建议。"


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


def _model(assessment, model_id):
    """从每日评估中按ID取模型；缺失时返回空字典。"""
    return next((item for item in (assessment or {}).get("models", [])
                 if item.get("id") == model_id), {})


def _analysis_lines(date_str, assessment, inversion_count):
    """把四模型结果组织成面向普通读者的解释，而不是逐项抄录数据。"""
    if not assessment or assessment.get("as_of") != date_str:
        return []
    share = _model(assessment, "share_flow")
    trend = _model(assessment, "trend")
    stress = _model(assessment, "stress")
    if not share or not trend or not stress:
        return []

    if share.get("vote") == "support" and trend.get("vote") == "risk":
        conclusion = ("份额侧出现承接，但价格趋势仍弱。这更像“有资金在接，"
                      "市场仍在探底”，还不能当作右侧修复已经成立。")
    elif share.get("vote") == "risk" and trend.get("vote") == "risk":
        conclusion = ("份额与价格趋势同时偏弱，风险信号正在同向增加，"
                      "比单一指数下跌更值得警惕。")
    elif share.get("vote") == "support" and trend.get("vote") == "support":
        conclusion = ("份额与价格趋势同时改善，修复信号比单日反弹完整，"
                      "但仍不能据此保证后续上涨。")
    else:
        conclusion = "份额和价格没有形成同一方向，当前最重要的是等待信号收敛。"

    counts = (assessment.get("verdict") or {}).get("counts", {})
    support = counts.get("support", 0)
    risk = counts.get("risk", 0)
    share_text = share.get("explanation", "暂无稳定方向。")
    share_text = share_text.replace(
        "它说明市场净申购偏强，但不能证明买方就是国家队。",
        "市场净申购偏强。")
    lines = [
        "**先看结论**", "",
        f"{conclusion}四个模型中{support}个偏暖、{risk}个提示风险，尚未共同收敛。", "",
        "**数据怎么说**", "",
        f"- ETF份额：{share_text}",
        f"- 指数趋势：{trend.get('explanation', '暂无稳定方向。')}",
        f"- 市场压力：{stress.get('explanation', '暂无稳定方向。')}",
    ]
    if inversion_count:
        lines.append(
            f"- 历史参考线：{inversion_count}只ETF的总份额低于2025年末持仓参考线。")

    lines += [
        "", "**接下来重点观察**", "",
        "- 如果多数ETF份额继续增加，同时至少两个指数重新站上20日和60日均线，才更接近完整的右侧修复。",
        "- 如果多数ETF份额转为连续减少，而指数仍在两条均线下方、恐慌压力不降，风险才会进一步升级。",
    ]
    issues = (((assessment.get("scorecard") or {}).get("data_confidence") or {})
              .get("issues", []))
    if issues:
        lines.append(f"- 数据时效：{'；'.join(issues)}，参考线的解释力度相应下降。")
    return lines + [""]


def build_comment(date_str, etfs, histories, assessment=None):
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
            tag = "当前仍低于历史参考线" if was_inverted else "首次低于历史参考线"
            inversions.append(
                f"{name}总份额{latest:.2f}亿份，低于汇金基线{baseline:.2f}亿份"
                f"（{tag}，差额{abs(gap):.1f}亿份，等待定期报告确认持仓变化）")
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
    analysis = _analysis_lines(date_str, assessment, len(inversions))
    if analysis:
        lines += analysis
    else:
        if inversions:
            lines += ["**历史参考线**", ""] + [f"- {x}" for x in inversions] + [""]
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
    assessment = load_json("daily_assessment.json", default={})
    text = build_comment(date_str, conf["etfs"], histories, assessment=assessment)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "comments", f"{date_str}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
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
