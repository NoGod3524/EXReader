"""Exact two-source composition admission; old tests and SDK remain unmodified."""
import hashlib,json,os,subprocess
from pathlib import Path
BASE='36fb8db3c088d665f87aac407f8e3739fa73e0f0'
WINDOWS='42445abd6dfeb312c8803d0a000a32f2a0459a15'
PRODUCT=('apps/reader/desktop/windows_accounts.inc','apps/reader/desktop/windows_accounts_ui.inc','apps/reader/desktop/windows_wave3.inc')
assert os.environ.get('GITHUB_ACTIONS')=='true'
def git(*a):return subprocess.check_output(['git',*a],text=True).strip()
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
subprocess.check_call(['git','merge-base','--is-ancestor',BASE,'HEAD'])
changed=git('diff','--name-only',BASE,'HEAD').splitlines()
assert all(p in PRODUCT or p=='.github/workflows/windows-android-book-relay.yml' or p.startswith(('tests/windows_android_book_relay/','docs/evidence/windows-android-book-relay/')) for p in changed),changed
assert not git('diff','--name-only',BASE,'HEAD','--','src','include','cmake','CMakeLists.txt','examples/android')
out=Path('build/windows-android-book');out.mkdir(parents=True,exist_ok=True)
(out/'source.json').write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],android_source=BASE,windows_source=WINDOWS,paths=changed,product_blobs={p:git('rev-parse','HEAD:'+p) for p in PRODUCT},old_tests_unchanged=True),indent=2))
