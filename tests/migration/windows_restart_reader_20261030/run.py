"""Actions-only fresh-process recovery classification; never admission."""
import argparse,concurrent.futures,hashlib,json,os,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--work',required=True);a=p.parse_args()
exe=str(pathlib.Path(a.probe).resolve());work=pathlib.Path(a.work).resolve();work.mkdir(parents=True,exist_ok=False);results=[]
def start(command,ready):
 proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
  f=pool.submit(proc.stdout.readline)
  try: line=f.result(timeout=30).strip()
  except BaseException:
   proc.kill();proc.wait(timeout=10);raise
  if line!=ready:
   proc.kill();out,err=proc.communicate(timeout=10);raise AssertionError((command,line,out,err))
 return proc
def kill(proc):
 proc.kill();proc.communicate(timeout=10)
def run(root,mode='normal',verb='read'):
 r=subprocess.run([exe,verb,str(root),mode],capture_output=True,text=True,timeout=30)
 assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
 data=json.loads(r.stdout)
 if verb=='read':
  assert data['source']==os.environ['GITHUB_SHA'] and data['sdk_open_attempts']==0
  assert not data['commit_acknowledged'] and not data['recovery_admission']
 return data
cases=[('before',1),('record',2),('published',2),('after',3),('reader-death',3),('partial',0),('missing-slot',0),('extra-slot',0),('previous-id',0),('payload',0),('both-targets',4),('missing-target',4),('generation',0),('root',0),('session',0)]
for name,want in cases:
 parent=work/name;parent.mkdir();root=parent/'private'
 fixture=name if name in ('before','record','published','after') else 'after'
 proc=start([exe,'fixture',str(root),fixture],'ready-'+fixture)
 busy=run(root);assert not busy['opened'] and busy['class']==0,busy
 kill(proc)
 assert run(root,verb='shared')['stale']
 if name=='partial':(root/'bridge-slot-00.rec').write_bytes(b'{"partial":')
 if name=='missing-slot':(root/'bridge-slot-01.rec').unlink()
 if name=='extra-slot':(root/'bridge-slot-07.rec').write_bytes(bytes(4096))
 if name=='previous-id':
  q=root/'bridge-slot-01.rec';r=json.loads(q.read_bytes());r.pop('seal')
  r['previous_id']=r['previous_id'][:-1]+('0' if r['previous_id'][-1]!='0' else '1')
  raw=json.dumps(r,separators=(',',':')).encode()+b'\n';r['seal']=hashlib.sha256(raw).hexdigest()
  q.write_bytes(json.dumps(r,separators=(',',':')).encode()+b'\n')
 if name=='payload':(parent/'published.bin').write_bytes(b'wrong')
 if name=='both-targets':(root/'target.bin').write_bytes((parent/'published.bin').read_bytes())
 if name=='missing-target':(parent/'published.bin').unlink()
 if name=='reader-death':
  reader=start([exe,'read',str(root),'hold'],'ready-reader')
  assert not run(root)['opened']
  kill(reader)
 data=run(root,name if name in ('generation','root','session') else 'normal')
 assert data['opened'] and data['class']==want,(name,data)
 if want in (1,2,3):
  assert data['checked'] and data['pending']==1 and data['generation']==0
  assert data['write_denied'] and data['rename_denied']
 else: assert not data['checked']
 assert run(root,verb='shared')['stale'],name
 data.update(case=name,original_process_terminated=True,shared_still_stale=True)
 data['files']={str(q.relative_to(parent)):{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in parent.rglob('*') if q.is_file()}
 results.append(data)
(work/'receipt.json').write_text(json.dumps(dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],passed=True,checks=len(results),results=results,classification_only=True,commit_acknowledged=False,recovery_admission=False,full_p0_acceptance=False,physical_power_loss=False),indent=2)+'\n')
