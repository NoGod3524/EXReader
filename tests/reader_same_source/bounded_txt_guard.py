# SPDX-License-Identifier: MIT
"""Admit the exact integration merge and retain the original same-source guards."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

MERGE = 'c53768881b022b5ac6bac665943320d27b3eaa5d'
COMMON = '2f215f5793a7344d22db350276ba9f8a07abe86f'
TXT = 'a87c1315218d20aaa456aebf51b1663be40960cf'
ALLOWED = {
    '.github/workflows/sdk-bounded-txt-windows-host.yml',
    '.github/workflows/integrated-bounded-txt-android.yml',
    '.github/workflows/integrated-bounded-txt-gtk.yml',
    '.github/workflows/integrated-bounded-txt-apple.yml',
    '.github/workflows/integrated-bounded-txt-windows.yml',
    'tests/reader_same_source/bounded_txt_guard.py',
}

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or args.source != os.environ.get('GITHUB_SHA') or git('rev-parse', 'HEAD') != args.source:
        raise ValueError('actual Actions source required')
    if git('rev-list', '--parents', '-n', '1', MERGE).split()[1:] != [COMMON, TXT]:
        raise ValueError('integration merge parents changed')
    subprocess.run(['git', 'merge-base', '--is-ancestor', MERGE, args.source], check=True)
    changed = set(filter(None, subprocess.check_output(['git', 'diff', '--name-only', '-z', MERGE, args.source]).decode().split('\0')))
    if changed != ALLOWED:
        raise ValueError('unexpected integration paths: ' + repr(sorted(changed)))
    for platform in ('android', 'gtk', 'apple', 'windows'):
        original = subprocess.check_output(['git', 'show', MERGE + ':.github/workflows/reader-same-source-' + platform + '.yml'], text=True)
        expected = original.replace('branches: [codex/reader-same-source-integration]', 'branches: [codex/reader-integrated-bounded-txt]').replace('tests/reader_same_source/guard.py --source', 'tests/reader_same_source/bounded_txt_guard.py --source')
        if Path('.github/workflows/integrated-bounded-txt-' + platform + '.yml').read_text() != expected:
            raise ValueError('original workflow changed: ' + platform)
    with tempfile.TemporaryDirectory() as temp:
        checkout = str(Path(temp) / 'common')
        subprocess.run(['git', 'worktree', 'add', '--detach', checkout, COMMON], check=True)
        try:
            env = os.environ.copy()
            env['GITHUB_SHA'] = COMMON
            subprocess.run([sys.executable, 'tests/reader_same_source/guard.py', '--source', COMMON,
                            '--report', 'build/original-same-source-admission.json'], cwd=checkout, env=env, check=True)
        finally:
            subprocess.run(['git', 'worktree', 'remove', '--force', checkout], check=True)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'source': args.source, 'merge': MERGE, 'common': COMMON, 'txt': TXT,
                                  'original_guard_passed': True, 'product_accepted': False}, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    main()
