"""Actions-only native installed-consumer acceptance. Never grants SDK admission."""
import argparse, hashlib, json, os, pathlib, subprocess, time
p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--work',required=True);a=p.parse_args()
work=pathlib.Path(a.work).resolve();work.mkdir(parents=True,exist_ok=False)
results=[]
for mode in ('normal','before','after'):
 parent=work/mode;parent.mkdir();root=parent/'private'
 command=[str(pathlib.Path(a.probe).resolve()),str(root),mode]
 if mode=='normal':
  r=subprocess.run(command,text=True,capture_output=True,timeout=60)
  (parent/'stdout.txt').write_text(r.stdout);(parent/'stderr.txt').write_text(r.stderr)
  assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
  data=json.loads(r.stdout);assert data['source']==os.environ['GITHUB_SHA'] and data['passed'] and data['checks']==24 and data['failed']==0
  assert len(data['identity'])==48 and data['sdk_open_attempts']==0 and not data['recovery_admission']
  assert (parent/'collision.bin').read_bytes()==b'retain'
  assert (parent/'collision-dir').is_dir() and not (root/'source.bin').exists()
  assert hashlib.sha256((parent/'published.bin').read_bytes()).hexdigest()==data['sha256']
  results.append(data)
 else:
  proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  # A bounded reader thread prevents a failed native operation from hanging the job.
  import concurrent.futures
  with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
   future=pool.submit(proc.stdout.readline)
   try: line=future.result(timeout=30).strip()
   except BaseException:
    proc.kill();proc.wait(timeout=10);raise
   assert line=='ready-'+mode,(line,proc.communicate(timeout=10) if proc.poll() is not None else 'unexpected ready')
   proc.kill();proc.wait(timeout=10)
  source=root/'source.bin';dest=parent/'published.bin'
  assert source.exists()==(mode=='before') and dest.exists()==(mode=='after')
  present=source if source.exists() else dest
  assert present.read_bytes()==b'private-to-public complete bytes\n'
  # No coordinator exists: process death cannot fabricate acknowledgement.
  assert not list(parent.glob('**/*ack*'))
  results.append(dict(mode=mode,terminated=True,retained=True,recovery_admission=False,commit_acknowledged=False))
receipt=dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],passed=True,results=results,full_p0_acceptance=False,physical_power_loss=False)
(work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
