"""Authenticate all five original ZIPs and independently parse the native xcresults."""
import hashlib, io, json, os, stat, sys, zipfile
from pathlib import PurePosixPath
from run import ROOT, HERE, identity, need, save, sha, command, guard, extract_metrics
def main():
    guard()
    out=ROOT/"build/f08-apple-audit";out.mkdir(parents=True)
    ident=identity();api=lambda p:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+p]))
    producer=api("actions/runs/"+ident["run_id"])
    need(producer["head_sha"]==ident["source_sha"] and str(producer["run_attempt"])==ident["attempt"],"run source/attempt")
    listed=api("actions/runs/"+ident["run_id"]+"/artifacts?per_page=100")["artifacts"]
    results=[]
    for kind in ("macos-sdk","iphonesimulator-sdk","macos","iphone","ipad"):
        name="f08-apple-"+kind+"-"+ident["run_id"]+"-"+ident["attempt"]
        matches=[a for a in listed if a["name"]==name];need(len(matches)==1,"artifact missing/duplicate "+name)
        meta=api("actions/artifacts/"+str(matches[0]["id"]))
        need(not meta["expired"] and meta["workflow_run"]["head_sha"]==ident["source_sha"]
             and str(meta["workflow_run"]["id"])==ident["run_id"],"artifact producer")
        data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(meta["id"])+"/zip"])
        digest=hashlib.sha256(data).hexdigest()
        need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest,"ZIP identity")
        folder=out/kind;folder.mkdir();(folder/"original.zip").write_bytes(data)
        save(folder/"metadata.json",meta);raw=folder/"raw";raw.mkdir()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos=archive.infolist();need(0<len(infos)<100000 and sum(i.file_size for i in infos)<4*1024**3,"ZIP bounds")
            names=set()
            for info in infos:
                path=PurePosixPath(info.filename);key=str(path).casefold()
                need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and
                     "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
                names.add(key)
                need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"ZIP kind")
                if info.is_dir():continue
                destination=raw/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(archive.read(info))
        manifest=json.loads((raw/"f08-manifest.json").read_text())
        need(all(manifest.get(k)==v for k,v in ident.items()) and manifest["kind"]==kind and manifest["f08_accepted"] is False,"manifest identity")
        files={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
        need(files==set(manifest["files"])|{"f08-manifest.json"},"complete inventory")
        for name,item in manifest["files"].items():
            need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"payload bytes")
        entry={"kind":kind,"artifact_id":meta["id"],"sha256":digest,"bytes":len(data),"files":len(files),"authenticated":True}
        if kind.endswith("-sdk"):
            entry["installed_identity_present"]=(raw/"sdk342-installed-identity.json").exists()
        elif (raw/"result.json").exists():
            result=json.loads((raw/"result.json").read_text())
            need(all(result.get(k)==v for k,v in ident.items()) and result["platform"]==kind and result["f08_accepted"] is False,"native identity")
            need((raw/"profile.json").read_bytes()==(HERE/"profile.json").read_bytes(),"profile bytes")
            entry["collection_complete"]=result["collection_complete"];entry["problems"]=result["problems"]
            if (raw/"original.xcresult").exists():
                sys.path.insert(0,str(ROOT/"tests/apple_host"));from collect_evidence import load_results
                entry["original_cases"]=load_results(raw/"original.xcresult")
            if "program_sha256" in result:
                binary=raw/"program/EXReaderHost.app"/("Contents/MacOS/EXReaderHost" if kind=="macos" else "EXReaderHost")
                need(sha(binary)==result["program_sha256"],"native program differs")
                entry["program_sha256"]=result["program_sha256"]
            if (raw/"performance-metrics.json").exists():
                _,metrics=extract_metrics(raw/"metrics.xcresult")
                need(metrics==json.loads((raw/"performance-metrics.json").read_text()),"xcresult metrics differ")
                entry["performance_metrics"]=metrics
            if (raw/"original/shelf-ui.json").exists():
                original=json.loads((raw/"original/shelf-ui.json").read_text())
                sys.path.insert(0,str(ROOT/"tests/apple_host"));from collect_evidence import load_results
                need(original["cases"]==load_results(raw/"original.xcresult"),"original case status differs")
                binary=raw/"program/EXReaderHost.app"/("Contents/MacOS/EXReaderHost" if kind=="macos" else "EXReaderHost")
                need(sha(binary)==result["program_sha256"],"native program differs")
                entry["original_ui_accepted"]=original["accepted"]
                entry["native_measurements"]=original["measurements"]
        results.append(entry)
        print("F08_APPLE_ARCHIVE",json.dumps(entry),flush=True)
    report={**ident,"archives":results,"authenticated":True,"f08_accepted":False}
    save(out/"audit.json",report);print("F08_APPLE_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":main()
