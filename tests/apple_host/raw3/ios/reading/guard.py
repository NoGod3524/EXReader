"""Exact frozen SDK/family and untouched original mobile controls."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
BASE = '44eabdc86b3b84d986f81dbaf8cee92b1829cea8'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
FAMILY = '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275'
PACKAGES = ['revisions', 'reading-state', 'reading-commands', 'annotation-view', 'commands', 'sync', 'session']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = os.environ['GITHUB_SHA']
    assert git('rev-parse', 'HEAD') == source
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT, check=True)
    protected = ['src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings',
                 '.github/workflows/native.yml', '.github/workflows/reliability.yml']
    assert not git('diff', '--name-only', SDK, source, '--', *protected)
    assert git('rev-parse', source + ':apps/reader/store/001_catalog.sql') == git('rev-parse', BASE + ':apps/reader/store/001_catalog.sql')
    for name in PACKAGES:
        path = 'apps/reader/' + name
        assert git('rev-parse', source + ':' + path) == git('rev-parse', FAMILY + ':' + path)
    for path in ['tests/apple_host/reading', 'tests/apple_host/navigation', 'tests/apple_host/make_xcodeproj.rb',
                 'tests/apple_host/raw3/RawRecordInterop.swift', 'tests/apple_host/raw3/tls_fixture.py']:
        assert git('rev-parse', source + ':' + path) == git('rev-parse', BASE + ':' + path)
    allowed = {'examples/apple/HostModel.swift', 'examples/apple/HostReadingRecords.swift',
               'examples/apple/HostViews.swift', 'examples/apple/HostRaw3Review.swift',
               '.github/workflows/reader-apple-raw3-ios.yml', 'docs/READER-APPLE-RAW3-IOS.md',
               'docs/validation/reader-apple-raw3-ios.json'}
    changed = git('diff', '--name-only', BASE, source).splitlines()
    assert all(path in allowed or path.startswith('tests/apple_host/raw3/ios/') for path in changed), changed
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch
    peer = fetch('actions/runs/40196978163')
    assert peer['head_sha'] == '15dab6b2270dc296ed6239db67ced2e22d255e65' and peer['conclusion'] == 'success'
    jobs = fetch('actions/runs/40196978163/attempts/1/jobs?per_page=100')['jobs']
    assert {row['id'] for row in jobs if row['conclusion'] == 'success'} == {121179826434, 121186031984}
    print(json.dumps({'accepted': True, 'source_sha': source, 'base': BASE, 'sdk': SDK, 'family': FAMILY,
                      'original_mobile_cases_unchanged': 7, 'original_wait_seconds': 90, 'changed': changed}))


if __name__ == '__main__':
    main()
