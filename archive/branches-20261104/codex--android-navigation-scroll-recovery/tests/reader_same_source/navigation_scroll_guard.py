# SPDX-License-Identifier: MIT
"""Preserve prior owner guards and admit only the navigation-driver candidate."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = '2f215f5793a7344d22db350276ba9f8a07abe86f'
ALLOWED = {
    'tests/reader_android_navigation/java/org/exreader/host/NavigationUiTest.java',
    'tests/reader_same_source/navigation_scroll_guard.py',
    '.github/workflows/android-navigation-scroll-recovery.yml',
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
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, args.source], check=True)
    changed = set(filter(None, subprocess.check_output(['git', 'diff', '--name-only', '-z', BASE, args.source]).decode().split('\0')))
    if changed != ALLOWED:
        raise ValueError('unexpected candidate paths: ' + repr(sorted(changed)))
    with tempfile.TemporaryDirectory() as temp:
        checkout = str(Path(temp) / 'base')
        subprocess.run(['git', 'worktree', 'add', '--detach', checkout, BASE], check=True)
        try:
            env = os.environ.copy()
            env['GITHUB_SHA'] = BASE
            subprocess.run([sys.executable, 'tests/reader_same_source/guard.py', '--source', BASE,
                            '--report', 'build/original-same-source-admission.json'], cwd=checkout, env=env, check=True)
        finally:
            subprocess.run(['git', 'worktree', 'remove', '--force', checkout], check=True)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'source': args.source, 'base': BASE, 'original_guard_passed': True,
                                  'candidate_paths': sorted(changed), 'product_accepted': False}, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    main()
