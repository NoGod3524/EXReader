# SPDX-License-Identifier: MIT
"""Verify the exact Apple integration and both original candidate guards."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

MERGE = '3099237bb52738a6cfff9e2fa4592c40d114bcec'
INTEGRATION = 'e5ea7382b654ba56df42d5f3fe94318e822f876b'
D24 = '45f7767f4ba6efc8f18e550ba8c2ab34b2b6ed04'
D21 = '5fe9a9d7a23a1e70cbd0d4270b520f61f7523466'
BASE = '2f215f5793a7344d22db350276ba9f8a07abe86f'
TXT_FIX = '6cf24162bc97e0054faa54b30ec3dab9972ccaeb'
ALLOWED = {'.github/workflows/integrated-apple-receive.yml',
           '.github/workflows/integrated-apple-large-type.yml',
           'tests/reader_same_source/apple_candidate_guard.py',
           'tests/reader_same_source/bounded_txt_guard.py', 'src/formats.c', 'src/chapter_reader.c',
           'apps/reader/desktop/windows_wave3_bridge.cpp'}

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

def main():
    source = git('rev-parse', 'HEAD')
    if os.environ.get('GITHUB_ACTIONS') != 'true' or source != os.environ.get('GITHUB_SHA'):
        raise ValueError('actual Actions source required')
    if git('rev-list', '--parents', '-n', '1', MERGE).split()[1:] != [INTEGRATION, D24, D21]:
        raise ValueError('integration parents changed')
    subprocess.run(['git', 'merge-base', '--is-ancestor', MERGE, source], check=True)
    changed = set(filter(None, subprocess.check_output(['git', 'diff', '--name-only', '-z', MERGE, source]).decode().split('\0')))
    subprocess.run(['git', 'merge-base', '--is-ancestor', TXT_FIX, source], check=True)
    for path in ('src/formats.c', 'src/chapter_reader.c', 'tests/reader_same_source/bounded_txt_guard.py',
                 'apps/reader/desktop/windows_wave3_bridge.cpp'):
        if Path(path).read_bytes() != subprocess.check_output(['git', 'show', TXT_FIX + ':' + path]):
            raise ValueError('bounded TXT fix differs: ' + path)
    if changed != ALLOWED:
        raise ValueError('unexpected candidate paths: ' + repr(sorted(changed)))
    subprocess.run(['git', 'diff', '--exit-code', BASE, D24, '--', 'src', 'include', 'bindings', 'cmake', 'CMakeLists.txt',
                    'tests/apple_host', 'tests/reader_team24_apple', 'tests/reader_a11y_apple', 'tools'], check=True)
    with tempfile.TemporaryDirectory() as temp:
        checkout = str(Path(temp) / 'd21')
        subprocess.run(['git', 'worktree', 'add', '--detach', checkout, D21], check=True)
        try:
            env = os.environ.copy()
            env['GITHUB_SHA'] = D21
            subprocess.run([sys.executable, 'tests/reader_d21_apple_receive/guard.py'], cwd=checkout, env=env, check=True)
        finally:
            subprocess.run(['git', 'worktree', 'remove', '--force', checkout], check=True)
    Path('build').mkdir(exist_ok=True)
    Path('build/apple-candidate-admission.json').write_text(json.dumps(
        {'source_sha': source, 'merge': MERGE, 'inputs': [INTEGRATION, D24, D21],
         'original_owner_guards_passed': True}, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    main()
