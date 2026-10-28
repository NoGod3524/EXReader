"""Exact candidate admission; this does not grant native runtime acceptance."""
import os
import subprocess
BASE = 'c63c860d9a346fa9973689f14a5fd82908a190ce'
SDK = '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'
BRANCH = 'codex/reader-windows-341-candidate-admission'
ANDROID_BRANCH = 'codex/reader-android130-candidate-admission'
WINDOWS_ADMITTED = 'aec1a685c40a2afd86467840eeec208a470609e2'
ANDROID_ALLOWED = {
    '.github/workflows/reader-android-page-theme.yml',
    'tests/reader_hosts_341/guard_android.py',
    'tests/reader_hosts_341/aggregate_android.py',
    'tests/reader_hosts_341/aggregate_native.py',
    'tests/reader_windows_341/candidate.py',
    'tests/reader_hosts_341/android_candidate.py',
}
ALLOWED = {
    '.github/workflows/reader-windows-341-common.yml',
    'tests/reader_windows_341/candidate.py',
    'tests/reader_windows_341/guard.py',
    'tests/reader_windows_341/identity.py',
    'tests/reader_windows_341/verify.py',
    'tests/reader_hosts_341/aggregate_native.py',
}
def active():
    return os.environ.get('GITHUB_REF_NAME') in (BRANCH, ANDROID_BRANCH)
def admit(source):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    git = lambda *args: subprocess.check_output(['git',*args],text=True).strip()
    assert git('rev-parse','HEAD') == source == os.environ['GITHUB_SHA']
    subprocess.run(['git','merge-base','--is-ancestor',BASE,source],check=True)
    changed = set(git('diff','--name-only',BASE,source).splitlines())
    if os.environ.get('GITHUB_REF_NAME') == ANDROID_BRANCH:
        subprocess.run(['git','merge-base','--is-ancestor',WINDOWS_ADMITTED,source],check=True)
        delta=set(git('diff','--name-only',WINDOWS_ADMITTED,source).splitlines())
        assert delta == ANDROID_ALLOWED, sorted(delta)
        assert changed == ALLOWED | ANDROID_ALLOWED, sorted(changed)
        for path in ALLOWED - {'tests/reader_windows_341/candidate.py','tests/reader_hosts_341/aggregate_native.py'}:
            assert git('rev-parse',source+':'+path)==git('rev-parse',WINDOWS_ADMITTED+':'+path),path
    else:
        assert changed == ALLOWED, sorted(changed)
    subprocess.run(['git','diff','--exit-code',BASE,source,'--','apps','examples','extras','tools',
                    'src','include','cmake','CMakeLists.txt','bindings','tests/fixtures','licenses'],check=True)
    subprocess.run(['git','diff','--exit-code',SDK,source,'--','src','include','cmake','CMakeLists.txt',
                    'bindings','tests/fixtures'],check=True)
    workflow='.github/workflows/reader-windows-341-common.yml'
    old=subprocess.check_output(['git','show',BASE+':'+workflow],text=True)
    before='            build/ws-host/CMakeCache.txt\n'
    after=before+'            build/ws-revisions/CMakeCache.txt\n            build/baseline-revisions/CMakeCache.txt\n'
    assert old.count(before)==1
    from pathlib import Path
    assert Path(workflow).read_text(encoding='utf-8') == old.replace(before,after)
    return changed
