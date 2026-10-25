"""Actions-only explicit Debug probe and Release exclusion; immutable writer/policy identities."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile
assert os.environ.get('GITHUB_ACTIONS')=='true'
out=Path('build/android-record-interop/native');out.mkdir(parents=True,exist_ok=True)
ndk=Path(os.environ['ANDROID_HOME'])/'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin'
def symbols(file):return subprocess.check_output([str(ndk/'llvm-nm'),'-D','--defined-only',str(file)],text=True)
app=Path('examples/android/app');checks=[]
for variant in ('debug','release'):
 file=app/'build/outputs/apk'/variant/('app-'+variant+('-unsigned' if variant=='release' else '')+'.apk')
 with zipfile.ZipFile(file) as apk:
  native=out/(variant+'-product.so');native.write_bytes(apk.read('lib/x86_64/libexreader_product.so'));names=symbols(native)
  found=all('Java_org_exreader_host_RecordWireProbe_'+name in names for name in ('outbox','retained','ownerIdentity'));assert found==(variant=='debug')
  if variant=='release':assert not any(b'RecordWireProbe' in apk.read(item) for item in apk.namelist())
  checks.append({'variant':variant,'probe_exported':found,'apk_sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
paths=['examples/android/app/src/main/java/org/exreader/host/'+name+'.java' for name in ('ReadingParserPolicy','NativeReadingSdk','NativeCbz')]
policy={}
for path in paths:
 actual=subprocess.check_output(['git','hash-object',path],text=True).strip();expected=subprocess.check_output(['git','rev-parse','b1a7b7891cd394671842164a07a86c8e316dace3:'+path],text=True).strip();assert actual==expected;policy[path]=actual
result={**{key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]},'accepted':True,'checks':checks,'policy_blobs':policy,'default_probe_enabled':False,'new_production_java_api':False}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
