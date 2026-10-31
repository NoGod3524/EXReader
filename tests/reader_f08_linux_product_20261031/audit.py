"""Authenticate and independently replay the complete full-product GTK evidence."""
import hashlib, io, json, os, shutil, stat, subprocess, sys, tarfile, zipfile
from pathlib import Path, PurePosixPath
import run as R
from run import identity, need, save, sha, command, load
ROOT=R.ROOT;OUT=ROOT/"build/f08-linux-product-audit"
def main():
    R.guard();OUT.mkdir(parents=True,exist_ok=False);ident=identity()
    api=lambda p:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+p]))
    aid=int(os.environ["F08_ARTIFACT_ID"]);meta=api("actions/artifacts/"+str(aid));save(OUT/"metadata.json",meta)
    need(meta["id"]==aid and not meta["expired"] and
         meta["name"]=="f08-linux-product-"+ident["run_id"]+"-"+ident["attempt"],"artifact identity")
    need(str(meta["workflow_run"]["id"])==ident["run_id"] and meta["workflow_run"]["head_sha"]==ident["source_sha"],"artifact source/run")
    producer=api("actions/runs/"+ident["run_id"])
    need(producer["head_sha"]==ident["source_sha"] and str(producer["run_attempt"])==ident["attempt"],"attempt")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(aid)+"/zip"])
    digest=hashlib.sha256(data).hexdigest()
    need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest and
         os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest,"ZIP identity")
    (OUT/"original.zip").write_bytes(data);raw=OUT/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist();need(0<len(infos)<20000 and sum(i.file_size for i in infos)<4*1024**3,"ZIP bounds")
        names=set()
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and
                 "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key)
            need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
            if info.is_dir():continue
            p=raw/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(info))
    manifest=load(raw/"manifest.json")
    need(all(manifest.get(k)==v for k,v in ident.items()) and manifest["f08_accepted"] is False,"manifest identity")
    actual={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    need(actual==set(manifest["files"])|{"manifest.json"},"complete inventory")
    for name,item in manifest["files"].items():
        need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"file: "+name)
    need((raw/"profile.json").read_bytes()==(R.HERE/"profile.json").read_bytes(),"fixed profile")
    report={**ident,"artifact_id":aid,"artifact_bytes":len(data),"artifact_sha256":digest,"files":len(actual),
        "authenticated":True,"build_complete":False,"collection_complete":False,"frame_budget_measured":False,"f08_accepted":False}
    if (raw/"build-identity.json").exists():
        built=load(raw/"build-identity.json")
        need(all(built.get(k)==v for k,v in ident.items()) and built["sdk_version"]=="3.42.0","build identity")
        need(set(built["helpers"])==set(R.FROZEN),"frozen helper coverage")
        for p,d in built["helpers"].items():need(sha(ROOT/p)==d,"unchanged helper: "+p)
        for p,d in built["components"].items():need(command(["git","rev-parse","HEAD:"+p],text=True).strip()==d,"production tree")
        options=R.compiled_features((raw/"host-CMakeCache.txt").read_text(),load(raw/"host-compile_commands.json"))
        need(options==built["compiled_options"],"full native compiler configuration")
        for p,d in built["probes"].items():need(sha(raw/p)==d,"probe bytes")
        package=load(raw/"perf-package/build.json");payload=raw/"perf-package/EXReader-Linux"
        need(package["source_sha"]==ident["source_sha"] and package["sdk_version"]=="3.42.0" and package["abi"]==1,"native package")
        files={p.relative_to(payload).as_posix():sha(p) for p in payload.rglob("*") if p.is_file()}
        need(files==package["files"] and sha(payload/"bin/exreader-linux")==built["program_sha256"],"exact installed binary")
        with tarfile.open(raw/"perf-package/EXReader-Linux.tar.gz","r:gz") as tar:
            zipped={}
            for member in tar.getmembers():
                p=PurePosixPath(member.name)
                need(not p.is_absolute() and ".." not in p.parts and not member.issym() and not member.islnk(),"package member")
                if member.isdir():continue
                need(member.isfile() and str(p) not in zipped,"regular unique package file")
                zipped[str(p)]=hashlib.sha256(tar.extractfile(member).read()).hexdigest()
        need(zipped==files,"original tar inventory")
        report.update(build_complete=True,program_sha256=built["program_sha256"])
    # Replay in separate copies at the original frozen verifier's paths; retain the downloaded ZIP and raw tree.
    for name in R.TREES:
        if (raw/name).is_dir():
            target=ROOT/"build"/name;need(not target.exists(),"fresh replay target")
            shutil.copytree(raw/name,target)
    for name in R.PROBES:
        if (raw/name).is_file():
            target=ROOT/"build"/name;target.parent.mkdir(parents=True,exist_ok=True);need(not target.exists(),"fresh probe copy")
            shutil.copyfile(raw/name,target)
    available={"original-summary":(raw/"perf-evidence/samples.json").exists(),
               "frameclock-verify":all((raw/c/"launches.json").exists() for c in R.COHORTS),
               "causal-verify":(raw/"f08-causal/driver.json").exists()}
    results={}
    for label,args in R.verify_commands():
        if not available[label]:continue
        with (OUT/(label+".log")).open("wb") as log:
            p=subprocess.run(list(map(str,args)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        results[label]=p.returncode
    report["replayed_verifiers"]=results
    sample=load(raw/"sample-result.json") if (raw/"sample-result.json").exists() else None
    if sample is not None:
        need(all(sample.get(k)==v for k,v in ident.items()) and sample["f08_accepted"] is False,"sample identity")
        report["sample_problems"]=sample["problems"];report["sample_steps"]=sample["steps"]
        if sample["collection_complete"] is True:
            need(report["build_complete"] and set(results)==set(available) and all(v==0 for v in results.values()),"complete independent verification")
            for p in ("perf-evidence/report.json","perf-evidence/summary.json","f08-result/summary.json","f08-causal/summary.json"):
                need(load(raw/p)==load(ROOT/"build"/p),"independent raw recomputation: "+p)
            evaluated=R.evaluate(raw,load(raw/"profile.json"))
            need(evaluated==sample["evaluation"],"budget recomputation")
            report.update(evaluated,collection_complete=True)
    save(OUT/"audit.json",report);print("F08_LINUX_PRODUCT_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":main()
