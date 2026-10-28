"""Strict own-package admission; no original suite or frozen SDK changes."""
import os,json,subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
BASE='36fb8db3c088d665f87aac407f8e3739fa73e0f0'
WINDOWS='42445abd6dfeb312c8803d0a000a32f2a0459a15'
PRODUCT=['apps/reader/desktop/windows_accounts.inc','apps/reader/desktop/windows_accounts_ui.inc','apps/reader/desktop/windows_wave3.inc']
git=lambda *args:subprocess.check_output(['git',*args],text=True).strip()
source=os.environ['GITHUB_SHA'];assert git('rev-parse','HEAD')==source
subprocess.run(['git','merge-base','--is-ancestor',BASE,source],check=True)
for path in git('diff','--name-only',BASE,source).splitlines():
    assert path in PRODUCT or path=='.github/workflows/windows-android-record-relay.yml' or path.startswith(('tests/windows_android_record_relay/','docs/windows-android-record-relay/')),path
for path in PRODUCT:
    expected='ba125b0df2937c1124c075e3423f0ced9c43f926' if path.endswith('/windows_wave3.inc') else git('rev-parse',WINDOWS+':'+path)
    assert git('rev-parse',source+':'+path)==expected,path
subprocess.run(['git','diff','--exit-code',BASE,source,'--','src','include','cmake','CMakeLists.txt','bindings','extras'],check=True)
out=Path('build/records-source.json');out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(dict(source_sha=source,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],android_source=BASE,windows_source=WINDOWS,product_paths=PRODUCT,frozen_sdk_unchanged=True),indent=2))
print(out.read_text())
