"""Actions-only independent review of the focused GTK scroll repair."""
import hashlib,io,json,os,sys,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get("GITHUB_ACTIONS")=="true"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch,download_artifact_zip
BIND=json.loads(Path(os.environ["CLOSURE_PINS"]).read_text())["c2"]
SOURCE=BIND["source"];RUN=BIND["run"]
LABELS={"gtk":"main","gtk-interactions":"interactions","gtk-verification":"producer-verification"}
PINS=[(LABELS[p["label"]],p["artifact"],p["size"],p["digest"]) for p in BIND["artifacts"] if p["label"] in LABELS]
OUT=Path("build/closure-gtk-independent");OUT.mkdir(parents=True,exist_ok=True)
result=dict(accepted=False,source=SOURCE,producer_run=RUN,attempt=1,f08_accepted=False,common_source_acceptance=False,catalog_changed=False)
def sha(data):return hashlib.sha256(data).hexdigest()
try:
 run=fetch(f"actions/runs/{RUN}/attempts/1")
 assert (run["head_sha"],run["run_attempt"],run["conclusion"])==(SOURCE,1,"success")
 for jid in BIND["jobs"]:
  j=fetch(f"actions/jobs/{jid}");assert (j["head_sha"],j["run_id"],j["run_attempt"],j["status"],j["conclusion"])==(SOURCE,RUN,1,"completed","success")
 archives={}
 for label,aid,size,digest in PINS:
  meta=fetch(f"actions/artifacts/{aid}")
  assert (meta["workflow_run"]["head_sha"],meta["workflow_run"]["id"],meta["size_in_bytes"],meta["digest"],meta["expired"])==(SOURCE,RUN,size,"sha256:"+digest,False)
  raw=download_artifact_zip(aid);assert len(raw)==size and sha(raw)==digest
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   names=z.namelist();assert len(names)==len(set(names))
   assert all(not PurePosixPath(n).is_absolute() and ".." not in n.split("/") and "\\" not in n and ":" not in n for n in names)
   files={i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
  archives[label]=files
  if label in ("main","interactions"):
   bundle=json.loads(files["bundle.json"])
   declared=set(bundle["files"])|{"bundle.json"}
   # Original interaction runner writes its derived summary after frozen write_evidence().
   # Bind that one summary separately to raw plans/statistics below; no unknown extra files.
   if label=="interactions":declared.add("interaction-summary.json")
   assert declared==set(files),(label,sorted(set(files)-declared),sorted(declared-set(files)))
   for name,record in bundle["files"].items():assert len(files[name])==record["bytes"] and sha(files[name])==record["sha256"]
 main=archives["main"];inter=archives["interactions"]
 report=json.loads(main["report.json"]);summary=json.loads(main["summary.json"]);samples=json.loads(main["samples.json"])
 assert report["accepted"] is True and report["complete_product"] is False and not report["problems"]
 assert report["source_sha"]==summary["source_sha"]==samples["source_sha"]==SOURCE
 assert str(report["run_id"])==str(summary["run_id"])==str(RUN) and str(report["attempt"])==str(summary["attempt"])=="1"
 assert report["launches"]==summary["launches"]["completed"]==32
 assert len(samples["samples"])==len(samples["plan"])==520 and all(x["outcome"]=="ok" for x in samples["samples"])
 ins=json.loads(inter["interaction-summary.json"]);items=json.loads(inter["samples.json"])
 assert (ins["source_sha"],str(ins["run_id"]),str(ins["attempt"]),ins["launches"],ins["planned_launches"])==(SOURCE,str(RUN),"1",12,12)
 expected=dict(startup_shelf_rows=6,shelf_scroll_down=36,shelf_scroll_up=36,resume_frame_painted=6,font_bigger=18,font_smaller=18,page_turn_forward=120)
 assert ins["expected_counts"]==expected and not ins["problems"] and ins["frame_time_measured"] is False
 assert len(items["samples"])==len(items["plan"])==240 and all(x["outcome"]=="ok" for x in items["samples"])
 for name,count in expected.items():
  rows=[x for x in items["samples"] if x["metric"]==name]
  assert len(rows)==count==ins["metrics"][name]["n"] and sorted(x["latency_ms"] for x in rows)==sorted(ins["metrics"][name]["samples"])
 traces=json.loads(inter["scroll-input-traces.json"])
 ready=[x for x in traces if x["phase"]=="interior-ready"];measured=[x for x in traces if x["phase"]=="measured-scroll"]
 assert len(ready)==6 and len(measured)==72
 assert all(x["details"]["state"]["host"]["shelf_before"] and x["details"]["state"]["host"]["shelf_after"] for x in ready)
 for trace in measured:
  before=trace["details"]["baseline"]["host"]["shelf_top_id"]
  assert any(e["state"]["host"].get("shelf_top_id")!=before for e in trace["events"])
 result.update(accepted=True,original_artifacts=[dict(label=l,id=a,bytes=b,sha256=d) for l,a,b,d in PINS],
  main_launches=32,main_samples=520,interaction_launches=12,interaction_samples=240,measured_scroll_traces=72,
  scope="focused GTK repair: exact original ZIPs, closed bundles, source/attempt, complete retained raw plans and interior-prepared native scroll observations",
  frame_time_measured=False,windows_checked_in_separate_c2_audit=True)
except Exception as error:result["error"]=repr(error)
finally:
 (OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
 print(json.dumps(result),flush=True)
assert result["accepted"],result.get("error")
