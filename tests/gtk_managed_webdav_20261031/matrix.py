"""Installed managed transport, isolated fault worker and persistent raw observations."""
import hashlib,json,os,shutil,signal,stat,subprocess,sys,time,zlib
from pathlib import Path
from fixture import Fixture
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"build/gtk-managed"
EVIDENCE=OUT/"matrix";PROBE=OUT/"probes/managed-consumer";FAULT=OUT/"probes/managed-fault-worker"
CASES=[];CURRENT=None;SERVER=None
def require(ok,reason):
 if not ok:raise AssertionError(reason)
def snapshot(base,label,payload=True):
 rows={}
 def visit(p):
  st=p.lstat();rel=p.relative_to(base).as_posix()
  r=dict(dev=st.st_dev,ino=st.st_ino,nlink=st.st_nlink,size=st.st_size,mode=stat.S_IMODE(st.st_mode),uid=st.st_uid)
  rows[rel]=r
  require(len(rows)<=4096,"snapshot bound")
  if stat.S_ISREG(st.st_mode):
   r["kind"]="file";b=p.read_bytes();r["sha256"]=hashlib.sha256(b).hexdigest()
   if payload or p.name in (".receipt",".receipt.next","registry","registry.next","registry.lock",".lock"):
    require(len(b)<=65536,"raw byte bound");r["bytes_hex"]=b.hex()
  elif stat.S_ISDIR(st.st_mode):
   r["kind"]="dir"
   for child in sorted(p.iterdir()):visit(child)
  elif stat.S_ISLNK(st.st_mode):r.update(kind="symlink",target=os.readlink(p))
  else:r["kind"]="other"
 visit(base);value=dict(label=label,entries=rows);CURRENT["snapshots"].append(value);return rows
def process(argv,extra=None,hold=False):
 env=dict(os.environ,MANAGED_AUTH=SERVER.auth);env.update(extra or {})
 path=EVIDENCE/(CURRENT["name"]+"-"+str(len(CURRENT["processes"]))+".log")
 log=path.open("w");p=subprocess.Popen(list(map(str,argv)),stdout=log,stderr=subprocess.STDOUT,env=env)
 r=dict(pid=p.pid,argv=list(map(str,argv)),returncode=None,kill_sent=False,signal_sent=None,log=path.name)
 CURRENT["processes"].append(r)
 if hold:
  end=time.monotonic()+15
  while time.monotonic()<end:
   if "HELD " in path.read_text():return p,log,r,path
   if p.poll() is not None:break
   time.sleep(.02)
  if p.poll() is None:p.kill();r.update(kill_sent=True,signal_sent=9)
  r["returncode"]=p.wait(timeout=10);log.close()
  raise AssertionError("worker hold missing: "+path.read_text()[-2000:])
 try:r["returncode"]=p.wait(timeout=240)
 except subprocess.TimeoutExpired:
  p.kill();r.update(kill_sent=True,signal_sent=9);r["returncode"]=p.wait(timeout=10);raise
 finally:log.close()
 require(r["returncode"]==0,"process exit: "+path.read_text()[-2000:])
 text=path.read_text();obs=[json.loads(x[4:]) for x in text.splitlines() if x.startswith("OBS ")]
 r["observations"]=obs;r["canaries"]=[json.loads(x[7:]) for x in text.splitlines() if x.startswith("CANARY ")]
 return obs
def kill(child):
 p,log,r,path=child;p.kill();r.update(kill_sent=True,signal_sent=9);r["returncode"]=p.wait(timeout=10);log.close()
 require(r["returncode"]==-9,"actual SIGKILL returncode")
 r["observations"]=[json.loads(x[4:]) for x in path.read_text().splitlines() if x.startswith("OBS ")]
 r["held"]=[x for x in path.read_text().splitlines() if x.startswith("HELD ")]
def download(base,leaf="book.txt",resource="payload",count=1,extra=None,fault=False,hold=False):
 return process([FAULT if fault else PROBE,"download",base,SERVER.url,base/"dest",leaf,resource,str(count)],extra,hold)
def recover(base):
 return process([PROBE,"recover",base])[-1]
def directories(base):
 return sorted((base/"webdav-managed-v1").glob("root-*"))
def txdirs(base):
 return sorted((base/"webdav-managed-v1").glob("root-*/tx-*"))
def decode(path):
 b=path.read_bytes();c=bytearray(b);c[60:64]=b"\0"*4
 require(len(b)==4160 and b[:8]==b"EXRWCRCT" and int.from_bytes(b[60:64],"little")==zlib.crc32(c),"receipt CRC")
 count=int.from_bytes(b[12:16],"little")
 return dict(uuid=b[32:48].hex(),generation=int.from_bytes(b[16:24],"little"),
  states=[int.from_bytes(b[64+i*64:68+i*64],"little") for i in range(count)])
def rewrite_registry(base,fn):
 p=base/"webdav-managed-v1/registry";b=p.read_bytes();body=fn(b[:-9]);p.write_bytes(body+("%08x\n"%zlib.crc32(body)).encode())
def targets_equal(before,after,links):
 for path,row in before.items():
  if not path.startswith("dest/") or row["kind"]!="file":continue
  other=after[path]
  require(all(row[k]==other[k] for k in ("dev","ino","size","sha256")),"published target changed")
  if links is not None:require(other["nlink"]==links,"published target links")
def recovery_pair(base,expected_pending,cleaned):
 before=snapshot(base,"before-recovery")
 first=recover(base);middle=snapshot(base,"recovery-1")
 second=recover(base);after=snapshot(base,"recovery-2")
 require(first["status"]==second["status"]==0,"recovery status")
 require(first["pending"]==second["pending"]==expected_pending,"recovery pending")
 require(first["cleaned"]==cleaned and second["cleaned"]==0,"idempotent recovery counters")
 require(middle==after,"idempotent disk image");targets_equal(before,after,1 if cleaned else None)
 return first,second
def case(name,fn):
 global CURRENT
 CURRENT=dict(name=name,passed=False,processes=[],snapshots=[],euid=os.geteuid(),observer_pid=os.getpid())
 CASES.append(CURRENT);folder=EVIDENCE/name;folder.mkdir(mode=0o700);base=folder/"profile";base.mkdir(mode=0o700);(base/"dest").mkdir(mode=0o700)
 try:
  fn(base);CURRENT["passed"]=True
 except Exception as e:
  CURRENT["error"]=type(e).__name__+": "+str(e)
  raise
 finally:
  snapshot(base,"final",payload=False)
  (EVIDENCE/"results.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],
   attempt=os.environ["GITHUB_RUN_ATTEMPT"],cases=CASES),indent=2)+"\n")
  print(("PASS " if CURRENT["passed"] else "FAIL ")+name,flush=True)
def main():
 global SERVER
 require(os.environ.get("GITHUB_ACTIONS")=="true" and os.geteuid()!=0,"Actions nonroot")
 EVIDENCE.mkdir(parents=True,exist_ok=True);SERVER=Fixture(OUT/"tls-private")
 def normal(base):
  r=download(base)[-1];require(r["status"]==0 and r["published"]==1 and r["pending"]==0,"normal managed download")
  require(decode(directories(base)[0]/".receipt")["states"]==[6],"normal cleaned")
  recovery_pair(base,0,0)
 def existing(base):
  download(base);before=snapshot(base,"before-existing");r=download(base)[-1]
  after=snapshot(base,"after-existing");require(r["status"]==11 and r["published"]==0,"no replace");targets_equal(before,after,1)
 def failure(base,mode):
  if mode=="cancel":SERVER.entries["/dav/payload"]=b"x"*65536
  SERVER.http=503 if mode=="http" else 0;SERVER.disconnect=mode=="disconnect"
  try:r=download(base,extra={"MANAGED_CANCEL":"1"} if mode=="cancel" else None)[-1]
  finally:SERVER.http=0;SERVER.disconnect=False;SERVER.entries["/dav/payload"]=b"managed product staging\n"*128
  require(r["status"]!=0 and r["published"]==0 and not (base/"dest/book.txt").exists(),"unpublished failure")
  require(r["pending"]==0 and decode(directories(base)[0]/".receipt")["states"]==[6],"safe abandon")
 def eacces(base):
  r=download(base,fault=True,extra={"MANAGED_DENY":"managed_sealed"})[-1]
  require(r["status"]==0 and r["published"]==1 and r["pending"]==1 and r["errno"]==13,"published pending EACCES")
  canary=CURRENT["processes"][-1]["canaries"];require(len(canary)==1 and canary[0]["errno"]==13 and canary[0]["rc"]==-1 and canary[0]["mode"]==0o500 and canary[0]["euid"]!=0,"raw EACCES canary")
  snapshot(base,"eacces");txdirs(base)[0].chmod(0o700);recovery_pair(base,0,1)
 def busy(base):
  child=process([PROBE,"hold",base,SERVER.url,base/"dest","book.txt","payload"],hold=True)
  try:r=recover(base);require(r["status"]==3,"registry lock busy")
  finally:kill(child)
  require(recover(base)["status"]==0,"lock released by death")
 def refused(base,kind):
  recover(base);ns=base/"webdav-managed-v1"
  if kind=="corrupt":(ns/"registry").write_bytes(b"broken")
  elif kind=="next":(ns/"registry.next").write_bytes(b"uncertain")
  elif kind=="unknown":(ns/"unknown").write_bytes(b"keep")
  elif kind=="missing":(ns/"registry").unlink()
  elif kind=="uuid":
   download(base);rewrite_registry(base,lambda body:body.replace(decode(directories(base)[0]/".receipt")["uuid"].encode(),b"0"*32))
  elif kind=="symlink":
   ns.rename(base/"outside");ns.symlink_to(base/"outside",target_is_directory=True)
  before=snapshot(base,"before-refusal");r=recover(base);after=snapshot(base,"after-refusal")
  require(r["status"] in (4,7),"fail closed "+kind);require(before==after,"refusal preserved all entries")
 def crash(base,phase,pending,cleaned):
  child=download(base,fault=True,extra={"MANAGED_HOLD":phase},hold=True)
  snapshot(base,"held");kill(child);snapshot(base,"after-death")
  recovery_pair(base,pending,cleaned)
 def registry_crash(base,phase):
  child=download(base,fault=True,extra={"MANAGED_HOLD":phase},hold=True)
  snapshot(base,"held");kill(child);before=snapshot(base,"after-death");r=recover(base);after=snapshot(base,"after-recovery")
  if phase=="registry_next":require(r["status"]==7 and before==after,"registry next refuses")
  else:
   require(r["status"]==0 and r["pending"]==1 and r["roots"][0]["unbound"]==1,"unbound root retained")
   require(before==after,"unbound residue not adopted")
 def uncertain(base):
  r=download(base,fault=True,extra={"MANAGED_DENY":"linked"})[-1]
  require(r["status"]==0 and r["published"]==1 and r["uncertain"]==1,"published fact survives uncertain receipt")
  snapshot(base,"uncertain");directories(base)[0].chmod(0o700);recovery_pair(base,1,0)
 def rotation(base):
  rows=download(base,count=65);require(len(rows)==66 and all(r["status"]==0 for r in rows),"64/65 boundary")
  require([r["slots"] for r in rows[-1]["roots"]]==[64,1],"root rotation without slot reuse")
  child=download(base,leaf="pending",fault=True,extra={"MANAGED_HOLD":"owned"},hold=True);kill(child)
  last=download(base,leaf="continued")[-1]
  require([r["slots"] for r in last["roots"]]==[64,2,1] and last["pending"]==1,"pending/full/available roots coexist")
  recovery_pair(base,1,0)
 def capacity(base):
  rows=download(base,count=1025);downloads=[r for r in rows if r["label"]=="download"]
  require(len(downloads)==1025 and all(r["status"]==0 for r in downloads[:-1]),"1024 lifetime slots")
  r=downloads[-1];require(r["status"]==8 and r["published"]==0 and r["exhausted"]==1 and len(r["roots"])==16,"pool refuses new download")
  require(all(x["slots"]==64 for x in r["roots"]),"no slot reuse")
  require(len(list((base/"dest").iterdir()))==1024,"no fallback file")
  before=snapshot(base,"before-recovery",False);r=recover(base);after=snapshot(base,"recovery-2",False)
  require(r["exhausted"]==1 and r["pending"]==0 and before==after,"full roots retained")
 try:
  case("01-installed-normal-and-reopen",normal);case("02-existing-target",existing)
  for n,mode in enumerate(("cancel","http","disconnect"),3):case("%02d-unpublished-%s"%(n,mode),lambda b,m=mode:failure(b,m))
  case("06-real-eacces-and-two-recoveries",eacces);case("07-process-lock",busy)
  for n,kind in enumerate(("corrupt","next","unknown","missing","uuid","symlink"),8):case("%02d-refuse-%s"%(n,kind),lambda b,k=kind:refused(b,k))
  for n,(phase,pending,cleaned) in enumerate((("directory_created",1,0),("owned",1,0),("sealed",1,0),("publish_intent",1,0),("linked",1,0),("published",0,1),("alias_unlinked",0,1)),14):
   case("%02d-kill-%s"%(n,phase),lambda b,p=phase,pe=pending,c=cleaned:crash(b,p,pe,c))
  case("21-registry-next-kill",lambda b:registry_crash(b,"registry_next"))
  case("22-root-created-unbound-kill",lambda b:registry_crash(b,"root_created"))
  case("23-published-receipt-uncertain",uncertain)
  case("24-root-rotation-and-mixed-restart",rotation)
  case("25-pool-exhaustion",capacity)
  require(len(CASES)==25 and all(c["passed"] for c in CASES),"fixed product transport matrix")
  require(all(r["authenticated"] for r in SERVER.requests),"HTTPS credential origin")
 finally:
  (EVIDENCE/"requests.json").write_text(json.dumps(SERVER.requests,indent=2)+"\n");SERVER.close()
if __name__=="__main__":main()
