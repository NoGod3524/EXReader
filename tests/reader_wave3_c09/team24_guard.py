"""Actions-only incremental Windows team scope; the original C09 guard remains frozen."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SEED = '310b4223a3d119555f1d04384af7f5b16b7b582f'
FILES = {'examples/reader.c', '.github/workflows/reader-team24-windows.yml',
         'HANDOFF-RESULT-C09.md'}
PREFIXES = ('examples/windows/', 'apps/reader/desktop/windows_', 'tests/reader_wave3_c09/',
            'docs/reader-wave3-c09/')
FROZEN = {'tests/reader_wave3_c09/guard.py'}
# Coordinator-approved dependency admission; these files remain owned by core.
CAPTURE_SOURCE = 'a911cd0e8405a362dae1bb489190de02c4c81d51'
CAPTURE_BLOBS = {
    'apps/reader/reading-state/CMakeLists.txt': '2b513deeb2681eb2e0c674fe447ddfee83cb3994',
    'apps/reader/reading-state/include/reader_reading_state_capture_raw_candidate.h': '0cce3515dbcbed3c6b49356e1d6dc137b5a31aaa',
    'apps/reader/reading-state/src/reading_state.cpp': '25de29dd59828371d7c35dc8a6295b9d74bc738d',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    head = git('rev-parse', 'HEAD')
    subprocess.check_call(['git', 'merge-base', '--is-ancestor', SEED, head], cwd=ROOT)
    changed = git('diff', '--name-only', SEED, head).splitlines()
    foreign = [p for p in changed if not (p in FILES or p.startswith(PREFIXES) or p in CAPTURE_BLOBS) or p in FROZEN]
    capture_blobs = {p: git('rev-parse', head + ':' + p) for p in CAPTURE_BLOBS}
    dependency_valid = capture_blobs == CAPTURE_BLOBS
    report = dict(seed=SEED, head=head, github_sha=os.environ['GITHUB_SHA'], changed=changed,
                  capture_source=CAPTURE_SOURCE, capture_blobs=capture_blobs,
                  dependency_valid=dependency_valid, foreign=foreign,
                  accepted=not foreign and dependency_valid and head == os.environ['GITHUB_SHA'])
    output = ROOT / 'build/team24-windows-guard'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not report['accepted']:
        sys.exit('Windows team modified frozen or unowned source')


if __name__ == '__main__':
    main()
