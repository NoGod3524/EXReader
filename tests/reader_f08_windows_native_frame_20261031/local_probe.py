"""Two bounded native diagnostic launches of a CI-authenticated full product."""
import argparse,ctypes as C,hashlib,importlib.util,json,os,subprocess,sys,time,zipfile
from ctypes import wintypes as W
from datetime import datetime,timezone
from pathlib import Path

def need(value,reason):
 if not value:raise ValueError(reason)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
 p=argparse.ArgumentParser();p.add_argument("--zip",required=True);p.add_argument("--metadata",required=True)
 p.add_argument("--expected-source",required=True);p.add_argument("--helper-root",required=True);p.add_argument("--observer",required=True);a=p.parse_args()
 need(os.name=="nt" and os.environ.get("COMPUTERNAME","").upper()=="LAP25002","named native Windows device")
 need(os.environ.get("GITHUB_ACTIONS")!="true","local-native provenance")
 data=Path(a.zip).read_bytes();meta=json.loads(Path(a.metadata).read_text(encoding="utf-8-sig"))
 need(len(data)==meta["size_in_bytes"] and hashlib.sha256(data).hexdigest()==meta["digest"].removeprefix("sha256:"),"native build ZIP bytes")
 need(meta["workflow_run"]["head_sha"]==a.expected_source and not meta["expired"],"native build source")
 out=Path(os.environ["USERPROFILE"])/".codex/f08-device-runs"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-native-frame")
 out.mkdir(parents=True,exist_ok=False);raw=out/"product";raw.mkdir()
 with zipfile.ZipFile(a.zip) as z:
  names=[v for v in z.namelist() if not v.endswith("/")]
  need(len(names)==len(set(names)),"unique build inventory")
  for name in names:
   need(not Path(name).is_absolute() and ".." not in Path(name).parts and "\\" not in name,"safe build member")
   target=raw/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
 manifest=json.loads((raw/"manifest.json").read_text());identity=json.loads((raw/"build-identity.json").read_text())
 need(manifest["source_sha"]==identity["source_sha"]==a.expected_source and str(manifest["run_id"])==str(meta["workflow_run"]["id"]),"build manifest origin")
 need(set(names)==set(manifest["files"])|{"manifest.json"},"complete artifact inventory")
 for name,item in manifest["files"].items():need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"build payload "+name)
 need(sha(raw/"program/EXReader.exe")==identity["program_sha256"] and sha(raw/"seed.exe")==identity["seed_sha256"],"executed native product and seed")
 helper=Path(a.helper_root)
 for name,digest in identity["unchanged_helpers"].items():need(sha(helper/name)==digest,"original helper "+name)
 need(sha(a.observer)=="d9091ee8b19cce806942d1c7127802b0cfe222eda10e378d95e0cd2bde9869c7" and Path(a.observer).stat().st_size==80896,"retained lossless WGC observer identity")
 sys.path.insert(0,str(helper/"tests/reader_perf_windows"));import perf_windows as H
 D=module("f08_native_display",helper/"tests/reader_wave3_c09/desktop.py")
 replay=module("f08_native_replay",raw/"native-source/replay.py")
 user=C.WinDLL("user32",use_last_error=True)
 user.EnumDisplaySettingsW.argtypes=[W.LPCWSTR,W.DWORD,C.POINTER(D.Settings)];user.EnumDisplaySettingsW.restype=W.BOOL
 user.GetForegroundWindow.restype=W.HWND;user.SetForegroundWindow.argtypes=[W.HWND]
 user.ShowWindow.argtypes=[W.HWND,C.c_int];user.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT];user.SetWindowPos.restype=W.BOOL
 user.GetDlgCtrlID.argtypes=[W.HWND];user.GetDlgCtrlID.restype=C.c_int
 H.K.QueryPerformanceCounter.argtypes=[C.POINTER(C.c_longlong)];H.K.QueryPerformanceFrequency.argtypes=[C.POINTER(C.c_longlong)]
 H.K.SetThreadExecutionState.argtypes=[W.DWORD];H.K.SetThreadExecutionState.restype=W.DWORD
 def qpc():
  v=C.c_longlong();need(H.K.QueryPerformanceCounter(C.byref(v)),"native QPC");return v.value
 before=D.Settings(size=C.sizeof(D.Settings));need(user.EnumDisplaySettingsW(None,0xffffffff,C.byref(before)),"display observation")
 foreground=user.GetForegroundWindow();frequency=C.c_longlong();H.K.QueryPerformanceFrequency(C.byref(frequency))
 report=dict(source_sha=a.expected_source,execution="local-native",machine="LAP25002",captures=[],problems=[],
  artifact_id=meta["id"],artifact_digest=meta["digest"],program_sha256=identity["program_sha256"],
  display_before=[before.width,before.height,before.frequency],display_mode_changed_by_harness=False,
  frame_boundary="worker-entry/native-scroll-entry to same-generation GDI execution completion",f08_accepted=False)
 profile=out/"profile";report["seed"]=H.seed_corpus(profile,raw/"seed.exe")
 awake=H.K.SetThreadExecutionState(0x80000003);need(awake,"temporary awake request")
 deadline=time.monotonic()+1200
 try:
  for index,kind in enumerate(("shelf","reader")):
   need(time.monotonic()<deadline,"20 minute native diagnostic bound")
   folder=out/("capture-%02d"%index);folder.mkdir();trace=folder/"product-native-trace.json"
   entry=dict(index=index,kind=kind,folder=folder.name,complete=False);report["captures"].append(entry)
   previous=os.environ.get("EXREADER_F08_TRACE");os.environ["EXREADER_F08_TRACE"]=str(trace)
   try:host=H.Host(raw/"program/EXReader.exe",raw/"program/Reader.otf",profile,folder/"application.log")
   finally:
    if previous is None:os.environ.pop("EXREADER_F08_TRACE",None)
    else:os.environ["EXREADER_F08_TRACE"]=previous
   entry.update(pid=host.process.pid,frequency=frequency.value);observer=None;stream=None
   def emit(event):
    with (folder/"driver.jsonl").open("a",encoding="utf-8") as f:f.write(json.dumps(event)+"\n")
   send=host.send
   def traced(hwnd,message,wparam=0,lparam=0,timeout=2000):
    if message not in (0xF5,0x20A,0x186,0x197,0x111,0xC):return send(hwnd,message,wparam,lparam,timeout)
    event=dict(kind="input",pid=host.process.pid,hwnd=int(hwnd),control=user.GetDlgCtrlID(hwnd),message=message,wparam=wparam,start_qpc=qpc())
    try:return send(hwnd,message,wparam,lparam,timeout)
    finally:event["end_qpc"]=qpc();emit(event)
   host.send=traced;emit(dict(kind="process",pid=host.process.pid,qpc=qpc(),frequency=frequency.value,exe_sha256=sha(host.exe)))
   try:
    entry["first_screen"]=H.op_first_screen(host,60);entry["hwnd"]=int(host.window)
    user.ShowWindow(host.window,9);need(user.SetWindowPos(host.window,W.HWND(-1),0,0,1168,752,0x42),"owned product window geometry")
    user.SetForegroundWindow(host.window);print("F08_ACTIVATE_OWNED_WINDOW",entry["pid"],entry["hwnd"],kind,flush=True)
    until=time.monotonic()+90
    while user.GetForegroundWindow()!=host.window:
     need(time.monotonic()<until,"foreground owned product window");time.sleep(.05)
    stream=(folder/"native.jsonl").open("wb")
    observer=subprocess.Popen([a.observer,str(entry["hwnd"]),str(host.process.pid),str(folder/"stop"),str(folder/"images")],stdout=stream,stderr=subprocess.STDOUT)
    until=time.monotonic()+10
    while '"kind":"ready"' not in (folder/"native.jsonl").read_text():
     need(observer.poll() is None and time.monotonic()<until,"WGC readiness");time.sleep(.01)
    if kind=="shelf":
     entry["first_scroll"]=H.op_shelf_next_page(host,20)
     for _ in range(3):host.wheel(4);time.sleep(.12);host.wheel_up(4);time.sleep(.12)
    else:
     H.op_reset_top(host);entry["open"]=H.op_open(host,"Shelf 0000",30)
     for _ in range(3):
      for control in ("font_inc","font_dec"):
       host.wait_enabled(control,10);host.click(control);time.sleep(.15)
     host.wait_enabled("font_inc",10)
    time.sleep(.2);entry["observed"]=True
   finally:
    if observer:
     (folder/"stop").write_text("bounded native diagnostic complete\n")
     try:entry["observer_exit"]=observer.wait(timeout=10)
     except subprocess.TimeoutExpired:observer.kill();entry["observer_exit"]=observer.wait(timeout=10);entry["observer_killed"]=True
     stream.close()
    entry["peak"]=host.close();entry["process_exit"]=host.process.poll();emit(dict(kind="close",pid=host.process.pid,qpc=qpc(),exit=entry["process_exit"]))
   need(entry["process_exit"]==0 and entry.get("observer_exit")==0 and entry.get("observed"),"normal complete native capture")
   native=json.loads(trace.read_text());need(native["pid"]==entry["pid"] and native["frequency"]==frequency.value,"native trace process clock")
   try:
    entry["analysis"]=replay.replay(native);save(folder/"analysis.json",entry["analysis"]);entry["complete"]=True
   except BaseException as error:
    entry["analysis_error"]=repr(error);report["problems"].append(kind+" replay: "+repr(error))
 except BaseException as error:report["problems"].append(repr(error));raise
 finally:
  report["execution_state_restored"]=bool(H.K.SetThreadExecutionState(awake))
  after=D.Settings(size=C.sizeof(D.Settings));report["display_unchanged"]=bool(user.EnumDisplaySettingsW(None,0xffffffff,C.byref(after))) and [after.width,after.height,after.frequency]==report["display_before"]
  if foreground:user.SetForegroundWindow(foreground)
  save(out/"result.json",report);save(out/"manifest.json",dict(execution="local-native",source_sha=a.expected_source,files={p.relative_to(out).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.rglob("*")) if p.is_file() and p!=out/"manifest.json"}))
  print("F08_NATIVE_FRAME_OUTPUT",str(out),flush=True);need(report["display_unchanged"],"display mode unchanged")
if __name__=="__main__":main()
