"""Actions-only fresh-process recovery classification; never admission."""
import argparse,concurrent.futures,hashlib,json,mmap,os,pathlib,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--work',required=True)
a=p.parse_args()
exe=str(pathlib.Path(a.probe).resolve());work=pathlib.Path(a.work).resolve()
work.mkdir(parents=True,exist_ok=False);results=[]
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
  assert data['source']==os.environ['GITHUB_SHA'] and data['sdk_open_attempts']==0,data
  assert not data['commit_acknowledged'] and not data['recovery_admission'],data
 return data
def lease_file(root):
 return pathlib.Path(run(root,'none','leasepath')['lease'])
def fixture(name,fixture=None):
 fixture=fixture or name;parent=work/name;parent.mkdir();root=parent/'private'
 proc=start([exe,'fixture',str(root),fixture],'ready-'+fixture)
 busy=run(root);assert not busy['opened'] and busy['class']==0,busy
 kill(proc)
 shared=run(root,verb='shared')
 assert shared['stale'] is True,(name,shared)
 return parent,root
def keep(name,parent,root,data,shared='stale',**extra):
 """shared is measured, never asserted from a literal. 'stale' requires the
 provider to still refuse shared admission; 'refused' requires a non-zero status
 without a stale verdict (the namespace itself is damaged, so no lease is handed
 out); 'admitted' records the known case where the control itself destroyed
 PENDING; 'skip' avoids asking at all, because asking would re-create a lease the
 reader must leave untouched."""
 data.update(case=name,original_process_terminated=True,**extra)
 if shared=='skip':
  data['shared_still_stale']=None;data['shared_probe']='not-run-lease-namespace-damaged'
 else:
  measured=run(root,verb='shared')
  data['shared_still_stale']=measured['stale'];data['shared_status']=measured['status']
  if shared=='stale':assert measured['stale'] is True,(name,measured)
  elif shared=='refused':assert measured['stale'] is False and measured['status']!=0,(name,measured)
  elif shared=='admitted':assert measured['stale'] is False and measured['status']==0,(name,measured)
  else:raise AssertionError(('unknown shared policy',shared))
 data['files']={str(q.relative_to(parent)):{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in parent.rglob('*') if q.is_file()}
 results.append(data)
def opened_full(name,fixture_mode,want):
 parent,root=fixture(name,fixture_mode)
 data=run(root)
 assert data['opened'] and data['class']==want,(name,data)
 assert data['checked'] and data['pending']==1 and data['generation']==0,data
 assert data['write_denied'] and data['rename_denied'] and not data['after_fail_rename'],data
 keep(name,parent,root,data)
def refused_content(name,mutate,want):
 parent,root=fixture(name)
 mutate(parent,root)
 data=run(root)
 assert data['opened'] and data['class']==want and not data['checked'],(name,data)
 keep(name,parent,root,data)
def refused_argument(name,mode,*,opened,reason):
 parent,root=fixture(name)
 data=run(root,mode)
 assert data['opened'] is opened and data['class']==0 and not data['checked'],(name,data)
 assert data['open_reason']==reason,(name,data)
 keep(name,parent,root,data)
# Original content classification: complete evidence, prefix and reserved.
for name,want in (('before',1),('record',2),('published',2),('after',3)):
 opened_full(name,name,want)
# A live reader must exclude a second reader, and its death must free custody.
parent,root=fixture('reader-death')
reader=start([exe,'read',str(root),'hold'],'ready-reader')
assert not run(root)['opened']
kill(reader)
data=run(root);assert data['opened'] and data['class']==3,data
assert data['checked'] and data['write_denied'] and data['rename_denied'],data
keep('reader-death',parent,root,data)
# Retained-content and namespace refusals.
refused_content('partial',lambda p,r:(r/'bridge-slot-00.rec').write_bytes(b'{"partial":'),0)
refused_content('missing-slot',lambda p,r:(r/'bridge-slot-01.rec').unlink(),0)
refused_content('extra-slot',lambda p,r:(r/'bridge-slot-07.rec').write_bytes(bytes(4096)),0)
def _previous_id(p,r):
 q=r/'bridge-slot-01.rec';d=json.loads(q.read_bytes());d.pop('seal')
 d['previous_id']=d['previous_id'][:-1]+('0' if d['previous_id'][-1]!='0' else '1')
 raw=json.dumps(d,separators=(',',':')).encode()+b'\n';d['seal']=hashlib.sha256(raw).hexdigest()
 q.write_bytes(json.dumps(d,separators=(',',':')).encode()+b'\n')
refused_content('previous-id',_previous_id,0)
refused_content('payload',lambda p,r:(p/'published.bin').write_bytes(b'wrong'),0)
refused_content('both-targets',lambda p,r:(r/'target.bin').write_bytes((p/'published.bin').read_bytes()),4)
refused_content('missing-target',lambda p,r:(p/'published.bin').unlink(),4)
# Caller-supplied bindings: a stale admitted generation is refused before any
# lease handle exists, so the pinned provider can never re-initialise a lease.
refused_argument('generation','generation',opened=False,reason='restart-lease-generation')
refused_argument('root','root',opened=True,reason='restart-root-binding')
refused_argument('session','session',opened=True,reason='restart-record-chain')
def _write64(q,off,value):
 raw=bytearray(q.read_bytes());raw[off:off+8]=struct.pack('<Q',value);q.write_bytes(bytes(raw))
def _header_edit(q):
 raw=bytearray(q.read_bytes());raw[10]=ord('0') if raw[10:11]!=b'0' else ord('1');q.write_bytes(bytes(raw))
def refused_lease(name,edit,reason,want_bytes,shared='stale'):
 parent,root=fixture(name,fixture='after')
 edit(lease_file(root))
 data=run(root)
 assert not data['opened'] and data['class']==0 and not data['checked'],(name,data)
 assert data['reason']==reason,(name,data)
 assert data['lease_bytes']==want_bytes,(name,data)
 keep(name,parent,root,data,shared=shared)
# Lease namespace negatives: the reader qualifies the provider's frozen 80-byte
# lease file itself and never lets OPEN_ALWAYS recreate or re-initialise it.
refused_lease('lease-missing',lambda q:q.unlink(),'restart-lease-missing',-1,shared='skip')
refused_lease('lease-empty',lambda q:q.write_bytes(b''),'restart-lease-empty',0,shared='skip')
refused_lease('lease-truncated',lambda q:q.write_bytes(q.read_bytes()[:40]),'restart-lease-size',40,shared='refused')
refused_lease('lease-grow',lambda q:q.write_bytes(q.read_bytes()+bytes(40)),'restart-lease-size',120,shared='refused')
refused_lease('lease-header',_header_edit,'restart-lease-header',80,shared='refused')
refused_lease('lease-generation',lambda q:_write64(q,64,9),'restart-lease-generation',80)
# The control itself clears PENDING, so shared admission is expected to open; the
# measured value is recorded instead of being papered over.
refused_lease('lease-pending',lambda q:_write64(q,72,0),'restart-lease-pending',80,shared='admitted')
# A failed wr_prepare must not leak the ancestor pins it already holds: the
# private root stays renameable, which is only true when every pin was closed.
parent,root=fixture('partial-pin',fixture='after')
data=run(root,'missing-root')
assert data['opened'] is True and data['class']==0 and not data['checked'],data
assert data['open_reason']=='ancestor-open',data
assert data['after_fail_rename'],data
keep('partial-pin',parent,root,data,required_root='absent-sub')
# The acquire window is injected, not argued about: the probe empties the lease
# between the reader's pre-validation and the provider acquire, so the provider's
# OPEN_ALWAYS branch re-initialises it and clears PENDING. The reader must restore
# the exact pre-acquire bytes, refuse custody, and leave shared admission closed.
parent,root=fixture('window-race',fixture='after')
data=run(root,'window-race')
assert data['opened'] is True and data['class']==0 and not data['checked'],data
assert data['open_reason']=='restart-lease-window-restored',data
assert data['lease_restored'] is True and data['lease_bytes']==80,data
keep('window-race',parent,root,data,shared='stale',window_injected=True)
# A write through a memory-mapped view bypasses the provider's byte-range locks.
# The reader must still report drift, because it re-reads the aged region.
parent,root=fixture('mapped-write',fixture='after')
lease=str(lease_file(root))
drift=subprocess.Popen([exe,'read',str(root),'drift'],stdout=subprocess.PIPE,text=True)
line=drift.stdout.readline().strip();assert line=='ready-reader',line
with open(lease,'r+b') as handle:
 view=mmap.mmap(handle.fileno(),0)
 view[64:72]=struct.pack('<Q',7);view.flush();view.close()
line=drift.stdout.readline().strip()
assert drift.wait(timeout=30)==0,(line,drift.stdout.read())
data=json.loads(line)
assert data['check_failed'] is True and data['reason']=='restart-lease-disk-drift',data
keep('mapped-write',parent,root,{'source':os.environ['GITHUB_SHA'],'opened':True,'class':3,'valid':2,
 'checked':False,'pending':1,'generation':0,'published':1,'write_denied':False,'rename_denied':False,
 'after_fail_rename':False,'lease_restored':False,'lease_bytes':80,'reason':data['reason'],
 'sdk_open_attempts':0,'commit_acknowledged':False,'recovery_admission':False})
# Recovery that cannot be proven safe must fail closed and keep custody. The
# lease here carries an advanced generation with no PENDING, which is what a real
# concurrent commit looks like, so the adapter must not write anything back; the
# refused object keeps the exclusive lease, so shared admission stays blocked for
# as long as it lives. After that process dies the drift survives: readers still
# refuse it, but the domain marker is gone, and this case records that instead of
# claiming durable isolation across a crash.
parent,root=fixture('window-drift',fixture='after')
drift2=subprocess.Popen([exe,'read',str(root),'window-drift'],stdout=subprocess.PIPE,text=True)
line=drift2.stdout.readline().strip()
data=json.loads(line)
assert data['opened'] is True and data['class']==0,data
assert data['reason']=='restart-lease-window-race',data
assert data['lease_restored'] is False,data
alive=run(root,verb='shared')
assert alive['stale'] is False and alive['status']==2,alive
kill(drift2)
after=run(root,verb='shared')
refused=run(root)
assert refused['opened'] is False and refused['reason']=='restart-lease-pending',refused
keep('window-drift',parent,root,data,shared='skip',recovery_failed=True,
     shared_while_alive_status=alive['status'],shared_while_alive_stale=alive['stale'],
     shared_after_crash_stale=after['stale'],shared_after_crash_status=after['status'],
     reader_after_crash_refused=True)
assert len(results)==26,len(results)
(work/'receipt.json').write_text(json.dumps(dict(source=os.environ['GITHUB_SHA'],run=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],passed=True,checks=len(results),results=results,classification_only=True,commit_acknowledged=False,recovery_admission=False,full_p0_acceptance=False,physical_power_loss=False,window_injection='test-seam-between-prevalidation-and-acquire',shared_admission_measured=True),indent=2)+'\n')
