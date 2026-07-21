# -*- coding: utf-8 -*-
"""生成面向非专业读者的每日多模型评估。

这不是价格预测器，也不把 ETF 总份额变化冒充为中央汇金的逐日交易。
四个模型分别观察份额、趋势、压力和历史先验；只有至少三个模型同向，
页面才显示“共同收敛”。所有核心函数保持纯函数，便于离线测试。
"""
import math
import statistics

from utils import load_json, save_json


INDEX_NAMES = {
    "000001": "上证指数",
    "399001": "深证成指",
    "000688": "科创50",
}


def _round(value, digits=2):
    return None if value is None else round(value, digits)


def _mean(values):
    return sum(values) / len(values) if values else None


def _is_recent_pair(previous, latest, max_gap_days=5):
    """两条记录间隔不超过5个自然日，才视作相邻交易日变化。"""
    import datetime as dt
    a = dt.date.fromisoformat(previous["date"])
    b = dt.date.fromisoformat(latest["date"])
    return 0 < (b - a).days <= max_gap_days


def assess_share_flow(histories):
    """按每只ETF最近两条有效记录计算市场总份额流向。"""
    changes = []
    latest_dates = []
    verified = 0
    for code, rows in histories.items():
        if not rows:
            continue
        latest_dates.append(rows[-1]["date"])
        verified += int(bool(rows[-1].get("verified")))
        if len(rows) < 2 or not _is_recent_pair(rows[-2], rows[-1]):
            continue
        changes.append({
            "code": code,
            "change_yi": rows[-1]["total_shares_yi"] - rows[-2]["total_shares_yi"],
        })

    total = sum(item["change_yi"] for item in changes)
    rising = sum(item["change_yi"] > 0 for item in changes)
    falling = sum(item["change_yi"] < 0 for item in changes)
    n = len(changes)
    if n and rising / n >= 0.625 and total > 0:
        vote = "support"
        title = "多数ETF总份额增加"
        explanation = (f"{rising}/{n}只ETF最近一条有效记录增加，合计约增加"
                       f"{total:.1f}亿份。它说明市场净申购偏强，但不能证明买方就是国家队。")
    elif n and falling / n >= 0.625 and total < 0:
        vote = "risk"
        title = "多数ETF总份额减少"
        explanation = (f"{falling}/{n}只ETF最近一条有效记录减少，合计约减少"
                       f"{abs(total):.1f}亿份。若连续多日发生，才值得提高警惕。")
    else:
        vote = "neutral"
        title = "ETF份额方向不一致"
        explanation = "各ETF有增有减，暂时不能从份额流向得到统一方向。"
    return {
        "id": "share_flow",
        "name": "模型1 · ETF份额流向",
        "vote": vote,
        "title": title,
        "explanation": explanation,
        "metrics": {
            "comparable_etfs": n,
            "rising_etfs": rising,
            "falling_etfs": falling,
            "net_change_yi": _round(total, 2),
            "latest_date": max(latest_dates) if latest_dates else None,
            "latest_verified": verified,
        },
    }


def index_metrics(rows):
    """计算一个指数的趋势和压力指标。"""
    if not rows:
        return None
    closes = [float(row["close"]) for row in rows]
    latest = closes[-1]
    ma20 = _mean(closes[-20:])
    ma60 = _mean(closes[-60:])
    peak120 = max(closes[-120:])
    return20 = latest / closes[-21] - 1 if len(closes) >= 21 else None
    daily_returns = [closes[i] / closes[i - 1] - 1
                     for i in range(max(1, len(closes) - 20), len(closes))]
    volatility20 = (statistics.pstdev(daily_returns) * math.sqrt(250)
                    if len(daily_returns) >= 2 else None)
    return {
        "date": rows[-1]["date"],
        "close": _round(latest),
        "ma20": _round(ma20),
        "ma60": _round(ma60),
        "above_ma20": latest >= ma20,
        "above_ma60": latest >= ma60,
        "return20": _round(return20, 4),
        "drawdown120": _round(latest / peak120 - 1, 4),
        "volatility20": _round(volatility20, 4),
    }


def assess_trend(index_data):
    metrics = {code: index_metrics(rows) for code, rows in index_data.items()}
    metrics = {code: value for code, value in metrics.items() if value}
    strong = sum(m["above_ma20"] and m["above_ma60"] for m in metrics.values())
    weak = sum(not m["above_ma20"] and not m["above_ma60"] for m in metrics.values())
    n = len(metrics)
    if strong >= 2:
        vote = "support"
        title = "多数指数仍在中短期均线上方"
        explanation = (f"{strong}/{n}个指数同时站在20日和60日均线上方，"
                       "属于右侧修复确认；它比猜最低点更稳健，但可能更晚。")
    elif weak >= 2:
        vote = "risk"
        title = "多数指数跌到中短期均线下方"
        explanation = (f"{weak}/{n}个指数同时位于20日和60日均线下方，"
                       "趋势仍弱，贸然把一次反弹当成见底的风险较高。")
    else:
        vote = "neutral"
        title = "三大指数趋势有分歧"
        explanation = "上证、深证、科创50没有形成统一趋势，仍处于观察区。"
    return {
        "id": "trend",
        "name": "模型2 · 三大指数趋势",
        "vote": vote,
        "title": title,
        "explanation": explanation,
        "metrics": metrics,
    }


def assess_stress(trend_model):
    metrics = trend_model["metrics"]
    panic = sum(m["drawdown120"] <= -0.10 or m["volatility20"] >= 0.30
                for m in metrics.values())
    calm = sum(m["drawdown120"] > -0.05 and m["volatility20"] < 0.25
               for m in metrics.values())
    n = len(metrics)
    if panic >= 2:
        vote = "risk"
        title = "市场仍有明显恐慌压力"
        explanation = (f"{panic}/{n}个指数出现较深的120日回撤或较高波动。"
                       "这更像风险释放阶段，不等于已经到最低点。")
    elif calm >= 2:
        vote = "support"
        title = "多数指数暂未处于恐慌状态"
        explanation = (f"{calm}/{n}个指数距120日高点不远且波动未过热，"
                       "说明当前更像修复或常态波动，而非恐慌性砸盘。")
    else:
        vote = "neutral"
        title = "恐慌压力处于中间地带"
        explanation = "回撤和波动尚未在三大指数上形成统一的极端信号。"
    return {
        "id": "stress",
        "name": "模型3 · 恐慌压力",
        "vote": vote,
        "title": title,
        "explanation": explanation,
        "metrics": {"panic_indices": panic, "calm_indices": calm, "total": n},
    }


def wilson_interval(wins, n, z=1.96):
    """二项比例的Wilson 95%区间；小样本时比正态近似稳健。"""
    if not n:
        return [None, None]
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [_round(max(0, centre - half), 3), _round(min(1, centre + half), 3)]


def assess_history(study):
    summary = study.get("summary", {}) if study else {}
    intervals = {}
    for horizon, item in summary.items():
        n = int(item.get("n") or 0)
        rate = item.get("win_rate")
        wins = int(round(rate * n)) if rate is not None else 0
        intervals[horizon] = {
            "n": n,
            "win_rate": rate,
            "wilson95": wilson_interval(wins, n),
        }
    d20 = intervals.get("20", {})
    if d20.get("n", 0) >= 5 and (d20.get("win_rate") or 0) >= 0.70:
        vote = "support"
        title = "历史上短期上涨次数较多，但证据很薄"
        explanation = ("A股7次样本中，干预后20个交易日有6次上涨。"
                       "但一个反例就会让胜率变动14.3个百分点，不能当成预测保证。")
    else:
        vote = "neutral"
        title = "历史样本不足以给出稳定方向"
        explanation = "可用事件太少，历史统计只能作为背景，不能单独触发行动。"
    return {
        "id": "history",
        "name": "模型4 · 历史事件先验",
        "vote": vote,
        "title": title,
        "explanation": explanation,
        "metrics": intervals,
    }


def combine_models(models):
    counts = {vote: sum(m["vote"] == vote for m in models)
              for vote in ("support", "risk", "neutral")}
    if counts["support"] >= 3:
        state = "repair"
        label = "多模型偏向修复，但不是买入指令"
        plain = "至少3个模型同向偏暖；仍要等价格与份额连续确认，不能据此追涨。"
    elif counts["risk"] >= 3:
        state = "risk"
        label = "多模型共同预警"
        plain = "至少3个模型同向偏弱；重点是控制风险，不要把国家队可能出手当成托底承诺。"
    else:
        state = "mixed"
        label = "信号尚未共同收敛"
        plain = "四个模型没有至少3个同向，最诚实的结论是继续观察。"
    return {
        "state": state,
        "label": label,
        "plain": plain,
        "counts": counts,
        "rule": "至少3/4个模型同向才称为共同收敛",
    }


def build_action_guide(verdict, models):
    share = next(m for m in models if m["id"] == "share_flow")
    trend = next(m for m in models if m["id"] == "trend")
    if verdict["state"] == "repair":
        level = "观察级：偏暖，不追涨"
        checklist = [
            "先看三大指数能否连续站稳20日与60日均线，而不是只看一天反弹。",
            "再看ETF总份额是否连续增加；单日增加不能证明是国家队买入。",
            "若指数重新跌破两条均线且多数ETF份额转为连续减少，修复判断失效。",
        ]
    elif verdict["state"] == "risk":
        level = "警惕级：先管风险"
        checklist = [
            "不要因为“国家队可能救市”就假定下跌空间已经消失。",
            "等待至少两个指数重回20日均线，并观察份额流出是否停止。",
            "连续大额份额减少、三大指数同步跌破60日均线，是需要升级警惕的组合。",
        ]
    else:
        level = "等待级：证据不足"
        checklist = [
            "不根据单一红色区域、单日申购或一条政策新闻做决定。",
            "等待份额模型与趋势模型转为同向，再重新评估。",
            "如果你看不懂一个信号，就先不行动；错过一点通常比在不理解时冒险更可控。",
        ]
    return {
        "level": level,
        "why": [share["title"], trend["title"]],
        "checklist": checklist,
        "boundary": "这是通用观察框架，不了解你的资金用途、期限和承受亏损能力，不能替代个性化投资建议。",
    }


def build_two_sided_view(models):
    """同时检查买入/承接侧与卖出/风险侧，不把历史买入样本外推为卖出模型。"""
    realtime = {model["id"]: model for model in models
                if model["id"] in {"share_flow", "trend", "stress"}}
    labels = {
        "share_flow": ("多数ETF份额增加", "多数ETF份额减少"),
        "trend": ("多数指数站上20日与60日均线", "多数指数跌破20日与60日均线"),
        "stress": ("多数指数脱离恐慌状态", "多数指数仍有明显恐慌压力"),
    }
    buy_checks = [{"label": labels[key][0], "met": realtime[key]["vote"] == "support"}
                  for key in ("share_flow", "trend", "stress")]
    sell_checks = [{"label": labels[key][1], "met": realtime[key]["vote"] == "risk"}
                   for key in ("share_flow", "trend", "stress")]
    buy_met = sum(item["met"] for item in buy_checks)
    sell_met = sum(item["met"] for item in sell_checks)
    return {
        "buy_side": {
            "label": f"买入/承接侧满足 {buy_met}/3 项",
            "checks": buy_checks,
            "meaning": ("3项同时满足才属于较完整的右侧修复组合；"
                        "即使满足，也不能确认买方身份或保证上涨。"),
        },
        "sell_side": {
            "label": f"卖出/风险侧满足 {sell_met}/3 项",
            "checks": sell_checks,
            "meaning": ("3项同时满足才升级为共同卖出风险警报；"
                        "份额下降仍是全市场结果，不等于国家队已确认卖出。"),
        },
        "history_boundary": ("历史事件研究只统计买入/政策干预。当前没有足够的、"
                             "经官方确认且可精确定位的A股国家队卖出事件，"
                             "因此不虚构卖出胜率模型。"),
    }


def build_assessment(conf, histories, index_data, study):
    # 防御性过滤：调用方即使误传入港台指数，也不得进入模型。
    index_data = {code: rows for code, rows in index_data.items()
                  if code in INDEX_NAMES}
    # 聚合后的事件研究无法再次按市场拆分；非纯CN结果宁可不用。
    if set(study.get("markets_included", [])) != {"CN"}:
        study = {}
    share = assess_share_flow(histories)
    trend = assess_trend(index_data)
    stress = assess_stress(trend)
    history = assess_history(study)
    models = [share, trend, stress, history]
    verdict = combine_models(models)
    baseline_count = sum(etf.get("huijin_shares_yi") is not None
                         for etf in conf.get("etfs", []))
    return {
        "schema_version": 1,
        "market_scope": "CN",
        "market_scope_label": "仅中国大陆A股",
        "as_of": max((m.get("date") for m in trend["metrics"].values()), default=None),
        "data_explanation": {
            "official_szse_etf": "159919嘉实沪深300ETF每日总份额来自深交所基金规模报表",
            "baseline": (f"{conf.get('baseline_date')}定期报告持仓参考线；"
                         f"{baseline_count}只ETF有可比较基线"),
            "important": "ETF总份额是全市场总量，不是中央汇金的逐日持仓。",
        },
        "verdict": verdict,
        "models": models,
        "two_sided": build_two_sided_view(models),
        "action_guide": build_action_guide(verdict, models),
        "star_market": {
            "answer": "公开数据能确认我们监测了科创50ETF及科创50指数，但目前没有可靠证据据此断言中央汇金直接买入了某只科创板股票。",
            "distinction": "买入科创50ETF会形成对一篮子科创板成份股的间接敞口，不等于直接出现在单只股票股东名单。",
            "tracked_etf": "588000 华夏科创50ETF",
            "huijin_baseline_available": False,
        },
    }


def main():
    conf = load_json("baselines.json", default={})
    histories = {etf["code"]: load_json(f"history/{etf['code']}.json", default=[])
                 for etf in conf.get("etfs", [])}
    index_data = {code: load_json(f"index/{code}.json", default=[])
                  for code in INDEX_NAMES}
    study = load_json("event_study_results.json", default={})
    result = build_assessment(conf, histories, index_data, study)
    save_json("daily_assessment.json", result)
    print("每日多模型评估已写入 data/daily_assessment.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
