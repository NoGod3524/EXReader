import os,subprocess,json,hashlib
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
base='2743f32a4eccd5823657da19cb4f77f2411424af'
assert subprocess.check_output(['git','rev-parse','HEAD']).decode().strip()==os.environ['GITHUB_SHA']
changed=subprocess.check_output(['git','diff','--name-only',base,'HEAD']).decode().splitlines()
prefixes=('extras/migration/windows_recovery_engine_20261030/','tests/migration/windows_recovery_engine_20261030/')
allowed={'extras/migration/CMakeLists.txt','.github/workflows/migration-windows-engine-20261030.yml','docs/MIGRATION-WINDOWS-ENGINE-20261030.md'}
assert all(p.startswith(prefixes) or p in allowed for p in changed),changed
old=subprocess.check_output(['git','show',base+':extras/migration/CMakeLists.txt']).decode()
now=Path('extras/migration/CMakeLists.txt').read_text()
assert now.startswith(old)
assert now[len(old):]=='\noption(EXR_MIGRATION_WINDOWS_ENGINE_CANDIDATE "Build private Windows observer; no migration admission" OFF)\nif(EXR_MIGRATION_WINDOWS_ENGINE_CANDIDATE)\n  add_subdirectory(windows_recovery_engine_20261030)\nendif()\n'
Path('build/engine-evidence/admission.json').write_text(json.dumps(dict(source=os.environ['GITHUB_SHA'],base=base,changed=changed,files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in changed},full_p0_acceptance=False),indent=2))
