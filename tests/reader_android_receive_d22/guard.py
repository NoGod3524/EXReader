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
assert all(p in ALLOWED or p.startswith('tests/reader_android_receive_d22/') or p.startswith('docs/d22-android-receive/') for p in changed),changed
with tempfile.TemporaryDirectory() as directory:
    subprocess.run(['git','worktree','add','--detach',directory,BASE],check=True)
    try:
        env=dict(os.environ,GITHUB_SHA=BASE)
        subprocess.run(['python3','tests/reader_same_source/guard.py','--source',BASE,'--report','build/original-admission.json'],cwd=directory,env=env,check=True)
    finally:subprocess.run(['git','worktree','remove','--force',directory],check=True)
report={'source_sha':sha,'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'base':BASE,'changed':changed,'original_tests_workflows_and_sdk_unchanged':True,'physical_device':False}
out=Path('build/android-composition-source.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
