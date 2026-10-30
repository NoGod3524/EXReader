"""Actions-only inspection of two pinned focused annotation failures; no product rerun or acceptance."""
import hashlib, io, json, math, os, re, stat, subprocess, sys, traceback, zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "darwin"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_parallel_integration import fetch, download_artifact_zip
SOURCE = "8ec841fe5127b810ad37f14662de51650c0b51c2"
RUN, ATTEMPT = 41139685986, 1
PINS = [
 ("iphone",124352004051,"Focused original five iphone",13019975357,"focused-original-five-iphone",183379104,"d12bab12756569b399360525c7f467ab7d73cc43f463dc1640f5aa6cfaf92be3"),
 ("ipad",124352004002,"Focused original five ipad",13019171221,"focused-original-five-ipad",186815394,"2f440cc587d1b35912fd1f3002f6bb0d5fbfacb629431ebbd165f90a65ee2273"),
]
OUT = ROOT / "build/dot-apple-query-diagnose"
OUT.mkdir(parents=True, exist_ok=True)
receipt = dict(producer_source=SOURCE, run=RUN, attempt=ATTEMPT, inspection_source=os.environ["GITHUB_SHA"], diagnostic_only=True, product_acceptance=False, artifacts=[], errors=[])
def save(path, obj):
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps(obj, indent=2) + "\n")
def inspect(pin):
 label, jid, jname, aid, stem, size, digest = pin
 dest = OUT / label
 dest.mkdir(parents=True, exist_ok=True)
 job, meta = fetch(f"actions/jobs/{jid}"), fetch(f"actions/artifacts/{aid}")
 save(dest/"job.json", job); save(dest/"metadata.json",meta)
 assert (job["head_sha"],job["run_id"],job["run_attempt"],job["name"],job["status"],job["conclusion"]) == (SOURCE,RUN,ATTEMPT,jname,"completed","failure")
 assert (meta["workflow_run"]["head_sha"],meta["workflow_run"]["id"],meta["name"],meta["size_in_bytes"],meta["digest"],meta["expired"]) == (SOURCE,RUN,f"{stem}-{RUN}-{ATTEMPT}",size,"sha256:"+digest,False)
 raw = download_artifact_zip(aid)
 assert len(raw)==size and hashlib.sha256(raw).hexdigest()==digest
 entry=dict(label=label,job=jid,artifact=aid,bytes=size,sha256=digest,raw_zip_verified=True)
 receipt["artifacts"].append(entry)
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  infos=z.infolist(); names=[x.filename for x in infos]
  assert len(names)==len(set(names)) and sum(x.file_size for x in infos)<4*1024**3
  canonical=set()
  for item in infos:
   p=PurePosixPath(item.filename)
   assert not p.is_absolute() and ".." not in p.parts and "\\" not in item.filename and ":" not in item.filename
   key=str(p); assert key not in canonical; canonical.add(key)
   assert stat.S_IFMT(item.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not item.flag_bits&1
  save(dest/"members.json",[dict(name=i.filename,bytes=i.file_size) for i in infos])
  selected=[]
  for item in infos:
   if item.is_dir(): continue
   name=item.filename
   bundle = any(part.endswith(".xcresult") and part=="wave3.xcresult" for part in PurePosixPath(name).parts)
   regular = name.endswith((".log",".json",".txt")) and ".xcresult/" not in name
   if not (bundle or regular): continue
   assert item.file_size < 256*1024**2
   data=z.read(name); target=dest/"extracted"/name
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
   selected.append(dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
   if regular and name.endswith(".json"):
    try:
     obj=json.loads(data)
     if isinstance(obj,dict) and ("failures" in obj or "accepted" in obj):
      print("PRODUCER_REPORT "+label+" "+name+" "+json.dumps({k:obj[k] for k in ("accepted","failures","failure","source_sha","run_id","attempt") if k in obj}),flush=True)
    except (ValueError,UnicodeError): pass
   if regular and name.endswith(".log"):
    lines=data.decode("utf-8","replace").splitlines()
    matches=[]
    for n,line in enumerate(lines):
     if any(s in line for s in ("error:","XCTAssert","Assertion Failure","Exceeded","Restarting after","Test Case","Timed out")):
      matches.append(dict(line=n+1,context=lines[max(0,n-15):min(len(lines),n+25)]))
    save(dest/("contexts-"+hashlib.sha256(name.encode()).hexdigest()[:12]+".json"),matches)
  save(dest/"extracted-hashes.json",selected)
 if label in ("iphone","ipad"):
  bundles=list((dest/"extracted").rglob("wave3.xcresult"))
  assert len(bundles)==1,("expected one original xcresult",bundles)
  bundle=bundles[0]
  for kind in ("summary","tests"):
   result=subprocess.run(["xcrun","xcresulttool","get","test-results",kind,"--path",str(bundle),"--format","json"],capture_output=True,text=True,timeout=120)
   (dest/(kind+".json")).write_text(result.stdout);(dest/(kind+".stderr.txt")).write_text(result.stderr)
   assert result.returncode==0,(kind,result.returncode)
  result=subprocess.run(["xcrun","xcresulttool","get","object","--legacy","--path",str(bundle),"--format","json"],capture_output=True,text=True,timeout=120)
  assert result.returncode==0,result.stderr
  obj=json.loads(result.stdout);save(dest/"legacy.json",obj)
  print("FIRST_ISSUES "+label+" "+json.dumps(obj.get("issues",{})),flush=True)
  pending=[]; seen=set()
  def refs(value):
   if isinstance(value,dict):
    for key,val in value.items():
     if key in ("testsRef","summaryRef") and isinstance(val,dict):
      ident=val.get("id",{}).get("_value")
      if ident and ident not in seen and ident not in pending: pending.append(ident)
     refs(val)
   elif isinstance(value,list):
    for val in value: refs(val)
  refs(obj)
  while pending:
   ident=pending.pop(0)
   if ident in seen: continue
   assert len(seen)<64,"bounded xcresult reference traversal exceeded"
   seen.add(ident)
   result=subprocess.run(["xcrun","xcresulttool","get","object","--legacy","--path",str(bundle),"--id",ident,"--format","json"],capture_output=True,text=True,timeout=120)
   assert result.returncode==0,result.stderr
   node=json.loads(result.stdout)
   save(dest/"activities"/(hashlib.sha256(ident.encode()).hexdigest()+".json"),node)
   refs(node)
  entry["xcresult_reference_objects"]=len(seen)
  result=subprocess.run(["xcrun","xcresulttool","export","attachments","--path",str(bundle),"--output-path",str(dest/"attachments")],capture_output=True,text=True,timeout=120)
  save(dest/"attachment-export.json",dict(exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
  assert result.returncode==0,result.stderr
def unwrap(v):
 if isinstance(v,dict):
  if "_value" in v:return v["_value"]
  if "_values" in v:return [unwrap(x) for x in v["_values"]]
  return {k:unwrap(x) for k,x in v.items() if k!="_type"}
 if isinstance(v,list):return [unwrap(x) for x in v]
 return v
def timestamp(v):
 try:
  n=float(v)
 except (ValueError,TypeError):
  try:n=datetime.fromisoformat(str(v).replace("Z","+00:00")).timestamp()
  except (ValueError,TypeError):return None
 return n if math.isfinite(n) else None
def interval(a):
 s,e=timestamp(a.get("start")),timestamp(a.get("finish"))
 return (s,e) if s is not None and e is not None and e>=s else None
def union_length(intervals):
 merged=[]
 for s,e in sorted(intervals):
  if merged and s<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],e)
  else:merged.append([s,e])
 return sum(e-s for s,e in merged)
def walk_activity(a,parent,path,depth,rows):
 title=a.get("title","")
 here=path+[title]
 iv=interval(a); kids=a.get("subactivities",[])
 if not isinstance(kids,list):kids=[]
 clipped=[]
 if iv:
  for child in kids:
   ci=interval(child)
   if ci and min(iv[1],ci[1])>=max(iv[0],ci[0]):clipped.append((max(iv[0],ci[0]),min(iv[1],ci[1])))
 row=dict(index=len(rows),parent=parent,path=here,depth=depth,title=title,start=a.get("start"),finish=a.get("finish"),inclusive=(iv[1]-iv[0]) if iv else None,exclusive=max(0,iv[1]-iv[0]-union_length(clipped)) if iv else None)
 rows.append(row)
 for child in kids:walk_activity(child,row["index"],here,depth+1,rows)
def cases(node):
 if isinstance(node,dict):
  if isinstance(node.get("activitySummaries"),list):yield node
  for v in node.values():yield from cases(v)
 elif isinstance(node,list):
  for v in node:yield from cases(v)
def analyze(label):
 dest=OUT/label
 target="testNativeAnnotationPreviewConfirmCancelAndDuplicate"
 logname="wave3-native-ui.log"
 activity_cases=[]
 for i in sorted((dest/"activities").glob("*.json")):
  if i.is_file():
   obj=unwrap(json.loads(i.read_text()))
   for case in cases(obj):
    ident=str(case.get("testIdentifier",case.get("name",case.get("testName",""))))
    rows=[]
    for a in case["activitySummaries"]:walk_activity(a,None,[],0,rows)
    failures=case.get("failureSummaries",[])
    activity_cases.append(dict(member=str(i.relative_to(OUT)),identifier=ident,failures=failures,activities=rows))
 save(OUT/(label+"-activities.json"),activity_cases)
 selected=[c for c in activity_cases if target in c["identifier"]]
 if not selected:
  print("CASE_SELECTION_UNCERTAIN "+label+" "+json.dumps([c["identifier"] for c in activity_cases]),flush=True)
  raise AssertionError("target annotation activities missing; preserve evidence without substitution")
 for case in selected:
  rows=case["activities"]
  print("CASE_FAILURES "+label+" "+json.dumps(dict(identifier=case["identifier"],failures=case["failures"])),flush=True)
  ranked=sorted((r for r in rows if r["inclusive"] is not None),key=lambda r:r["inclusive"],reverse=True)
  print("SLOWEST_ACTIVITIES "+label+" "+json.dumps(ranked[:20]),flush=True)
  exclusive=sorted((r for r in rows if r["exclusive"] is not None),key=lambda r:r["exclusive"],reverse=True)
  print("SLOWEST_EXCLUSIVE "+label+" "+json.dumps(exclusive[:20]),flush=True)
 logs=list((dest/"extracted").rglob(logname))
 assert len(logs)==1,(label,logs)
 lines=logs[0].read_text(errors="replace").splitlines()
 segments=[];segment=None;launch=0;active=False
 for n,line in enumerate(lines,1):
  if "Restarting after" in line or "Running tests" in line:
   launch+=1
  if "Test Case" in line and "started" in line:
   active=target in line
   if active:
    segment=dict(launch=launch,start_line=n,lines=[],markers=[],timed_actions=[],failure_context=[])
    segments.append(segment)
  if active and segment is not None:
   segment["lines"].append(dict(line=n,text=line))
   match=re.search(r"t\s*=\s*([0-9.]+)s\s+(.*)",line)
   if match:
    t=float(match.group(1))
    segment["timed_actions"].append(dict(line=n,t=t,text=match.group(2)))
   if any(m in line for m in ("font-distinct-applied","font-invalid-preserved","font-reader-exit-released","font-lease-released","annotation","MARK")):
    segment["markers"].append(dict(line=n,text=line))
   if any(m in line.lower() for m in ("exceeded","timed out","timeout","restarting after","error:","assertion failure")):
    segment["failure_context"].append(dict(line=n,context=lines[max(0,n-6):n+5]))
   if "Restarting after" in line or ("Test Case" in line and ("passed" in line or "failed" in line)):
    active=False
 save(OUT/(label+"-log-segments.json"),segments)
 assert segments,"target annotation log segment missing"
 for segment in segments:
  actions=segment["timed_actions"];gaps=[]
  for a,b in zip(actions,actions[1:]):
   if b["t"]>=a["t"]:gaps.append(dict(seconds=b["t"]-a["t"],before=a,after=b))
  before240=[g for g in gaps if g["before"]["t"]<240]
  print("LOG_SEGMENT "+label+" "+json.dumps(dict(launch=segment["launch"],start_line=segment["start_line"],markers=segment["markers"],failure_context=segment["failure_context"],slowest_gaps=sorted(gaps,key=lambda x:x["seconds"],reverse=True)[:10],slowest_pre240_gaps=sorted(before240,key=lambda x:x["seconds"],reverse=True)[:10],tail=segment["lines"][-20:])),flush=True)
 receipt.setdefault("timelines",[]).append(dict(label=label,activity_cases=len(activity_cases),selected_cases=len(selected),log_segments=len(segments)))
run=fetch(f"actions/runs/{RUN}")
save(OUT/"producer-run.json",run)
assert (run["head_sha"],run["run_attempt"],run["status"],run["conclusion"])==(SOURCE,ATTEMPT,"completed","failure")
for pin in PINS:
 try:
  inspect(pin)
  analyze(pin[0])
 except Exception as error:
  receipt["errors"].append(dict(label=pin[0],type=type(error).__name__,message=str(error),traceback=traceback.format_exc()))
  save(OUT/"receipt.json",receipt)
save(OUT/"receipt.json",receipt)
print("DIAGNOSTIC_RECEIPT "+json.dumps(receipt),flush=True)
assert not receipt["errors"],"Retain diagnostic errors; no product acceptance"
