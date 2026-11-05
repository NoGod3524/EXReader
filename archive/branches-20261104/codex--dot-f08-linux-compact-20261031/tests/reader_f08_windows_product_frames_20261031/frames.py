"""Capture real product Windows ETW through unchanged interaction test bodies."""
import argparse, contextlib, ctypes as C, hashlib, io, json, os, runpy, shutil, subprocess, sys, time, traceback, zipfile
from ctypes import wintypes as T
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"tests/reader_f08_windows_product_20261031"))
import audit as PRODUCT
from build import identity, need, save, sha, command
sys.path.insert(0,str(ROOT/"tests/reader_f08_windows_etw_20261031"))
import replay_audit as REPLAY
from capture import PROVIDERS
BASE="6bb0a7083c218b8899f9451336654c650b53495c"
PIN={"source_sha":"6bb0a7083c218b8899f9451336654c650b53495c","run_id":"41188896369","attempt":"1",
     "artifact_id":13038192218,"bytes":46042724,"digest":"94433d419c3bdee542e968d682a2ede7102527036a4a64e82b8cdf77a0145877"}
OUT=ROOT/"build/f08-windows-product-frames"
FILES={"tests/reader_f08_windows_product_frames_20261031/frames.py",".github/workflows/dot-f08-windows-product-frames-20261031.yml"}
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and os.name=="nt","Windows Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==FILES,"test-only scope")
def api(path):return json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+path]))
def extract(data,directory,manifest_name,ident):
    directory.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in PRODUCT.entries(archive):
            if item.is_dir():continue
            p=directory/item.filename;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.read(item))
    manifest=json.loads((directory/manifest_name).read_text())
    need(all(manifest.get(k)==v for k,v in ident.items()) and manifest["f08_accepted"] is False,"manifest identity")
    actual={p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    need(actual==set(manifest["files"])|{manifest_name},"complete inventory")
    for name,item in manifest["files"].items():
        need(sha(directory/name)==item["sha256"] and (directory/name).stat().st_size==item["bytes"],"file bytes: "+name)
    return manifest
def product(target,provided=None):
    meta=api("actions/artifacts/"+str(PIN["artifact_id"]))
    producer=api("actions/runs/"+PIN["run_id"]+"/attempts/"+PIN["attempt"])
    ident={k:PIN[k] for k in ("source_sha","run_id","attempt")}
    need(producer["head_sha"]==PIN["source_sha"] and str(producer["run_attempt"])==PIN["attempt"],"program producer")
    need(meta["id"]==PIN["artifact_id"] and not meta["expired"] and meta["size_in_bytes"]==PIN["bytes"]
         and meta["digest"]=="sha256:"+PIN["digest"] and meta["workflow_run"]["head_sha"]==PIN["source_sha"]
         and str(meta["workflow_run"]["id"])==PIN["run_id"],"program artifact")
    data=provided if provided is not None else command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(PIN["artifact_id"])+"/zip"])
    need(len(data)==PIN["bytes"] and hashlib.sha256(data).hexdigest()==PIN["digest"],"program ZIP bytes")
    target.mkdir(parents=True,exist_ok=False);(target/"original.zip").write_bytes(data);save(target/"metadata.json",meta)
    raw=target/"raw";extract(data,raw,"manifest.json",ident)
    built=json.loads((raw/"build-identity.json").read_text());package=json.loads((raw/"package-build.json").read_text())
    need(all(built.get(k)==v for k,v in ident.items()) and built["sdk_version"]=="3.42.0","program build")
    for name,digest in built["components"].items():
        need(command(["git","rev-parse","HEAD:"+name],text=True).strip()==digest,"frozen production tree")
    for name,digest in built["unchanged_helpers"].items():need(sha(ROOT/name)==digest,"original helper")
    need(built["features"]=={"wave3":True,"raw_selector":True,"cloud_content_bound":True,"txt_progress":True},"full host features")
    need(sha(raw/"program/EXReader.exe")==built["program_sha256"] and sha(raw/"seed.exe")==built["seed_sha256"]
         and sha(raw/"program.zip")==built["package_sha256"],"actual program")
    need(package["passed"] is True and package["source_sha"]==PIN["source_sha"] and
         package["sdk_version"]=="3.42.0" and package["selftest_checks"]>=26,"native package")
    need((raw/"profile.json").read_bytes()==(ROOT/"tests/reader_f08_windows_product_20261031/profile.json").read_bytes(),"fixed platform")
    sample=json.loads((raw/"sample-result.json").read_text())
    verification=json.loads((raw/"observations/verification.json").read_text())
    need(sample["collection_complete"] is True and verification["accepted"] is True and
         verification["checks_passed"]==verification["checks_total"]==20,"complete original observations")
    budgets=PRODUCT.raw_budgets(raw,json.loads((raw/"observations/summary.json").read_text()),
                               json.loads((raw/"profile.json").read_text()))
    need(budgets==sample["budget_evaluation"] and budgets["non_frame_budget_passed"],"same-program memory and interaction budgets")
    return raw,{"pin":PIN,"program_sha256":built["program_sha256"],"build_authenticated":True,
                "producer_observations_accepted":True,"non_frame_budgets":budgets,"unchanged_helpers":built["unchanged_helpers"]}
def execute(args,log,checked=True,timeout=180):
    done=subprocess.run(list(map(str,args)),cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    Path(log).write_bytes(done.stdout)
    if checked and done.returncode:
        print(done.stdout.decode("utf-8",errors="replace"),flush=True)
        need(False,"command failed: "+str(args[0]))
    return done
def analyze(folder,pid,frequency,native):
    rows=list(REPLAY.events(folder/"events.xml"))
    headers=[r for r in rows if r["provider"].startswith("{9e814aad") and "PerfFreq" in r["data"]]
    need(len(headers)==1,"single ETW header")
    header=headers[0]["data"]
    need(int(header["PerfFreq"].strip())==frequency and int(header["EventsLost"].strip())==0
         and int(header["BuffersLost"].strip())==0,"same QPC and zero ETW loss")
    events=[json.loads(line) for line in native.read_text().splitlines()]
    need(events and events[0]["kind"]=="process" and events[0]["pid"]==pid and
         events[0]["frequency"]==frequency and events[-1]["kind"]=="close","native endpoints")
    bindings=[r for r in events if r["kind"]=="window"]
    need(bindings and all(r["pid"]==pid and r["observed_pid"]==pid and r["hwnd"]>0 for r in bindings),"PID-owned windows")
    handles={r["hwnd"] for r in bindings}
    formats={str(v).strip().casefold() for r in rows for k,v in r["data"].items()
             if ("wnd" in k.casefold() or "window" in k.casefold()) and REPLAY.unsigned(v) in handles}
    with (folder/"analysis.log").open("w",encoding="utf-8") as log,contextlib.redirect_stdout(log):
        context=REPLAY.inspect_composition(rows,formats,pid,folder)
    joins=json.loads((folder/"frame-retirement-joins.json").read_text())
    durations=[1000*(r["qpc_confirmed"]-r["cycle_start_qpc"])/frequency for r in joins if r["frame_id_retirement_join_valid"]]
    summary={"pid":pid,"qpc_frequency":frequency,"etw_events":len(rows),"bound_windows":len(handles),
        "input_dispatches":sum(r["kind"]=="input" for r in events),"composition":context,
        "dwm_cycle_to_retirement_ms":durations,"scope":"DWM composition cycle; not application input-to-frame time",
        "application_paint_generation_bound":False,"frame_budget_measured":False,"physical_presentation_proven":False}
    save(folder/"analysis.json",summary)
    return summary
def launch_bindings(records,captures,root):
    lifetimes=[];indexes=set()
    for entry in captures:
        index=entry["index"];need(index not in indexes and entry["folder"]=="trace-%03d"%index,"trace identity")
        indexes.add(index)
        events=[json.loads(line) for line in (root/entry["folder"]/"native.jsonl").read_text().splitlines()]
        first,last=events[0],events[-1]
        need(first["kind"]=="process" and last["kind"]=="close" and
             first["pid"]==last["pid"]==entry["pid"] and first["frequency"]==entry["frequency"] and
             type(first["qpc"]) is int and type(last["qpc"]) is int and 0<first["qpc"]<last["qpc"]
             and type(last["exit"]) is int,"closed native process lifetime")
        log=Path(first["log"])
        need(log.parent.name=="logs" and log.parent.parent.name=="observations","native sampler log origin")
        lifetimes.append({"trace_index":index,"pid":entry["pid"],"start_qpc":first["qpc"],
            "end_qpc":last["qpc"],"frequency":first["frequency"],"log_name":log.name,"complete":entry["complete"]})
    for index,current in enumerate(lifetimes):
        for previous in lifetimes[:index]:
            if previous["pid"]==current["pid"]:
                need(previous["frequency"]==current["frequency"] and previous["end_qpc"]<current["start_qpc"],
                     "overlapping lifetimes for a reused PID")
    result=[];used=set()
    for row in records:
        launch=row["launch_id"]
        need(launch=="%s-%02d"%(row["cohort"],row["index"]),"original launch identifier")
        matches=[x for x in lifetimes if x["pid"]==row["pid"] and x["log_name"]==launch+".log"]
        need(len(matches)==1 and matches[0]["trace_index"] not in used and matches[0]["complete"],"unique launch lifetime")
        match=matches[0];used.add(match["trace_index"])
        log=root/"observations/logs"/match["log_name"]
        need(log.is_file() and log.stat().st_size==row["log_bytes"],"exact original process log")
        result.append({"launch_id":launch,**match})
    need(len(result)==len(records),"complete launch bindings")
    return result

def binding_regression():
    guard()
    target=ROOT/"build/f08-windows-lifetime-regression";target.mkdir(parents=True,exist_ok=False)
    pin={"source_sha":"f751c2ac8e0c9359119b3558d59aa76f2fb74188","run_id":"41189536724","attempt":"1"}
    artifact=13038376565;digest="be6b47c8ccbb7d81e2a99e471dead5ad34540c7579469a255855339206e408c6";size=119484609
    meta=api("actions/artifacts/"+str(artifact));producer=api("actions/runs/"+pin["run_id"]+"/attempts/1")
    need(meta["id"]==artifact and not meta["expired"] and meta["size_in_bytes"]==size and meta["digest"]=="sha256:"+digest
         and meta["workflow_run"]["head_sha"]==pin["source_sha"] and str(meta["workflow_run"]["id"])==pin["run_id"]
         and producer["head_sha"]==pin["source_sha"] and producer["run_attempt"]==1,"retained regression producer")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(artifact)+"/zip"])
    need(len(data)==size and hashlib.sha256(data).hexdigest()==digest,"retained regression ZIP")
    raw=target/"raw";extract(data,raw,"manifest.json",pin)
    original=json.loads((raw/"result.json").read_text())
    need(original["capture_complete"] is False and original["problems"]==["ValueError('process PID reused within cohort')"]
         and len(original["captures"])==12 and all(x["complete"] for x in original["captures"]),"actual retained PID failure")
    records=json.loads((raw/"observations/per-launch.json").read_text());need(len(records)==10,"regression launches")
    bindings=launch_bindings(records,original["captures"],raw)
    need(len({x["pid"] for x in original["captures"]})<len(original["captures"]),"actual reused PID")
    negatives=[]
    for field,value in (("pid",-1),("launch_id","foreign-00")):
        changed=[dict(x) for x in records];changed[0][field]=value
        try:launch_bindings(changed,original["captures"],raw)
        except ValueError:negatives.append(field)
        else:raise ValueError("foreign launch identity accepted")
    report={**identity(),"producer":pin,"artifact_id":artifact,"sha256":digest,"authenticated":True,
        "bindings":bindings,"negative_controls":negatives,"original_failure_preserved":True,"resampled":False,"f08_accepted":False}
    save(target/"regression.json",report);print("F08_PROCESS_LIFETIME_REGRESSION",json.dumps(report),flush=True)

def capture():
    guard();OUT.mkdir(parents=True,exist_ok=False)
    report={**identity(),"capture_complete":False,"captures":[],"problems":[],"f08_accepted":False,
            "frame_budget_measured":False,"application_paint_generation_bound":False}
    fatal=None
    try:
        raw,report["product"]=product(OUT/"product")
        execute([sys.executable,"tests/reader_wave3_c09/desktop.py","--output",OUT/"desktop.json"],OUT/"desktop.log")
        profile=json.loads((raw/"profile.json").read_text());desktop=json.loads((OUT/"desktop.json").read_text())
        need(desktop["accepted"] is True and desktop["after"]==[profile["screen_width"],profile["screen_height"]],"fixed desktop")
        providers=OUT/"providers.txt";providers.write_text("\n".join(p+" 0xffffffffffffffff 5" for p in PROVIDERS)+"\n")
        import native_picker as ADAPTER
        P=ADAPTER.P
        kernel=C.WinDLL("kernel32",use_last_error=True);user=C.WinDLL("user32",use_last_error=True)
        kernel.QueryPerformanceCounter.argtypes=[C.POINTER(C.c_longlong)];kernel.QueryPerformanceCounter.restype=T.BOOL
        kernel.QueryPerformanceFrequency.argtypes=[C.POINTER(C.c_longlong)];kernel.QueryPerformanceFrequency.restype=T.BOOL
        frequency=C.c_longlong();need(kernel.QueryPerformanceFrequency(C.byref(frequency)),"QPC frequency")
        def qpc():
            counter=C.c_longlong();need(kernel.QueryPerformanceCounter(C.byref(counter)),"QPC");return counter.value
        enum=C.WINFUNCTYPE(T.BOOL,T.HWND,T.LPARAM)
        user.EnumChildWindows.argtypes=[T.HWND,enum,T.LPARAM];user.EnumChildWindows.restype=T.BOOL
        user.GetWindowThreadProcessId.argtypes=[T.HWND,C.POINTER(T.DWORD)];user.GetWindowThreadProcessId.restype=T.DWORD
        user.GetClassNameW.argtypes=[T.HWND,T.LPWSTR,C.c_int];user.GetClassNameW.restype=C.c_int
        user.GetDlgCtrlID.argtypes=[T.HWND];user.GetDlgCtrlID.restype=C.c_int
        original_init,original_close,original_find,original_send=P.Host.__init__,P.Host.close,P.Host.find_window,P.Host.send
        def emit(host,event):
            with (host._f08_folder/"native.jsonl").open("a",encoding="utf-8") as stream:
                stream.write(json.dumps(event)+"\n")
        def bind(host,window):
            handle=int(window or 0)
            if not handle or handle in host._f08_handles:return
            owner=T.DWORD();thread=user.GetWindowThreadProcessId(window,C.byref(owner))
            need(owner.value==host.process.pid,"window ownership")
            kind=C.create_unicode_buffer(128);need(user.GetClassNameW(window,kind,128)>0,"window class")
            emit(host,{"kind":"window","pid":host.process.pid,"observed_pid":owner.value,"tid":thread,
                "hwnd":handle,"class":kind.value,"control_id":user.GetDlgCtrlID(window),"qpc":qpc()})
            host._f08_handles.add(handle)
        def init(host,*args,**kwargs):
            index=len(report["captures"]);folder=OUT/("trace-%03d"%index);folder.mkdir()
            session="F08-product-"+identity()["run_id"]+"-"+str(index)
            entry={"index":index,"folder":folder.name,"complete":False};report["captures"].append(entry)
            host._f08_folder=folder;host._f08_handles=set();host._f08_entry=entry;host._f08_session=session;host._f08_started=False
            trace=["logman","create","trace",session,"-ets","-o",folder/"raw.etl","-f","bin","-max","256",
                   "-bs","64","-nb","32","128","-ct","perf","-pf",providers]
            save(folder/"trace-command.json",list(map(str,trace)))
            try:
                execute(trace,folder/"start.log");host._f08_started=True
                state=execute(["logman","query",session,"-ets"],folder/"state.log").stdout
                text=state.decode("utf-16" if state.startswith(b"\xff\xfe") else "utf-8",errors="replace")
                need("Running" in text and all(p in text for p in PROVIDERS),"ETW readiness")
                original_init(host,*args,**kwargs)
                entry.update(pid=host.process.pid,frequency=frequency.value)
                emit(host,{"kind":"process","pid":host.process.pid,"frequency":frequency.value,"qpc":qpc(),
                    "exe_sha256":sha(host.exe),"log":str(host.log_path)})
            except BaseException as error:
                entry["error"]=repr(error)
                if host._f08_started:execute(["logman","stop",session,"-ets"],folder/"stop-init.log",False);host._f08_started=False
                raise
        def find(host):
            result=original_find(host)
            if result and int(result) not in host._f08_handles:
                bind(host,result)
                errors=[]
                @enum
                def child(window,unused):
                    try:bind(host,window)
                    except BaseException as error:errors.append(repr(error))
                    return True
                user.EnumChildWindows(result,child,0);need(not errors,"child ownership: "+str(errors))
            return result
        def send(host,hwnd,message,wparam=0,lparam=0,timeout=2000):
            if message not in (0xF5,0x20A,0x186,0x111,0xC):return original_send(host,hwnd,message,wparam,lparam,timeout)
            bind(host,hwnd);start=qpc()
            event={"kind":"input","pid":host.process.pid,"hwnd":int(hwnd),"message":message,"wparam":wparam,
                   "control_id":user.GetDlgCtrlID(hwnd),"start_qpc":start,"completed":False}
            try:
                result=original_send(host,hwnd,message,wparam,lparam,timeout);event["completed"]=True;return result
            except BaseException as error:event["error"]=repr(error);raise
            finally:event["end_qpc"]=qpc();emit(host,event)
        def close(host,*args,**kwargs):
            try:return original_close(host,*args,**kwargs)
            finally:
                if host._f08_started:
                    folder=host._f08_folder;entry=host._f08_entry
                    try:
                        emit(host,{"kind":"close","pid":host.process.pid,"qpc":qpc(),"exit":host.process.poll()})
                        time.sleep(0.25)
                        execute(["logman","stop",host._f08_session,"-ets"],folder/"stop.log");host._f08_started=False
                        execute(["tracerpt",folder/"raw.etl","-rts","-of","XML","-o",folder/"events.xml","-y"],folder/"tracerpt.log")
                        entry["analysis"]=analyze(folder,host.process.pid,frequency.value,folder/"native.jsonl")
                        need(entry["analysis"]["composition"]["target_window_cycles"]>0 and
                             entry["analysis"]["composition"]["retirement_join"]["valid_frame_id_retirement_joins"]>0,
                             "no product composition frame retirement")
                        entry["complete"]=True
                    except BaseException as error:
                        entry["error"]=repr(error);report["problems"].append(repr(error))
                    finally:
                        if host._f08_started:execute(["logman","stop",host._f08_session,"-ets"],folder/"stop-finally.log",False);host._f08_started=False
        P.Host.__init__,P.Host.close,P.Host.find_window,P.Host.send=init,close,find,send
        ADAPTER.prepare_scroll_origin()
        script=ROOT/"tests/reader_product_performance_handoff/sample_windows_interactions.py"
        sys.argv=[str(script),"--package",str(raw/"program"),"--seed",str(raw/"seed.exe"),
            "--output",str(OUT/"observations"),"--work",str(ROOT/"build/f08-windows-product-frames-work"),"--cohorts","warm_shelf,reading","--launches-per-cohort","5"]
        try:
            with (OUT/"original-interactions.log").open("w",encoding="utf-8") as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                try:runpy.run_path(str(script),run_name="__main__")
                except SystemExit as error:need(error.code in (None,0),"original interaction exit "+str(error.code))
        finally:P.Host.__init__,P.Host.close,P.Host.find_window,P.Host.send=original_init,original_close,original_find,original_send
        interactions=json.loads((OUT/"observations/interactions.json").read_text())
        need(not interactions["faults"] and len(interactions["font_order"])==5,"original interaction coverage")
        for name,count in {"shelf_scroll_down":15,"shelf_scroll_up":15,"font_bigger":10,"font_smaller":10}.items():
            need(len(interactions[name])==count,"original interaction count")
        launches=json.loads((OUT/"observations/per-launch.json").read_text())
        need(len(launches)==10 and {r["cohort"] for r in launches}=={"warm_shelf","reading"},"original launches")
        report["launch_bindings"]=launch_bindings(launches,report["captures"],OUT)
        need(report["captures"] and all(x["complete"] for x in report["captures"]) and not report["problems"],"complete traces")
        report["capture_complete"]=True
    except BaseException as error:
        fatal=error;report["problems"].append(repr(error));report["traceback"]=traceback.format_exc()
    finally:
        save(OUT/"result.json",report)
        save(OUT/"manifest.json",{**identity(),"f08_accepted":False,
             "files":{p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
                      for p in sorted(OUT.rglob("*")) if p.is_file() and p!=OUT/"manifest.json"}})
        print("F08_PRODUCT_ETW",json.dumps({k:v for k,v in report.items() if k!="captures"}),flush=True)
        for entry in report["captures"]:
            print("F08_PRODUCT_ETW_CAPTURE",json.dumps({k:v for k,v in entry.items() if k!="analysis"}),flush=True)
    if fatal:raise fatal
def audit():
    guard();target=ROOT/"build/f08-windows-product-frames-audit";target.mkdir(parents=True,exist_ok=False)
    artifact=int(os.environ["F08_ARTIFACT_ID"]);meta=api("actions/artifacts/"+str(artifact));ident=identity()
    need(meta["id"]==artifact and not meta["expired"] and meta["name"]=="f08-windows-product-frames-"+ident["run_id"]+"-"+ident["attempt"]
         and str(meta["workflow_run"]["id"])==ident["run_id"] and meta["workflow_run"]["head_sha"]==ident["source_sha"],"trace artifact")
    run=api("actions/runs/"+ident["run_id"])
    need(run["head_sha"]==ident["source_sha"] and str(run["run_attempt"])==ident["attempt"],"trace producer")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(artifact)+"/zip"])
    digest=hashlib.sha256(data).hexdigest()
    need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest and
         os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest,"trace ZIP")
    save(target/"metadata.json",meta);raw=target/"raw";extract(data,raw,"manifest.json",ident)
    result=json.loads((raw/"result.json").read_text())
    need(all(result.get(k)==v for k,v in ident.items()) and result["f08_accepted"] is False,"result identity")
    verified=[]
    if (raw/"product/original.zip").exists():
        _,bound=product(target/"verified-product",(raw/"product/original.zip").read_bytes())
        if "product" in result:need(bound==result["product"],"product binding")
    for entry in result["captures"]:
        if not entry["complete"]:continue
        folder=target/entry["folder"];folder.mkdir()
        source=raw/entry["folder"]
        execute(["tracerpt",source/"raw.etl","-rts","-of","XML","-o",folder/"events.xml","-y"],folder/"tracerpt.log")
        recomputed=analyze(folder,entry["pid"],entry["frequency"],source/"native.jsonl")
        need(recomputed==entry["analysis"] and recomputed==json.loads((source/"analysis.json").read_text()),"independent frame analysis")
        verified.append({"pid":entry["pid"],"composition":recomputed["composition"],
                         "native_input_dispatches":recomputed["input_dispatches"]})
    bindings=None
    if result["capture_complete"]:
        need(len(verified)==len(result["captures"]) and len(verified)>=10,"every trace independently verified")
        bindings=launch_bindings(json.loads((raw/"observations/per-launch.json").read_text()),result["captures"],raw)
        need(bindings==result["launch_bindings"],"independent process lifetime bindings")
    report={**ident,"artifact_id":artifact,"sha256":digest,"authenticated":True,"capture_complete":result["capture_complete"],
        "captures":verified,"launch_bindings":bindings,"problems":result["problems"],"frame_budget_measured":False,
        "application_paint_generation_bound":False,"f08_accepted":False}
    save(target/"audit.json",report);print("F08_PRODUCT_ETW_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("capture","audit","binding_regression"));globals()[parser.parse_args().mode]()
