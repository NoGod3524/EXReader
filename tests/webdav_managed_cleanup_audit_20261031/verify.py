#!/usr/bin/env python3
"""Actions-only authentication of two fixed historical artifacts; never runs their code."""
import base64, copy, hashlib, io, json, os, re, stat, subprocess, sys, zipfile, zlib
from pathlib import Path, PurePosixPath

REPO="NoGod3524/EXReader"
BASE="d69bae312fd0791dac119509437fb29abc92a25c"
TESTS="711e1fc8a8c5b86f210bcddc934c479599387582"
CORE="dba079b550f9ec83054e6b7b0b7475f43bc1739f"
PRODUCER_BASE="666d0d81730ac3cf7caea52b05ca1f01b1d183b1"
RUN=41174402876
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"build/managed-cleanup-audit"
OWNED={"tests/webdav_managed_cleanup_audit_20261031/verify.py",
".github/workflows/dot-webdav-managed-cleanup-audit-20261031.yml",
"docs/reader-total-progress/DOT_WEBDAV_MANAGED_CLEANUP_AUDIT_20261031.md"}
PINS=[
  {
    "platform": "Linux",
    "system": "Linux",
    "machine": "x86_64",
    "euid": 1001,
    "job": 124458850309,
    "id": 13031778309,
    "size": 114285,
    "digest": "4520aae748dff728019ce865116685930cd887a3783c827c2ac3bf4422554946",
    "archive": "276bb6c488e6ed916e87d77a3e062e1e1f650d89cb1a12229ac75cf0a20bfdd3",
    "consumer": "a069cd2970f4a370a9f99beaac78df20d1a650cd80247866de046d9c01c9b222",
    "hookworker": "c045fcd16d88e64f5c1d31a3222b15a8cd4f6dab4a83a193ffd2f87919956b84"
  },
  {
    "platform": "macOS",
    "system": "Darwin",
    "machine": "arm64",
    "euid": 501,
    "job": 124458849971,
    "id": 13031863107,
    "size": 101735,
    "digest": "3c8533a40556485d8818821068fe6cceef67e83e94cd15d26d59ba431abfe2ec",
    "archive": "807cd16f551bd9da7fd3be0e101b68f0e698b11003516e8bfea37e93ef9c7bdf",
    "consumer": "2a0607ef46b66b610fb857359befae461fab843d553b3d05fd36f7025ddd3098",
    "hookworker": "b88fc3eafab0a0eb7bdc8a1f1b8a4a395aa11a7ea9e0557d3c9d816bceaff20d"
  }
]
SOURCE={
 "build/core/extras/webdav-cleanup/src/cleanup_posix.c":(CORE,"extras/webdav-cleanup/src/cleanup_posix.c","2ebb5a27b62998b6fc185277a04d81b506871880f7edb3860923f775dfb70590"),
 "build/core/extras/webdav-cleanup/include/exr_webdav_cleanup.h":(CORE,"extras/webdav-cleanup/include/exr_webdav_cleanup.h","5c683d07eb87c21d521bab95b0fc56738da12975ebbc022257ef338498edd979"),
 "tests/webdav_managed_cleanup_20261031/worker.c":(TESTS,"tests/webdav_managed_cleanup_20261031/worker.c","83fd9d19d99119203bcc23df9bcb9ca53b57c82f69cb0958ecdd7d9f2fe38b05"),
 "tests/webdav_managed_cleanup_20261031/run.py":(TESTS,"tests/webdav_managed_cleanup_20261031/run.py","afaf4cf7c140172e4045c1b97a91dbb52bf50a7327e06f55a5b8a83cfd5d00ea")}
NAMES=[
"01-normal-publish-cleanup","02-abandon-owned","03-abandon-sealed","04-unauthorized-abandon-refused",
"05-same-process-lock","06-cross-process-lock","07-active-tx-blocks-close","08-existing-target-not-replaced",
"09-root-or-txdir-destination-refused","10-payload-inode-replacement-refused","11-payload-symlink-refused",
"12-unknown-entry-preserved","13-real-eacces-recovered","14-bounded-paging-idempotent","15-lifetime-slot-limit",
"16-wrong-uuid","17-legacy-unreceipted-directory","18-root-symlink","19-receipt-checksum-corruption",
"20-residual-receipt-next","21-illegal-leaf","22-kill-directory-created","23-kill-payload-created",
"24-kill-owned","25-kill-sealed","26-kill-publish-intent","27-kill-linked","28-kill-published",
"29-kill-alias-unlinked","30-kill-receipt-next-reserved"]
KILLS=[
("directory_created",1,[1],0,1),("payload_created",1,[1],0,1),("owned",2,[2],0,1),
("sealed",3,[3],0,1),("publish_intent",4,[4],0,1),("linked",4,[4],0,1),
("published",5,[6],1,0),("alias_unlinked",5,[6],1,0),("receipt_next_synced",1,[],0,0)]
class Invalid(Exception): pass
def need(ok,reason):
 if not ok: raise Invalid(reason)
def sha(b): return hashlib.sha256(b).hexdigest()
def no_duplicates(pairs):
 out={}
 for k,v in pairs:
  need(k not in out,"duplicate_json_key");out[k]=v
 return out
def loads(b):
 return json.loads(b,object_pairs_hook=no_duplicates,parse_constant=lambda x: (_ for _ in ()).throw(Invalid("nonfinite_json")))
def encoded(x): return (json.dumps(x,sort_keys=True,indent=2)+"\n").encode()
def api(path):
 return loads(subprocess.check_output(["gh","api","repos/"+REPO+"/"+path],timeout=60))
def source_bytes(ref,path):
 r=api("contents/"+path+"?ref="+ref)
 need(r.get("encoding")=="base64","source_encoding")
 return base64.b64decode(r["content"],validate=False)
def scope():
 git=lambda *a:subprocess.check_output(["git",*a],cwd=ROOT,text=True).strip()
 need(git("rev-parse","HEAD")==os.environ["GITHUB_SHA"],"audit_source")
 need(set(git("diff","--name-only",BASE,"HEAD").splitlines())==OWNED,"audit_scope")
def unpack(data):
 files={};seen=set()
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  infos=z.infolist()
  need(0<len(infos)<=200,"zip_count")
  need(sum(i.file_size for i in infos)<=32*1024*1024,"zip_total")
  for i in infos:
   n=i.filename;p=PurePosixPath(n)
   need(n and not p.is_absolute() and ".." not in p.parts and "\\" not in n and ":" not in n and "\x00" not in n,"zip_path")
   canonical=str(p)
   need(canonical not in ("",".") and canonical==n.rstrip("/"),"zip_normal")
   need(canonical.casefold() not in seen,"zip_duplicate");seen.add(canonical.casefold())
   need(not i.flag_bits&1 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"zip_kind")
   need(i.file_size<=8*1024*1024 and i.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),"zip_member")
   if not i.is_dir():
    b=z.read(i);need(len(b)==i.file_size,"zip_size");files[n]=b
 return files
def locate(files,suffix):
 candidates=[n for n in files if n==suffix or n.endswith("/"+suffix)]
 need(len(candidates)==1,"member:"+suffix)
 return candidates[0]
def get(files,suffix):return files[locate(files,suffix)]
def obj(files,suffix):return loads(get(files,suffix))
def seal(files):return {"files":files,"inventory":{n:sha(b) for n,b in files.items()}}
def validate_seal(package):
 need(package["inventory"]=={n:sha(b) for n,b in package["files"].items()},"inner_seal")
 return package["files"]
def reports(log):
 return [loads(x[len("RECOVER "):]) for x in log if x.startswith("RECOVER ")]
def recovery(log,states,cleaned,pending,reason):
 need([x for x in log if x.startswith("OPEN ")]==["OPEN 0"],reason)
 rows=reports(log);need(len(rows)==2,reason)
 for i,r in enumerate(rows):
  expected=dict(status=0,refused=0,receipt_uncertain=0,native_error=0,states=states,
   pending=pending,cleaned=cleaned if i==0 else 0,inspected=len(states),total_slots=len(states),next_slot=len(states))
  need(all(type(r.get(k)) is type(v) and r[k]==v for k,v in expected.items()),reason)

def raw_entries(snapshot):
 rows=snapshot["entries"]
 if type(rows) is list:
  need(len({r["path"] for r in rows})==len(rows),"raw_duplicate_path")
  rows={r["path"]:{k:v for k,v in r.items() if k!="path"} for r in rows}
 need(type(rows) is dict and 0<len(rows)<=1024,"raw_entries")
 for path,r in rows.items():
  p=PurePosixPath(path)
  need((path=="." or (not p.is_absolute() and ".." not in p.parts)) and "error" not in r,"raw_path_or_error")
  need(r.get("kind") in ("file","dir","symlink","other"),"raw_kind")
  for k in ("dev","ino","nlink","size","mode","uid","gid"):
   need(type(r.get(k)) is int and r[k]>=0,"raw_stat")
  if r["kind"]=="file":
   try:b=bytes.fromhex(r["bytes_hex"])
   except (ValueError,KeyError):raise Invalid("raw_bytes")
   need(len(b)==r["size"] and len(b)<=65536,"raw_bytes")
   if "sha256" in r:need(sha(b)==r["sha256"],"raw_hash")
 return rows
def one(rows,key,value):
 found=[r for r in rows if r.get(key)==value]
 need(len(found)==1,"raw_unique:"+value)
 return found[0]
def snap(c,label,worker=False):
 rows=c["raw"]["worker_events"] if worker else c["raw"]["snapshots"]
 return raw_entries(one(rows,"label",label))
def receipt(entries,path="root/.receipt"):
 need(path in entries and entries[path]["kind"]=="file","raw_receipt")
 b=bytes.fromhex(entries[path]["bytes_hex"])
 need(len(b)==4160 and b[:8]==b"EXRWCRCT","raw_receipt")
 u32=lambda p:int.from_bytes(b[p:p+4],"little")
 u64=lambda p:int.from_bytes(b[p:p+8],"little")
 need(u32(8)==1 and u32(12)<=64 and u64(16)>0 and u64(24)>0 and not any(b[48:60]),"raw_receipt")
 need(zlib.crc32(b[:60]+b"\0"*4+b[64:])==u32(60),"raw_crc")
 need(u64(24)==entries["root"]["ino"],"raw_root_identity")
 slots=[]
 for i in range(64):
  pos=64+i*64;s=b[pos:pos+64]
  if i>=u32(12):need(not any(s),"raw_receipt");continue
  state=u32(pos)
  need(state in range(1,7) and not any(s[4:8]+s[48:64]),"raw_receipt")
  size,di,pi=u64(pos+8),u64(pos+16),u64(pos+24)
  need((size==di==pi==0) if state==1 else di>0 and pi>0,"raw_receipt")
  slots.append(dict(state=state,bytes=size,dir_ino=di,payload_ino=pi,id=s[32:48].hex()))
 return dict(generation=u64(16),root_ino=u64(24),uuid=b[32:48].hex(),slots=slots)
def target(entries):
 t=entries.get("dest/book.epub")
 if t:
  need(t["kind"]=="file","raw_target")
  need(bytes.fromhex(t["bytes_hex"])==b"managed cleanup payload 20261031\n","raw_target_bytes")
 return t
def same_target(a,b,links):
 ta,tb=target(a),target(b)
 need((ta is None)==(tb is None),"raw_target_presence")
 if ta:
  need(all(ta[k]==tb[k] for k in ("dev","ino","size","bytes_hex")),"raw_target_identity")
  need(tb["nlink"]==links,"raw_target_links")
def transaction_disk(entries,phase):
 tx=[p for p,r in entries.items() if p.startswith("root/tx-") and p.count("/")==1]
 need(len(tx)==(0 if phase=="receipt_next_synced" else 1),"raw_disk_phase")
 payload=[p for p in entries if p.startswith("root/tx-") and p.endswith("/payload")]
 need(len(payload)==(0 if phase in ("directory_created","alias_unlinked","receipt_next_synced") else 1),"raw_disk_phase")
 t=target(entries);has_book=phase in ("linked","published","alias_unlinked")
 need((t is not None)==has_book,"raw_disk_phase")
 if t:need(t["nlink"]==(1 if phase=="alias_unlinked" else 2),"raw_target_links")
 if payload and t:
  q=entries[payload[0]]
  need(all(q[k]==t[k] for k in ("dev","ino","size","nlink","bytes_hex")),"raw_alias_identity")
 need(("root/.receipt.next" in entries)==(phase=="receipt_next_synced"),"raw_disk_phase")
 return tx,payload
def raw_case(c,index,pin):
 raw=c.get("raw",{})
 need(raw.get("schema")==1 and raw.get("euid")==pin["euid"] and raw.get("observer_pid",0)>0,"raw_schema")
 processes=raw.get("processes",[])
 need(len(processes)>=1 and len({p["pid"] for p in processes})==len(processes),"raw_process")
 killed=[]
 for p in processes:
  need(type(p["pid"]) is int and p["pid"]>0 and p["pid"]!=raw["observer_pid"]
   and p.get("timed_out") is False and len(p["argv"])>=3,"raw_process")
  if p["argv"][1] in ("hold","kill-flow"):
   need(p.get("kill_sent") is True and p.get("signal_sent")==9 and p.get("returncode")==-9,"raw_sigkill")
   killed.append(p)
  else:
   need(p.get("kill_sent") is False and p.get("signal_sent") is None and p.get("returncode")==0,"raw_process")
 need(len(killed)==(1 if index==5 or index>=21 else 0),"raw_sigkill")
 events=[loads(x[4:]) for x in c["log"] if x.startswith("RAW ")]
 need(events==raw.get("worker_events"),"raw_event_binding")
 for s in raw.get("snapshots",[]):raw_entries(s)
 for e in events:
  need(e.get("pid") in [p["pid"] for p in processes] and e.get("euid")==pin["euid"],"raw_event_process")
  if e.get("type")=="snapshot":raw_entries(e)
 snap(c,"before-case");snap(c,"final")
 if killed:
  before=snap(c,"held");dead=snap(c,"after-death")
  need(before==dead,"raw_death_disk")
 if index==5:
  need([p["argv"][1] for p in processes]==["prep","hold","try-open","try-open"],"raw_lock_processes")
  return
 if index!=12 and index<21:return
 recoverer=[p for p in processes if p["argv"][1]=="recover"]
 need(len(recoverer)==1 and all(recoverer[0]["pid"]!=p["pid"] for p in killed),"raw_recovery_process")
 before=snap(c,"before-recovery");after=snap(c,"after-recovery")
 first=snap(c,"recovery-1",True);second=snap(c,"recovery-2",True)
 # Hash fields are a Python convenience; compare all actual stat/byte observations.
 strip=lambda rows:{p:{k:v for k,v in r.items() if k!="sha256"} for p,r in rows.items()}
 need(strip(first)==strip(second)==strip(after),"raw_idempotence")
 old=receipt(before);new=receipt(first);again=receipt(second)
 uuid=one([dict(uuid=x[5:]) for x in c["log"] if x.startswith("UUID ")],"uuid",old["uuid"])["uuid"]
 need(new["uuid"]==again["uuid"]==uuid,"raw_uuid")
 if index==12:
  need([p["argv"][1] for p in processes]==["case","recover"],"raw_eacces_process")
  ca=one(events,"type","canary");cl=one(events,"type","cleanup")
  need(ca.get("euid",0)>0 and ca.get("mode")==0o500 and ca.get("returncode")==-1 and ca.get("errno")==13 and ca.get("exists")==1,"raw_eacces")
  need(cl.get("euid",0)>0 and cl.get("mode")==0o500 and cl.get("status")==2 and cl.get("removed")==0
   and cl.get("pending")==1 and cl.get("native_error")==13 and cl.get("receipt_uncertain")==0,"raw_eacces")
  cb=snap(c,"canary-before",True);ce=snap(c,"canary-after",True)
  need(cb==ce and cb["canary"]["mode"]==0o500 and cb["canary/c"]["bytes_hex"]=="630a","raw_canary")
  eb=snap(c,"eacces-before",True);ee=snap(c,"eacces-after",True)
  need(eb==ee,"raw_eacces_preservation")
  dirs=[p for p in eb if p.startswith("root/tx-") and p.count("/")==1]
  need(len(dirs)==1 and eb[dirs[0]]["mode"]==0o500 and before[dirs[0]]["mode"]==0o700,"raw_eacces_permissions")
  same_target(eb,before,2);same_target(before,after,1)
  need([s["state"] for s in receipt(eb)["slots"]]==[5],"raw_eacces_receipt")
  states,cleaned=[6],1
 else:
  phase,state,states,cleaned,pending=KILLS[index-21]
  need(snap(c,"after-death")==before,"raw_recovery_start")
  dirs,payloads=transaction_disk(before,phase)
  if phase=="receipt_next_synced":
   nxt=receipt(before,"root/.receipt.next")
   need(old["slots"]==[] and len(nxt["slots"])==1 and nxt["slots"][0]["state"]==1
    and nxt["generation"]==old["generation"]+1 and nxt["uuid"]==old["uuid"]
    and nxt["root_ino"]==old["root_ino"],"raw_next_amendment")
  else:
   need(len(old["slots"])==1 and old["slots"][0]["state"]==state,"raw_phase_receipt")
   slot=old["slots"][0]
   need(dirs==["root/tx-"+slot["id"]],"raw_transaction_id")
   if state>=2:
    need(before[dirs[0]]["ino"]==slot["dir_ino"],"raw_alias_identity")
    if payloads:need(before[payloads[0]]["ino"]==slot["payload_ino"],"raw_alias_identity")
  same_target(before,after,1 if cleaned else (target(before) or {}).get("nlink"))
  if not cleaned:
   for path,row in before.items():
    if path.startswith("root/tx-"):need(after.get(path)==row,"raw_pending_preserved")
 need([s["state"] for s in new["slots"]]==states,"raw_recovery_receipt")
 need(new["generation"]==old["generation"]+cleaned,"raw_recovery_generation")
 need("root/.receipt.next" not in after,"raw_next_survived")
 if cleaned:need(not any(p.startswith("root/tx-") for p in after),"raw_cleanup_disk")

def semantic(package,pin):
 files=validate_seal(package)
 binding=obj(files,"wc-logs/binding.json")
 need(binding.get("tests_source")==TESTS and binding.get("core_source")==CORE and binding.get("base")==PRODUCER_BASE
  and binding.get("run")==str(RUN) and binding.get("attempt")=="1","binding_identity")
 expected={k:v[2] for k,v in SOURCE.items()}
 header=SOURCE["build/core/extras/webdav-cleanup/include/exr_webdav_cleanup.h"][2]
 actuals={
 "build/wc-prefix/include/exr_webdav_cleanup.h":("wc-prefix/include/exr_webdav_cleanup.h",header),
 "build/wc-prefix/lib/libexr_webdav_cleanup.a":("wc-prefix/lib/libexr_webdav_cleanup.a",pin["archive"]),
 "build/wc-tests/wc-consumer":("wc-tests/wc-consumer",pin["consumer"]),
 "build/wc-tests/wc-hookworker":("wc-tests/wc-hookworker",pin["hookworker"])}
 expected.update({k:v[1] for k,v in actuals.items()})
 need(binding.get("files")==expected,"binding_hashes")
 for key,(suffix,digest) in actuals.items():need(sha(get(files,suffix))==digest,"binary_identity")
 nm=get(files,"wc-logs/archive-nm.txt").decode()
 need("exr_wc_test_hook" not in nm,"installed_hook")
 for name in ("create_at","open_at","begin","seal","publish_at","cleanup","inspect","recover","tx_close","close"):
  need(re.search(r"\sT _?exr_wc_"+name+r"$",nm,re.M) is not None,"export:"+name)
 need("exr_wc_test_hook" not in get(files,"wc-logs/consumer-nm.txt").decode(),"consumer_hook")
 need("exr_wc_test_hook" in get(files,"wc-logs/hookworker-nm.txt").decode(),"missing_hook")
 build=get(files,"wc-logs/tests-build.log").decode()
 h=[x for x in build.splitlines() if " -o wc-hookworker" in x]
 c=[x for x in build.splitlines() if " -o wc-consumer" in x]
 need(len(h)==len(c)==1 and "libexr_webdav_cleanup.a" not in h[0]
  and "libexr_webdav_cleanup.a" in c[0],"link_isolation")
 r=obj(files,"wc-evidence/results.json");s=r["summary"];cases=r["cases"]
 need(s.get("core_sha")==CORE and s.get("tests_sha")==TESTS,"result_identity")
 need((s.get("system"),s.get("machine"),s.get("euid"))==(pin["system"],pin["machine"],pin["euid"]),"platform")
 need([c.get("name") for c in cases]==NAMES and s.get("names")==NAMES,"case_set")
 need(s.get("total")==30 and s.get("passed")==30 and s.get("failed")==[] and s.get("complete") is True,"summary")
 for i,c in enumerate(cases):
  need(c.get("passed") is True and c.get("detail")=="" and type(c.get("seconds")) in (int,float) and c["seconds"]>=0,"case_result")
  log=c.get("log");need(type(log) is list and all(type(x) is str for x in log),"case_log")
  need(not any(x.startswith(("FAIL ","NOHOLD","Traceback")) for x in log),"worker_failure")
  if i not in [5]+list(range(21,30)):
   need(log.count("PASS "+NAMES[i])==1,"pass_marker")
  if i==5:
   need([x for x in log if x.startswith(("HELD ","STATUS "))]==["HELD 0","STATUS 3","STATUS 0"],"lock_handshake")
  if i==12:recovery(log,[6],1,0,"eacces_recovery")
  if i>=21:
   phase,state,states,cleaned,pending=KILLS[i-21]
   need([x for x in log if x.startswith("HELD ")]==[f"HELD {phase} 0 {state}"],"kill_marker")
   recovery(log,states,cleaned,pending,"kill_recovery")
 for i,c in enumerate(cases):raw_case(c,i,pin)
 matrix=get(files,"wc-logs/matrix.log").decode().splitlines()
 need([x for x in matrix if x.startswith("PASS ")]==["PASS "+n for n in NAMES],"matrix_cases")
 return {"producer_case_execution_authenticated":True,"cases":30,
 "source_bound_assertions_authenticated":True,"raw_recovery_reports_recomputed":10,
 "critical_evidence_complete":True,"raw_cases_checked":30,"raw_process_deaths_checked":10,"receipt_recovery_pairs_checked":10,"gaps":[],
 "disclosed_contract_amendment":{"case":30,"difference":"valid successor .receipt.next is discarded and old receipt reopened; frozen handoff said refuse every .next",
 "observed_constraints":"CRC/structural decode, matching UUID/root inode, next generation=current+1; no predecessor hash or full old/new slot transition comparison in open",
 "producer_document_discloses_amendment":True,"approval_origin_independently_verified":False,"current_user_authorized_upstream_takeover":True},
 "product_failure_proven":False,"product_cleanup_passed":False,"power_loss_validated":False}
def controls(files,pin):
 # Mutations are re-encoded and the inner inventory seal is recomputed, so
 # rejection must arise from semantics, never the unchanged historical ZIP digest.
 positive=semantic(seal(files),pin)
 cases=[]
 for name,expected in [("duplicate_case","case_set"),("case_false","case_result"),
 ("missing_pass","pass_marker"),("wrong_hook","kill_marker"),("wrong_recovery","kill_recovery"),
 ("root_uid","platform"),("wrong_core","binding_identity"),("binary_changed","binary_identity")]:
  changed=dict(files)
  if name=="wrong_core":
   n=locate(changed,"wc-logs/binding.json");r=loads(changed[n]);r["core_source"]="0"*40;changed[n]=encoded(r)
  elif name=="binary_changed":
   n=locate(changed,"wc-tests/wc-consumer");changed[n]=changed[n]+b"changed"
  else:
   n=locate(changed,"wc-evidence/results.json");r=loads(changed[n])
   if name=="duplicate_case":r["cases"][1]["name"]=r["cases"][0]["name"]
   elif name=="case_false":r["cases"][0]["passed"]=False
   elif name=="missing_pass":r["cases"][0]["log"]=[]
   elif name=="root_uid":r["summary"]["euid"]=0
   elif name=="wrong_hook":
    r["cases"][21]["log"]=[x.replace("HELD directory_created 0 1","HELD linked 0 4") for x in r["cases"][21]["log"]]
   elif name=="wrong_recovery":
    log=r["cases"][27]["log"]
    for j,x in enumerate(log):
     if x.startswith("RECOVER "):
      report=loads(x[8:]);report["pending"]=1;log[j]="RECOVER "+json.dumps(report);break
   changed[n]=encoded(r)
  actual=None
  try:semantic(seal(changed),pin)
  except Invalid as e:actual=str(e)
  need(actual==expected,"negative_control:"+name)
  cases.append(dict(name=name,expected=expected,actual=actual,resealed=True))
 return dict(positive=1,negative=8,passed=True,cases=cases)

def raw_controls(files,pin):
 cases=[]
 names=["signal_return","canary_errno","cleanup_errno","target_inode","target_link_count",
        "target_bytes","receipt_crc","receipt_uuid","receipt_state","recovery_repeat"]
 for name in names:
  changed=dict(files);n=locate(changed,"wc-evidence/results.json");r=loads(changed[n])
  if name=="signal_return":
   p=next(p for p in r["cases"][21]["raw"]["processes"] if p["argv"][1]=="kill-flow");p["returncode"]=0
  elif name in ("canary_errno","cleanup_errno"):
   c=r["cases"][12];kind,key=("canary","errno") if name=="canary_errno" else ("cleanup","native_error")
   next(e for e in c["raw"]["worker_events"] if e.get("type")==kind)[key]=0
  elif name.startswith("target_") or name=="recovery_repeat":
   c=r["cases"][27]
   snapshots=[s for s in c["raw"]["snapshots"] if s["label"]=="after-recovery"]
   snapshots += [s for s in c["raw"]["worker_events"] if s.get("label") in ("recovery-1","recovery-2")]
   if name=="recovery_repeat":snapshots=snapshots[-1:]
   for s in snapshots:
    rows=s["entries"];t=rows["dest/book.epub"] if type(rows) is dict else next(x for x in rows if x["path"]=="dest/book.epub")
    if name=="target_inode":t["ino"]+=1
    elif name=="target_link_count":t["nlink"]+=1
    elif name=="target_bytes":
     b=b"X"+bytes.fromhex(t["bytes_hex"])[1:];t["bytes_hex"]=b.hex()
     if "sha256" in t:t["sha256"]=sha(b)
    else:t["nlink"]+=1
  else:
   c=r["cases"][27]
   for s in c["raw"]["snapshots"]:
    if s["label"] not in ("held","after-death","before-recovery"):continue
    t=s["entries"]["root/.receipt"];b=bytearray.fromhex(t["bytes_hex"])
    if name=="receipt_crc":b[60]^=1
    else:
     if name=="receipt_uuid":b[32]^=1
     else:b[64:68]=(3).to_bytes(4,"little")
     b[60:64]=b"\0"*4;b[60:64]=zlib.crc32(b).to_bytes(4,"little")
    t["bytes_hex"]=b.hex();t["sha256"]=sha(b)
  # Keep the redundant raw event transcript consistent, then reseal the package.
  for c in r["cases"]:
   it=iter(c["raw"]["worker_events"])
   c["log"]=["RAW "+json.dumps(next(it)) if x.startswith("RAW ") else x for x in c["log"]]
  changed[n]=encoded(r);actual=None
  try:semantic(seal(changed),pin)
  except Invalid as e:actual=str(e)
  need(actual is not None and actual.startswith("raw_"),"negative_control:"+name)
  cases.append(dict(name=name,actual=actual,resealed=True))
 return dict(positive=1,negative=len(cases),passed=True,cases=cases)
def authenticate(pin):
 meta=api("actions/artifacts/"+str(pin["id"]))
 name=f"webdav-managed-cleanup-{pin['platform']}-{RUN}-1"
 need(meta.get("id")==pin["id"] and meta.get("name")==name and meta.get("expired") is False,"artifact_identity")
 need(meta.get("size_in_bytes")==pin["size"] and meta.get("digest")=="sha256:"+pin["digest"],"artifact_metadata_hash")
 wr=meta["workflow_run"]
 need(wr["id"]==RUN and wr["head_sha"]==TESTS and wr["head_branch"]=="codex/dot-webdav-managed-cleanup-tests-20261031","artifact_source")
 data=subprocess.check_output(["gh","api","repos/"+REPO+"/actions/artifacts/"+str(pin["id"])+"/zip"],timeout=60)
 need(len(data)==pin["size"] and sha(data)==pin["digest"],"outer_hash")
 path=OUT/(pin["platform"]+"-original.zip");path.write_bytes(data)
 need(sha(path.read_bytes())==pin["digest"],"preserved_zip")
 files=unpack(data);package=seal(files)
 (OUT/(pin["platform"]+"-inventory.json")).write_bytes(encoded(package["inventory"]))
 result=semantic(package,pin);result["controls"]=controls(files,pin);result["raw_controls"]=raw_controls(files,pin)
 result.update(platform=pin["platform"],artifact=meta,original_zip_sha256=pin["digest"],
  evidence_integrity_passed=True)
 return result
def main():
 need(os.environ.get("GITHUB_ACTIONS")=="true","Actions_only");scope()
 OUT.mkdir(parents=True,exist_ok=True)
 result={"audit_source":os.environ["GITHUB_SHA"],"audit_run":os.environ["GITHUB_RUN_ID"],
 "audit_attempt":os.environ["GITHUB_RUN_ATTEMPT"],"producer_run":RUN,"producer_attempt":1,
 "tests_source":TESTS,"core_source":CORE,"audit_completed":False,
 "evidence_integrity_passed":False,"critical_evidence_complete":False,"audit_passed":False,
 "product_failure_proven":False,"product_cleanup_passed":False,"formal_acceptance":False,
 "platforms":[],"errors":[]}
 try:
  run=api("actions/runs/"+str(RUN))
  need(run["head_sha"]==TESTS and run["run_attempt"]==1 and run["status"]=="completed" and run["conclusion"]=="success","producer_run")
  jobs=api("actions/runs/"+str(RUN)+"/attempts/1/jobs")["jobs"]
  need({j["id"] for j in jobs}=={p["job"] for p in PINS} and all(j["conclusion"]=="success" for j in jobs),"producer_jobs")
  for ref,path,digest in SOURCE.values():
   b=source_bytes(ref,path);need(sha(b)==digest,"fixed_source_hash")
   dest=OUT/"fixed-source"/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
  for pin in PINS:
   try:result["platforms"].append(authenticate(pin))
   except Exception as e:
    result["errors"].append({"platform":pin["platform"],"error_type":type(e).__name__,
      "reason":str(e) if isinstance(e,Invalid) else "artifact_processing_failed"})
  result["audit_completed"]=True
  result["evidence_integrity_passed"]=len(result["platforms"])==2 and not result["errors"]
  result["critical_evidence_complete"]=result["evidence_integrity_passed"] and all(p["critical_evidence_complete"] for p in result["platforms"])
  result["audit_passed"]=result["critical_evidence_complete"]
 except Exception as e:
  result["errors"].append({"error_type":type(e).__name__,"reason":str(e) if isinstance(e,Invalid) else "setup_or_identity_failed"})
 finally:
  (OUT/"summary.json").write_bytes(encoded(result))
  print("MANAGED-CLEANUP-AUDIT "+json.dumps(result),flush=True)
 return 0 if result["audit_passed"] else 1
if __name__=="__main__":sys.exit(main())
