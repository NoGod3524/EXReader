"""Same-run Windows sender, fixed-source admission and Actions-only evidence helpers."""
import hashlib,importlib.util,io,json,os,re,stat,struct,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'build/f02-android'
INPUT=ROOT/'build/f02-android-input'
LOCK=json.loads((HERE/'source_lock.json').read_text())
def need(value,reason):
 if not value:raise AssertionError(reason)
def actions():need(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
def identity():return dict(source=os.environ['GITHUB_SHA'],run=int(os.environ['GITHUB_RUN_ID']),attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))
def sha(data):return hashlib.sha256(data).hexdigest()
def file_sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(65536),b''):h.update(b)
 return h.hexdigest()
def save(path,value):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def api(path,binary=False):
 raw=subprocess.check_output(['gh','api','repos/NoGod3524/EXReader/'+path],timeout=180)
 return raw if binary else json.loads(raw)
def old_verifier():
 old=ROOT/'tests/reader_f02_win_gtk_20261031'
 sys.path.insert(0,str(old))
 spec=importlib.util.spec_from_file_location('frozen_f02_auth',old/'authenticate.py')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 expected=identity()
 mod.identity=lambda:dict(expected)
 return mod
def unpack_current(raw):
 need(0<len(raw)<=128*1024**2,'receiver ZIP bytes')
 result={};names=set();total=0
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  need(0<len(z.infolist())<=10000,'receiver ZIP entries')
  for row in z.infolist():
   n=row.filename;p=PurePosixPath(n)
   need(n and not p.is_absolute() and '..' not in p.parts and '\\' not in n and ':' not in n and '\0' not in n,'receiver ZIP path')
   need(n.rstrip('/')==str(p) and n.casefold() not in names,'receiver ZIP duplicate')
   names.add(n.casefold())
   need(stat.S_IFMT(row.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not row.flag_bits&1,'receiver ZIP type')
   total+=row.file_size;need(row.file_size<=128*1024**2 and total<=512*1024**2,'receiver ZIP expansion')
   if not row.is_dir():result[n]=z.read(row)
 return result
def guard():
 actions();need(os.environ['GITHUB_RUN_ATTEMPT']=='1','attempt1')
 need(os.environ['GITHUB_EVENT_NAME']=='push' and os.environ['GITHUB_REF']=='refs/heads/'+LOCK['branch'],'branch push')
 def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
 head=git('rev-parse','HEAD');need(head==identity()['source'],'source')
 if subprocess.run(['git','cat-file','-e',LOCK['sdk']+'^{commit}'],cwd=ROOT,capture_output=True).returncode:
  subprocess.run(['git','fetch','--no-tags','origin',LOCK['sdk']],cwd=ROOT,check=True)
 subprocess.run(['git','merge-base','--is-ancestor',LOCK['base'],head],cwd=ROOT,check=True)
 changed=set(git('diff','--name-only',LOCK['base'],head).splitlines());need(changed==set(LOCK['owned']),'exact six same-source paths')
 for path,blob in LOCK['frozen_sdk'].items():need(git('rev-parse','HEAD:'+path)==blob,'frozen '+path)
 for path,blob in LOCK['production_baseline_blobs'].items():need(git('rev-parse',LOCK['original_base']+':'+path)==blob,'baseline '+path)
 for path,blob in LOCK['production_result_blobs'].items():need(git('rev-parse','HEAD:'+path)==blob,'production '+path)
 for path in ('src','include','cmake','CMakeLists.txt','bindings'):
  need(git('rev-parse',LOCK['sdk']+':'+path)==git('rev-parse','HEAD:'+path),'fixed SDK '+path)
 for path in ('docs/reader-total-progress/catalog.json','examples/android/app/src/main/cpp','examples/android/app/build.gradle'):
  subprocess.run(['git','diff','--exit-code',LOCK['base'],head,'--',path],cwd=ROOT,check=True)
 runs=api('actions/runs?branch='+LOCK['branch']+'&per_page=100')['workflow_runs']
 owned=[r for r in runs if r.get('path')=='.github/workflows/dot-f02-win-android-transfer-20261031.yml']
 need(len(owned)==1 and owned[0]['head_sha']==head,'single approved run')
 save(OUT/'admission.json',dict(identity=identity(),base=LOCK['base'],sdk=LOCK['sdk'],changed=sorted(changed),approved_minutes=115,rounds=1,F02_accepted=False))
 print('F02_ANDROID_SCOPE exact6 same-source SDK8357 frozen product/Java/Windows recipe; one115-minute round',flush=True)
def contract_fingerprint(value):
 return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
def verify_sdk_contract(manifest,role):
 need(manifest['identity']==identity() and manifest['role']==role,'SDK proof identity')
 need(manifest['contract']==LOCK['sdk_contract'] and manifest['fingerprint']==contract_fingerprint(LOCK['sdk_contract']),'SDK fingerprint')
def emit_sdk_proof(role):
 actions();need(role in ('windows','android'),'SDK proof role')
 root=ROOT/'build/windows-sdk342/sdk' if role=='windows' else ROOT/'build/wave3/sdk-stage'
 out=ROOT/'build/f02-windows-sdk' if role=='windows' else OUT/'android-sdk-proof'
 need(root.is_dir() and not out.exists(),'fresh installed SDK proof')
 out.mkdir(parents=True)
 files={}
 def capture(path,name):
  need(path.is_file() and path.stat().st_size<=128*1024**2,'installed SDK file')
  data=path.read_bytes();target=out/'files'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
  files[name]=dict(bytes=len(data),sha256=sha(data))
 for path in sorted(root.rglob('*')):
  if path.is_file() and (path.suffix in ('.h','.hpp','.cmake','.lib','.a') or '.so' in path.name):
   capture(path,'sdk/'+path.relative_to(root).as_posix())
 if role=='windows':
  for name,path in {
   'sdk-build/CMakeCache.txt':ROOT/'build/windows-sdk342/sdk-build/CMakeCache.txt',
   'host/CMakeCache.txt':ROOT/'build/windows-sdk342/host/CMakeCache.txt',
   'host/windows-host.map':ROOT/'build/windows-sdk342/host/windows-host.map',
   'host/EXReader.exe':ROOT/'build/windows-sdk342/package/EXReader/EXReader.exe',
   'host/sdk-inspector.exe':ROOT/'build/f02-inspector/received-sdk-inspect.exe',
   'package/build.json':ROOT/'build/windows-sdk342/package/build.json',
   'package/report.json':ROOT/'build/windows-sdk342/package/report.json'}.items():capture(path,name)
 else:
  for role_name in ('host','test'):
   apk=OUT/'artifacts'/(role_name+'.apk')
   entries=unpack_current(apk.read_bytes())
   for name,data in entries.items():
    if name.startswith('lib/x86_64/') and name.endswith('.so'):
     p=out/'files'/'apk'/role_name/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
     files['apk/'+role_name+'/'+name]=dict(bytes=len(data),sha256=sha(data))
  caches=list((ROOT/'examples/android/app/.cxx').rglob('CMakeCache.txt'))
  need(bool(caches),'Android installed host caches')
  for n,path in enumerate(sorted(caches)):capture(path,'host/cache-'+str(n)+'.txt')
 def git_object(ref,path):return subprocess.check_output(['git','rev-parse',ref+':'+path],cwd=ROOT,text=True).strip()
 actual=dict(LOCK['sdk_contract'],sdk_trees={p:git_object(LOCK['sdk'],p) for p in LOCK['sdk_contract']['sdk_trees']},
  shared_trees={p:git_object('HEAD',p) for p in LOCK['sdk_contract']['shared_trees']})
 manifest=dict(identity=identity(),role=role,contract=actual,fingerprint=contract_fingerprint(actual),
  linkage='static-reading' if role=='windows' else 'shared-jni',files=files)
 verify_sdk_contract(manifest,role);save(out/'manifest.json',manifest)
 print('F02_SDK_PROOF '+json.dumps(dict(identity=identity(),role=role,fingerprint=manifest['fingerprint'],files=len(files),linkage=manifest['linkage'])),flush=True)
def elf_load_fingerprint(data):
 need(data[:6]==b'\x7fELF\x02\x01' and int.from_bytes(data[18:20],'little')==62,'Android x86_64 provider')
 phoff=struct.unpack_from('<Q',data,32)[0];entsize,count=struct.unpack_from('<HH',data,54)
 need(entsize==56 and 0<count<=100 and phoff+entsize*count<=len(data),'ELF program headers')
 chunks=[]
 for index in range(count):
  kind,flags,offset,vaddr,_,size,memsize,align=struct.unpack_from('<IIQQQQQQ',data,phoff+index*entsize)
  if kind!=1:continue
  need(offset+size<=len(data) and size<=memsize,'ELF load bounds')
  chunk=bytearray(data[offset:offset+size])
  # Gradle may strip non-loaded symbols; section-table header fields are not the loaded SDK code.
  for start,length in ((40,8),(58,6)):
   for pos in range(start,start+length):
    if offset<=pos<offset+size:chunk[pos-offset]=0
  chunks.append(struct.pack('<IQQQQ',flags,vaddr,size,memsize,align)+bytes(chunk))
 need(bool(chunks),'ELF load segments')
 return sha(b''.join(chunks))
def verify_sdk_proof(files,role,sender=None,receiver=None):
 manifest=json.loads(files['manifest.json']);verify_sdk_contract(manifest,role)
 declared=manifest['files']
 need(declared and set(files)=={'manifest.json'}|{'files/'+p for p in declared},'SDK proof inventory')
 for name,item in declared.items():
  data=files['files/'+name]
  need(len(data)==item['bytes'] and sha(data)==item['sha256'],'installed SDK bytes')
 header=files['files/sdk/include/exr/base.h']
 need(re.search(rb'#define\s+EXR_VERSION\s+"3\.42\.0"',header) and re.search(rb'#define\s+EXR_ABI_VERSION\s+1u?\b',header),'installed SDK version ABI')
 configs=[p for p in declared if p.startswith('sdk/') and p.endswith('.cmake')]
 need(bool(configs),'installed SDK configs')
 if role=='windows':
  need(manifest['linkage']=='static-reading','Windows static linkage')
  archives=[p for p in declared if p.startswith('sdk/') and p.endswith('.lib')]
  need(bool(archives) and all(files['files/'+p].startswith(b'!<arch>\n') for p in archives),'installed static archives')
  cache=files['files/sdk-build/CMakeCache.txt'];link_map=files['files/host/windows-host.map'].lower()
  need(b'EXR_BUILD_SHARED_COMPAT:BOOL=OFF' in cache and b'EXR_BUILD_JNI:BOOL=OFF' in cache and b'EXR_ENABLE_LIBRARY:BOOL=ON' in cache,'static SDK build config')
  need(b'exr_webdav_download_observed' in link_map and any(Path(p).name.lower().encode() in link_map for p in archives),'static SDK link map')
  build=json.loads(files['files/package/build.json']);test=json.loads(files['files/package/report.json'])
  need(build['source_sha']==identity()['source'] and build['sdk_version']=='3.42.0' and build['linkage']=='static-reading'
       and test['passed'] is True and test['checks']>=26 and test['engine_version']=='3.42.0','Windows package SDK selftest')
  if sender is not None:
   need(files['files/host/EXReader.exe']==sender['host.exe'] and files['files/host/sdk-inspector.exe']==sender['sdk-inspector.exe'],'actual Windows installed programs')
 else:
  need(manifest['linkage']=='shared-jni','Android shared linkage')
  libraries=[p for p in declared if p.startswith('sdk/') and Path(p).name=='libexreader.so']
  need(len(libraries)==1,'installed Android provider')
  provider=files['files/'+libraries[0]]
  need(provider.startswith(b'\x7fELF') and int.from_bytes(provider[18:20],'little')==62,'Android x86_64 provider')
  apk_provider=files['files/apk/host/lib/x86_64/libexreader.so']
  need(elf_load_fingerprint(apk_provider)==elf_load_fingerprint(provider),'installed provider equals APK load image')
  need('apk/host/lib/x86_64/libexreader_host.so' in declared,'actual Android host JNI')
  caches=[files['files/'+p] for p in declared if p.startswith('host/cache-')]
  need(caches and all(b'EXR_HOST_SDK_VERSION:STRING=3.42.0' in p for p in caches),'Android actual host SDK config')
  if receiver is not None:
   for name in ('host','test'):
    apk=unpack_current(receiver['artifacts/'+name+'.apk'])
    for p in declared:
     if p.startswith('apk/'+name+'/'):
      need(files['files/'+p]==apk[p[len('apk/'+name+'/'):]],'runtime APK JNI bytes')
 result=dict(passed=True,role=role,fingerprint=manifest['fingerprint'],linkage=manifest['linkage'],files=len(declared))
 if role=='android':result.update(installed_provider_sha256=sha(provider),apk_provider_sha256=sha(apk_provider),load_image_sha256=elf_load_fingerprint(provider),provider_byte_equal=provider==apk_provider)
 return result
def producer_run_and_job():
 actions();run=api('actions/runs/'+str(identity()['run']))
 need(run['head_sha']==identity()['source'] and run['run_attempt']==identity()['attempt']==1
      and run['event']=='push' and run['head_branch']==LOCK['branch'],'same-source run identity')
 jobs=api('actions/runs/'+str(identity()['run'])+'/attempts/'+str(identity()['attempt'])+'/jobs?per_page=100')['jobs']
 found=[j for j in jobs if j['name']==LOCK['sender']['job']]
 need(len(found)==1 and found[0]['conclusion']=='success','same-source Windows job')
 return run,found[0]
def verify_producer_meta(meta,aid,prefix,digest,job):
 need(meta['id']==aid and meta['expired'] is False,'same-source artifact identity')
 need(meta['name']==prefix+'-'+str(identity()['run'])+'-'+str(identity()['attempt']),'same-source artifact attempt')
 need(meta['workflow_run']['id']==identity()['run'] and meta['workflow_run']['head_sha']==identity()['source'],'same-source artifact source')
 need(0<meta['size_in_bytes']<=128*1024**2 and re.fullmatch(r'[0-9a-f]{64}',digest)
      and meta['digest']=='sha256:'+digest,'same-source artifact digest')
 need(job['started_at']<=meta['created_at']<=job['completed_at'],'same-source producer job window')
def current_sender(directory=None):
 _,job=producer_run_and_job();records=[];bodies=[]
 for prefix,env_name in ((LOCK['sender']['artifact_prefix'],'F02_WINDOWS'),(LOCK['sender']['sdk_artifact_prefix'],'F02_WINDOWS_SDK')):
  aid=int(os.environ[env_name+'_ARTIFACT_ID']);digest=os.environ[env_name+'_ARTIFACT_DIGEST'].removeprefix('sha256:')
  meta=api('actions/artifacts/'+str(aid));verify_producer_meta(meta,aid,prefix,digest,job)
  raw=api('actions/artifacts/'+str(aid)+'/zip',True)
  need(len(raw)==meta['size_in_bytes'] and sha(raw)==digest,'same-source original ZIP')
  records.append(dict(artifact_id=aid,artifact_name=meta['name'],bytes=len(raw),sha256=sha(raw),identity=identity(),producer_job=job['id']))
  bodies.append(raw)
 frozen=old_verifier();files=frozen.unpack(bodies[0]);sender=frozen.verify_sender(files)
 need(sender['original_bytes']==LOCK['sender']['original_bytes'] and sender['original_sha256']==LOCK['sender']['original_sha256'],'fixed Windows original')
 sdk_files=unpack_current(bodies[1]);sdk=verify_sdk_proof(sdk_files,'windows',sender=files)
 receipt=dict(records[0],consumer=identity(),sdk_artifact=records[1],sdk_fingerprint=sdk['fingerprint'])
 if directory is not None:
  (directory/'windows.zip').write_bytes(bodies[0]);(directory/'windows-sdk.zip').write_bytes(bodies[1])
 proof=dict(job=dict(id=job['id'],name=job['name'],started_at=job['started_at'],completed_at=job['completed_at']),
  sdk=sdk,metadata=[api('actions/artifacts/'+str(v['artifact_id'])) for v in records])
 return bodies[0],files,sender,receipt,proof,bodies[1]
def prepare():
 guard();raw,files,sender,receipt,proof,sdk_raw=current_sender()
 INPUT.mkdir(parents=True,exist_ok=False);(INPUT/'sender.zip').write_bytes(raw);(INPUT/'windows-sdk.zip').write_bytes(sdk_raw)
 for name,data in files.items():
  p=INPUT/'sender'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 save(INPUT/'sender-receipt.json',receipt);save(INPUT/'producer-proof.json',proof)
 save(INPUT/'admission.json',json.loads((OUT/'admission.json').read_text()))
 print('F02_ANDROID_INPUT '+json.dumps(dict(identity=identity(),sender=receipt,book_key=sender['book_key'],bytes=sender['original_bytes'])),flush=True)
if __name__=='__main__':
 mode=sys.argv[1] if len(sys.argv)>1 else 'prepare'
 if mode=='guard':guard()
 elif mode in ('windows-proof','android-proof'):emit_sdk_proof(mode.split('-')[0])
 else:need(mode=='prepare','input mode');prepare()
