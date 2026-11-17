"""Regression coverage for the AKShare 1.20.44 interface rename."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fetch_index_daily import backfill_with_akshare


class IndexFetchTests(unittest.TestCase):
    def test_new_and_legacy_api_preserve_date_and_close(self):
        frame = SimpleNamespace(
            columns=['date', 'close'],
            iterrows=lambda: iter([(0, {'date': '2026-11-17', 'close': 4000.25})]))
        for renamed in (True, False):
            with self.subTest(renamed=renamed):
                fetch = Mock(return_value=frame)
                module = SimpleNamespace()
                if renamed:
                    module.index_zh_daily_sina = fetch
                    module.stock_zh_index_daily = Mock(side_effect=AttributeError('renamed'))
                else:
                    module.stock_zh_index_daily = fetch
                with patch.dict(sys.modules, {'akshare': module}), \
                        patch('fetch_index_daily.save_json') as save:
                    backfill_with_akshare('000001', 'sh000001', '2005-01-01')
                fetch.assert_called_once_with(symbol='sh000001')
                save.assert_called_once_with('index/000001.json',
                    [{'date': '2026-11-17', 'close': 4000.25}])
                if renamed:
                    module.stock_zh_index_daily.assert_not_called()
