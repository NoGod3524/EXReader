"""Verify every current-job target/runner uses this runner's same debug signer."""
import hashlib,json,os,re,subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
out=Path('build/current-android/apks')
identity={k:os.environ[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}
rows=[]
for name in ('host.apk','reading.apk','sync.apk','owner.apk','history-compat.apk'):
 path=out/name
 text=subprocess.check_output([str(Path(os.environ['ANDROID_HOME'])/'build-tools/35.0.0/apksigner'),'verify','--print-certs',str(path)],text=True)
 (out/(name+'.cert.txt')).write_text(text)
 signer,=re.findall(r'Signer #1 certificate SHA-256 digest: ([0-9a-f]+)',text)
 rows.append(dict(name=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),signer_sha256=signer))
assert len({row['signer_sha256'] for row in rows})==1
report=dict(**identity,apks=rows,debug_signer_only=True,production_signature=False)
(out/'identity.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
