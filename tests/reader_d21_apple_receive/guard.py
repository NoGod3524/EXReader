# SPDX-License-Identifier: MIT
"""D21 additive owner gate. Original owner guards and tests stay unchanged."""
import json, os, subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true'
base = '2f215f5793a7344d22db350276ba9f8a07abe86f'
allowed = {'examples/apple/HostAccount.swift', 'examples/apple/HostCatalog.swift',
           'examples/apple/HostModel.swift', 'examples/apple/HostViews.swift',
           '.github/workflows/reader-d21-apple-receive.yml'}
paths = subprocess.check_output(['git','diff','--name-only',base,'HEAD'], text=True).splitlines()
subprocess.run(['git','merge-base','--is-ancestor','a7020b07b8515e0d4b8e2693522920e2ec78eb35','HEAD'],check=True)
integration_changes = subprocess.check_output(['git','diff','--name-only','a7020b07b8515e0d4b8e2693522920e2ec78eb35','HEAD'],text=True).splitlines()
assert all(p in ['.github/workflows/sdk-txt-anchor-resolve.yml', 'apps/reader/desktop/windows_records.inc', 'apps/reader/desktop/windows_records_owner.cpp', 'include/exr/formats.h', 'src/formats.c', 'tests/txt_anchor_resolve/CMakeLists.txt', 'tests/txt_anchor_resolve/check.c', '.github/workflows/reader-d21-apple-receive.yml', '.github/workflows/reader-d22-android-receive.yml', '.github/workflows/reader-d23-relay.yml', '.github/workflows/reader-d24-apple-large-type.yml', '.github/workflows/reader-d25-real-formats.yml', '.github/workflows/reader-d26-accessibility.yml', 'tests/reader_d21_apple_receive/guard.py', 'tests/reader_android_receive_d22/guard.py', 'tests/reader_d25_real_formats/run.py', 'examples/reader.c', 'apps/reader/desktop/windows_search.inc', 'apps/reader/desktop/windows_search_types.h', 'apps/reader/desktop/windows_txt_search.inc', 'apps/reader/desktop/windows_wave3.inc', 'apps/reader/original-export/include/reader_original_export.h', 'apps/reader/original-export/src/original_export.cpp', 'tests/reader_txt_mixed_export/CMakeLists.txt', 'tests/reader_txt_mixed_export/mixed.c', '.github/workflows/reader-txt-mixed-export.yml', 'tests/windows_host/txt/check_progress.py', 'tests/reader_wave3_c09/build.py', 'tests/reader_d26_accessibility/current_expectations.py', 'tests/reader_d26_accessibility/g13_current.py', 'docs/READER-WINDOWS-TXT-PROGRESS.md', 'tests/reader_d26_accessibility/audit_current.py', 'tests/reader_d26_accessibility/tools_current.py', 'tests/reader_d26_accessibility/account_status.py', 'docs/reader-total-progress/catalog.json', 'docs/reader-total-progress/README.md', 'docs/reader-total-progress/android-jump-d22.md', 'docs/reader-total-progress/android-annotations-d22.md', '.github/workflows/windows-wave3-txt-progress.yml'] for p in integration_changes), integration_changes
# The approved candidate may change only the pinned TXT selector files.
for reference, files in [('9727ca1624ee59e561fd6aad7a22bb85a0fd2632',['src/formats.c','include/exr/formats.h']),
                         ('e09b25aa02b03297dc8a7f1f6eb32c092e11d410',['apps/reader/desktop/windows_records.inc','apps/reader/desktop/windows_records_owner.cpp'])]:
 assert not subprocess.check_output(['git','diff','--name-only',reference,'HEAD','--',*files],text=True).strip()
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip() == os.environ['GITHUB_SHA']
Path('build').mkdir(exist_ok=True)
Path('build/d21-admission.json').write_text(json.dumps({'base':base,'source_sha':os.environ['GITHUB_SHA'],
    'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'changed_paths':paths},indent=2))
