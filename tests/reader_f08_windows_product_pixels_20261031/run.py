"""Real Windows product desktop pixels beside unchanged interaction test bodies."""
import argparse, contextlib, ctypes as C, hashlib, json, os, runpy, shutil, struct, subprocess, sys, time, traceback
from ctypes import wintypes as T
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"tests/reader_f08_windows_product_frames_20261031"))
import frames as F
from build import identity, need, save, sha, command
BASE="dcce81889859e66149f9544f2493898b84549d60"
OUT=ROOT/"build/f08-windows-product-pixels"
FILES={"tests/reader_f08_windows_product_pixels_20261031/CMakeLists.txt",
       "tests/reader_f08_windows_product_pixels_20261031/observer.cpp",
       "tests/reader_f08_windows_product_pixels_20261031/run.py",
       ".github/workflows/dot-f08-windows-product-pixels-20261031.yml"}
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and os.name=="nt","Windows Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"source identity")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==FILES,"test-only scope")
def rows(path):return [json.loads(line) for line in path.read_text().splitlines()]
def bitmap(path):
    data=path.read_bytes();need(len(data)>54,"bitmap bytes")
    magic,size,reserved1,reserved2,offset=struct.unpack_from("<2sIHHI",data)
    info,width,height,planes,bits,compression,image_size,xppm,yppm,used,important=struct.unpack_from("<IiiHHIIiiII",data,14)
    need(magic==b"BM" and size==len(data) and reserved1==reserved2==0 and offset==54 and info==40 and
         width>0 and height<0 and planes==1 and bits==32 and compression==0 and
         image_size==width*-height*4 and len(data)==54+image_size,"native top-down BGRA bitmap")
    pixels=data[54:];need(all(a==255 for a in pixels[3::4]),"opaque normalized desktop alpha")
    return {"sha256":hashlib.sha256(data).hexdigest(),"width":width,"height":-height,
            "bgr_sha256":hashlib.sha256(pixels).hexdigest(),"nonuniform":len(set(pixels[0::4]))>1 or
            len(set(pixels[1::4]))>1 or len(set(pixels[2::4]))>1}
def analyze(folder,entry):
    native=rows(folder/"native.jsonl");driver=rows(folder/"driver.jsonl")
    need(native and native[0]["kind"]=="start" and native[-1]["kind"]=="summary","native capture endpoints")
    first,last=native[0],native[-1];pid=entry["pid"];freq=entry["frequency"]
    need(first["product_pid"]==pid and first["root_hwnd"]==entry["hwnd"] and first["frequency"]==freq and
         first["observer_pid"]==entry["observer_pid"] and 0<first["qpc"]<last["qpc"] and not last["deadline_expired"],
         "native product/window/observer identity")
    need(not [r for r in native if r["kind"] in ("error","fatal")],"native capture error")
    ready=[r for r in native if r["kind"]=="ready"]
    need(len(ready)==1 and ready[0]["width"]==1280 and ready[0]["height"]==800 and ready[0]["format"]==87 and
         ready[0]["rotation"] in (0,1) and ready[0]["ring_slots"]==8,"fixed native desktop")
    need(driver[0]["kind"]=="process" and driver[-1]["kind"]=="close" and
         driver[0]["pid"]==driver[-1]["pid"]==pid and driver[0]["frequency"]==freq and
         driver[0]["exe_sha256"]==entry["program_sha256"] and driver[0]["qpc"]<=first["qpc"]<last["qpc"]<=driver[-1]["qpc"] and
         type(driver[-1]["exit"]) is int,"actual native process lifetime")
    images={};previous={};changed={119:[],123:[]};valid={119:0,123:0};invalid={119:0,123:0};indices=set();present=0;extra=0
    frames=sorted([r for r in native if r["kind"] in ("frame","pointer_only")],key=lambda r:r["index"])
    need([r["index"] for r in frames]==list(range(1,len(frames)+1)) and len(frames)==last["desktop_records"],"no omitted acquisition records")
    for frame in frames:
        index=frame["index"];extra+=max(0,frame["accumulated_frames"]-1)
        if frame["kind"]=="pointer_only":continue
        need(first["qpc"]<=frame["start_qpc"]<=frame["acquired_qpc"]<=frame["geometry_qpc"]<=frame["readback_finished_qpc"]<=last["qpc"] and
             0<frame["last_present_qpc"]<=frame["acquired_qpc"] and frame["last_present_qpc"]>present and
             frame["accumulated_frames"]>0,"native frame QPC chronology")
        present=frame["last_present_qpc"]
        need([r["control_id"] for r in frame["regions"]]==[119,123],"both native content regions")
        for region in frame["regions"]:
            control=region["control_id"];rect=region["rect"]
            valid_native=region["pid"]==pid and all(region[k] is True for k in
                ("visible","unoccluded","in_bounds","geometry_stable")) and frame["protected_content"] is False
            need(type(region["valid"]) is bool and region["valid"]==valid_native,"native visibility predicate")
            if not region["valid"]:
                need(region["image"]=="" and region["changed"] is False,"unavailable content retained without image")
                invalid[control]+=1;continue
            valid[control]+=1
            name=region["image"];parts=name.removesuffix(".bmp").split("-")
            need(name.endswith(".bmp") and len(parts)==2 and parts[0]==str(control) and parts[1].isdigit() and
                 0<int(parts[1])<=index and region["hwnd"]>0 and len(rect)==4 and
                 all(type(x) is int for x in rect) and rect[2]>rect[0]>=0 and rect[3]>rect[1]>=0 and
                 rect[2]<=1280 and rect[3]<=800,"native region geometry and image identity")
            if name not in images:images[name]=bitmap(folder/"images"/name)
            image=images[name];need(image["width"]==rect[2]-rect[0] and image["height"]==rect[3]-rect[1],"bitmap/native region dimensions")
            key=(image["width"],image["height"],image["bgr_sha256"])
            actual_changed=previous.get(control)!=key
            need(region["changed"]==actual_changed,"independent pixel-change recomputation")
            if actual_changed:
                need(int(parts[1])==index,"new pixels use this native frame identity")
                changed[control].append({"index":index,"qpc":frame["last_present_qpc"],"image":name,"sha256":image["sha256"]})
            previous[control]=key
    need(set(images)=={p.name for p in (folder/"images").glob("*")},"complete raw image inventory")
    need(extra==last["accumulated_extra_frames"] and sum(r["kind"]=="pointer_only" for r in frames)==last["pointer_only"],
         "native accumulated and pointer-only record accounting")
    inputs=[r for r in driver if r["kind"]=="input"]
    for event in inputs:
        need(event["pid"]==pid and driver[0]["qpc"]<=event["start_qpc"]<=event["end_qpc"]<=driver[-1]["qpc"],"native input lifetime")
        if event["dispatched"]:
            need(event["start_qpc"]<=event["dispatch_qpc"]<=event["end_qpc"],"actual dispatch time")
            if event["message"]==0xF5 and event["control_id"] in (113,114):
                need(event["enabled_at_dispatch"] is True and 0<event["remaining_ms"]<=2000,"original font deadline and readiness")
    return {"pid":pid,"observer_pid":entry["observer_pid"],"qpc_frequency":freq,
        "desktop_records":len(frames),"desktop_updates":len(frames)-last["pointer_only"],
        "pointer_only_records":last["pointer_only"],"accumulated_extra_frames":extra,"ring_backpressure":last["ring_backpressure"],
        "valid_region_records":valid,"unavailable_region_records":invalid,"distinct_content_frames":{k:len(v) for k,v in changed.items()},
        "nonuniform_images":sum(x["nonuniform"] for x in images.values()),"raw_images":images,"changed_content":changed,
        "native_input_dispatches":sum(x["dispatched"] for x in inputs),
        "scope":"Actual desktop pixels from PID-owned visible shelf/reading regions with native desktop-update QPC",
        "application_paint_generation_bound":False,"input_to_verified_content_measured":False,
        "frame_budget_measured":False,"physical_scanout_proven":False,"f08_accepted":False}
def capture():
    guard();OUT.mkdir(parents=True,exist_ok=False)
    report={**identity(),"collection_complete":False,"captures":[],"problems":[],"f08_accepted":False}
    fatal=None
    try:
        raw,report["product"]=F.product(OUT/"product")
        F.execute([sys.executable,"tests/reader_wave3_c09/desktop.py","--output",OUT/"desktop.json"],OUT/"desktop.log")
        desktop=json.loads((OUT/"desktop.json").read_text());need(desktop["accepted"] is True and desktop["after"]==[1280,800],"fixed desktop")
        binary=ROOT/"build/f08-product-pixels-build/Release/f08_product_pixels.exe"
        shutil.copyfile(binary,OUT/"observer.exe");report["observer_sha256"]=sha(binary)
        import native_picker as ADAPTER
        P=ADAPTER.P;kernel=C.WinDLL("kernel32",use_last_error=True);user=C.WinDLL("user32",use_last_error=True)
        for name in ("QueryPerformanceFrequency","QueryPerformanceCounter"):
            getattr(kernel,name).argtypes=[C.POINTER(C.c_longlong)];getattr(kernel,name).restype=T.BOOL
        user.GetDlgCtrlID.argtypes=[T.HWND];user.GetDlgCtrlID.restype=C.c_int
        user.IsWindowEnabled.argtypes=[T.HWND];user.IsWindowEnabled.restype=T.BOOL
        frequency=C.c_longlong();need(kernel.QueryPerformanceFrequency(C.byref(frequency)),"QPC frequency")
        def qpc():
            v=C.c_longlong();need(kernel.QueryPerformanceCounter(C.byref(v)),"QPC");return v.value
        original_init,original_find,original_send,original_close=P.Host.__init__,P.Host.find_window,P.Host.send,P.Host.close
        def emit(host,event):
            with (host._pixels_folder/"driver.jsonl").open("a",encoding="utf-8") as stream:stream.write(json.dumps(event)+"\n")
        def init(host,*args,**kwargs):
            index=len(report["captures"]);folder=OUT/("capture-%03d"%index);folder.mkdir()
            entry={"index":index,"folder":folder.name,"complete":False};report["captures"].append(entry)
            host._pixels_folder=folder;host._pixels_entry=entry;host._pixels_observer=None;host._pixels_stream=None
            original_init(host,*args,**kwargs)
            entry.update(pid=host.process.pid,frequency=frequency.value,program_sha256=sha(host.exe))
            emit(host,{"kind":"process","pid":host.process.pid,"qpc":qpc(),"frequency":frequency.value,
                "log":str(host.log_path),"exe_sha256":entry["program_sha256"]})
        def find(host):
            result=original_find(host)
            if result and host._pixels_observer is None:
                entry=host._pixels_entry;folder=host._pixels_folder;entry["hwnd"]=int(result)
                host._pixels_stream=(folder/"native.jsonl").open("wb")
                observer=subprocess.Popen([str(binary),str(int(result)),str(host.process.pid),
                    str(folder/"stop"),str(folder/"images")],cwd=ROOT,stdout=host._pixels_stream,stderr=subprocess.STDOUT)
                host._pixels_observer=observer;entry["observer_pid"]=observer.pid
                deadline=time.perf_counter()+10
                while True:
                    need(observer.poll() is None,"native observer stopped before readiness")
                    lines=(folder/"native.jsonl").read_text().splitlines()
                    if any('"kind":"ready"' in line for line in lines):break
                    need(time.perf_counter()<deadline,"native observer readiness timeout");time.sleep(0.01)
            return result
        def send(host,hwnd,message,wparam=0,lparam=0,timeout=2000):
            if message not in (0xF5,0x20A,0x186,0x111,0xC):return original_send(host,hwnd,message,wparam,lparam,timeout)
            deadline=time.perf_counter()+timeout/1000
            event={"kind":"input","pid":host.process.pid,"hwnd":int(hwnd),"message":message,"wparam":wparam,
                "control_id":user.GetDlgCtrlID(hwnd),"start_qpc":qpc(),"dispatched":False,"completed":False}
            try:
                remaining=timeout
                if message==0xF5 and event["control_id"] in (113,114):
                    remaining,polls=F.remaining_dispatch_budget(lambda:bool(user.IsWindowEnabled(hwnd)),deadline)
                    event.update(enabled_at_dispatch=bool(user.IsWindowEnabled(hwnd)),remaining_ms=remaining,ready_polls=polls)
                    need(event["enabled_at_dispatch"],"native font readiness")
                event.update(dispatch_qpc=qpc(),dispatched=True)
                value=original_send(host,hwnd,message,wparam,lparam,remaining);event["completed"]=True;return value
            except BaseException as error:event["error"]=repr(error);raise
            finally:event["end_qpc"]=qpc();emit(host,event)
        def close(host,*args,**kwargs):
            try:return original_close(host,*args,**kwargs)
            finally:
                entry=host._pixels_entry;folder=host._pixels_folder;observer=host._pixels_observer
                try:
                    if observer is not None:
                        (folder/"stop").write_text("original sampler has closed product\n")
                        try:code=observer.wait(timeout=30)
                        except subprocess.TimeoutExpired:observer.kill();code=observer.wait(timeout=10);entry["observer_killed"]=True
                        host._pixels_stream.close();entry["observer_returncode"]=code
                        emit(host,{"kind":"close","pid":host.process.pid,"qpc":qpc(),"exit":host.process.poll()})
                        need(code==0,"native observer exit")
                        entry["analysis"]=analyze(folder,entry);entry["complete"]=True
                    else:raise RuntimeError("product never exposed a native window")
                except BaseException as error:entry["error"]=repr(error);report["problems"].append(repr(error))
        P.Host.__init__,P.Host.find_window,P.Host.send,P.Host.close=init,find,send,close
        ADAPTER.prepare_scroll_origin()
        script=ROOT/"tests/reader_product_performance_handoff/sample_windows_interactions.py"
        sys.argv=[str(script),"--package",str(raw/"program"),"--seed",str(raw/"seed.exe"),"--output",str(OUT/"observations"),
            "--work",str(ROOT/"build/f08-windows-product-pixels-work"),"--cohorts","warm_shelf,reading","--launches-per-cohort","5"]
        try:
            with (OUT/"original-interactions.log").open("w",encoding="utf-8") as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                try:runpy.run_path(str(script),run_name="__main__")
                except SystemExit as error:need(error.code in (0,None),"original interaction exit "+str(error.code))
        finally:P.Host.__init__,P.Host.find_window,P.Host.send,P.Host.close=original_init,original_find,original_send,original_close
        interaction=json.loads((OUT/"observations/interactions.json").read_text())
        need(not interaction["faults"] and len(interaction["font_order"])==5,"original interaction coverage")
        for name,count in {"shelf_scroll_down":15,"shelf_scroll_up":15,"font_bigger":10,"font_smaller":10}.items():
            need(len(interaction[name])==count,"original interaction count")
        launches=json.loads((OUT/"observations/per-launch.json").read_text())
        report["launch_bindings"]=bindings(launches,report["captures"],OUT)
        need(len(report["launch_bindings"])==10 and not report["problems"] and all(x["complete"] for x in report["captures"]),"all original captures")
        need(all(sum(x["analysis"]["distinct_content_frames"][k] for x in report["captures"])>10 for k in (119,123)),
             "real shelf and reading content changed")
        report["collection_complete"]=True
    except BaseException as error:fatal=error;report["problems"].append(repr(error));report["traceback"]=traceback.format_exc()
    finally:
        save(OUT/"result.json",report)
        save(OUT/"manifest.json",{**identity(),"f08_accepted":False,"files":{
            p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
            for p in sorted(OUT.rglob("*")) if p.is_file() and p!=OUT/"manifest.json"}})
        print("F08_PRODUCT_PIXELS",json.dumps({k:v for k,v in report.items() if k not in ("captures","launch_bindings")}),flush=True)
        for e in report["captures"]:
            a=e.get("analysis",{})
            print("F08_PRODUCT_PIXEL_CAPTURE",json.dumps({**{k:v for k,v in e.items() if k!="analysis"},
                "summary":{k:v for k,v in a.items() if k not in ("raw_images","changed_content")}}),flush=True)
    if fatal:raise fatal
def bindings(launches,captures,root):
    lifetimes=[];indices=set()
    for entry in captures:
        need(entry["index"] not in indices and entry["folder"]=="capture-%03d"%entry["index"],"capture identity")
        indices.add(entry["index"]);events=rows(root/entry["folder"]/"driver.jsonl");first,last=events[0],events[-1]
        need(first["kind"]=="process" and last["kind"]=="close" and first["pid"]==last["pid"]==entry["pid"] and
             first["frequency"]==entry["frequency"] and 0<first["qpc"]<last["qpc"] and type(last["exit"]) is int,
             "closed native process lifetime")
        log=Path(first["log"]);need(log.parent.name=="logs" and log.parent.parent.name=="observations","original log origin")
        current={"capture":entry["index"],"pid":entry["pid"],"frequency":entry["frequency"],"start_qpc":first["qpc"],
                 "end_qpc":last["qpc"],"log":log.name,"complete":entry["complete"]}
        for previous in lifetimes:
            if previous["pid"]==current["pid"]:
                need(previous["frequency"]==current["frequency"] and previous["end_qpc"]<current["start_qpc"],
                     "nonoverlapping reused process ID")
        lifetimes.append(current)
    answer=[];used=set()
    for record in launches:
        launch=record["launch_id"];need(launch=="%s-%02d"%(record["cohort"],record["index"]),"original launch identity")
        matching=[x for x in lifetimes if x["pid"]==record["pid"] and x["log"]==launch+".log"]
        need(len(matching)==1 and matching[0]["capture"] not in used and matching[0]["complete"],"unique complete native launch")
        match=matching[0];used.add(match["capture"]);log=root/"observations/logs"/match["log"]
        need(log.is_file() and log.stat().st_size==record["log_bytes"],"exact original process log")
        answer.append({"launch_id":launch,**match,"log_sha256":sha(log)})
    return answer
def audit():
    guard();target=ROOT/"build/f08-windows-product-pixels-audit";target.mkdir(parents=True,exist_ok=False)
    ident=identity();artifact=int(os.environ["F08_ARTIFACT_ID"]);meta=F.api("actions/artifacts/"+str(artifact))
    run=F.api("actions/runs/"+ident["run_id"])
    need(meta["id"]==artifact and not meta["expired"] and meta["name"]=="f08-windows-product-pixels-"+ident["run_id"]+"-"+ident["attempt"] and
         meta["workflow_run"]["head_sha"]==ident["source_sha"] and str(meta["workflow_run"]["id"])==ident["run_id"] and
         run["head_sha"]==ident["source_sha"] and str(run["run_attempt"])==ident["attempt"],"capture producer identity")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(artifact)+"/zip"]);digest=hashlib.sha256(data).hexdigest()
    need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest and
         os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest,"native capture ZIP")
    raw=target/"raw";F.extract(data,raw,"manifest.json",ident);result=json.loads((raw/"result.json").read_text())
    need(all(result.get(k)==v for k,v in ident.items()) and result["f08_accepted"] is False,"capture result identity")
    verified=[]
    if (raw/"product/original.zip").is_file():
        _,bound=F.product(target/"verified-product",(raw/"product/original.zip").read_bytes())
        need(bound==result["product"],"unchanged full product")
    for entry in result["captures"]:
        if not entry["complete"]:continue
        observed=analyze(raw/entry["folder"],entry)
        # JSON dictionary keys are strings after storage.
        need(json.loads(json.dumps(observed))==entry["analysis"],"independent bitmap/QPC replay")
        verified.append({k:v for k,v in observed.items() if k not in ("raw_images","changed_content")})
    bound_launches=None
    if result["collection_complete"]:
        need(len(verified)==len(result["captures"])>=10 and not result["problems"],"every original capture independently replayed")
        bound_launches=bindings(json.loads((raw/"observations/per-launch.json").read_text()),result["captures"],raw)
        need(bound_launches==result["launch_bindings"] and len(bound_launches)==10,"independent original launch bindings")
    report={**ident,"artifact_id":artifact,"sha256":digest,"authenticated":True,"collection_complete":result["collection_complete"],
            "captures":verified,"launch_bindings":bound_launches,"problems":result["problems"],
            "application_paint_generation_bound":False,"input_to_verified_content_measured":False,
            "frame_budget_measured":False,"physical_scanout_proven":False,"f08_accepted":False}
    save(target/"audit.json",report);print("F08_PRODUCT_PIXELS_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("capture","audit"));globals()[parser.parse_args().mode]()
