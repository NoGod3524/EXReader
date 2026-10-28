"""Additive relay admission; do not rewrite earlier task-specific guards."""
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
BASE = 'c5688c4adf0506d44e097b076be30e1985341012'
def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()
assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
paths = git('diff', '--name-only', BASE, 'HEAD').splitlines()
for path in paths:
    assert (path in {'.github/workflows/reader-apple-android-relay.yml',
                     '.github/workflows/windows-wave3-txt-progress.yml',
                     '.github/workflows/sdk-ot-cache-acceptance.yml',
                     'tests/bounded_txt_scan/CMakeLists.txt',
                     'tests/bounded_txt_scan/large_pager.c',
                     'tests/bounded_txt_scan/ot_compare.c',
                     'docs/SDK-OT-CONTEXT-MISS.md',
                     'docs/WINDOWS-TXT-HISTORY-RECOVERY.md'}
        or path.startswith('tests/opentype_cache_acceptance/')
        or path.startswith('docs/handoffs/ot-cache-acceptance')
        or path.startswith('tests/apple_android_relay/')
        or path.startswith('docs/handoffs/apple-android-relay')
        or path in {'examples/apple/HostAccount.swift', 'examples/apple/HostCatalog.swift',
            'examples/apple/HostModel.swift', 'examples/apple/HostViews.swift',
            'examples/android/app/src/main/java/org/exreader/host/MainActivity.java',
            'examples/android/app/src/main/java/org/exreader/host/SyncController.java',
            'examples/android/app/src/main/java/org/exreader/host/SyncOriginal.java',
            'examples/android/app/src/main/java/org/exreader/host/NativeSync.java',
            'examples/android/app/src/main/java/org/exreader/host/ReadingPanel.java',
            'examples/android/app/src/main/java/org/exreader/host/BoundedEpub.java',
            'examples/android/app/src/main/java/org/exreader/host/PageSnapshot.java',
            'examples/android/app/src/main/java/org/exreader/host/ReaderView.java',
            'examples/android/app/src/main/cpp/bounded_epub_jni.inc',
            'examples/android/app/src/main/cpp/sync_jni.cpp'}), path
subprocess.run(['git', 'diff', '--exit-code', '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9',
                'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt',
                'tests/bounded_txt_scan'], check=True)
for path in ('src', 'include', 'bindings', 'cmake', 'CMakeLists.txt', 'tests/fixtures',
             'tests/reader_d21_apple_receive', 'tests/reader_android_receive_d22',
             'tests/reader_d23_relay', 'tests/reader_team24_apple', 'tests/reader_wave3_c11'):
    assert not git('diff', '--name-only', BASE, 'HEAD', '--', path), path
out = Path('build/apple-android/admission.json')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'base': BASE, 'source_sha': os.environ['GITHUB_SHA'],
    'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
    'changes': paths, 'candidate_sdk_and_old_suites_unchanged_from_base': True}, indent=2))
