"""Authenticate the diagnostic artifact and independently count all feedback rows."""
import hashlib,io,json,os,stat,subprocess,zipfile
from pathlib import PurePosixPath
import run as R
def main():
 R.guard();out=R.ROOT/"build/f08-linux-presentation-audit";out.mkdir(parents=True,exist_ok=False)
 aid=int(os.environ["F08_ARTIFACT_ID"]);ident=R.identity();base="repos/NoGod3524/EXReader/"
 api=lambda path:subprocess.check_output(["gh","api",base+path])
 meta=json.loads(api("actions/artifacts/"+str(aid)));R.save(out/"metadata.json",meta)
 R.need(meta["id"]==aid and not meta["expired"] and meta["name"]=="f08-linux-presentation-"+ident["run_id"]+"-"+ident["attempt"],"artifact identity")
 R.need(str(meta["workflow_run"]["id"])==ident["run_id"] and meta["workflow_run"]["head_sha"]==ident["source_sha"],"artifact source/run")
 run=json.loads(api("actions/runs/"+ident["run_id"]))
 R.need(run["head_sha"]==ident["source_sha"] and str(run["run_attempt"])==ident["attempt"],"attempt")
 data=api("actions/artifacts/"+str(aid)+"/zip");digest=hashlib.sha256(data).hexdigest()
 R.need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest and os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest,"ZIP bytes/digest")
 (out/"original.zip").write_bytes(data);raw=out/"raw";raw.mkdir()
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  infos=z.infolist();R.need(0<len(infos)<100 and sum(i.file_size for i in infos)<20*1024**2,"ZIP bounds");names=set()
  for info in infos:
   p=PurePosixPath(info.filename);key=str(p).casefold()
   R.need(str(p)!="." and not p.is_absolute() and ".." not in p.parts and "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
   names.add(key);R.need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
   if info.is_dir():continue
   target=raw/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))
 manifest=json.loads((raw/"manifest.json").read_text())
 R.need(all(manifest.get(k)==v for k,v in ident.items()) and manifest["f08_accepted"] is False,"manifest identity")
 actual={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
 R.need(actual==set(manifest["files"])|{"manifest.json"},"complete inventory")
 for name,item in manifest["files"].items():R.need((raw/name).stat().st_size==item["bytes"] and R.sha(raw/name)==item["sha256"],"file: "+name)
 controls=R.controls();R.need(controls==json.loads((raw/"controls.json").read_text()),"control replay")
 report={**ident,"artifact_id":aid,"artifact_bytes":len(data),"artifact_sha256":digest,"authenticated":True,"files":len(actual),"controls":controls,"product_sampled":False,"frame_budget_measured":False,"f08_accepted":False}
 if (raw/"feedback.json").exists() and (raw/"feedback.json").stat().st_size:
  result=R.evaluate(json.loads((raw/"feedback.json").read_text()))
  R.need(result==json.loads((raw/"capability-summary.json").read_text()),"independent all-row recomputation")
  report["capability"]=result
 report["collection"]=json.loads((raw/"collection.json").read_text())
 R.save(out/"audit.json",report);print(json.dumps(report),flush=True)
if __name__=="__main__":main()
