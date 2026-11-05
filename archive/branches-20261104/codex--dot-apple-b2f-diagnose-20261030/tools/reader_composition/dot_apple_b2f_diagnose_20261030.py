"""Actions-only phase 2: read pinned diagnostic evidence; never rerun a product."""
import hashlib, io, json, math, os, re, stat, sys, zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
assert os.environ.get("GITHUB_ACTIONS") == "true"
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
from check_parallel_integration import fetch, download_artifact_zip
AID=13014050688
SIZE=8073242
DIGEST="053ad7636b08170c1ad3f3452468471e98a9ac5117b826f6da9951b0d544fb8b"
SOURCE="d498f4fc283cddcead37f0ff99c52688a6fcfd7c"
OUT=ROOT/"build/dot-apple-b2f-diagnose"
OUT.mkdir(parents=True,exist_ok=True)
def save(name,obj):
 (OUT/name).write_text(json.dumps(obj,indent=2)+"\n")
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
meta=fetch(f"actions/artifacts/{AID}")
run=fetch("actions/runs/41132326112")
assert (meta["size_in_bytes"],meta["digest"],meta["expired"],meta["workflow_run"]["id"],meta["workflow_run"]["head_sha"],meta["name"])==(SIZE,"sha256:"+DIGEST,False,41132326112,SOURCE,"dot-apple-b2f-diagnose-41132326112-1")
assert (run["head_sha"],run["run_attempt"],run["conclusion"])==(SOURCE,1,"success")
save("input-metadata.json",meta)
raw=download_artifact_zip(AID)
assert len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==DIGEST
results=[]
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 infos=z.infolist()
 assert len(infos)==len({i.filename for i in infos}) and sum(i.file_size for i in infos)<512*1024**2
 canonical=set()
 for i in infos:
  p=PurePosixPath(i.filename)
  assert not p.is_absolute() and ".." not in p.parts and "\\" not in i.filename and ":" not in i.filename
  assert str(p) not in canonical;canonical.add(str(p))
  assert stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not i.flag_bits&1
 original_receipt=json.loads(z.read("receipt.json"))
 assert (original_receipt["producer_source"],original_receipt["run"],original_receipt["attempt"],original_receipt["errors"])==("b2f4e6e1363d0ee20fcb87a6acef548e0624318a",41093873914,1,[])
 assert len(original_receipt["artifacts"])==4 and all(a["raw_zip_verified"] for a in original_receipt["artifacts"])
 save("original-receipt.json",original_receipt)
 for label,target,logname in (("iphone","testNativeAnnotationPreviewConfirmCancelAndDuplicate","wave3-native-ui.log"),("font-ipad","testDistinctFontInvalidRollbackLeaseAndReopen","font-native-ui.log")):
  activity_cases=[]
  for i in infos:
   if i.filename.startswith(label+"/activities/") and i.filename.endswith(".json"):
    obj=unwrap(json.loads(z.read(i)))
    for case in cases(obj):
     ident=str(case.get("testIdentifier",case.get("name",case.get("testName",""))))
     rows=[]
     for a in case["activitySummaries"]:walk_activity(a,None,[],0,rows)
     failures=case.get("failureSummaries",[])
     activity_cases.append(dict(member=i.filename,identifier=ident,failures=failures,activities=rows))
  save(label+"-activities.json",activity_cases)
  selected=[c for c in activity_cases if target in c["identifier"]]
  if not selected:
   print("CASE_SELECTION_UNCERTAIN "+label+" "+json.dumps([c["identifier"] for c in activity_cases]),flush=True)
   selected=activity_cases
  for case in selected:
   rows=case["activities"]
   print("CASE_FAILURES "+label+" "+json.dumps(dict(identifier=case["identifier"],failures=case["failures"])),flush=True)
   ranked=sorted((r for r in rows if r["inclusive"] is not None),key=lambda r:r["inclusive"],reverse=True)
   print("SLOWEST_ACTIVITIES "+label+" "+json.dumps(ranked[:20]),flush=True)
   exclusive=sorted((r for r in rows if r["exclusive"] is not None),key=lambda r:r["exclusive"],reverse=True)
   print("SLOWEST_EXCLUSIVE "+label+" "+json.dumps(exclusive[:20]),flush=True)
  logs=[i.filename for i in infos if i.filename.startswith(label+"/extracted/") and PurePosixPath(i.filename).name==logname]
  assert len(logs)==1,(label,logs)
  lines=z.read(logs[0]).decode("utf-8","replace").splitlines()
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
  save(label+"-log-segments.json",segments)
  for segment in segments:
   actions=segment["timed_actions"];gaps=[]
   for a,b in zip(actions,actions[1:]):
    if b["t"]>=a["t"]:gaps.append(dict(seconds=b["t"]-a["t"],before=a,after=b))
   before240=[g for g in gaps if g["before"]["t"]<240]
   print("LOG_SEGMENT "+label+" "+json.dumps(dict(launch=segment["launch"],start_line=segment["start_line"],markers=segment["markers"],failure_context=segment["failure_context"],slowest_gaps=sorted(gaps,key=lambda x:x["seconds"],reverse=True)[:10],slowest_pre240_gaps=sorted(before240,key=lambda x:x["seconds"],reverse=True)[:10],tail=segment["lines"][-20:])),flush=True)
  results.append(dict(label=label,activity_cases=len(activity_cases),selected_cases=len(selected),log_segments=len(segments)))
save("receipt.json",dict(input_artifact=AID,input_size=SIZE,input_sha256=DIGEST,input_run=41132326112,input_attempt=1,diagnostic_only=True,product_acceptance=False,results=results))
print("TIMELINE_RECEIPT "+json.dumps(results),flush=True)
