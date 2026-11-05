"""Actions-only source scope guard for the independent F3 host correction."""
import json, os, subprocess, sys
from pathlib import Path
BASE='e330a415b733db18dea5aa6010d13cf3063587fd'
ROOT=Path(__file__).resolve().parents[2]
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT).decode().strip()
assert os.environ.get('GITHUB_ACTIONS')=='true'
assert os.environ['GITHUB_REF_NAME']=='codex/dot-windows-f3-focus-fix'
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
assert not git('diff','HEAD','--name-only')
changed=git('diff','--name-only',BASE,'HEAD').splitlines()
for p in changed:
    assert p=='examples/reader.c' or p=='.github/workflows/windows-f3-focus.yml' or p.startswith(('tests/windows_f3_focus/','docs/windows-f3-focus/')), p
assert not git('diff',BASE,'HEAD','--','src','include','cmake','CMakeLists.txt','tests/reader_windows_preferences')
out=ROOT/'build/f3-focus-source';out.mkdir(parents=True,exist_ok=True)
proof=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],base=BASE,changed=changed,sdk_tree=git('rev-parse','HEAD:src'),original_f3_judge=git('rev-parse','HEAD:tests/reader_windows_preferences/check_ui.py'))
(out/'source.json').write_text(json.dumps(proof,indent=2))
print(json.dumps(proof),flush=True)
subprocess.run([sys.executable,str(ROOT/'tests/reader_native_owner_repairs/display.py')],check=True)