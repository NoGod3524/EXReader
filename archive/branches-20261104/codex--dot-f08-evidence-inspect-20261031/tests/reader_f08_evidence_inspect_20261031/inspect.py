"""Actions-only, read-only inspection of a pinned and fully authenticated evidence ZIP."""
import hashlib, io, json, os, re, stat, sys, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity, need, save, command
BASE="bf3ca78c42add246faebc0a208bbe8a6150e856c"
OUT=ROOT/"build/f08-evidence-inspect"
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"inspector source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
        {"tests/reader_f08_evidence_inspect_20261031/inspect.py",".github/workflows/dot-f08-evidence-inspect-20261031.yml"},"test-only scope")
    pin={key:os.environ["F08_"+key.upper()] for key in ("source","run","attempt","artifact","digest","bytes","manifest")}
    need(re.fullmatch("[0-9a-f]{40}",pin["source"]) and re.fullmatch("[0-9a-f]{64}",pin["digest"]),"source/digest")
    for key in ("run","attempt","artifact","bytes"):need(int(pin[key])>0,"positive pin")
    paths=json.loads(os.environ["F08_PATHS"]);need(type(paths) is list and 0<len(paths)<=12,"selected paths")
    OUT.mkdir(parents=True,exist_ok=False)
    api=lambda p:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+p]))
    meta=api("actions/artifacts/"+pin["artifact"])
    producer=api("actions/runs/"+pin["run"]+"/attempts/"+pin["attempt"])
    need(producer["head_sha"]==pin["source"] and str(producer["run_attempt"])==pin["attempt"],"producer")
    need(meta["id"]==int(pin["artifact"]) and not meta["expired"] and meta["size_in_bytes"]==int(pin["bytes"])
         and meta["digest"]=="sha256:"+pin["digest"] and meta["workflow_run"]["id"]==int(pin["run"])
         and meta["workflow_run"]["head_sha"]==pin["source"],"artifact metadata")
    save(OUT/"metadata.json",meta)
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+pin["artifact"]+"/zip"])
    need(len(data)==int(pin["bytes"]) and hashlib.sha256(data).hexdigest()==pin["digest"],"ZIP bytes")
    selected={}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos=archive.infolist();need(0<len(infos)<100000 and sum(i.file_size for i in infos)<4*1024**3,"ZIP bounds")
        names=set();files={}
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and
                 "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key)
            need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"ZIP kind")
            if not info.is_dir():files[info.filename]=info
        manifest=json.loads(archive.read(pin["manifest"]))
        need(manifest["source_sha"]==pin["source"] and manifest["run_id"]==pin["run"] and
             manifest["attempt"]==pin["attempt"] and manifest["f08_accepted"] is False,"manifest producer")
        need(set(files)==set(manifest["files"])|{pin["manifest"]},"complete inventory")
        for name,item in manifest["files"].items():
            need(files[name].file_size==item["bytes"],"file size")
            digest=hashlib.sha256()
            with archive.open(name) as stream:
                for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
            need(digest.hexdigest()==item["sha256"],"file digest")
        for name in paths:
            need(name in files and name!=pin["manifest"],"requested file absent: "+str(name))
            content=archive.read(name);text=content.decode("utf-8",errors="replace")
            if len(content)<=65536:
                selected[name]={"bytes":len(content),"complete":True,"text":text}
            else:
                lines=text.splitlines()
                selected[name]={"bytes":len(content),"complete":False,"lines":len(lines),
                    "first_lines":lines[:60],"last_lines":lines[-100:]}
    result={**identity(),"pin":pin,"authenticated":True,"inventory_files":len(files),"selected":selected,"f08_accepted":False}
    save(OUT/"inspection.json",result)
    for name,value in selected.items():print("F08_EVIDENCE_FILE",name,json.dumps(value),flush=True)
    print("F08_EVIDENCE_INSPECT",json.dumps({k:v for k,v in result.items() if k!="selected"}),flush=True)
if __name__=="__main__":main()
