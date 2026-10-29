"""Actions-only independent audit of C2 original observation ZIPs."""
import hashlib,io,json,math,os,sys,zipfile,statistics
from pathlib import Path,PurePosixPath
assert os.environ.get("GITHUB_ACTIONS")=="true"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch,download_artifact_zip
SOURCE="c3c143c12cb583e33d7b51149d00db5d86806965"
RUN=40975652186
PINS=[
("windows",12941823669,897497,"4f2f680eb0a76ccb7666f13ba88777d3bde114d57710fbf863aca9b84176104d"),
("windows-identity",12942841265,1078,"b3300ab9ae8a64ff9710055a88ba83f028c3547813b9f7b70218fdbec08523d9"),
("gtk",12943100548,2525546,"4e70a9d796a67c97925d554ce5373bc49cb258c871aee36884c93fa2c6ee6f70"),
("gtk-interactions",12943055753,511186,"23d49ef53d0de16017eccdaba49ded32d9cecee9f9f916c4ca7544436eb8b114"),
("gtk-verification",12943055795,1122634,"a5ed857ef5aac9a2d9acf755cc443bec2b9cad46f931326ce15b25342a094554"),
("handoff",12942114409,3179,"89fb470a36a140ab3e7b6132b9ef25ae2127dad9d9711305f83d20e7a24d53c7")]
OUT=Path("build/claude-c2-independent");OUT.mkdir(parents=True,exist_ok=True)
result=dict(accepted=False,source=SOURCE,run=RUN,attempt=1,f08_accepted=False,catalog_changed=False,common_source_acceptance=False)
def sha(x):return hashlib.sha256(x).hexdigest()
def one(files,suffix):
 names=[n for n in files if n==suffix or n.endswith("/"+suffix)]
 assert len(names)==1,(suffix,names)
 return files[names[0]]
def js(files,suffix):return json.loads(one(files,suffix))
def identity(j):
 assert j["source_sha"]==SOURCE
 assert str(j["run_id"])==str(RUN) and str(j["attempt"])=="1"
try:
 r=fetch(f"actions/runs/{RUN}/attempts/1")
 assert (r["head_sha"],r["status"],r["conclusion"],r["run_attempt"])==(SOURCE,"completed","success",1)
 for jobid in (123802906901,123802907080,123804686096,123804757777):
  j=fetch(f"actions/jobs/{jobid}")
  assert (j["run_id"],j["head_sha"],j["conclusion"],j["run_attempt"])==(RUN,SOURCE,"success",1)
 archives={}
 for label,aid,size,digest in PINS:
  p=fetch(f"actions/artifacts/{aid}")
  assert not p["expired"] and (p["size_in_bytes"],p["digest"])==(size,"sha256:"+digest)
  assert (p["workflow_run"]["id"],p["workflow_run"]["head_sha"])==(RUN,SOURCE)
  raw=download_artifact_zip(aid);assert len(raw)==size and sha(raw)==digest
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   names=z.namelist();assert len(names)==len(set(names))
   assert all(not PurePosixPath(n).is_absolute() and ".." not in n.split("/") and "\\" not in n and ":" not in n for n in names)
   archives[label]={i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
 w=archives["windows"];g=archives["gtk"];gi=archives["gtk-interactions"]
 ws=js(w,"perf-windows/summary.json");wb=js(w,"desktop-windows-package/build.json");wi=js(w,"perf-windows-interactions/interactions.json")
 gs=js(g,"summary.json");samples=js(g,"samples.json");launches=js(g,"launches.json")["launches"]
 gr=js(g,"report.json");bundle=js(g,"bundle.json");ins=js(gi,"interaction-summary.json")
 report=js(archives["handoff"],"handoff-report.json")
 for j in (wb,gs,gr,ins,report):identity(j)
 assert (ws.get("source_sha") or ws["environment"]["source_sha"])==SOURCE
 assert wb["sdk_version"]==report["sdk_version"]=="3.42.0" and wb["passed"] is True
 assert not ws["problems"] and wi["faults"]==[] and not ins["problems"]
 assert report["evidence_complete"] is True and report["problems"]==[] and report["f08_accepted"] is False and report["ratified_numeric_budgets"]==0
 assert report["windows_exe_sha256"]==wb["files"]["EXReader.exe"]
 assert len(launches)==gs["launches"]["completed"]==gr["launches"]==32
 assert all(l["process_exit"]==0 and l["vm_hwm_kb"]>0 for l in launches)
 assert gr["accepted"] is True and gr["complete_product"] is False and not gr["problems"]
 assert len(samples["samples"])==len(samples["plan"]) and all(x["outcome"]=="ok" for x in samples["samples"])
 assert set(bundle["files"])|{"bundle.json"}==set(g)
 for name,meta in bundle["files"].items():assert len(g[name])==meta["bytes"] and sha(g[name])==meta["sha256"]
 assert ins["launches"]==ins["planned_launches"]==12 and ins["frame_time_measured"] is False and ins["jump_measured"] is False
 windows={}
 for name,count in (("shelf_scroll_down",30),("shelf_scroll_up",30),("font_bigger",20),("font_smaller",20)):
  values=sorted(wi[name]);assert len(values)==count and all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in values)
  row=[x for x in report["rows"] if x["platform"]=="windows" and x.get("cohort")=="interactions" and x["metric"]==name]
  assert len(row)==1
  expected=(count,values[count//2],values[math.ceil(.95*count)-1],values[-1])
  assert tuple(row[0][k] for k in ("n","p50","p95","max"))==expected
  windows[name]=dict(n=count,p50=expected[1],p95=expected[2],max=expected[3])
 for name,m in gs["metrics"].items():
  assert len(m["samples_ms"])==m["count"] and m["count"]>0
  assert m["max_ms"]==max(m["samples_ms"])
 assert all(row["ratified_threshold"] is None and row["n"]>0 for row in report["rows"])
 result.update(accepted=True,original_artifacts=[dict(label=l,id=a,bytes=b,sha256=s) for l,a,b,s in PINS],
  gtk_launches=32,gtk_interaction_launches=12,windows_interactions=windows,report_rows=len(report["rows"]),
  windows_exe_declared_sha256=wb["files"]["EXReader.exe"],
  scope="original ZIP identities, GTK closed bundle/raw planned outcomes and launch counts, same-source report and Windows raw interaction statistics",
  limitations=["original installed Windows EXE and GTK runtime archive not retained for independent binary reexecution",
               "main Windows metric aggregates reviewed as producer records; not all recomputed from process traces",
               "GTK shelf scroll is host state observation; inter-paint intervals are not frame time",
               "no ratified budget or F08/full-product/physical-device acceptance"])
except Exception as error:result["error"]=repr(error)
finally:
 (OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
 print(json.dumps(result),flush=True)
assert result["accepted"],result.get("error")
