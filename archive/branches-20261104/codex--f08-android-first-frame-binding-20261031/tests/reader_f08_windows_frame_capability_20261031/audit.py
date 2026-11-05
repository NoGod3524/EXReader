#!/usr/bin/env python3
"""Authenticate the existing capability ZIP and expose diagnostic logs in Actions."""
import hashlib, io, json, os, stat, subprocess, zipfile
from pathlib import Path, PurePosixPath
SOURCE="5ddf0aa8f2d628649289fc1bcfd9d536a566910c"
RUN=41178921492
ARTIFACT=13033922515
BYTES=468201
DIGEST="5349698214ec4ffe305594dc0f0b32007b124ff99b7785c537324f7bcdd150c1"
NAME="f08-windows-frame-capability-41178921492-1"
OUT=Path("build/f08-windows-frame-audit")
def need(value,message):
    if not value:raise RuntimeError(message)
def sha(value):return hashlib.sha256(value).hexdigest()
def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2)+"\n")
def api(path):
    return json.loads(subprocess.check_output(["gh","api","repos/NoGod3524/EXReader/"+path]))
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    git=lambda *a:subprocess.check_output(["git",*a],text=True).strip()
    need(git("rev-parse","HEAD")==os.environ["GITHUB_SHA"],"audit source")
    subprocess.run(["git","merge-base","--is-ancestor",SOURCE,"HEAD"],check=True)
    need(set(git("diff","--name-only",SOURCE,"HEAD").splitlines())=={
        ".github/workflows/dot-f08-windows-frame-capability-20261031.yml",
        "tests/reader_f08_windows_frame_capability_20261031/audit.py"},"audit scope")
    OUT.mkdir(parents=True,exist_ok=False)
    run=api("actions/runs/"+str(RUN))
    need(run["head_sha"]==SOURCE and run["run_attempt"]==1 and run["conclusion"]=="success","producer")
    meta=api("actions/artifacts/"+str(ARTIFACT));save("metadata.json",meta)
    need(meta["id"]==ARTIFACT and meta["name"]==NAME and not meta["expired"] and
         meta["workflow_run"]["id"]==RUN and meta["workflow_run"]["head_sha"]==SOURCE and
         meta["size_in_bytes"]==BYTES and meta["digest"]=="sha256:"+DIGEST,"artifact identity")
    data=subprocess.check_output(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(ARTIFACT)+"/zip"])
    need(len(data)==BYTES and sha(data)==DIGEST,"ZIP identity");(OUT/"original.zip").write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist();need(0<len(infos)<100 and sum(i.file_size for i in infos)<8*1024*1024,"ZIP bounds")
        names=set()
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(info.filename and str(path)!="." and not path.is_absolute() and ".." not in path.parts and
                 "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key)
            need(not info.flag_bits&1 and info.file_size<4*1024*1024 and
                 stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"ZIP kind")
        files={i.filename:z.read(i) for i in infos if not i.is_dir()}
    receipts=[n for n in files if n.endswith("/receipt.json") or n=="receipt.json"]
    need(len(receipts)==1,"receipt unique")
    prefix=receipts[0][:-len("receipt.json")];receipt=json.loads(files[receipts[0]])
    need(receipt["source"]==SOURCE and receipt["run"]==str(RUN) and receipt["attempt"]=="1" and
         receipt["diagnostic_complete"] is True and receipt["product_measured"] is False and
         receipt["F08_accepted"] is False,"receipt identity")
    expected={prefix+n.replace("\\","/"):digest for n,digest in receipt["files"].items()}
    need(all(n in files and sha(files[n])==digest for n,digest in expected.items()),"file inventory")
    binary=[n for n in files if n.endswith("/f08_frame_control.exe")]
    need(len(binary)==1 and sha(files[binary[0]])==receipt["control_sha256"],"control binary")
    need(set(files)==set(expected)|{receipts[0],binary[0]},"complete inventory")
    need(receipt["controls"]==dict(positive=2,negative=2),"controls")
    rows=[]
    for capture in receipt["captures"]:
        mode=capture["mode"];need(mode in ("gdi","dxgi") and capture["complete"] is True,"mode")
        raw=[json.loads(line) for line in files[prefix+mode+"/control.jsonl"].splitlines()]
        need(raw[0]["kind"]=="start" and raw[-1]["kind"]=="stop" and raw[-1]["ticks"]==41,"native control")
        need(all(r["pid"]==capture["pid"] for r in raw),"PID")
        paints=[r for r in raw if r["kind"] in ("gdi_paint","dxgi_present")]
        need(len(paints)==capture["draw_calls"] and all(r["result"]==0 and r["end_qpc"]>=r["start_qpc"] for r in paints),"draw calls")
        rows.append(dict(mode=mode,pid=capture["pid"],draw_calls=len(paints),
                         captured_rows=capture["rows"],missing_csv=capture["missing_csv"]))
        print("F08_COLLECTOR_LOG",mode,files[prefix+mode+"/collector.log"].decode(errors="replace"),flush=True)
        print("F08_SESSION",mode,files[prefix+mode+"/session.txt"].decode(errors="replace"),flush=True)
        print("F08_COMMAND",mode,files[prefix+mode+"/command.json"].decode(),flush=True)
    print("F08_DISPLAY",files[prefix+"display.txt"].decode(errors="replace"),flush=True)
    help_text=files[prefix+"help.txt"].decode(errors="replace")
    lines=help_text.splitlines()
    for i,line in enumerate(lines):
        if any(key in line for key in ("process_id","qpc_time","timed","session_name","capture","exclude","delay")):
            print("F08_HELP","\n".join(lines[max(0,i-1):i+4]),flush=True)
    report=dict(audit_source=os.environ["GITHUB_SHA"],audit_run=os.environ["GITHUB_RUN_ID"],
        producer_source=SOURCE,producer_run=RUN,artifact_id=ARTIFACT,sha256=DIGEST,
        files=len(files),captures=rows,passed=True,F08_accepted=False)
    save("receipt.json",report);print("F08_WINDOWS_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":main()
