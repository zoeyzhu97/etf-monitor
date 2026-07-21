# -*- coding: utf-8 -*-
"""离线单元测试: python -m unittest discover tests"""
import datetime
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from utils import gap_to_baseline  # noqa: E402
from daily_comment import build_comment, _trend  # noqa: E402
from event_study import forward_return, max_drawdown_after, random_baseline  # noqa: E402
from daily_assessment import (assess_share_flow, assess_trend, assess_history,
                              build_assessment, build_scorecard,
                              build_two_sided_view, combine_models,
                              _recent_streak, wilson_interval)  # noqa: E402
from fetch_etf_shares import _parse_sse_share_payload  # noqa: E402
from backfill_etf_shares import _date_chunks  # noqa: E402


def mk_rows(vals, start_day=1):
    return [{"date": f"2026-01-{start_day+i:02d}", "total_shares_yi": v,
             "source": "t", "verified": True} for i, v in enumerate(vals)]


class TestInversion(unittest.TestCase):
    def test_gap(self):
        gap, inv = gap_to_baseline(685.35, 735.13)
        self.assertAlmostEqual(gap, -49.78)
        self.assertTrue(inv)

    def test_no_baseline(self):
        gap, inv = gap_to_baseline(100.0, None)
        self.assertIsNone(gap)
        self.assertFalse(inv)


class TestOfficialShareBackfill(unittest.TestCase):
    def test_parse_sse_direct_total_shares(self):
        payload = {"result": [
            {"STAT_DATE": "2026-01-05", "SEC_CODE": "510300",
             "TOT_VOL": "8905818.77"},
            {"STAT_DATE": "2026-01-05", "SEC_CODE": "999999",
             "TOT_VOL": "10000"},
        ]}
        rows = _parse_sse_share_payload(payload, codes=["510300"])
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["total_shares_yi"], 890.581877)
        self.assertEqual(rows[0]["source"], "sse_official_shares")
        self.assertTrue(rows[0]["verified"])

    def test_szse_backfill_uses_short_contiguous_chunks(self):
        start = datetime.date(2023, 10, 23)
        end = datetime.date(2024, 4, 30)
        chunks = list(_date_chunks(start, end, chunk_days=80))
        self.assertEqual(chunks[0][0], start)
        self.assertEqual(chunks[-1][1], end)
        for current, following in zip(chunks, chunks[1:]):
            self.assertEqual(current[1] + datetime.timedelta(days=1),
                             following[0])


class TestComment(unittest.TestCase):
    ETFS = [{"code": "510300", "name": "华泰柏瑞沪深300ETF",
             "huijin_shares_yi": 735.13}]

    def test_new_inversion(self):
        rows = mk_rows([740.0, 685.35], start_day=21)
        txt = build_comment("2026-01-22", self.ETFS, {"510300": rows})
        self.assertIn("新出现倒挂", txt)
        self.assertIn("49.8", txt)

    def test_quiet_day(self):
        rows = mk_rows([800.0, 800.1], start_day=21)
        txt = build_comment("2026-01-22", self.ETFS, {"510300": rows})
        self.assertIn("无显著变化", txt)


    def test_no_data_today(self):
        rows = mk_rows([800.0, 800.1], start_day=21)  # 最新为01-22
        txt = build_comment("2026-01-23", self.ETFS, {"510300": rows})
        self.assertIn("暂无份额数据", txt)
        self.assertNotIn("无显著变化", txt)


    def test_sparse_gap_not_daily(self):
        # 相隔半年的两条记录不得报"单日", 必须标注跨期与数据缺失
        rows = [{"date": "2026-01-22", "total_shares_yi": 685.35, "source": "t", "verified": True},
                {"date": "2026-07-20", "total_shares_yi": 244.22, "source": "t", "verified": True}]
        txt = build_comment("2026-07-20", self.ETFS, {"510300": rows})
        self.assertNotIn("单日净", txt)
        self.assertIn("非单日变动", txt)
        self.assertIn("179个自然日前", txt)

    def test_sparse_no_trend(self):
        # 稀疏(跨月)记录不得判定连续流入/流出趋势
        rows = [{"date": f"2026-0{m}-01", "total_shares_yi": 700 - m * 50,
                 "source": "t", "verified": True} for m in range(1, 7)]
        self.assertIsNone(_trend(rows))

    def test_trend(self):
        self.assertEqual(_trend(mk_rows([10, 9, 8, 7, 6, 5])), "out")
        self.assertEqual(_trend(mk_rows([1, 2, 3, 4, 5, 6])), "in")
        self.assertIsNone(_trend(mk_rows([1, 2, 1, 2, 1, 2])))


class TestEventStudy(unittest.TestCase):
    def setUp(self):
        self.dates = [f"2020-{m:02d}-01" for m in range(1, 13)] + \
                     [f"2021-{m:02d}-01" for m in range(1, 13)]
        self.closes = [100, 90, 80, 70, 60, 65, 70, 75, 80, 85, 90, 95,
                       100, 105, 110, 115, 120, 125, 130, 135, 140, 145, 150, 155]

    def test_forward_return(self):
        r = forward_return(self.dates, self.closes, "2020-03-01", 2)
        self.assertAlmostEqual(r, 60 / 80 - 1, places=4)

    def test_drawdown(self):
        dd, days = max_drawdown_after(self.dates, self.closes, "2020-02-01")
        self.assertAlmostEqual(dd, 60 / 90 - 1, places=4)
        self.assertEqual(days, 3)


    def test_locate_out_of_range(self):
        # 早于数据起点的事件不得被映射到数据首日
        r = forward_return(self.dates, self.closes, "2008-09-18", 2)
        self.assertIsNone(r)
        dd, days = max_drawdown_after(self.dates, self.closes, "2008-09-18")
        self.assertIsNone(dd)

    def test_baseline_dist(self):
        b = random_baseline(self.dates, self.closes, 3, n=200)
        self.assertIn("win_rate", b)
        self.assertTrue(0 <= b["win_rate"] <= 1)


class TestDailyAssessment(unittest.TestCase):
    @staticmethod
    def score_models(direction="out", trend="weak", stress="panic"):
        share = {
            "id": "share_flow",
            "metrics": {
                "streak_comparable_etfs": 8,
                "consecutive_inflow_etfs": 8 if direction == "in" else 0,
                "consecutive_outflow_etfs": 6 if direction == "out" else 0,
                "latest_total": 8,
                "latest_verified": 8,
                "latest_date": "2026-07-20",
                "earliest_latest_date": "2026-07-20",
            },
        }
        trends = {}
        for code in ("000001", "399001", "000688"):
            trends[code] = {
                "date": "2026-07-20",
                "above_ma20": trend == "strong",
                "above_ma60": trend == "strong",
            }
        return [
            share,
            {"id": "trend", "metrics": trends},
            {"id": "stress", "metrics": {
                "panic_indices": 3 if stress == "panic" else 0,
                "calm_indices": 3 if stress == "calm" else 0,
                "total": 3,
            }},
        ]

    def test_share_flow_never_claims_state_buyer(self):
        model = assess_share_flow({
            "a": mk_rows([10, 12]), "b": mk_rows([10, 11]),
            "c": mk_rows([10, 9]), "d": mk_rows([10, 13]),
        })
        self.assertEqual(model["vote"], "support")
        self.assertIn("不能证明买方就是国家队", model["explanation"])

    def test_trend_three_mainland_indexes(self):
        rows = [{"date": f"2026-01-{i:02d}", "close": 100 + i}
                for i in range(1, 29)]
        model = assess_trend({"000001": rows, "399001": rows, "000688": rows})
        self.assertEqual(model["vote"], "support")

    def test_small_sample_interval_is_wide(self):
        lo, hi = wilson_interval(6, 7)
        self.assertLess(lo, 0.50)
        self.assertGreater(hi, 0.95)

    def test_history_requires_cn_scope(self):
        conf = {"baseline_date": "2025-12-31", "etfs": []}
        rows = [{"date": f"2026-01-{i:02d}", "close": 100 + i}
                for i in range(1, 29)]
        assessment = build_assessment(
            conf, {}, {"000001": rows, "399001": rows, "000688": rows,
                       "TWII": rows},
            {"markets_included": ["CN", "TW"],
             "summary": {"20": {"n": 99, "win_rate": 0.99}}})
        self.assertEqual(assessment["market_scope"], "CN")
        trend_codes = assessment["models"][1]["metrics"].keys()
        self.assertNotIn("TWII", trend_codes)
        self.assertEqual(assessment["models"][3]["vote"], "neutral")

    def test_convergence_needs_three_votes(self):
        models = [{"vote": v} for v in
                  ("support", "support", "neutral", "risk")]
        self.assertEqual(combine_models(models)["state"], "mixed")

    def test_buy_and_sell_sides_are_both_counted(self):
        models = [
            {"id": "share_flow", "vote": "support"},
            {"id": "trend", "vote": "risk"},
            {"id": "stress", "vote": "risk"},
            {"id": "history", "vote": "support"},
        ]
        view = build_two_sided_view(models)
        self.assertIn("1/3", view["buy_side"]["label"])
        self.assertIn("2/3", view["sell_side"]["label"])
        self.assertIn("不虚构卖出胜率模型", view["history_boundary"])

    def test_recent_share_streak_requires_three_adjacent_intervals(self):
        self.assertEqual(_recent_streak(mk_rows([4, 3, 2, 1])), "out")
        self.assertEqual(_recent_streak(mk_rows([1, 2, 3, 4])), "in")
        self.assertIsNone(_recent_streak(mk_rows([1, 2, 1, 2])))
        sparse = [
            {"date": "2026-01-01", "total_shares_yi": 4},
            {"date": "2026-02-01", "total_shares_yi": 3},
            {"date": "2026-03-01", "total_shares_yi": 2},
            {"date": "2026-04-01", "total_shares_yi": 1},
        ]
        self.assertIsNone(_recent_streak(sparse))

    def test_high_risk_combo_gets_bonus_and_alert(self):
        scorecard = build_scorecard(
            {"baseline_date": "2026-07-01"},
            self.score_models(direction="out", trend="weak", stress="panic"),
            evaluation_date="2026-07-21")
        self.assertEqual(scorecard["market_risk"]["score"], 94)
        self.assertTrue(scorecard["market_risk"]["alert"])
        self.assertEqual(scorecard["general_signal"]["state"], "risk_priority")

    def test_full_repair_combo_gets_100(self):
        scorecard = build_scorecard(
            {"baseline_date": "2026-07-01"},
            self.score_models(direction="in", trend="strong", stress="calm"),
            evaluation_date="2026-07-21")
        self.assertEqual(scorecard["repair_readiness"]["score"], 100)
        self.assertTrue(scorecard["repair_readiness"]["alert"])
        self.assertEqual(scorecard["general_signal"]["state"], "repair_confirmed")

    def test_stale_baseline_reduces_data_confidence(self):
        scorecard = build_scorecard(
            {"baseline_date": "2026-01-01"},
            self.score_models(direction="none", trend="mixed", stress="middle"),
            evaluation_date="2026-07-21")
        self.assertEqual(scorecard["data_confidence"]["score"], 70)
        self.assertTrue(scorecard["data_confidence"]["alert"])
        self.assertIn("持仓参考线超过120天未更新",
                      scorecard["data_confidence"]["issues"])


if __name__ == "__main__":
    unittest.main()
