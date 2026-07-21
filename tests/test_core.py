# -*- coding: utf-8 -*-
"""离线单元测试: python -m unittest discover tests"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from utils import gap_to_baseline  # noqa: E402
from daily_comment import build_comment, _trend  # noqa: E402
from event_study import forward_return, max_drawdown_after, random_baseline  # noqa: E402
from daily_assessment import (assess_share_flow, assess_trend, assess_history,
                              build_assessment, build_two_sided_view, combine_models,
                              wilson_interval)  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
