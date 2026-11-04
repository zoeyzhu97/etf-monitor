"""Prevent recurrence of the 2026-11-03 stale f84 snapshot incident."""
import datetime as dt
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_etf_shares as fetch
from check_data_freshness import quality_errors
from utils import append_history


def records():
    return [{'date': f'2026-{day}', 'total_shares_yi': 1000.0,
             'source': 'sse_official_shares', 'verified': True}
            for day in ['10-27', '10-28', '10-29', '10-30', '11-02', '11-03']]


class TestShareIntegrity(unittest.TestCase):
    def test_publish_requires_continuous_verified_finite_official_records(self):
        def errors(rows):
            return quality_errors([{'code': '588000'}], {'588000': rows}, '2026-11-03')
        self.assertEqual(errors(records()), [])
        for field, value in [('source', 'eastmoney_f84'), ('verified', False),
                             ('total_shares_yi', float('nan')),
                             ('total_shares_yi', float('inf')), ('total_shares_yi', 0)]:
            with self.subTest(field=field, value=value):
                rows = records()
                rows[-2][field] = value  # Even when the latest day is valid.
                self.assertTrue(errors(rows))
        self.assertTrue(errors(records()[1:]))
        self.assertTrue(errors(records() + [records()[-1]]))
        self.assertTrue(errors(records() + [dict(records()[-1], date='2026-11-04')]))
        self.assertTrue(quality_errors([], {}, '2026-11-03'))

    @mock.patch('utils.save_json')
    @mock.patch('utils.load_history', return_value=records())
    def test_no_downgrade_or_undated_write(self, load, save):
        for source, verified in [('eastmoney_f84', False), ('other', False), ('eastmoney_f84', True)]:
            with self.assertRaises(ValueError):
                append_history('588000', '2026-11-03', 851.37, source, verified)
        save.assert_not_called()
        append_history('588000', '2026-11-03', 1047.716682, 'sse_official_shares', True)
        self.assertEqual(save.call_args.args[1][-1]['total_shares_yi'], 1047.72)

    @mock.patch('utils.save_json')
    @mock.patch('utils.load_history', return_value=[])
    def test_invalid_values_never_written(self, load, save):
        for value in [float('nan'), float('inf'), 0, -10, True]:
            with self.assertRaises(ValueError):
                append_history('588000', '2026-11-03', value, 'sse_official_shares', True)
        save.assert_not_called()

    @mock.patch('fetch_etf_shares._fetch_sse_share_payload_for_date')
    def test_stale_official_response_is_rejected(self, raw):
        raw.return_value = {'result': [{'STAT_DATE': '2026-10-28', 'SEC_CODE': '588000',
                                      'TOT_VOL': '8513666.82'}]}
        with self.assertRaises(ValueError):
            fetch.fetch_sse_share_rows_for_date('2026-11-03', ['588000'])

    @mock.patch('fetch_etf_shares._get_json')
    def test_szse_out_of_range_response_is_rejected(self, raw):
        raw.return_value = [{'metadata': {'tabkey': 'tab1', 'pagecount': 1}, 'data': [
            {'fund_code': '159915', 'size_date': '2026-10-28', 'current_size': '1000000'}]}]
        with self.assertRaises(ValueError):
            fetch.fetch_szse_share_rows('159915', dt.date(2026, 11, 3), dt.date(2026, 11, 3))

    @mock.patch('fetch_etf_shares.append_history')
    @mock.patch('fetch_etf_shares.fetch_official')
    @mock.patch('fetch_etf_shares.load_history')
    def test_repair_replaces_stale_history_only_with_exact_date(self, load, official, append):
        rows = records()
        rows[-1].update(source='eastmoney_f84', verified=False, total_shares_yi=851.37)
        load.return_value = rows
        official.return_value = (1047.716682, 'sse_official_shares', '2026-11-03')
        self.assertEqual(fetch.repair_recent_history('588000', 'SH', dt.date(2026, 11, 4)), 0)
        append.assert_called_once_with('588000', '2026-11-03', 1047.716682, 'sse_official_shares', True)
        append.reset_mock()
        official.return_value = (851.37, 'sse_official_shares', '2026-10-28')
        self.assertEqual(fetch.repair_recent_history('588000', 'SH', dt.date(2026, 11, 4)), 1)
        append.assert_not_called()

    @mock.patch('fetch_etf_shares.fetch_sse_scale_rows')
    @mock.patch('fetch_etf_shares.fetch_sse_share_rows_for_date', return_value=[])
    def test_missing_direct_shares_do_not_fall_back_to_estimates(self, direct, scale):
        self.assertEqual(fetch.fetch_official('588000', 'SH', dt.date(2026, 11, 3)),
                         (None, None, None))
        scale.assert_not_called()

    def test_all_publish_paths_have_quality_gate(self):
        workflows = Path(__file__).resolve().parents[1] / '.github/workflows'
        for name, count in [('daily.yml', 2), ('deploy-pages.yml', 1), ('deploy-cloudbase.yml', 1)]:
            self.assertEqual((workflows / name).read_text().count('scripts/check_data_freshness.py --snapshot'), count)
