"""Actions-only D22 ownership and original-evidence guard; not a replacement SDK gate."""
import json, os, subprocess, tempfile
from pathlib import Path
BASE='2f215f5793a7344d22db350276ba9f8a07abe86f'
ALLOWED={
'examples/android/app/src/main/java/org/exreader/host/SyncController.java',
'examples/android/app/src/main/java/org/exreader/host/SyncOriginal.java',
'examples/android/app/src/main/java/org/exreader/host/NativeSync.java',
'examples/android/app/src/main/java/org/exreader/host/MainActivity.java',
'examples/android/app/src/main/cpp/sync_jni.cpp',
'.github/workflows/reader-d22-android-receive.yml',
}
def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
assert os.environ.get('GITHUB_ACTIONS')=='true'
sha=git('rev-parse','HEAD');assert sha==os.environ['GITHUB_SHA']
subprocess.run(['git','merge-base','--is-ancestor',BASE,sha],check=True)
changed=git('diff','--name-only',BASE,sha).splitlines()
subprocess.run(['git','merge-base','--is-ancestor','a7020b07b8515e0d4b8e2693522920e2ec78eb35',sha],check=True)
integration_changes=git('diff','--name-only','a7020b07b8515e0d4b8e2693522920e2ec78eb35',sha).splitlines()
assert all(p in ['.github/workflows/sdk-txt-anchor-resolve.yml', 'apps/reader/desktop/windows_records.inc', 'apps/reader/desktop/windows_records_owner.cpp', 'include/exr/formats.h', 'src/formats.c', 'tests/txt_anchor_resolve/CMakeLists.txt', 'tests/txt_anchor_resolve/check.c', '.github/workflows/reader-d21-apple-receive.yml', '.github/workflows/reader-d22-android-receive.yml', '.github/workflows/reader-d23-relay.yml', '.github/workflows/reader-d24-apple-large-type.yml', '.github/workflows/reader-d25-real-formats.yml', '.github/workflows/reader-d26-accessibility.yml', 'tests/reader_d21_apple_receive/guard.py', 'tests/reader_android_receive_d22/guard.py', 'tests/reader_d25_real_formats/run.py', 'examples/reader.c', 'apps/reader/desktop/windows_search.inc', 'apps/reader/desktop/windows_search_types.h', 'apps/reader/desktop/windows_txt_search.inc', 'apps/reader/desktop/windows_wave3.inc', 'apps/reader/original-export/include/reader_original_export.h', 'apps/reader/original-export/src/original_export.cpp', 'tests/reader_txt_mixed_export/CMakeLists.txt', 'tests/reader_txt_mixed_export/mixed.c', '.github/workflows/reader-txt-mixed-export.yml', 'tests/windows_host/txt/check_progress.py', 'tests/reader_wave3_c09/build.py', 'tests/reader_d26_accessibility/current_expectations.py', 'tests/reader_d26_accessibility/g13_current.py', 'docs/READER-WINDOWS-TXT-PROGRESS.md', 'tests/reader_d26_accessibility/audit_current.py', 'tests/reader_d26_accessibility/tools_current.py', 'tests/reader_d26_accessibility/account_status.py', 'docs/reader-total-progress/catalog.json', 'docs/reader-total-progress/README.md', 'docs/reader-total-progress/android-jump-d22.md', 'docs/reader-total-progress/android-annotations-d22.md', '.github/workflows/windows-wave3-txt-progress.yml'] for p in integration_changes),integration_changes
# Require exact source already exercised by the candidate runs.
for reference, files in [('9727ca1624ee59e561fd6aad7a22bb85a0fd2632',['src/formats.c','include/exr/formats.h']),
                         ('e09b25aa02b03297dc8a7f1f6eb32c092e11d410',['apps/reader/desktop/windows_records.inc','apps/reader/desktop/windows_records_owner.cpp'])]:
 assert not git('diff','--name-only',reference,sha,'--',*files)
with tempfile.TemporaryDirectory() as directory:
    subprocess.run(['git','worktree','add','--detach',directory,BASE],check=True)
    try:
        env=dict(os.environ,GITHUB_SHA=BASE)
        subprocess.run(['python3','tests/reader_same_source/guard.py','--source',BASE,'--report','build/original-admission.json'],cwd=directory,env=env,check=True)
    finally:subprocess.run(['git','worktree','remove','--force',directory],check=True)
report={'source_sha':sha,'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'base':BASE,'changed':changed,'original_tests_unchanged':True,'sdk_candidate_exact':True,'physical_device':False}
out=Path('build/android-composition-source.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
