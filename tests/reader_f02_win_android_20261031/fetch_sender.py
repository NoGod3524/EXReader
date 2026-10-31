"""Fixed external sender input, source admission and shared Actions-only evidence helpers."""
import hashlib,importlib.util,io,json,os,stat,subprocess,sys,zipfile
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
 expected=dict(source=LOCK['sender']['source'],run=LOCK['sender']['run'],attempt=LOCK['sender']['attempt'])
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
 changed=set(git('diff','--name-only',LOCK['base'],head).splitlines());need(changed==set(LOCK['owned']),'exact11 paths')
 for path,blob in LOCK['frozen_sdk'].items():need(git('rev-parse','HEAD:'+path)==blob,'frozen '+path)
 for path,blob in LOCK['production_baseline_blobs'].items():need(git('rev-parse',LOCK['base']+':'+path)==blob,'baseline '+path)
 for path,blob in LOCK['production_result_blobs'].items():need(git('rev-parse','HEAD:'+path)==blob,'production '+path)
 for path in ('src','include','cmake','CMakeLists.txt','bindings'):
  need(git('rev-parse',LOCK['sdk']+':'+path)==git('rev-parse','HEAD:'+path),'fixed SDK '+path)
 for path in ('docs/reader-total-progress/catalog.json','examples/android/app/src/main/cpp','examples/android/app/build.gradle'):
  subprocess.run(['git','diff','--exit-code',LOCK['base'],head,'--',path],cwd=ROOT,check=True)
 runs=api('actions/runs?branch='+LOCK['branch']+'&per_page=100')['workflow_runs']
 owned=[r for r in runs if r.get('path')=='.github/workflows/dot-f02-win-android-transfer-20261031.yml']
 need(len(owned)==1 and owned[0]['head_sha']==head,'single approved run')
 save(OUT/'admission.json',dict(identity=identity(),base=LOCK['base'],sdk=LOCK['sdk'],changed=sorted(changed),approved_minutes=30,rounds=1,F02_accepted=False))
 print('F02_ANDROID_SCOPE exact11 SDK8357 frozen old assertions; one30-minute round',flush=True)
def external_sender():
 actions();s=LOCK['sender'];meta=api('actions/artifacts/'+str(s['sender_artifact']))
 need(meta['id']==s['sender_artifact'] and meta['name']==s['sender_name'] and not meta['expired'],'external artifact identity')
 need(meta['workflow_run']['id']==s['run'] and meta['workflow_run']['head_sha']==s['source'],'external source')
 need(meta['size_in_bytes']==s['bytes'] and meta['digest']=='sha256:'+s['sha256'],'external API digest')
 run=api('actions/runs/'+str(s['run']))
 need(run['head_sha']==s['source'] and run['run_attempt']==s['attempt'] and run['conclusion']=='success','external run')
 jobs=api('actions/runs/'+str(s['run'])+'/attempts/1/jobs?per_page=100')['jobs']
 for jid in (s['job'],124451949329):need(any(j['id']==jid and j['conclusion']=='success' for j in jobs),'original sender/auth job')
 raw=api('actions/artifacts/'+str(meta['id'])+'/zip',True)
 need(len(raw)==s['bytes'] and sha(raw)==s['sha256'],'external original ZIP')
 frozen=old_verifier();files=frozen.unpack(raw);sender=frozen.verify_sender(files)
 need(sender['original_bytes']==s['original_bytes'] and sender['original_sha256']==s['original_sha256'],'fixed Windows original')
 receipt=dict(artifact_id=meta['id'],artifact_name=meta['name'],bytes=len(raw),sha256=sha(raw),
  identity=dict(source=s['source'],run=s['run'],attempt=s['attempt']),consumer=identity())
 return raw,files,sender,receipt
def prepare():
 guard();raw,files,sender,receipt=external_sender()
 INPUT.mkdir(parents=True,exist_ok=False);(INPUT/'sender.zip').write_bytes(raw)
 for name,data in files.items():
  p=INPUT/'sender'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 save(INPUT/'sender-receipt.json',receipt);save(INPUT/'admission.json',json.loads((OUT/'admission.json').read_text()))
 print('F02_ANDROID_INPUT '+json.dumps(dict(identity=identity(),sender=receipt,book_key=sender['book_key'],bytes=sender['original_bytes'])),flush=True)
if __name__=='__main__':prepare()
