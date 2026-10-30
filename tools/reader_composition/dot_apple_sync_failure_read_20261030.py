"""Actions-only authentication and diagnosis of retained c46 fresh iPad sync 401 failure."""
import hashlib,io,json,os,stat,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform=="darwin"
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"tools"))
from check_parallel_integration import fetch,download_artifact_zip
SOURCE="c46f7036d81f88d8529871590f780b5430630e47";RUN=41011360858;JOB=123918768257;AID=12960002952
SIZE=118501766;DIGEST="1e32b02bf23e9ccf43bad6140964077449072f76a1e17f21393ac764afc6ceb1"
out=Path("build/dot-apple-sync-failure");out.mkdir(parents=True,exist_ok=True)
job=fetch(f"actions/jobs/{JOB}");meta=fetch(f"actions/artifacts/{AID}")
assert (job["head_sha"],job["run_id"],job["run_attempt"],job["name"],job["status"],job["conclusion"])==(SOURCE,RUN,1,"Apple 3.42 sync ipad","completed","failure")
assert (meta["workflow_run"]["head_sha"],meta["workflow_run"]["id"],meta["name"],meta["size_in_bytes"],meta["digest"],meta["expired"])==(SOURCE,RUN,f"apple-sdk342-supplemental-sync-ipad-{RUN}-1",SIZE,"sha256:"+DIGEST,False)
raw=download_artifact_zip(AID);assert len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==DIGEST
prefix="apple-sdk342-supplemental/ipad/sync/"
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 infos=z.infolist();names=[i.filename for i in infos]
 assert len(names)==len(set(names)) and sum(i.file_size for i in infos)<3*1024**3
 for i in infos:
  p=PurePosixPath(i.filename)
  assert not p.is_absolute() and ".." not in p.parts and "\\" not in i.filename and ":" not in i.filename
  assert stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not i.flag_bits&1
 report=json.loads(z.read(prefix+"sdk342-supplemental.json"))
 assert (report["source_sha"],str(report["run_id"]),str(report["attempt"]),report["platform"],report["accepted"])==(SOURCE,str(RUN),"1","ipad",False)
 for relative,item in report["files"].items():
  data=z.read(prefix+relative)
  assert len(data)==item["bytes"] and hashlib.sha256(data).hexdigest()==item["sha256"],relative
 print("AUTHENTICATED_FILE_COUNT "+str(len(report["files"])),flush=True)
 log=z.read(prefix+"account-failure/xcodebuild.log");(out/"native.log").write_bytes(log)
 hashes={}
 for name in names:
  if name.startswith(prefix+"account-failure/failure.xcresult/") and not name.endswith("/"):
   data=z.read(name);relative=name[len(prefix):];dest=out/relative
   dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
   hashes[relative]={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
 assert hashes,"missing original xcresult"
(out/"extracted-hashes.json").write_text(json.dumps(hashes,indent=2))
bundle=out/"account-failure/failure.xcresult"
for kind in ("summary","tests"):
 text=subprocess.check_output(["xcrun","xcresulttool","get","test-results",kind,"--path",str(bundle),"--format","json"],text=True)
 (out/(kind+".json")).write_text(text);print("XCRESULT_"+kind.upper()+" "+text,flush=True)
legacy=json.loads(subprocess.check_output(["xcrun","xcresulttool","get","object","--legacy","--path",str(bundle),"--format","json"],text=True))
issues=legacy.get("issues",{});(out/"legacy-issues.json").write_text(json.dumps(issues,indent=2))
print("FIRST_ASSERTIONS "+json.dumps(issues),flush=True)
lines=log.decode("utf-8","replace").splitlines();contexts=[]
print("AUTHENTICATED_NATIVE_LOG\n"+log.decode("utf-8","replace"),flush=True)
for i,line in enumerate(lines):
 if any(x in line for x in ("error:","XCTAssert","Assertion Failure","Testing failed:","Failed to","Test Case")):
  contexts.append({"line":i+1,"context":lines[max(0,i-70):min(len(lines),i+100)]})
(out/"failure-context.json").write_text(json.dumps(contexts,indent=2))
for item in contexts:print("FAILURE_CONTEXT "+json.dumps(item),flush=True)
attachments=out/"attachments"
subprocess.run(["xcrun","xcresulttool","export","attachments","--path",str(bundle),"--output-path",str(attachments)],check=True)
manifest=json.loads((attachments/"manifest.json").read_text());trees=[]
for group in manifest:
 for item in group["attachments"]:
  if item.get("suggestedHumanReadableName","").startswith("native-tree"):
   file=item["exportedFileName"];assert Path(file).name==file
   trees.append({"test":group.get("testIdentifier") or group.get("testName"),"text":(attachments/file).read_text(errors="replace")})
(out/"native-trees.json").write_text(json.dumps(trees,indent=2))
for tree in trees:print("NATIVE_TREE "+json.dumps(tree),flush=True)
receipt={"producer_source":SOURCE,"run":RUN,"attempt":1,"job":JOB,"artifact":AID,"bytes":SIZE,"sha256":DIGEST,"inspection_source":os.environ["GITHUB_SHA"],"diagnostic_only":True,"product_acceptance":False,"producer_result":report,"issues":issues}
(out/"receipt.json").write_text(json.dumps(receipt,indent=2));print("INSPECTION_RECEIPT "+json.dumps(receipt),flush=True)
