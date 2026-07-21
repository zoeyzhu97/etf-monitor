# -*- coding: utf-8 -*-
"""ETF时间轴的前端回归约束。"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestEtfChartRangeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        cls.index = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_default_range_is_bound_to_real_dates(self):
        self.assertIn("startValue: defaultZoomStart, endValue: last.date", self.app)
        self.assertNotIn("zoomStartPercent", self.app)

    def test_each_chart_has_latest_and_recovery_controls(self):
        self.assertIn('class="chart-latest"', self.app)
        self.assertIn('class="chart-range-btn latest-btn"', self.app)
        self.assertIn('class="chart-range-btn all-btn"', self.app)
        self.assertIn("setDateRange(defaultZoomStart)", self.app)
        self.assertIn("setDateRange(rows[0].date)", self.app)

    def test_frontend_cache_versions_stay_in_sync(self):
        css_version = re.search(r"style\.css\?v=([^\"']+)", self.index)
        js_version = re.search(r"app\.js\?v=([^\"']+)", self.index)
        self.assertIsNotNone(css_version)
        self.assertIsNotNone(js_version)
        self.assertEqual(css_version.group(1), js_version.group(1))


if __name__ == "__main__":
    unittest.main()
