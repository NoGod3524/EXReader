# SPDX-License-Identifier: MIT
"""Actions-only: installed C and C++ search consumers against real frozen-SDK sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

REQUIRED_CHECKS = [
    'empty query is refused', 'embedded NUL is refused', 'overlong UTF-8 is refused', 'UTF-16 surrogate in UTF-8 is refused',
    '4097-byte query is refused', '4096-byte query is accepted', 'batch of 101 is refused',
    'reflow-250 completes with the batch contract', 'reflow-250 matches the independent full-text scan',
    '250 hits continue as 100, 100, 50', 'exactly 100 hits end with a separate empty complete batch',
    'hit at the very start of the text', 'hit at the very end of the text', 'search is case-sensitive',
    'reflow-emoji matches the independent full-text scan', 'reflow-chinese matches the independent full-text scan',
    'a stored cursor resumes at the next hit in a new handle', 'a cursor bound to a different query is refused',
    'the same verified original resumes through an independent SDK instance',
    'unbound version 1 cursors are refused', 'a reflow cursor with a nonzero unit is refused',
    'a cursor past the verified source is refused', 'an early complete cursor is refused',
    'an unterminated cursor source key is refused', 'a changed parser projection identity is refused',
    'resume requires a verified source key', 'invalid source key is refused',
    'a transient search advances on its live handle', 'a transient cursor cannot resume as a verified source',
    'cross-book fixtures have different text with equal normalized length',
    'a cursor is refused for another equal-length book with the same query',
    'wrong-thread next cursor stats and close are refused without changing the owner state',
    'the creating owner still searches after worker rejection',
    'epub-token matches the independent per-chapter scan',
    'a repeated spine path yields one hit per spine index with the same verbatim path',
    'a quote split across two chapters is never a hit',
    'long chapter hits equal the independent full-chapter scan',
    'long chapter has hits that straddle observed 32 KiB stream block boundaries',
    'every chapter byte is scanned exactly once across batches',
    'multi-page PDF hits keep distinct pages around an empty page',
    'pdf-shared-quote matches the independent per-page scan',
    'gen-emoji matches the independent per-page scan',
    '180 fixed hits continue mid-page across 100 then 80',
    'a failing provider returns an SDK error and an empty result',
    'the failed batch leaves the previous successful cursor',
    'retry after the provider recovers returns the same next batch',
    'cancel-reflow cancellation at every poll point keeps the cursor and the retry returns the identical batch',
    'cancel-epub cancellation at every poll point keeps the cursor and the retry returns the identical batch',
    'cancel-fixed cancellation at every poll point keeps the cursor and the retry returns the identical batch',
    'reentry-reflow reentrant next/cursor/stats/close return BUSY and the outer call succeeds',
    'reentry-epub reentrant next/cursor/stats/close return BUSY and the outer call succeeds',
    'reentry-fixed reentrant next/cursor/stats/close return BUSY and the outer call succeeds',
    'source bytes of txt are unchanged', 'source bytes of long are unchanged', 'current reading progress is unchanged',
    'no SDK note was created', 'no product revision was inserted or queued', 'product progress heads are unchanged',
    'wire v1 bytes of a search hit equal the plain SDK capture', 'wire v2 bytes of a search hit equal the plain SDK capture',
]
REQUIRED_CASES = ['reflow-chinese', 'reflow-emoji', 'reflow-250', 'reflow-exact-100', 'epub-token', 'epub-repeated-spine', 'epub-long-needle',
                  'pdf-shared-quote', 'pdf-ambiguous', 'gen-emoji', 'gen-180']


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(root):
    root = Path(root)
    return [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256(p)}
            for p in sorted(root.rglob('*')) if p.is_file()]


def main():
    p = argparse.ArgumentParser()
    for name in ('probe', 'c-consumer', 'fixtures', 'font', 'installed', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = a.output.resolve(); out.mkdir(parents=True)

    c = subprocess.run([str(a.c_consumer.resolve())], capture_output=True, text=True, encoding='utf-8', timeout=120)
    (out / 'c-consumer.log').write_text(c.stdout + '\n' + c.stderr, encoding='utf-8')
    print(c.stdout); print(c.stderr)
    assert c.returncode == 0 and c.stdout.strip() == 'c-consumer-ok', 'installed C consumer refused: exit %s' % c.returncode

    manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
    assert set(manifest) == {'txt', 'epub', 'pdf', 'long'}, manifest.keys()
    work = out / 'work'; work.mkdir()
    command = [str(a.probe.resolve()), '--fixtures', str(a.fixtures.resolve()), '--font', str(a.font.resolve()),
               '--work', str(work), '--report', str(out / 'probe.json')]
    for role, entry in manifest.items():
        assert hashlib.sha256((a.fixtures / entry['file']).read_bytes()).hexdigest() == entry['sha256'], role
        command += ['--sha', role + '=' + entry['sha256']]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=1500)
    (out / 'probe.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    print(result.stdout); print(result.stderr)
    assert result.returncode == 0, 'C++ search probe refused: exit %s' % result.returncode

    report = json.loads((out / 'probe.json').read_text(encoding='utf-8'))
    checks = report['checks']
    assert report['failures'] == 0 and checks and all(c['pass'] is True for c in checks), 'a probe check failed'
    names = {c['name'] for c in checks}
    missing = [n for n in REQUIRED_CHECKS if n not in names]
    assert not missing, 'required checks absent: %s' % missing
    case_ids = [c['id'] for c in report['cases']]
    assert len(case_ids) == len(set(case_ids)), 'duplicate case ids'
    assert all(n in case_ids for n in REQUIRED_CASES), 'required cases absent'
    for case in report['cases']:
        assert case['mislocated'] == 0 and case['other'] == 0, case['id']
    measurement = [m for m in report['measurements'] if m['id'] == 'epub-long-chapter']
    assert len(measurement) == 1 and measurement[0]['straddling_hits'] >= 1, 'long-chapter measurement missing'

    windows = sys.platform.startswith('win')
    summary = {
        'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'platform_detail': platform.platform(),
        'runner_os': os.environ.get('RUNNER_OS'), 'runner_arch': os.environ.get('RUNNER_ARCH'), 'image': os.environ.get('ImageVersion'),
        'checks': len(checks), 'cases': report['cases'], 'measurements': report['measurements'],
        'fixtures': manifest, 'probe_sha256': sha256(a.probe), 'c_consumer_sha256': sha256(a.c_consumer),
        'installed_files': tree(a.installed),
        'granted_platform': 'windows' if windows else 'linux', 'macos_accepted': False,
        'performance_claimed': False, 'host_ui_accepted': False, 'six_platform_accepted': False, 'complete_product': False,
        'schema_changed': False, 'sdk_changed': False,
    }
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)


if __name__ == '__main__': main()
