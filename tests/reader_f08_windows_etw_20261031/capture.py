"""Actions-only raw ETW capability experiment; synthetic controls are never product evidence."""
import argparse, collections, hashlib, io, json, os, shutil, stat, subprocess, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity, need, save, sha, command
OUT=ROOT/"build/f08-windows-etw"
BASE="37cbd2566167f633fe70387eb4d0c139751a5b0b"
PROVIDERS=("Microsoft-Windows-DXGI","Microsoft-Windows-D3D9","Microsoft-Windows-DxgKrnl","Microsoft-Windows-Dwm-Core","Microsoft-Windows-Win32k")
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
        {"tests/reader_f08_windows_etw_20261031/capture.py",".github/workflows/dot-f08-windows-etw-20261031.yml"},"scope")
def xml_counts(path,pid):
    counts=collections.Counter();fixture=collections.Counter();examples={}
    for _,node in ET.iterparse(path,events=("end",)):
        if node.tag.rsplit("}",1)[-1]!="Event":continue
        system=next((x for x in node if x.tag.rsplit("}",1)[-1]=="System"),None)
        if system is None:node.clear();continue
        fields={x.tag.rsplit("}",1)[-1]:x for x in system}
        provider=fields.get("Provider")
        name=provider.attrib.get("Name",provider.attrib.get("Guid","unknown")) if provider is not None else "unknown"
        event=fields.get("EventID");event_id=event.text if event is not None else "unknown"
        execution=fields.get("Execution");process=execution.attrib.get("ProcessID") if execution is not None else None
        key=name+"/"+str(event_id);counts[key]+=1
        if process==str(pid):
            fixture[key]+=1
            if key not in examples and len(examples)<80:examples[key]=ET.tostring(node,encoding="unicode")
        node.clear()
    return {"all_events":sum(counts.values()),"fixture_events":sum(fixture.values()),
        "all_by_provider_event":dict(sorted(counts.items())),"fixture_by_provider_event":dict(sorted(fixture.items())),
        "fixture_event_examples":examples}
def capture():
    import ctypes
    guard();OUT.mkdir(parents=True,exist_ok=False)
    report={**identity(),"synthetic_only":True,"product_measured":False,"f08_accepted":False,"captures":[],"problems":[]}
    binary=ROOT/"build/f08-win-control/Release/f08_frame_control.exe"
    shutil.copyfile(binary,OUT/"f08_frame_control.exe")
    report["control_sha256"]=sha(binary)
    report["control_source_sha256"]=sha(ROOT/"tests/reader_f08_windows_frame_capability_20261031/control.cpp")
    providers=OUT/"providers.txt";providers.write_text("\n".join(p+" 0xffffffffffffffff 5" for p in PROVIDERS)+"\n")
    def execute(args,log,checked=True,timeout=60):
        result=subprocess.run(list(map(str,args)),cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        Path(log).write_bytes(result.stdout)
        if checked:need(result.returncode==0,"command failed: "+str(args[0]))
        return result
    execute(["powershell","-NoProfile","-Command","Get-Process -Name dwm,explorer -ErrorAction SilentlyContinue | Select-Object Name,Id,SessionId | ConvertTo-Json"],OUT/"desktop-processes.json",False)
    execute(["query","session"],OUT/"sessions.txt",False)
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.CreateEventW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_wchar_p];kernel.CreateEventW.restype=ctypes.c_void_p
    kernel.SetEvent.argtypes=[ctypes.c_void_p];kernel.SetEvent.restype=ctypes.c_int
    kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle.restype=ctypes.c_int
    for mode in ("dxgi","gdi"):
        folder=OUT/mode;folder.mkdir()
        session="F08-raw-"+identity()["run_id"]+"-"+mode;event_name="Local\\"+session
        event=kernel.CreateEventW(None,True,False,event_name);need(event,"start event")
        producer=None;started=False;entry={"mode":mode,"complete":False};report["captures"].append(entry)
        try:
            with (folder/"control.jsonl").open("wb") as output:
                producer=subprocess.Popen([str(binary),mode,event_name],stdout=output,stderr=output)
                entry["pid"]=producer.pid
                trace=["logman","create","trace",session,"-ets","-o",folder/"raw.etl","-f","bin","-max","256",
                       "-bs","64","-nb","32","128","-ct","perf","-pf",providers]
                save(folder/"trace-command.json",trace if all(isinstance(x,str) for x in trace) else list(map(str,trace)))
                execute(trace,folder/"trace-start.txt");started=True
                state=execute(["logman","query",session,"-ets"],folder/"trace-state.txt")
                decoded=state.stdout.decode("utf-16" if state.stdout.startswith(b"\xff\xfe") else "utf-8",errors="replace")
                need("Running" in decoded and all(p in decoded for p in PROVIDERS),"ETW readiness")
                need(kernel.SetEvent(event),"release control")
                entry["exit"]=producer.wait(timeout=15);need(entry["exit"]==0,"native control")
            execute(["logman","stop",session,"-ets"],folder/"trace-stop.txt");started=False
            execute(["tracerpt",folder/"raw.etl","-of","XML","-o",folder/"events.xml",
                     "-summary",folder/"summary.txt","-y"],folder/"tracerpt.txt",timeout=180)
            rows=[json.loads(line) for line in (folder/"control.jsonl").read_text().splitlines()]
            need(rows[0]["kind"]=="start" and rows[-1]["kind"]=="stop" and rows[-1]["ticks"]==41,"control endpoints")
            need(all(x["pid"]==producer.pid for x in rows),"control PID")
            draws=[x for x in rows if x["kind"] in ("gdi_paint","dxgi_present")]
            need(len(draws)>=35 and all(x["result"]==0 and x["end_qpc"]>=x["start_qpc"] for x in draws),"native draws")
            entry.update(draw_calls=len(draws),events=xml_counts(folder/"events.xml",producer.pid),complete=True)
        except Exception as error:
            entry["error"]=repr(error);report["problems"].append(mode+": "+repr(error))
        finally:
            if producer is not None and producer.poll() is None:producer.terminate();producer.wait(timeout=15)
            if started:execute(["logman","stop",session,"-ets"],folder/"trace-stop-finally.txt",False)
            kernel.CloseHandle(event)
        print("F08_ETW_CAPTURE",json.dumps(entry),flush=True)
    report["diagnostic_complete"]=not report["problems"]
    report["files"]={p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
                     for p in sorted(OUT.rglob("*")) if p.is_file()}
    save(OUT/"receipt.json",report)
    print("F08_ETW_RESULT",json.dumps({k:v for k,v in report.items() if k not in ("files","captures")}),flush=True)
    need(report["diagnostic_complete"],"raw capture failed")
def audit():
    guard()
    target=ROOT/"build/f08-windows-etw-audit";target.mkdir(parents=True)
    api=lambda p:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+p]))
    artifact=int(os.environ["F08_ARTIFACT_ID"]);meta=api("actions/artifacts/"+str(artifact))
    ident=identity();save(target/"metadata.json",meta)
    need(meta["name"]=="f08-windows-etw-"+ident["run_id"]+"-"+ident["attempt"] and not meta["expired"]
         and str(meta["workflow_run"]["id"])==ident["run_id"] and meta["workflow_run"]["head_sha"]==ident["source_sha"],"artifact producer")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(artifact)+"/zip"])
    digest=hashlib.sha256(data).hexdigest()
    need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest
         and os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest,"ZIP bytes")
    (target/"original.zip").write_bytes(data);raw=target/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos=archive.infolist();need(0<len(infos)<100 and sum(i.file_size for i in infos)<2*1024**3,"ZIP bounds")
        names=set()
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and "\\" not in info.filename
                 and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key)
            need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"ZIP kind")
            if info.is_dir():continue
            destination=raw/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(archive.read(info))
    receipt=json.loads((raw/"receipt.json").read_text())
    need(all(receipt.get(k)==v for k,v in ident.items()) and receipt["synthetic_only"] is True
         and receipt["product_measured"] is False and receipt["f08_accepted"] is False,"receipt identity")
    files={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    need(files==set(receipt["files"])|{"receipt.json"},"inventory")
    for name,item in receipt["files"].items():need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"payload bytes")
    need(sha(raw/"f08_frame_control.exe")==receipt["control_sha256"],"control binary")
    for entry in receipt["captures"]:
        if entry["complete"]:need(xml_counts(raw/entry["mode"]/"events.xml",entry["pid"])==entry["events"],"raw events differ")
    result={**ident,"artifact_id":artifact,"sha256":digest,"authenticated":True,
            "diagnostic_complete":receipt["diagnostic_complete"],"captures":receipt["captures"],"f08_accepted":False}
    save(target/"audit.json",result);print("F08_ETW_AUDIT",json.dumps(result),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("capture","audit"))
    globals()[parser.parse_args().mode]()
