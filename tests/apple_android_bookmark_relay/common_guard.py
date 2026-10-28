"""Admit the bookmark relay on the pinned combined reader source."""
import json
import os
from pathlib import Path
import subprocess

BASE = '5bc11100a4ef31430c7f9a2d865f58d9e705b3e1'
SDK = '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'
assert os.environ.get('GITHUB_ACTIONS') == 'true'
def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()
assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
paths = git('diff', '--name-only', BASE, 'HEAD').splitlines()
for path in paths:
    assert (path == '.github/workflows/reader-apple-android-bookmark-relay.yml'
            or path.startswith('tests/apple_android_bookmark_relay/')
            or path.startswith('docs/handoffs/cross-records/')), path
subprocess.run(['git', 'diff', '--exit-code', SDK, 'HEAD', '--',
                'src', 'include', 'cmake', 'CMakeLists.txt', 'tests/bounded_txt_scan'], check=True)
subprocess.run(['git', 'diff', '--exit-code', BASE, 'HEAD', '--',
                'src', 'include', 'bindings', 'cmake', 'CMakeLists.txt', 'tests/fixtures',
                'tests/reader_d21_apple_receive', 'tests/reader_android_receive_d22',
                'tests/reader_d23_relay', 'tests/reader_team24_apple', 'tests/reader_wave3_c11'], check=True)
out = Path('build/apple-android/admission.json')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'base': BASE, 'source_sha': os.environ['GITHUB_SHA'],
    'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
    'changes': paths, 'candidate_sdk_and_old_suites_unchanged_from_base': True}, indent=2))
