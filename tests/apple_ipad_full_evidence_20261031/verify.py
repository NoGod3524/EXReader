"""One-shot Ubuntu text-only inspection of fixed iPad failure ZIPs. Never runs producer code."""
import hashlib,json,os,re,stat,subprocess,sys,tempfile,zipfile
from collections import deque
from pathlib import Path,PurePosixPath
BASE="94fb236a4a2da87dfbaf4f1dd2a47885d615a230"
RUN=41170540560
BRANCH="codex/dot-apple-ipad-full-evidence-20261031"
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"build/apple-ipad-full-evidence"
OWNED={"tests/apple_ipad_full_evidence_20261031/verify.py",".github/workflows/dot-apple-ipad-full-evidence-20261031.yml","docs/reader-total-progress/DOT_APPLE_IPAD_FULL_EVIDENCE_20261031.md"}
PINS=[
 dict(label="native",job=124448285973,job_name="Team24 Apple native ipad",id=13032504303,name="team24-apple-native-ipad-41170540560-1",size=464812115,sha="b0b85e0f441c0744bb7cd944f1e6c541cc9ac3ae495e645d93ca494bfb76661b"),
 dict(label="organization",job=124448286050,job_name="Apple 3.42 organization ipad",id=13031193956,name="apple-sdk342-supplemental-organization-ipad-41170540560-1",size=134077340,sha="185ea31bb53fff8ee051fa827f6b8530b95f928a4e9571e482bddd19c511e987")]
class Invalid(Exception):pass
def need(ok,why):
 if not ok:raise Invalid(why)
def save(name,value):
 (OUT/name).write_text(json.dumps(value,indent=2)+"\n")
def api(path):
 return json.loads(subprocess.check_output(["gh","api","repos/NoGod3524/EXReader/"+path],timeout=90))
def redacted(text):
 if re.search(r"(?i)\b(?:authorization|bearer|password|secret|access_token|refresh_token|credential)\b",text):return "<sensitive line redacted>"
 text=re.sub(r"\x1b\[[0-9;]*[A-Za-z]","",text)
 text=re.sub(r"https?://\S+","<url>",text)
 text=re.sub(r"(?i)(authorization|password|secret|access_token|refresh_token|credential)(\s*[:=]\s*)\S+",r"\1\2<redacted>",text)
 text=re.sub(r"/Users/[^/\s]+","/Users/<user>",text)
 # Debug trees retain native type, geometry and identifier, not fixture/user labels/values.
 text=re.sub(r"(?:label|value|placeholderValue):\s*'[^']*'","<display-content-redacted>",text)
 return text
def row(n,text):
 need(len(text)<=32768,"text_line_cap")
 return {"line":n,"text":redacted(text)}
def analyze_log(z,info,label):
 need(info.file_size<=256*1024**2,"selected_log_size_cap")
 result={"member":info.filename,"bytes":info.file_size,"segments":[],"global_errors":[]}
 target="testNativeAnnotationPreviewConfirmCancelAndDuplicate"
 recent=deque(maxlen=12);active=None;launch=0;last_t=None;tail=deque(maxlen=16);context_remaining=0
 digest=hashlib.sha256();count=0
 with z.open(info) as stream:
  for n,raw in enumerate(stream,1):
   count+=len(raw);digest.update(raw)
   need(n<=1000000 and len(raw)<=32768,"log_line_or_count_cap")
   text=raw.decode("utf-8","replace").rstrip("\r\n")
   restart="Restarting after" in text
   if restart or "Running tests" in text:launch+=1
   start="Test Case" in text and "started" in text
   if start:
    if active:
     active["end_observed"]=False;active["tail"]=list(tail)
    selected=target in text if label=="native" else "OrganizationUITests" in text
    active=None;last_t=None;tail.clear();context_remaining=0
    if selected:
     active={"launch":launch,"start":row(n,text),"actions":[],"decisions":[],"failures":[],"slowest_observed_gaps":[],"teardown":[],"end_observed":False}
     result["segments"].append(active)
   failure=any(v in text.lower() for v in ("error:","xctassert","assertion failure","exceeded execution time","timed out","background assertion","restarting after"))
   if failure:
    need(len(result["global_errors"])<300,"global_error_cap")
    result["global_errors"].append(row(n,text))
   if active:
    r=row(n,text);tail.append(r)
    if context_remaining:
     active["failure_context"].append(r);context_remaining-=1
    if failure:
     active["failures"].append(r)
     if "failure_context" not in active:active["failure_context"]=list(recent)+[r];context_remaining=25
    m=re.search(r"t\s*=\s*([0-9.]+)s\s+(.*)",text)
    if m:
     t=float(m.group(1))
     action={"line":n,"t":t,"text":redacted(m.group(2))}
     if last_t and t>=last_t["t"]:
      active["slowest_observed_gaps"].append({"seconds":round(t-last_t["t"],6),"before":last_t,"after":action})
     last_t=action
     active["actions"].append(action)
    if "EXR-DECISION" in text or "snapshot-tap-frame" in text:active["decisions"].append(r)
    if any(x in text for x in ("Tear Down","Terminate","Test Case")):active["teardown"].append(r)
    need(len(active["actions"])<=15000 and len(active["decisions"])<=5000,"segment_cap")
    end="Test Case" in text and ("passed" in text or "failed" in text)
    if end or restart:
     active["end"]=r;active["end_observed"]=end;active["tail"]=list(tail);active=None;last_t=None
   recent.append(row(n,text))
 need(count==info.file_size,"log_read_size")
 if active:active["tail"]=list(tail)
 result["sha256"]=digest.hexdigest()
 for segment in result["segments"]:
  segment["slowest_observed_gaps"]=sorted(segment["slowest_observed_gaps"],key=lambda r:r["seconds"],reverse=True)[:30]
  segment["first_error"]=segment["failures"][0] if segment["failures"] else None
  segment["body_end_exact"]="not explicitly marked; last action before first Tear Down is an observation, not inferred completion"
  segment["gap_semantics"]="adjacent log timestamp difference; not exclusive AX call duration; no merging across test/launch boundaries"
 return result
def scrub(value):
 if isinstance(value,str):return redacted(value)
 if isinstance(value,list):return [scrub(v) for v in value]
 if isinstance(value,dict):return {k:scrub(v) for k,v in value.items()}
 return value
def report_json(data,name):
 obj=json.loads(data)
 if not isinstance(obj,dict):return {"member":name,"kind":"non-object"}
 keys=("source_sha","run_id","attempt","platform","suite","accepted","sdk_version","failure")
 result={k:obj[k] for k in keys if k in obj}
 if "source_sha" in obj:
  need(obj["source_sha"]==BASE and str(obj.get("run_id"))==str(RUN) and str(obj.get("attempt"))=="1","inner_result_identity")
 def cases(items):return [{k:c[k] for k in ("name","result","duration") if k in c} for c in items]
 if isinstance(obj.get("phases"),list):
  result["phases"]=[dict(mode=p.get("mode"),accepted=p.get("accepted"),failure=p.get("failure"),cases=cases(p.get("cases",[]))) for p in obj["phases"]]
 if isinstance(obj.get("cases"),list):result["cases"]=cases(obj["cases"])
 # No command argv, dependencies, fixture payload, credentials or environment.
 return {"member":name,"report":scrub(result)}
def inspect(pin):
 meta=api("actions/artifacts/"+str(pin["id"]));job=api("actions/jobs/"+str(pin["job"]))
 need((job["head_sha"],job["run_id"],job["run_attempt"],job["name"],job["status"],job["conclusion"])==(BASE,RUN,1,pin["job_name"],"completed","failure"),"job_identity")
 need((meta["id"],meta["name"],meta["size_in_bytes"],meta["digest"],meta["expired"],meta["workflow_run"]["id"],meta["workflow_run"]["head_sha"])==(pin["id"],pin["name"],pin["size"],"sha256:"+pin["sha"],False,RUN,BASE),"artifact_identity")
 result={"pin":pin,"source":BASE,"run":RUN,"attempt":1,"raw_zip_verified":False,"logs":[],"reports":[],"gaps":[],"xcresult_binary_parsed":False}
 with tempfile.TemporaryDirectory(prefix="ipad-fixed-") as tmp:
  path=Path(tmp)/"original.zip"
  with path.open("wb") as out:
   subprocess.run(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(pin["id"])+"/zip"],stdout=out,check=True,timeout=240)
  need(path.stat().st_size==pin["size"],"zip_bytes")
  h=hashlib.sha256()
  with path.open("rb") as stream:
   for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
  need(h.hexdigest()==pin["sha"],"zip_sha256");result["raw_zip_verified"]=True
  with zipfile.ZipFile(path) as z:
   infos=z.infolist();need(0<len(infos)<=50000,"zip_count")
   need(sum(x.file_size for x in infos)<=8*1024**3,"zip_uncompressed_total")
   seen=set();selected=[]
   for info in infos:
    name=info.filename;p=PurePosixPath(name);canonical=str(p)
    need(name and not p.is_absolute() and ".." not in p.parts and "\\" not in name and ":" not in name and "\x00" not in name,"zip_path")
    need(canonical==name.rstrip("/") and canonical.casefold() not in seen,"zip_alias_or_duplicate");seen.add(canonical.casefold())
    need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"zip_kind")
    need(info.file_size<=1024**3 and info.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),"zip_member")
    if info.is_dir() or ".xcresult/" in name or ".app/" in name:continue
    islog=(p.name=="wave3-native-ui.log") if pin["label"]=="native" else (p.suffix==".log" and "organization" in p.name.lower() and "build" not in p.name.lower())
    if islog:selected.append(info)
    if p.name in ("result.json","sdk342-host-result.json","summary.json") and info.file_size<=8*1024**2:
     result["reports"].append(report_json(z.read(info),name))
   need(0<len(selected)<=8,"required_original_text_log_missing_or_ambiguous")
   for info in selected:result["logs"].append(analyze_log(z,info,pin["label"]))
   need(any(l["segments"] for l in result["logs"]),"required_test_segment_missing")
   result["xcresult_members_present"]=any(".xcresult/" in x.filename for x in infos)
   result["xml_members_present"]=any(x.filename.lower().endswith(".xml") for x in infos)
   if result["xml_members_present"]:result["gaps"].append("XML members present but not parsed; this bounded parser supports selected original logs and JSON only.")
   result["gaps"].append("Ubuntu does not decode xcresult object/attachment binaries; absent exported issue/activity fields remain unavailable.")
   if not any(s["first_error"] for l in result["logs"] for s in l["segments"]):
    result["gaps"].append("Selected original text segments contain no explicit first error; do not infer one from duration or exit 65.")
 result["diagnostic_complete"]=True
 save(pin["label"]+"-evidence.json",result)
 for log in result["logs"]:
  for segment in log["segments"]:
   print("IPAD_SEGMENT "+json.dumps({"label":pin["label"],"member":log["member"],"start":segment["start"],"first_error":segment["first_error"],"end":segment.get("end"),"tail":segment.get("tail"),"failure_context":segment.get("failure_context",[]),"slowest_observed_gaps":segment["slowest_observed_gaps"][:12],"decisions":segment["decisions"]}),flush=True)
 return result
def main():
 need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform=="linux","Actions_Ubuntu_only")
 git=lambda *a:subprocess.check_output(["git",*a],text=True).strip()
 need(git("rev-parse","HEAD")==os.environ["GITHUB_SHA"] and os.environ["GITHUB_REF_NAME"]==BRANCH,"audit_source_branch")
 need(set(git("diff","--name-only",BASE,"HEAD").splitlines())==OWNED,"three_paths_only")
 OUT.mkdir(parents=True,exist_ok=True)
 receipt={"source":BASE,"run":RUN,"attempt":1,"audit_source":os.environ["GITHUB_SHA"],"audit_run":os.environ["GITHUB_RUN_ID"],"audit_attempt":os.environ["GITHUB_RUN_ATTEMPT"],"product_acceptance":False,"formal_acceptance":False,"artifacts":[],"errors":[]}
 try:
  run=api("actions/runs/"+str(RUN))
  need((run["head_sha"],run["run_attempt"],run["status"],run["conclusion"])==(BASE,1,"completed","failure"),"producer_run")
  for pin in PINS:
   try:
    r=inspect(pin);receipt["artifacts"].append({"label":pin["label"],"pin":pin,"raw_zip_verified":r["raw_zip_verified"],"diagnostic_complete":r["diagnostic_complete"],"gaps":r["gaps"]})
   except Exception as e:receipt["errors"].append({"label":pin["label"],"type":type(e).__name__,"reason":str(e) if isinstance(e,Invalid) else "read_or_parse_failure"})
 except Exception as e:receipt["errors"].append({"type":type(e).__name__,"reason":str(e) if isinstance(e,Invalid) else "identity_setup_failure"})
 receipt["diagnostic_complete"]=len(receipt["artifacts"])==2 and not receipt["errors"]
 save("receipt.json",receipt);print("IPAD_EVIDENCE_RECEIPT "+json.dumps(receipt),flush=True)
 return 0 if receipt["diagnostic_complete"] else 1
if __name__=="__main__":sys.exit(main())
