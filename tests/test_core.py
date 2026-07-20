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


if __name__ == "__main__":
    unittest.main()
