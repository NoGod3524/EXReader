"""Actions-only live bridge evidence. No restart reader or admission is provided."""
import argparse,concurrent.futures,hashlib,json,os,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--work',required=True);a=p.parse_args()
work=pathlib.Path(a.work).resolve();work.mkdir(parents=True,exist_ok=False);results=[]
for mode in ('normal','before','record','published','after'):
 parent=work/mode;parent.mkdir();root=parent/'private';command=[str(pathlib.Path(a.probe).resolve()),str(root),mode]
 if mode=='normal':
  r=subprocess.run(command,capture_output=True,text=True,timeout=60)
  (parent/'stdout.txt').write_text(r.stdout);(parent/'stderr.txt').write_text(r.stderr)
  assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
  data=json.loads(r.stdout);assert data['source']==os.environ['GITHUB_SHA'] and data['passed'] and data['failed']==0 and data['checks']==26,data
  assert data['sdk_open_attempts']==0 and not data['commit_acknowledged'] and not data['recovery_admission']
 else:
  proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
   f=pool.submit(proc.stdout.readline)
   try: line=f.result(timeout=30).strip()
   except BaseException:
    proc.kill();proc.wait(timeout=10);raise
   if line!='ready-'+mode:
    proc.kill();out,err=proc.communicate(timeout=10);raise AssertionError((line,out,err))
   proc.kill();out,err=proc.communicate(timeout=10)
  (parent/'stdout.txt').write_text(line+'\n'+out);(parent/'stderr.txt').write_text(err)
  data=dict(mode=mode,terminated=True,commit_acknowledged=False,recovery_admission=False)
 source=root/'target.bin';dest=parent/'published.bin'
 published=mode in ('normal','published','after')
 assert source.exists()!=published and dest.exists()==published
 assert (dest if published else source).read_bytes()==b'bridge payload\n'
 records=[]
 for index in range(2):
  raw=(root/f'bridge-slot-{index:02d}.rec').read_bytes()
  valid=(index==0 and mode!='before') or (index==1 and mode in ('normal','after'))
  if valid:
   record=json.loads(raw);assert record['magic']=='EXRWINRECOVERY1' and record['ordinal']==index
   assert all(len(record[k])==48 for k in ('root','parent','target'))
   canonical=dict(record);seal=canonical.pop('seal');body=json.dumps(canonical,separators=(',',':')).encode()+b'\n'
   assert hashlib.sha256(body).hexdigest()==seal
   records.append(record)
  else: assert raw==bytes(4096)
 if len(records)==2:
  assert records[1]['previous_sha']==hashlib.sha256((root/'bridge-slot-00.rec').read_bytes()).hexdigest()
 data['files']={str(q.relative_to(parent)):{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in parent.rglob('*') if q.is_file()}
 results.append(data)
(work/'receipt.json').write_text(json.dumps(dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],passed=True,results=results,live_bridge_only=True,restart_reader=False,full_p0_acceptance=False,physical_power_loss=False),indent=2)+'\n')
