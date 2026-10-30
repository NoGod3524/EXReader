"""Actions-only first-assertion review of retained Apple mobile failures."""
import argparse,hashlib,io,json,os,stat,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform=="darwin"
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"tools"))
from check_parallel_integration import fetch,download_artifact_zip
PINS={
 "common343":("343bb94eb6513beaf5b344e7828342f6602a3b7b",40946894035,123726898357,12941146187,476424539,"b5037093b8da93b3ff779bead2a0dcc21971f18221f64f7326f236ed80a94b9c"),
 "helper141":("141304d36e451d34c2720f74ce0b3da4f412df3a",40958251556,123750471325,12939157786,470359292,"17237d31e21df747d4baf771f918947886428aec9eef5e37746caabcedde6a18")}
PINS["features550-ipad"]=("550556de68ba1d861cc3fcce8f4a60a66706f7c2",40982450461,123826706940,12945688879,186995142,"5277167b985c1063abd4ab907cf850ad5ea7ea660bdfcec1184ff94cd432e67c")
p=argparse.ArgumentParser();p.add_argument("--input",choices=PINS,required=True);args=p.parse_args()
source,run,jobid,aid,size,digest=PINS[args.input]
out=Path("build/repair-apple-failure")/args.input;out.mkdir(parents=True,exist_ok=True)
job=fetch(f"actions/jobs/{jobid}");assert (job["head_sha"],job["run_id"],job["conclusion"])==(source,run,"failure")
meta=fetch(f"actions/artifacts/{aid}")
assert (meta["workflow_run"]["head_sha"],meta["workflow_run"]["id"],meta["size_in_bytes"],meta["digest"],meta["expired"])==(source,run,size,"sha256:"+digest,False)
raw=download_artifact_zip(aid);assert len(raw)==size and hashlib.sha256(raw).hexdigest()==digest
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 infos=z.infolist();names=[i.filename for i in infos]
 assert len(names)==len(set(names)) and sum(i.file_size for i in infos)<3*1024**3
 for i in infos:
  n=i.filename;p=PurePosixPath(n)
  assert not p.is_absolute() and ".." not in p.parts and "\\" not in n and ":" not in n
  assert stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not i.flag_bits&1
 result=json.loads(z.read("result.json"))
 assert (result["source_sha"],str(result["run_id"]),str(result["attempt"]),result["platform"],result["accepted"])==(source,str(run),"1",("ipad" if args.input.endswith("-ipad") else "iphone"),False)
 log=z.read("wave3-native-ui.log");pin=result["files"]["wave3-native-ui.log"]
 assert len(log)==pin["bytes"] and hashlib.sha256(log).hexdigest()==pin["sha256"]
 (out/"native-ui.log").write_bytes(log)
 for name in names:
  if name.startswith("wave3.xcresult/") and not name.endswith("/"):
   data=z.read(name);pin=result["files"][name]
   assert len(data)==pin["bytes"] and hashlib.sha256(data).hexdigest()==pin["sha256"]
   dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
bundle=out/"wave3.xcresult"
for kind in ("summary","tests"):
 text=subprocess.check_output(["xcrun","xcresulttool","get","test-results",kind,"--path",str(bundle),"--format","json"],text=True)
 (out/(kind+".json")).write_text(text);print("XCRESULT_"+kind.upper()+" "+text,flush=True)
legacy=subprocess.check_output(["xcrun","xcresulttool","get","object","--legacy","--path",str(bundle),"--format","json"],text=True)
j=json.loads(legacy);issues=j.get("issues",{})
(out/"legacy-issues.json").write_text(json.dumps(issues,indent=2))
print("FIRST_ASSERTIONS "+json.dumps(issues),flush=True)
lines=log.decode("utf-8","replace").splitlines()
contexts=[]
for i,line in enumerate(lines):
 if "error:" in line or "XCTAssert" in line or "Assertion Failure" in line:
  contexts.append(dict(line=i+1,context=lines[max(0,i-90):min(len(lines),i+140)]))
(out/"failure-context.json").write_text(json.dumps(contexts,indent=2))
for item in contexts:print("FAILURE_CONTEXT "+json.dumps(item),flush=True)
annotation=[]
active=False
for line in lines:
 if "Test Case" in line and "testNativeAnnotationPreviewConfirmCancelAndDuplicate" in line and "started" in line:active=True
 if active:annotation.append(line)
 if active and "Test Case" in line and "testNativeAnnotationPreviewConfirmCancelAndDuplicate" not in line:active=False
print("ANNOTATION_BEGIN "+json.dumps(annotation[:100]),flush=True)
print("ANNOTATION_END "+json.dumps(annotation[-180:]),flush=True)
print("ANNOTATION_MILESTONES "+json.dumps([line for line in annotation if "Added attachment" in line or ("t = " in line and any(x in line for x in ("Find the \"features.","Tap ","Press ","Open Application","Terminate ")))][-180:]),flush=True)
import re
previous=None
for index,line in enumerate(annotation):
 match=re.search(r"t =\s*([0-9.]+)s",line)
 if not match:continue
 current=float(match[1])
 if previous is not None and current-previous[0]>=10:
  print("ANNOTATION_IDLE_GAP "+json.dumps(dict(seconds=current-previous[0],context=annotation[max(0,previous[1]-5):index+12])),flush=True)
 previous=(current,index)
receipt=dict(input=args.input,producer_source=source,producer_run=run,producer_job=jobid,
 artifact=aid,bytes=size,sha256=digest,inspection_source=os.environ["GITHUB_SHA"],
 diagnostic_only=True,product_acceptance=False,issues=issues)
(out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
print("INSPECTION_RECEIPT "+json.dumps(receipt),flush=True)
