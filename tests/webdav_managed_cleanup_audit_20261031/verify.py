#!/usr/bin/env python3
"""Actions-only authentication of two fixed historical artifacts; never runs their code."""
import base64, copy, hashlib, io, json, os, re, stat, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath

REPO="NoGod3524/EXReader"
BASE="d69bae312fd0791dac119509437fb29abc92a25c"
TESTS="12da717cef38c90ae2097e52d33f7b3682aef043"
CORE="dba079b550f9ec83054e6b7b0b7475f43bc1739f"
PRODUCER_BASE="666d0d81730ac3cf7caea52b05ca1f01b1d183b1"
RUN=41170057297
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"build/managed-cleanup-audit"
OWNED={"tests/webdav_managed_cleanup_audit_20261031/verify.py",
".github/workflows/dot-webdav-managed-cleanup-audit-20261031.yml",
"docs/reader-total-progress/DOT_WEBDAV_MANAGED_CLEANUP_AUDIT_20261031.md"}
PINS=[
 dict(platform="Linux",system="Linux",machine="x86_64",euid=1001,job=124445872128,
 id=13030965993,size=86807,digest="25b95345c6607c6fc0fadd54c95bdd62c515bcc460498664bddabdf88c88b442",
 archive="276bb6c488e6ed916e87d77a3e062e1e1f650d89cb1a12229ac75cf0a20bfdd3",
 consumer="2a527a976611c260d999a67c685ef13dcac5db62104ea259108cb02d01cf1af7",
 hookworker="038d520caf990618f371f8c3396d824720863d526c2ced207b8f88c51e63e217"),
 dict(platform="macOS",system="Darwin",machine="arm64",euid=501,job=124445872050,
 id=13030352879,size=74101,digest="72ac0c1e56854a06669e01b7e9714605562c03275e482853d0088901f8d566fe",
 archive="89a9e40095ee94197c979c5291f8a846257cef0c36a9f120c89095d7e4d4698a",
 consumer="55436fa7faccf0c1ab26d77a2e4f7c0e08f76636d4e8ee3b250e2d4081bcf89b",
 hookworker="de8aa56936f14230e818979df8c83ffee33e4ae6747218b4a8dc533b2aeee0ba")]
SOURCE={
 "build/core/extras/webdav-cleanup/src/cleanup_posix.c":(CORE,"extras/webdav-cleanup/src/cleanup_posix.c","2ebb5a27b62998b6fc185277a04d81b506871880f7edb3860923f775dfb70590"),
 "build/core/extras/webdav-cleanup/include/exr_webdav_cleanup.h":(CORE,"extras/webdav-cleanup/include/exr_webdav_cleanup.h","5c683d07eb87c21d521bab95b0fc56738da12975ebbc022257ef338498edd979"),
 "tests/webdav_managed_cleanup_20261031/worker.c":(TESTS,"tests/webdav_managed_cleanup_20261031/worker.c","a0dfb8cdb620051e8beb5592afb3b27624ccb2b17c14a09a4557e6b00b1e4d30"),
 "tests/webdav_managed_cleanup_20261031/run.py":(TESTS,"tests/webdav_managed_cleanup_20261031/run.py","ec16b703e61b7de0b6ece18e43731b99a1228b7b2b6151cc018f6fb0506661ba")}
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
 matrix=get(files,"wc-logs/matrix.log").decode().splitlines()
 need([x for x in matrix if x.startswith("PASS ")]==["PASS "+n for n in NAMES],"matrix_cases")
 return {"producer_case_execution_authenticated":True,"cases":30,
 "source_bound_assertions_authenticated":True,"raw_recovery_reports_recomputed":10,
 "critical_evidence_complete":False,
 "gaps":[
 {"requirement":"independent target preservation verification","cases":[13,27,28,29],
  "missing":"before/after dev,ino,sha256,nlink were checked in producer memory but not serialized",
  "classification":"independent_recomputation_unavailable_not_product_failure"},
 {"requirement":"independent actual EACCES verification","cases":[13],
  "missing":"actual canary unlink errno and cleanup errno/mode observations are not logged; pinned C CHECK and PASS only",
  "classification":"source_bound_assertion_only_not_product_failure"},
 {"requirement":"independent process death verification","cases":list(range(22,31)),
  "missing":"HELD markers retained, but actual kill returncode/PID and before/after disk snapshot not serialized",
  "classification":"source_bound_runner_assertion_only_not_product_failure"}],
 "disclosed_contract_amendment":{"case":30,"difference":"valid successor .receipt.next is discarded and old receipt reopened; frozen handoff said refuse every .next",
 "observed_constraints":"CRC/structural decode, matching UUID/root inode, next generation=current+1; no predecessor hash or full old/new slot transition comparison in open",
 "producer_document_discloses_amendment":True,"approval_origin_independently_verified":False},
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
 result=semantic(package,pin);result["controls"]=controls(files,pin)
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
  result["audit_passed"]=result["evidence_integrity_passed"] and all(p["critical_evidence_complete"] for p in result["platforms"])
 except Exception as e:
  result["errors"].append({"error_type":type(e).__name__,"reason":str(e) if isinstance(e,Invalid) else "setup_or_identity_failed"})
 finally:
  (OUT/"summary.json").write_bytes(encoded(result))
  print("MANAGED-CLEANUP-AUDIT "+json.dumps(result),flush=True)
 return 0 if result["audit_passed"] else 1
if __name__=="__main__":sys.exit(main())
