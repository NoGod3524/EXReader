"""Exact candidate admission; this does not grant native runtime acceptance."""
import os
import subprocess
BASE = 'c63c860d9a346fa9973689f14a5fd82908a190ce'
SDK = '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'
BRANCH = 'codex/windows-j10-triage'
ALLOWED = {
    '.github/workflows/reader-windows-341-common.yml',
    'tests/reader_windows_341/candidate.py',
    'tests/reader_windows_341/guard.py',
    'tests/reader_windows_341/identity.py',
    'tests/reader_windows_341/verify.py',
    'tests/reader_hosts_341/aggregate_native.py',
}
def active():
    return os.environ.get('GITHUB_REF_NAME') == BRANCH
def admit(source):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    git = lambda *args: subprocess.check_output(['git',*args],text=True).strip()
    assert git('rev-parse','HEAD') == source == os.environ['GITHUB_SHA']
    subprocess.run(['git','merge-base','--is-ancestor',BASE,source],check=True)
    changed = set(git('diff','--name-only',BASE,source).splitlines())
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
    original = '          python3 tests/reader_bulk_organization/check_bulk.py --probe'
    adapted = '          python3 tests/sdk_bulk_v3/verify_parity.py\n          python3 tests/sdk_bulk_v3/check_bulk_v3.py --probe'
    assert old.count(original) == 1
    assert Path(workflow).read_text(encoding='utf-8') == old.replace(before,after).replace(original,adapted)
    return changed
