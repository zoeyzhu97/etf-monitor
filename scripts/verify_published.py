"""Verify the public site's data against the exact checkout that was deployed."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def snapshot_files(root=ROOT):
    data = root / 'data'
    assessment = json.loads((data / 'daily_assessment.json').read_text())
    return sorted([*data.glob('history/*.json'), *data.glob('index/*.json'),
                   data / 'daily_assessment.json', data / 'comments/manifest.json',
                   data / 'comments' / (assessment['as_of'] + '.md')])


def check_file(base_url, path, root=ROOT):
    relative = path.relative_to(root).as_posix()
    request = urllib.request.Request(
        base_url.rstrip('/') + '/' + relative + '?verify=' + str(time.time_ns()),
        headers={'Cache-Control': 'no-cache', 'User-Agent': 'etf-monitor-verifier'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            remote = response.read().decode('utf-8')
        local = path.read_text(encoding='utf-8')
        equal = (json.loads(remote) == json.loads(local) if path.suffix == '.json'
                 else remote == local)
        return None if equal else f'{relative}: published content differs from deployment'
    except Exception as exc:
        return f'{relative}: {type(exc).__name__}'


def verify(base_url, attempts=6, delay=15, root=ROOT):
    paths = snapshot_files(root)
    for attempt in range(attempts):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            errors = [error for error in pool.map(
                lambda path: check_file(base_url, path, root), paths) if error]
        if not errors:
            print(f'Public snapshot verified: {len(paths)} files')
            return 0
        print(f'Attempt {attempt + 1}/{attempts}: ' + '; '.join(errors), flush=True)
        if attempt + 1 < attempts:
            time.sleep(delay)
    return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--attempts', type=int, default=6)
    args = parser.parse_args()
    raise SystemExit(verify(args.url, args.attempts))
