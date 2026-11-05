"""Actions-only independent acceptance of this one exact closure source."""
import hashlib,io,json,os,re,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get("GITHUB_ACTIONS")=="true"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch,download_artifact_zip
SOURCE="PENDING_REPAIR_SOURCE"
RUNS=dict(c1=0,c3=0,recovery=0,qualification=0,record=0,c2=0,apple=0)
OUT=Path("build/closure-independent");OUT.mkdir(parents=True,exist_ok=True)
result=dict(accepted=False,source=SOURCE,producer_runs=RUNS,catalog_changed=False,full_product_accepted=False,apple_full_accepted=False)
allpins=[]
def sha(data):return hashlib.sha256(data).hexdigest()
def one(files,suffix):
 found=[n for n in files if n==suffix or n.endswith("/"+suffix)]
 assert len(found)==1,(suffix,found)
 return files[found[0]]
def zipfiles(raw):
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  names=z.namelist();assert len(names)==len(set(names))
  assert all(not PurePosixPath(n).is_absolute() and ".." not in n.split("/") and "\\" not in n and ":" not in n for n in names)
  return {i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
def call(script,*args):
 subprocess.run([sys.executable,"tools/reader_composition/"+script,*map(str,args)],check=True)
try:
 jobs={};artifacts={}
 for label,runid in RUNS.items():
  run=fetch(f"actions/runs/{runid}/attempts/1")
  assert (run["head_sha"],run["head_branch"],run["run_attempt"],run["status"],run["conclusion"])==(SOURCE,"codex/closure-candidate-20261029",1,"completed","success")
  j=fetch(f"actions/runs/{runid}/attempts/1/jobs?per_page=100")
  assert j["total_count"]==len(j["jobs"]) and all(x["head_sha"]==SOURCE and x["run_id"]==runid and x["run_attempt"]==1 and x["status"]=="completed" and x["conclusion"]=="success" for x in j["jobs"])
  jobs[label]=j["jobs"]
  a=fetch(f"actions/runs/{runid}/artifacts?per_page=100")
  assert a["total_count"]==len(a["artifacts"])
  artifacts[label]=a["artifacts"]
 def pin(label,name,job_prefix):
  aa=[a for a in artifacts[label] if a["name"]==name];assert len(aa)==1,(label,name)
  a=aa[0];jj=[j for j in jobs[label] if j["name"].startswith(job_prefix)];assert len(jj)==1,(label,job_prefix)
  assert not a["expired"] and a["workflow_run"]["head_sha"]==SOURCE and a["workflow_run"]["id"]==RUNS[label]
  assert re.fullmatch("sha256:[0-9a-f]{64}",a["digest"]) and a["size_in_bytes"]>0
  p=dict(source=SOURCE,run=RUNS[label],attempt=1,job=jj[0]["id"],artifact=a["id"],size=a["size_in_bytes"],digest=a["digest"].split(":")[1],name=name)
  allpins.append(p);return p
 def tup(p):return [p["run"],p["job"],p["artifact"],p["size"],p["digest"]]
 pins={}
 pins["c1"]=pin("c1",f"claude-c1-android-installed-sync-{RUNS['c1']}-1","android")
 pins["c3"]=pin("c3",f"c3-android-sdk342-licenses-{RUNS['c3']}-1","android")
 pins["windows"]=[]
 for host,prefix in (("linux","integration (ubuntu-22.04"),("macos","integration (macos-15"),("windows","integration (windows-latest")):
  p=pin("recovery","migration-new-target-recovery-"+host,prefix)
  pins["windows"].append([host,SOURCE,*tup(p)])
 p=pin("record","windows-record-candidate-"+SOURCE,"record")
 pins["windows"].append(["record",SOURCE,*tup(p)])
 q=pin("qualification","migration-windows-handoff-"+SOURCE,"windows-native")
 startup=pin("qualification","migration-public-source-startup-"+SOURCE,"windows-native")
 pins["c2"]=dict(source=SOURCE,run=RUNS["c2"],jobs=[j["id"] for j in jobs["c2"]],artifacts=[])
 for label,stem,prefix in (("windows","windows","Windows product performance observation"),("windows-identity","windows-identity","Windows product performance observation"),("gtk","gtk","GTK product performance sampling"),("gtk-interactions","gtk-interactions","GTK product performance sampling"),("gtk-verification","gtk-verification","artifact identity verification"),("handoff","handoff","same-source handoff record")):
  p=pin("c2",f"reader-product-perf-{stem}-{RUNS['c2']}-1",prefix)
  p["label"]=label;pins["c2"]["artifacts"].append(p)
 pins["apple"]=[]
 for a in artifacts["apple"]:
  name=a["name"]
  if name.startswith("team24-apple-sdk-"):
   target=name[len("team24-apple-sdk-"):].rsplit("-",2)[0];prefix="Team24 Apple installed "+target
  elif name.startswith("team24-apple-native-"):
   platform=name[len("team24-apple-native-"):].rsplit("-",2)[0];prefix="Team24 Apple native "+platform
  elif name.startswith("apple-sdk342-supplemental-"):
   suffix=name[len("apple-sdk342-supplemental-"):].rsplit("-",2)[0];suite,platform=suffix.split("-");prefix="Apple 3.42 "+suite+" "+platform
  elif name.startswith("team24-apple-authentication-"):prefix="Team24 Apple original ZIP authentication"
  else:
   assert name==f"apple-sdk342-full-summary-{RUNS['apple']}-1",name
   prefix="full-host-summary"
  pins["apple"].append(pin("apple",name,prefix))
 assert len(pins["apple"])==19
 pinfile=OUT/"producer-pins.json";pinfile.write_text(json.dumps(pins,indent=2)+"\n")
 os.environ["CLOSURE_PINS"]=str(pinfile.resolve())
 for script in ("closure_c1_independent.py","closure_c3_independent.py","closure_windows_independent.py"):call(script)
 call("closure_startup_independent.py","--run",startup["run"],"--job",startup["job"],"--artifact",startup["artifact"],"--bytes",startup["size"],"--source",SOURCE,"--sha256",startup["digest"],"--artifact-name",startup["name"])
 for script in ("closure_c2_independent.py","closure_gtk_independent.py","closure_apple_independent.py"):call(script)
 for folder in ("claude-c2-independent","closure-gtk-independent","closure-apple-independent"):
  scope=json.loads((Path("build")/folder/"result.json").read_text());assert scope["accepted"] is True and scope["source"]==SOURCE
 result["apple_full_accepted"]=True
 raw=download_artifact_zip(q["artifact"]);assert len(raw)==q["size"] and sha(raw)==q["digest"]
 files=zipfiles(raw);manifest=json.loads(one(files,"manifest.json"))
 assert manifest["complete"] is True and manifest["reparse_objects_are_metadata_only"] is True
 count=0
 for item in manifest["entries"]:
  if item["kind"]=="regular":
   data=one(files,item["path"]);assert len(data)==item["size"] and sha(data)==item["sha256"];count+=1
 for suffix,expected in (("windows-frozen-preflight/result.json",43),("windows-native/evidence.json",24)):
  data=json.loads(one(files,suffix));assert data["passed"] is True and len(data["cases"])==expected and all(c["passed"] is True for c in data["cases"])
 aggregate=json.loads(one(files,"evidence/aggregate.json"))
 assert aggregate["sha"]==SOURCE and aggregate["passed"] is True and aggregate["total_expected"]==67 and aggregate["full_p0_acceptance"] is False
 result.update(accepted=True,same_source_scoped_acceptance=True,artifacts=allpins,qualification_cases=67,qualification_retained_regular_files_verified=count,
  scope="C1 Sync16; C3 Android licence archive/install receipt; C2 observations; recovery270; Windows43+24+startup10; Windows record27+refusal8; Apple original39 each and12 supplemental suites, all bound to one exact source",
  exclusions=["physical devices","F08 numeric budget acceptance","F12 complete delivery","full Windows recovery","full P0/product completion"])
except Exception as error:
 result["error"]=repr(error)
finally:
 (OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
 print(json.dumps(result),flush=True)
assert result["accepted"],result.get("error")
