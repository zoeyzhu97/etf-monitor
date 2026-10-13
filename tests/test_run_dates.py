# -*- coding: utf-8 -*-
"""延迟到UTC次日、周末及收盘界限的日更回归测试。"""
import datetime
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_data_freshness
import fetch_etf_shares
import sync_market_holidays
from utils import market_data_date


class TestMarketDataDate(unittest.TestCase):
    def test_delayed_run_and_close_boundaries(self):
        cases = {
            "2026-10-12T12:17:00+00:00": "2026-10-12",
            "2026-10-12T18:17:00+00:00": "2026-10-12",
            # 实际失败时间：北京时间次日08:48，尚未开盘。
            "2026-10-13T00:48:33+00:00": "2026-10-12",
            "2026-10-13T14:59:59+08:00": "2026-10-12",
            "2026-10-13T15:00:00+08:00": "2026-10-13",
            # 周五任务延迟至周六早上，仍应抓取周五数据。
            "2026-10-17T00:48:00+00:00": "2026-10-16",
            "2027-01-01T00:48:00+00:00": "2026-12-31",
        }
        for timestamp, expected in cases.items():
            with self.subTest(timestamp=timestamp):
                instant = datetime.datetime.fromisoformat(timestamp)
                self.assertEqual(market_data_date(instant).isoformat(), expected)
                self.assertEqual(market_data_date(instant.astimezone(
                    datetime.timezone(datetime.timedelta(hours=-7))
                )).isoformat(), expected)

    def test_naive_time_is_rejected(self):
        with self.assertRaises(ValueError):
            market_data_date(datetime.datetime(2026, 10, 13, 0, 48))

    def test_weekend_and_holiday_freshness(self):
        for timestamp, expected in (
            ("2026-10-12T08:00:00+08:00", "2026-10-09"),
            ("2026-10-08T08:00:00+08:00", "2026-09-30"),
        ):
            with self.subTest(timestamp=timestamp):
                day = market_data_date(datetime.datetime.fromisoformat(timestamp))
                self.assertEqual(check_data_freshness.expected_trading_date(day), expected)


class TestRunDatePropagation(unittest.TestCase):
    @mock.patch("sync_market_holidays.sync")
    @mock.patch("sync_market_holidays.market_data_date",
                return_value=datetime.date(2026, 10, 16))
    def test_calendar_keeps_friday_active_for_delayed_saturday_run(self, clock, sync):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}):
                self.assertEqual(sync_market_holidays.main([]), 0)
            self.assertEqual(output.read_text(), "trading_day=true\nas_of=2026-10-16\n")
        sync.assert_called_once_with(datetime.date(2026, 10, 16))

    @mock.patch("check_data_freshness.load_json",
                return_value={"etfs": [{"code": "510300"}]})
    @mock.patch("check_data_freshness.load_history",
                return_value=[{"date": "2026-10-12"}])
    @mock.patch("check_data_freshness.market_data_date",
                return_value=datetime.date(2026, 10, 12))
    def test_original_failure_passes_but_real_staleness_still_fails(self, clock, history, config):
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": ""}):
            self.assertEqual(check_data_freshness.main([]), 0)
            history.return_value = [{"date": "2026-10-09"}]
            self.assertEqual(check_data_freshness.main([]), 1)

    @mock.patch("check_data_freshness.load_json",
                return_value={"etfs": [{"code": "510300"}]})
    @mock.patch("check_data_freshness.load_history",
                return_value=[{"date": "2026-10-12"}])
    @mock.patch("check_data_freshness.market_data_date")
    def test_fixed_date_survives_clock_crossing_close(self, clock, history, config):
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": ""}):
            self.assertEqual(check_data_freshness.main(["--as-of", "2026-10-12"]), 0)
        clock.assert_not_called()

    @mock.patch("fetch_etf_shares.time.sleep")
    @mock.patch("fetch_etf_shares.append_history")
    @mock.patch("fetch_etf_shares.fetch_official",
                return_value=(100.0, "sse_official_shares", "2026-10-16"))
    @mock.patch("fetch_etf_shares.load_json", return_value={"etfs": [{
        "code": "510300", "exchange": "SH", "name": "test", "huijin_shares_yi": None,
    }]})
    @mock.patch("fetch_etf_shares.market_data_date")
    def test_fetch_uses_fixed_date_and_preserves_official_date(self, clock, config, fetch, append, sleep):
        self.assertEqual(fetch_etf_shares.main(["--as-of", "2026-10-16"]), 0)
        clock.assert_not_called()
        fetch.assert_called_once_with("510300", "SH", datetime.date(2026, 10, 16))
        append.assert_called_once_with("510300", "2026-10-16", 100.0, "sse_official_shares", True)


if __name__ == "__main__":
    unittest.main()
