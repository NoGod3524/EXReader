import hashlib,json,os,subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
root=Path.cwd()
worker=root/'engine-stage/bin/exreader-migration-windows-observer.exe'
consumer=root/'build/engine-check/Release/windows-engine-check.exe'
evidence=root/'build/engine-evidence'
private=evidence/'private'
digest=hashlib.sha256(worker.read_bytes()).hexdigest()
p=subprocess.run([str(consumer),str(private),str(worker),digest,os.environ['GITHUB_SHA'],str(root/'build/engine-check/Release/windows-engine-stall.exe')],capture_output=True,text=True,timeout=120)
(evidence/'stdout.txt').write_text(p.stdout);(evidence/'stderr.txt').write_text(p.stderr)
assert p.returncode==0,(p.returncode,p.stdout,p.stderr)
r=json.loads(p.stdout);assert r['passed'] and r['checks']==28 and r['failed']==0,r
assert r['migration_admission'] is False and r['full_p0_acceptance'] is False
assert {x.name for x in private.iterdir()}=={'target.fixture','observed.bin','deadline.bin'}
assert (private/'target.fixture').read_bytes()==b'retained-byte-observation'
built=root/'build/migration/windows_recovery_engine_20261030/Release/exreader-migration-windows-observer.exe'
assert built.read_bytes()==worker.read_bytes()
lib=root/'engine-stage/lib/exreader-migration-windows-engine.lib'
assert lib.read_bytes()==(root/'build/migration/windows_recovery_engine_20261030/Release/exreader-migration-windows-engine.lib').read_bytes()
(evidence/'receipt.json').write_text(json.dumps(dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],consumer=r,worker_sha256=digest,library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),files={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in private.iterdir()},full_p0_acceptance=False),indent=2))
