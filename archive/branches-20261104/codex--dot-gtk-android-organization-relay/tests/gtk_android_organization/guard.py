"""Actions source-only gate; immutable SDK and original assertions."""
import hashlib,json,os,subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
base='36fb8db3c088d665f87aac407f8e3739fa73e0f0'
def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
subprocess.run(['git','merge-base','--is-ancestor',base,'HEAD'],check=True)
subprocess.run(['git','diff','--exit-code',base,'HEAD','--','src','include','cmake','CMakeLists.txt','bindings','apps','examples','extras','tools'],check=True)
changed=git('diff','--name-only',base,'HEAD').splitlines()
assert all(p.startswith('tests/gtk_android_organization/') or p=='.github/workflows/gtk-android-organization-relay.yml' for p in changed),changed
Path('build').mkdir(exist_ok=True);Path('build/organization-source.json').write_text(json.dumps({'source_sha':os.environ['GITHUB_SHA'],'base_sha':base,'changed_files':changed},indent=2))
