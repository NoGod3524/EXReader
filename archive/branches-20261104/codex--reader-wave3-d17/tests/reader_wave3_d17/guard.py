"""New exact D17 scope; original guards remain byte-for-byte unchanged."""
import hashlib,json,os,pathlib,subprocess
assert os.environ.get('GITHUB_ACTIONS')=='true'
SEED='d263ce5228838ac90c0a0dc13a5193d4a7739681';SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
def allowed(p):return p.startswith(('tests/reader_wave3_d17/','docs/reader-wave3-d17/')) or p in ('.github/workflows/reader-wave3-d17.yml','HANDOFF-RESULT-D17.md')
source=os.environ['GITHUB_SHA'];assert git('rev-parse','HEAD')==source
subprocess.run(['git','merge-base','--is-ancestor',SEED,source],check=True)
rows=[line.split('\t') for line in git('diff','--name-status',SEED,source).splitlines()]
assert rows and all(len(row)==2 and row[0] in ('A','M') and allowed(row[1]) for row in rows),rows
assert not git('diff',SDK,source,'--','include','src','bindings'),'frozen SDK source changed'
assert all(not allowed(p) for p in ['examples/apple/HostViews.swift','tests/apple_host/make_xcodeproj.rb','CMakeLists.txt','include/exr/base.h','apps/reader/store/001_catalog.sql'])
report=dict(source_sha=source,seed=SEED,sdk_source=SDK,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],changed_paths=rows,source_preflight_passed=True,complete_product=False)
out=pathlib.Path('build/d17');out.mkdir(parents=True,exist_ok=True);(out/'guard.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
