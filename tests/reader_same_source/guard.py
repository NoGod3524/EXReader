# SPDX-License-Identifier: MIT
"""Source-bound integration admission; original owner guards remain unchanged."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = '85b531504b4d830e5839affad2cb80cf02a90507'
WINDOWS_OWNER = '895ccb10a78e037d72b3a9ab60beb9903fa868c8'
APPLE_OWNER = '937f61057b06c5c9de3b562046e52c91b5be62b9'
EXPECTED = {
    '.github/workflows/reader-same-source-windows.yml': 'bfbb9d62497d23b0bec4d219201807eb64f4ad58',
    '.github/workflows/reader-same-source-android.yml': '0c0c540f784b0e10ae51dc217078cb734cd7e1c5',
    '.github/workflows/reader-same-source-gtk.yml': '8a830b80d46ee3e4cc00ebe08ec42c51583216d8',
    '.github/workflows/reader-same-source-apple.yml': '6eb1ac577f55727a1c107f3b9a49097d8c0e8f49',
}
SELF = 'tests/reader_same_source/guard.py'

def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or args.source != os.environ.get('GITHUB_SHA') or git('rev-parse', 'HEAD') != args.source or len(args.source) != 40:
        raise ValueError('actual Actions source required')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, args.source], check=True)
    diff = subprocess.check_output(['git', 'diff', '--name-only', '-z', BASE, args.source]).decode().split('\0')
    if set(filter(None, diff)) != set(EXPECTED) | {SELF}:
        raise ValueError('unexpected integration paths')
    for path, blob in EXPECTED.items():
        if git('rev-parse', args.source + ':' + path) != blob or git('ls-tree', args.source, '--', path).split()[0] != '100644':
            raise ValueError('integration workflow changed: ' + path)
    if git('ls-tree', args.source, '--', SELF).split()[0] != '100644':
        raise ValueError('integration guard mode changed')
    owners = [(WINDOWS_OWNER, ['tools/reader_composition/guard.py', '--source', git('rev-parse', WINDOWS_OWNER), '--report', 'build/owner-composition.json']),
              (APPLE_OWNER, ['tests/reader_team24_apple/guard_owner.py']),
              ('f92d1bb9a40dd05ec6b8603172091648e4575b98', ['tests/reader_wave3_c09/team24_guard.py']),
              ('af87ba8db0c43f4fcf878983eaa2290e7889b0ee', ['tests/reader_gtk_raw_wave3/guard.py']),
              ('28f49ee0399d48518cc2afb0048009b6c38edcfa', ['tests/reader_wave3_c11/guard.py'])]
    checked = []
    with tempfile.TemporaryDirectory() as temp:
        for index, (owner, command) in enumerate(owners):
            full = git('rev-parse', owner + '^{commit}')
            subprocess.run(['git', 'merge-base', '--is-ancestor', full, args.source], check=True)
            path = str(Path(temp) / str(index))
            subprocess.run(['git', 'worktree', 'add', '--detach', path, full], check=True)
            try:
                env = os.environ.copy()
                env['GITHUB_SHA'] = full
                subprocess.run([sys.executable, *command], cwd=path, env=env, check=True)
                checked.append(full)
            finally:
                subprocess.run(['git', 'worktree', 'remove', '--force', path], check=True)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'source': args.source, 'run': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'exact_base': BASE, 'original_guards_on_ancestors': checked, 'workflow_blobs': EXPECTED, 'product_accepted': False}, indent=2) + '\n')

if __name__ == '__main__':
    main()
