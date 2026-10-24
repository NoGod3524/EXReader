# SPDX-License-Identifier: MIT
"""Actions-only: installed C and C++ navigation consumers against real frozen-SDK sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

REQUIRED_CASES = ['epub3-nav', 'epub2-ncx', 'epub3-repeated-spine', 'empty']
CASE_CHECKS = ["snapshot opens", "info is authored and counts the spine", "paging contract holds with 100 rows",
               "5-row paging equals 100-row paging",
               "rows equal the SDK's entries in order, parent, label, href, base, role and part",
               "row strings are copies, not SDK pointers", "every row matches the hand-written expectation list",
               "every row resolves to its expected outcome on both SDK objects",
               "resolved targets name the same spine index and path on the second object",
               "fragment targets carry the node and part-only never carries one",
               "the fragment node's id is confirmed on the second independent SDK object",
               "children queries equal the original parent links", "a different book is refused with MISMATCH",
               "document snapshot opens", "document rows equal publication rows",
               "document targets resolve to the same outcomes with confirmed nodes",
               "snapshot rows are unchanged after the publication is freed", "the original file bytes are unchanged"]
REQUIRED_CHECKS = ['%s: %s' % (case, name) for case in ('epub3-nav', 'epub2-ncx', 'epub3-repeated-spine') for name in CASE_CHECKS] + [
    'epub3-repeated-spine: repeated spine paths list every candidate and only an explicit matching part resolves',
    'open: cancelling at every poll point yields CANCELLED with no handle',
    'open: a retry after cancellation returns the identical snapshot',
    'empty: a book without authored navigation gives an empty snapshot that is not an author outline',
    'damaged: broken.epub is CORRUPT with no handle and an SDK code',
    'damaged: entity.epub is CORRUPT with no handle and an SDK code',
    'damaged: missing-ncx.epub is CORRUPT with no handle and an SDK code',
    'custom: a path repeated in the spine is AMBIGUOUS and never the first match',
    'custom: explicit spine index 2 resolves the second repeated item with its verbatim path',
    'custom: explicit index of another path is MISMATCH', 'custom: explicit index beyond the book is RANGE',
    'custom: a missing fragment keeps the part and no node (PART_ONLY)',
    'custom: the independent SDK fixture has a chapter and reports a missing fragment',
    'custom: a row without href is UNRESOLVED',
    'custom: one path match that the SDK left unresolved is not guessed',
    'custom: cancelling at every poll point of resolve yields CANCELLED and no target',
    'custom: reentrant rows/info/children/close from a control callback return BUSY and the outer call succeeds',
    'limits: 150 rows with max_nodes 100 are refused, not truncated', 'limits: exactly max_nodes is accepted',
    'limits: text over max_text_bytes is refused', 'limits: five levels with max_depth 4 are refused',
    'limits: exactly max_depth levels are accepted and counted',
    'limits: a chain of 64 levels is accepted at the default depth', 'limits: a chain of 65 levels is refused at the default depth',
    'limits: 10000 rows are accepted by default', 'limits: 10000 rows page as 100 pages of 100 in original order',
    'cfi: a CFI of each repeated spine item resolves to that spine index, not the first path match',
    'cfi: an invalid CFI is refused and yields no target', 'cfi: a CFI against another book is MISMATCH',
    'pages: it is flagged as pages and never as an author outline',
    'pages: every page is a root row with role page, its page id and no PDF outline text',
    'pages: each page row is confirmed on a second independently opened PDF', 'pages: another document is MISMATCH',
    'pages: more pages than max_nodes are refused', 'pages: the PDF bytes are unchanged',
    'identity: different originals retain identical part paths and IDs',
    'identity: a verified source snapshot opens',
    'identity: open copies the source key and allows an independently opened identical original',
    'identity: another original with identical directory is MISMATCH',
    'identity: a wrong key is refused even for the original handle',
    'identity: CFI resolution checks the actual source key',
    'identity: missing resolve options and missing key are ARGUMENT',
    'identity: parser version is part of the source key',
    'identity: an unbound snapshot remains display-only',
    'identity: empty oversized malformed UTF-8 and unterminated keys are refused',
    'identity: one-byte and 255-byte UTF-8 keys roundtrip exactly',
    'owner: all handle calls refuse another thread before SDK access and keep the handle',
    'owner: the creating owner can still navigate after wrong-thread calls',
    'identity: malformed options and outside row clear the target',
    'identity: document resolution rejects a different original with the same chapters',
    'identity: fixed pages reject another original with identical page IDs',
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(root):
    root = Path(root)
    return [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256(p)}
            for p in sorted(root.rglob('*')) if p.is_file()]


def main():
    p = argparse.ArgumentParser()
    for name in ('probe', 'c-consumer', 'fixtures', 'installed', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(); assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = a.output.resolve(); out.mkdir(parents=True)

    c = subprocess.run([str(a.c_consumer.resolve())], capture_output=True, text=True, encoding='utf-8', timeout=120)
    (out / 'c-consumer.log').write_text(c.stdout + '\n' + c.stderr, encoding='utf-8')
    print(c.stdout); print(c.stderr)
    assert c.returncode == 0 and c.stdout.strip() == 'c-consumer-ok', 'installed C consumer refused: exit %s' % c.returncode

    manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
    for name, entry in manifest.items():
        assert sha256(a.fixtures / name) == entry['sha256'], name
    command = [str(a.probe.resolve()), '--fixtures', str(a.fixtures.resolve()), '--report', str(out / 'probe.json')]
    for name, entry in manifest.items():
        command += ['--source-key', name + '=' + entry['sha256']]
    result = subprocess.run(command,
                            capture_output=True, text=True, encoding='utf-8', timeout=1500)
    (out / 'probe.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    print(result.stdout); print(result.stderr)
    assert result.returncode == 0, 'C++ navigation probe refused: exit %s' % result.returncode

    report = json.loads((out / 'probe.json').read_text(encoding='utf-8'))
    checks = report['checks']
    assert report['failures'] == 0 and checks and all(c['pass'] is True for c in checks), 'a probe check failed'
    names = {c['name'] for c in checks}
    missing = [n for n in REQUIRED_CHECKS if n not in names]
    assert not missing, 'required checks absent: %s' % missing
    ids = [c['id'] for c in report['cases']]
    assert len(ids) == len(set(ids)) and all(n in ids for n in REQUIRED_CASES), 'required cases absent or duplicated'
    for case in report['cases']:
        assert case['mislocated'] == 0 and case['other'] == 0, case['id']
    by_id = {c['id']: c for c in report['cases']}
    assert by_id['epub3-nav']['rows'] == 13 and by_id['epub2-ncx']['rows'] == 8 and by_id['epub3-repeated-spine']['rows'] == 3
    assert by_id['epub3-repeated-spine']['ambiguous'] == 2 and by_id['empty']['rows'] == 0

    windows = sys.platform.startswith('win')
    summary = {
        'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'platform_detail': platform.platform(),
        'runner_os': os.environ.get('RUNNER_OS'), 'runner_arch': os.environ.get('RUNNER_ARCH'), 'image': os.environ.get('ImageVersion'),
        'checks': len(checks), 'cases': report['cases'], 'fixtures': manifest,
        'probe_sha256': sha256(a.probe), 'c_consumer_sha256': sha256(a.c_consumer), 'installed_files': tree(a.installed),
        'granted_platform': 'windows' if windows else 'linux', 'macos_accepted': False,
        'performance_claimed': False, 'host_ui_accepted': False, 'six_platform_accepted': False, 'complete_product': False,
        'author_outline_for_fixed_documents': False, 'schema_changed': False, 'sdk_changed': False,
    }
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)


if __name__ == '__main__': main()
