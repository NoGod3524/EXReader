"""Actions-only inspection of the exact failed candidate interaction ZIP."""
import hashlib,io,json,os,re,sys,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get("GITHUB_ACTIONS")=="true"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch,download_artifact_zip
SOURCE="fd592cd97afc759df764de7face5d1e3b5ec87ee";RUN=40977062625;AID=12943801389;SIZE=511100
SHA="1a481dc59aac75532173ec77271031e9a2052ea620f221767814f204ae315fa5"
out=Path("build/closure-perf-diagnosis");out.mkdir(parents=True,exist_ok=True)
p=fetch(f"actions/artifacts/{AID}")
assert p["workflow_run"]["head_sha"]==SOURCE and p["workflow_run"]["id"]==RUN
assert p["size_in_bytes"]==SIZE and p["digest"]=="sha256:"+SHA and not p["expired"]
raw=download_artifact_zip(AID);assert len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==SHA
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 names=z.namelist();assert len(names)==len(set(names))
 assert all(not PurePosixPath(n).is_absolute() and ".." not in n.split("/") and "\\" not in n for n in names)
 files={i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
def one(suffix):
 found=[n for n in files if n==suffix or n.endswith("/"+suffix)];assert len(found)==1,(suffix,found)
 return json.loads(files[found[0]])
summary=one("interaction-summary.json");assert summary["source_sha"]==SOURCE and str(summary["run_id"])==str(RUN)
samples=one("samples.json")["samples"];failures=[s for s in samples if s["outcome"]!="ok"]
launches={r["launch"] for r in failures}
result=dict(source=SOURCE,producer_run=RUN,artifact=AID,bytes=SIZE,sha256=SHA,acceptance=False,problems=failures,files=list(files),traces={})
print("FAILED_SAMPLES "+json.dumps(failures),flush=True)
print("RETAINED_FILES "+json.dumps(list(files)),flush=True)
for launch in one("launches.json")["launches"]:
 if launch["launch"] in launches:
  print("FINAL_LAUNCH "+json.dumps({k:launch.get(k) for k in ("launch","geometry","final_state","state_writes","paint_count")}),flush=True)
for name,data in files.items():
 if not name.endswith(".jsonl"):continue
 match=re.search(r"launch[-_]?([0-9]+)",name)
 if match and int(match.group(1)) not in launches:continue
 changes=[];previous=None;firstkeys=None
 for index,line in enumerate(data.splitlines()):
  try:v=json.loads(line)
  except (ValueError,UnicodeError):continue
  if firstkeys is None:firstkeys=list(v)
  state=v.get("state") or {};host=state.get("host") or v.get("host")
  if not isinstance(host,dict):continue
  top=host.get("shelf_top_id")
  if top!=previous:
   changes.append(dict(line=index,at=v.get("at"),host=host));previous=top
 result["traces"][name]=dict(first_keys=firstkeys,changes=changes)
 print("TRACE "+name+" "+json.dumps(result["traces"][name]),flush=True)
(out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
