# -*- coding: utf-8 -*-
"""上交所年度休市表解析与同步回归测试。"""
import datetime
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sync_market_holidays import parse_sse_holidays, sync  # noqa: E402


SAMPLE = """<strong>2026年休市安排</strong><table>
<tr><td>元旦：</td><td>1月1日（星期四）至1月3日（星期六）休市，1月5日开市。</td></tr>
<tr><td>春节：</td><td>2月15日（星期日）至2月23日（星期一）休市。</td></tr>
<tr><td>清明节：</td><td>4月4日（星期六）至4月6日（星期一）休市。</td></tr>
<tr><td>劳动节：</td><td>5月1日（星期五）至5月5日（星期二）休市。</td></tr>
<tr><td>端午节：</td><td>6月19日（星期五）至6月21日（星期日）休市。</td></tr>
<tr><td>中秋节：</td><td>9月25日（星期五）至9月27日（星期日）休市。</td></tr>
<tr><td>国庆节：</td><td>10月1日（星期四）至10月7日（星期三）休市。
另外，10月10日（星期六）为周末休市。</td></tr>
</table>"""


class TestMarketHolidays(unittest.TestCase):
    def test_official_schedule_includes_only_weekday_closures(self):
        days = parse_sse_holidays(SAMPLE, 2026)
        self.assertIn("2026-09-25", days)
        self.assertIn("2026-10-01", days)
        self.assertIn("2026-10-07", days)
        self.assertNotIn("2026-09-26", days)
        self.assertNotIn("2026-10-10", days)
        self.assertEqual(len(days), 19)

    def test_outdated_official_schedule_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "2027"):
            parse_sse_holidays(SAMPLE, 2027)

    @mock.patch("sync_market_holidays.requests.get")
    @mock.patch("sync_market_holidays.load_json", return_value=["2026-09-25"])
    def test_known_year_survives_temporary_official_outage(self, _, get):
        import requests
        get.side_effect = requests.RequestException("offline")
        sync(datetime.date(2026, 10, 1))

    @mock.patch("sync_market_holidays.requests.get")
    @mock.patch("sync_market_holidays.load_json", return_value=["2026-09-25"])
    def test_new_year_without_calendar_fails_clearly(self, _, get):
        import requests
        get.side_effect = requests.RequestException("offline")
        with self.assertRaisesRegex(RuntimeError, "2027 年休市表缺失"):
            sync(datetime.date(2027, 1, 1))


if __name__ == "__main__":
    unittest.main()
