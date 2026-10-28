import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_published as published


class PublishedTests(unittest.TestCase):
    def test_http_200_with_old_data_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'data.json'
            path.write_text('{"as_of":"2026-10-28"}')
            for body, valid in [(b'{"as_of":"2026-10-27"}', False),
                                (b'<html>error</html>', False),
                                (b'{ "as_of": "2026-10-28" }', True)]:
                with self.subTest(body=body), patch.object(
                        published.urllib.request, 'urlopen', return_value=io.BytesIO(body)):
                    self.assertEqual(published.check_file('https://example.org', path, root)
                                     is None, valid)

    def test_retries_cdn_lag_but_fails_persistent_mismatch(self):
        with patch.object(published, 'snapshot_files', return_value=[Path('data.json')]), \
             patch.object(published.time, 'sleep') as sleep, \
             patch.object(published, 'check_file', side_effect=['stale', None]):
            self.assertEqual(published.verify('https://example.org', attempts=2), 0)
            sleep.assert_called_once()
        with patch.object(published, 'snapshot_files', return_value=[Path('data.json')]), \
             patch.object(published, 'check_file', return_value='stale'):
            self.assertEqual(published.verify('https://example.org', attempts=1), 1)
