import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'build/c02-webdav-joint'
M=json.loads((HERE/'manifest.json').read_text())
def actions():
 assert os.environ.get('GITHUB_ACTIONS')=='true','Actions only'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2)+'\n')
def run(label,args,cwd=ROOT,timeout=1800,expected=(0,)):
 actions();OUT.mkdir(parents=True,exist_ok=True)
 p=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 (OUT/(label+'.log')).write_text(p.stdout+'\n'+p.stderr)
 print('JOINT-RUN '+label+' exit='+str(p.returncode)+'\n'+p.stdout[-1200:]+p.stderr[-1200:],flush=True)
 if expected is not None:assert p.returncode in expected,(label,p.returncode)
 return p
def cmake(name,source,args=(),prefix=None,targets=(),install=True):
 b=OUT/name
 values=['cmake','-S',ROOT/source,'-B',b,'-G',('Unix Makefiles' if name in ('c02-sdk','c02-gtk') else 'Ninja'),'-DCMAKE_BUILD_TYPE=Release',*args]
 if prefix:values+=['-DCMAKE_INSTALL_PREFIX='+str(prefix)]
 run(name+'-configure',values)
 run(name+'-build',['cmake','--build',b,'--parallel','4',*(['--target',*targets] if targets else [])])
 if install:run(name+'-install',['cmake','--install',b])
 return b
def revision(ref):
 p=subprocess.run(['git','cat-file','-e',ref+'^{commit}'],cwd=ROOT,capture_output=True)
 if p.returncode:run('fetch-'+ref[:8],['git','fetch','--no-tags','origin',ref])
def overlay():
 actions();rows=[]
 for row in M['runtime_test_blobs']:
  ref,path=row['source'],row['path'];revision(ref)
  assert path.startswith('tests/migration/') and '..' not in Path(path).parts
  raw=subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)
  assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==row['blob']
  p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  rows.append(dict(path=path,source=ref,blob=row['blob'],sha256=hashlib.sha256(raw).hexdigest()))
 save(OUT/'tester-overlay.json',rows)
def sdk():
 revision(M['sdk']);source=OUT/'sdk-source'
 run('sdk-worktree',['git','worktree','add','--detach',source,M['sdk']])
 run('sdk-configure',['cmake','--preset','reading-library'],source)
 run('sdk-build',['cmake','--build','--preset','reading-library','--parallel','4'],source)
 run('sdk-install',['cmake','--install','build/reading-library'],source)
 return source/'build/reading-library/stage'
def c02_deps(sdk,prefix,owner=False):
 sdk=Path(sdk);prefix=Path(prefix)
 wh=(OUT/'abi2-prefix').resolve();wh3=(OUT/'abi3-prefix').resolve();native=(OUT/'native-prefix').resolve()
 cmake('c02-abi2','extras/migration/windows_coordinator_hardening_20261030',prefix=wh)
 cmake('c02-abi3','extras/migration/windows_coordinator_cas_20261030',['-DWH_PREFIX='+str(wh)],wh3)
 cmake('c02-native','extras/migration/posix_c02_admission_20261031',['-DWH_PREFIX='+str(wh)],native)
 cmake('c02-sdk','extras/migration/posix_c02_sdk_admission_20261031',[
  '-DWH_PREFIX='+str(wh),'-DPC02_PREFIX='+str(native),'-DEXR_SDK='+str(sdk)],prefix)
 if owner:
  cmake('c02-owner','extras/migration/posix_c02_migration_20261031',[
   '-DEXR_SDK='+str(sdk),'-DPC02_SDK_PREFIX='+str(prefix),'-DWH3_PREFIX='+str(wh3),'-DWH_PREFIX='+str(wh),
   '-DPC02_BUILD_SOURCE='+os.environ['GITHUB_SHA'],'-DPC02_BUILD_RUN='+os.environ['GITHUB_RUN_ID'],
   '-DPC02_BUILD_ATTEMPT='+os.environ['GITHUB_RUN_ATTEMPT'],'-DPC02_MIGRATION_ACTIONS_CONTROLS=ON'],prefix)
 return prefix

def native_decoder():
 actions()
 old=ROOT/'tests/migration/c02_completion_audit_20261031/posix_native.py'
 text=old.read_text()
 a='snapshot_required = head_snapshot_required(source)'
 b='snapshot_required = head_snapshot_required('+repr(M['c02'])+')'
 assert text.count(a)==1
 text=text.replace(a,b)
 sys.path.insert(0,str(old.parent))
 ns=dict(__file__=str(old),__name__='_joint_native_decoder')
 exec(compile(text,str(OUT/'derived-native-decoder.py'),'exec'),ns)
 save(OUT/'native-protocol-source-adaptation.json',dict(product_source=os.environ['GITHUB_SHA'],
   test_source=M['c02'],audit_source=M['c02_audit'],original_sha256=sha(old),
   derived_sha256=hashlib.sha256(text.encode()).hexdigest(),assertions_removed=False,
   only_change='feature-contract source lookup uses the pinned test source; receipt/product source remains current H'))
 (OUT/'derived-native-decoder.py').write_text(text)
 return ns
def native_audit(evidence,tool,output):
 ns=native_decoder();previous=sys.argv
 try:
  sys.argv=[str(ROOT/'tests/migration/c02_completion_audit_20261031/posix_native.py'),
   '--evidence',str(evidence),'--tool',str(tool),'--output',str(output)]
  ns['main']()
 finally:sys.argv=previous
