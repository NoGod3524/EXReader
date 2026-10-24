# SPDX-License-Identifier: MIT
"""Actions-only: real captures through product revisions and public SDK resolve."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_reading_state'))
from check_reading_state import sqlite_providers

EXPECTED = ['txt-progress-start', 'txt-progress-multibyte', 'txt-progress-end', 'txt-bookmark', 'txt-highlight', 'txt-ambiguous',
            'epub-global-highlight', 'epub-global-progress', 'epub-bookmark-part-0', 'epub-bookmark-part-1',
            'epub-chapter-progress', 'epub-bookmark-part-2', 'pdf-highlight', 'pdf-bookmark', 'pdf-textless-bookmark',
            'pdf-progress', 'cbz-bookmark', 'cbz-progress']


def main():
    p = argparse.ArgumentParser()
    for name in ('probe', 'legacy-probe', 'legacy-c-consumer', 'fixtures', 'font', 'legacy-map', 'link-map', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = a.output.resolve(); out.mkdir(parents=True)
    legacy_output = out / 'legacy'
    legacy = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'reader_reading_state/check_reading_state.py'),
                             '--probe', str(a.legacy_probe.resolve()), '--c-consumer', str(a.legacy_c_consumer.resolve()),
                             '--fixtures', str(a.fixtures.resolve()), '--font', str(a.font.resolve()), '--link-map', str(a.legacy_map.resolve()),
                             '--output', str(legacy_output)], capture_output=True, text=True, encoding='utf-8', timeout=180)
    (out / 'legacy-run.log').write_text(legacy.stdout + '\n' + legacy.stderr, encoding='utf-8')
    print(legacy.stdout); print(legacy.stderr); assert legacy.returncode == 0, 'original 121-check probe refused'
    manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
    work = out / 'work'; work.mkdir()
    command = [str(a.probe.resolve()), '--fixtures', str(a.fixtures.resolve()), '--font', str(a.font.resolve()),
               '--work', str(work), '--report', str(out / 'probe.json')]
    for role, entry in manifest.items():
        assert hashlib.sha256((a.fixtures / entry['file']).read_bytes()).hexdigest() == entry['sha256']
        command += ['--sha', role + '=' + entry['sha256']]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=180)
    (out / 'probe.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    print(result.stdout); print(result.stderr); assert result.returncode == 0, 'v2 real-capture probe refused'
    report = json.loads((out / 'probe.json').read_text(encoding='utf-8'))
    assert report['failures'] == 0 and report['checks'] and all(c['pass'] is True for c in report['checks'])
    assert [c['id'] for c in report['cases']] == EXPECTED
    assert report['receiver_found'] == 17 and report['receiver_mislocated'] == 0
    for case in report['cases']:
        assert case['state'] == ('AMBIGUOUS' if case['id'] == 'txt-ambiguous' else 'FOUND')
    providers = sqlite_providers(a.link_map.read_text(encoding='utf-8', errors='replace'))
    assert len(providers) == 1 and 'reader_catalog_sqlite' in providers[0], providers
    summary = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
               'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'legacy_checks': 121,
               'cases': report['cases'], 'checks': len(report['checks']), 'receiver_found': 17, 'receiver_mislocated': 0,
               'sqlite_providers': providers, 'consumer_sha256': hashlib.sha256(a.probe.read_bytes()).hexdigest(),
               'schema_changed': False, 'sdk_changed': False, 'webdav_roundtrip_accepted': False,
               'host_ui_accepted': False, 'six_platform_accepted': False, 'complete_product': False}
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)


if __name__ == '__main__': main()
