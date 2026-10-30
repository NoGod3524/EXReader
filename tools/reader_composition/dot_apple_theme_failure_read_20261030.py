"""Actions-only c46 iPhone theme-preflight retained evidence."""
import hashlib,io,json,os,stat,sys,zipfile
from pathlib import Path,PurePosixPath
assert os.environ.get("GITHUB_ACTIONS")=="true"
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"tools"))
from check_parallel_integration import fetch,download_artifact_zip
S="c46f7036d81f88d8529871590f780b5430630e47";R=41005300066;J=123899742139;A=12956108633
SIZE=263006465;H="8557dfb2266a69279cd38d0f470d13b73b1b6ba55437f4bd1b9f842e6195c762"
out=Path("build/dot-apple-theme-failure");out.mkdir(parents=True,exist_ok=True)
j=fetch(f"actions/jobs/{J}");a=fetch(f"actions/artifacts/{A}")
assert (j["head_sha"],j["run_id"],j["run_attempt"],j["name"],j["status"],j["conclusion"])==(S,R,1,"Team24 Apple native iphone","completed","failure")
assert (a["workflow_run"]["head_sha"],a["workflow_run"]["id"],a["name"],a["size_in_bytes"],a["digest"],a["expired"])==(S,R,f"team24-apple-native-iphone-{R}-1",SIZE,"sha256:"+H,False)
raw=download_artifact_zip(A);assert len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==H
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 infos=z.infolist();names=[i.filename for i in infos]
 assert len(names)==len(set(names)) and sum(i.file_size for i in infos)<3*1024**3
 for i in infos:
  p=PurePosixPath(i.filename)
  assert not p.is_absolute() and ".." not in p.parts and "\\" not in i.filename and ":" not in i.filename
  assert stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not i.flag_bits&1
 result=json.loads(z.read("result.json"))
 assert (result["source_sha"],str(result["run_id"]),str(result["attempt"]),result["platform"],result["accepted"])==(S,str(R),"1","iphone",False)
 selected=[n for n in names if n.startswith("theme") and n.endswith(".log")]
 assert "theme-native-ui.log" in selected
 for name in selected:
  data=z.read(name);pin=result["files"][name]
  assert len(data)==pin["bytes"] and hashlib.sha256(data).hexdigest()==pin["sha256"]
  (out/name).write_bytes(data)
  if name=="theme-native-ui.log":print("AUTHENTICATED_THEME_LOG\n"+data.decode("utf-8","replace"),flush=True)
 phases=[{"mode":p["mode"],"accepted":p["accepted"],"cases":p.get("cases",[]),"failure":p.get("failure")} for p in result["phases"]]
 receipt={"source":S,"run":R,"attempt":1,"job":J,"artifact":A,"bytes":SIZE,"sha256":H,"inspection_source":os.environ["GITHUB_SHA"],"phases":phases,"theme_members":[n for n in names if n.startswith("theme")],"diagnostic_only":True,"product_acceptance":False}
 (out/"receipt.json").write_text(json.dumps(receipt,indent=2))
 print("INSPECTION_RECEIPT "+json.dumps(receipt),flush=True)
