"""Two bounded native diagnostic launches of a CI-authenticated full product."""
import argparse,ctypes as C,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,time,types,zipfile
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
 p.add_argument("--expected-source",required=True);p.add_argument("--harness-source");p.add_argument("--cohorts",default="shelf,reader,page");p.add_argument("--helper-root",required=True);p.add_argument("--observer",required=True);p.add_argument("--observer-sha256",default="d9091ee8b19cce806942d1c7127802b0cfe222eda10e378d95e0cd2bde9869c7");p.add_argument("--observer-bytes",type=int,default=80896);p.add_argument("--observer-source",default="679895786e4a2c62b961583441f894d373aba4b1");a=p.parse_args()
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
 need(sha(a.observer)==a.observer_sha256 and Path(a.observer).stat().st_size==a.observer_bytes,"retained lossless WGC observer identity")
 sys.path.insert(0,str(helper/"tests/reader_perf_windows"));import perf_windows as H
 D=module("f08_native_display",helper/"tests/reader_wave3_c09/desktop.py")
 replay=module("f08_native_replay",raw/"native-source/replay.py")
 user=C.WinDLL("user32",use_last_error=True)
 user.EnumDisplaySettingsW.argtypes=[W.LPCWSTR,W.DWORD,C.POINTER(D.Settings)];user.EnumDisplaySettingsW.restype=W.BOOL
 user.GetForegroundWindow.restype=W.HWND;user.SetForegroundWindow.argtypes=[W.HWND]
 user.ShowWindow.argtypes=[W.HWND,C.c_int];user.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT];user.SetWindowPos.restype=W.BOOL
 user.GetDlgCtrlID.argtypes=[W.HWND];user.GetDlgCtrlID.restype=C.c_int
 user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];user.PostMessageW.restype=W.BOOL
 user.GetPropW.argtypes=[W.HWND,W.LPCWSTR];user.GetPropW.restype=W.HANDLE
 H.K.QueryPerformanceCounter.argtypes=[C.POINTER(C.c_longlong)];H.K.QueryPerformanceFrequency.argtypes=[C.POINTER(C.c_longlong)]
 H.K.SetThreadExecutionState.argtypes=[W.DWORD];H.K.SetThreadExecutionState.restype=W.DWORD
 def qpc():
  v=C.c_longlong();need(H.K.QueryPerformanceCounter(C.byref(v)),"native QPC");return v.value
 before=D.Settings(size=C.sizeof(D.Settings));need(user.EnumDisplaySettingsW(None,0xffffffff,C.byref(before)),"display observation")
 foreground=user.GetForegroundWindow();frequency=C.c_longlong();H.K.QueryPerformanceFrequency(C.byref(frequency))
 report=dict(source_sha=a.expected_source,harness_source_sha=a.harness_source or a.expected_source,harness_sha256=sha(__file__),execution="local-native",machine="LAP25002",captures=[],problems=[],
  artifact_id=meta["id"],artifact_digest=meta["digest"],program_sha256=identity["program_sha256"],
  observer_sha256=sha(a.observer),observer_source_sha=a.observer_source,
  display_before=[before.width,before.height,before.frequency],display_mode_changed_by_harness=False,
  operation_boundary="worker-entry/native-scroll-entry to same-generation GDI execution completion",
  ui_frame_candidate_boundary="ready-frame native UI accept through layout to same-generation GDI completion",f08_accepted=False)
 profile=out/"profile";report["seed"]=H.seed_corpus(profile,raw/"seed.exe")
 awake=H.K.SetThreadExecutionState(0x80000003);need(awake,"temporary awake request")
 deadline=time.monotonic()+1200
 try:
  cohorts=a.cohorts.split(",");need(cohorts and len(cohorts)==len(set(cohorts)) and set(cohorts)<={"shelf","reader","page"},"named diagnostic cohorts")
  for index,kind in enumerate(cohorts):
   need(time.monotonic()<deadline,"20 minute native diagnostic bound")
   folder=out/("capture-%02d"%index);folder.mkdir();trace=folder/"product-native-trace.json"
   entry=dict(index=index,kind=kind,folder=folder.name,complete=False);report["captures"].append(entry)
   launch_profile=profile
   if kind=="page":
    launch_profile=out/"reading-profile";shutil.copytree(out/"reading-base" if (out/"reading-base").exists() else profile,launch_profile)
   previous=os.environ.get("EXREADER_F08_TRACE");os.environ["EXREADER_F08_TRACE"]=str(trace)
   try:host=H.Host(raw/"program/EXReader.exe",raw/"program/Reader.otf",launch_profile,folder/"application.log")
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
   def painted():return int(user.GetPropW(host.control("page"),"EXReaderF08PaintedGeneration") or 0)
   def shelf_property(name):return int(user.GetPropW(host.control("books"),name) or 0)
   def await_shelf():
    host.poll(lambda:(True,) if H.U.IsWindowVisible(host.control("books")) and shelf_property("EXReaderShelfSnapshot")>0 and shelf_property("EXReaderShelfSnapshot")==shelf_property("EXReaderF08ShelfPaintedSnapshot") else None,10,interval=.001)
   def shelf_state():
    top=host.lb_top();return dict(top=top,top_book_id=shelf_property("EXReaderF08ShelfTopBookId"),snapshot=shelf_property("EXReaderShelfSnapshot"),query=host.text(host.control("search")),rows=host.lb_count(),top_text=host.lb_item(top) if top>=0 else None)
   def back_to_shelf():
    back=H.U.GetDlgItem(host.window,46001);need(back,"real compact Shelf control");host.send(back,0xF5);await_shelf()
   def await_paint(previous):
    host.poll(lambda:(True,) if painted()>previous else None,10,interval=.001)
    emit(dict(kind="paint_readiness",pid=host.process.pid,qpc=qpc(),previous_generation=previous,painted_generation=painted()))
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
    elif kind=="reader":
     H.op_reset_top(host);before_paint=painted();entry["open"]=H.op_open(host,"Shelf 0000",30);await_paint(before_paint)
     for _ in range(3):
      for control in ("font_inc","font_dec"):
       host.wait_enabled(control,10);before_paint=painted();host.click(control);await_paint(before_paint);time.sleep(.15)
     host.wait_enabled("font_inc",10)
     # Validation only: use a nonzero, filtered anchor and return from a real book.
     back_to_shelf();host.set_text(host.control("search"),"Shelf")
     host.poll(lambda:(True,) if host.lb_count()==50 and "Shelf 0000" in host.lb_item(0) else None,10)
     await_shelf();H.op_shelf_next_page(host,20);await_shelf();anchor=shelf_state()
     need(anchor["top"]>0 and anchor["top_book_id"]>0,"nonzero filtered shelf anchor")
     title=re.search(r"Shelf \d{4}",anchor["top_text"])[0]
     before_paint=painted();H.op_open(host,title,30);await_paint(before_paint);back_to_shelf()
     restored=shelf_state();need(restored["query"]=="Shelf" and restored["top_book_id"]==anchor["top_book_id"],"filtered nonzero anchor restored")
     entry["return_validation"]=dict(before=anchor,after=restored)
    else:
     # Original reading preparation adds one fixed packaged EPUB in a separate
     # profile; the shelf corpus remains the untouched 2202 seeded originals.
     fixture=raw/"program/Sample-positive.epub";entry["reading_fixture_sha256"]=sha(fixture)
     host.wait_enabled("import",30)
     emit(dict(kind="picker_post",pid=host.process.pid,qpc=qpc(),fixture_sha256=sha(fixture)))
     need(user.PostMessageW(host.control("import"),0xF5,0,0),"native import button post")
     print("F08_PICKER_EXPECTED",host.process.pid,str(fixture),flush=True)
     # The agent selects this fixed packaged fixture through computer-use.
     host.poll(lambda:(True,) if any("EXReader benchmark" in row for row in host.rows()) else None,90,interval=.02)
     host.set_text(host.control("search"),"EXReader benchmark")
     host.poll(lambda:(True,) if host.lb_count()==1 and "EXReader benchmark" in host.lb_item(0) else None,10)
     await_shelf();entry["metadata_anchor_before"]=shelf_state()
     before_paint=painted();entry["open"]=H.op_open(host,"EXReader benchmark",30);await_paint(before_paint);key=entry["open"]["key"];entry["page_turns"]=[]
     for _ in range(8):
      before_paint=painted();turn=H.op_page_turn(host,key);await_paint(before_paint);entry["page_turns"].append(turn);key=turn["to"]
     host.wait_enabled("metadata",10);host.send(host.window,0x111,128,0)
     def find_metadata():
      found=[]
      @H.ENUM
      def visit(hwnd,unused):
       owner=W.DWORD();H.U.GetWindowThreadProcessId(hwnd,C.byref(owner))
       if owner.value==host.process.pid and H.U.GetDlgItem(hwnd,129) and H.U.GetDlgItem(hwnd,132):found.append(hwnd)
       return True
      H.U.EnumWindows(visit,0);need(len(found)<=1,"unique owned metadata dialog");return (found[0],) if found else None
     dialog=host.poll(find_metadata,10)[0];title=H.U.GetDlgItem(dialog,129);save_button=H.U.GetDlgItem(dialog,132)
     host.poll(lambda:(True,) if H.U.IsWindowEnabled(save_button) else None,10)
     new_title="EXReader benchmark F08 metadata";host.set_text(title,new_title);host.send(save_button,0xF5)
     host.poll(lambda:(True,) if "书籍信息已保存" in host.status() else None,30)
     before_return=shelf_property("EXReaderShelfSnapshot");back_to_shelf()
     host.poll(lambda:(True,) if any(new_title in row for row in host.rows()) else None,10);await_shelf();restored=shelf_state()
     anchor=entry["metadata_anchor_before"]
     need(restored["query"]==anchor["query"] and restored["top_book_id"]==anchor["top_book_id"] and restored["snapshot"]>before_return,"pending metadata refresh and filtered anchor restored")
     entry["metadata_return_validation"]=dict(before=anchor,after=restored,title=new_title,pending_snapshot=before_return)
    time.sleep(.2);entry["observed"]=True
   finally:
    if observer:
     (folder/"stop").write_text("bounded native diagnostic complete\n")
     try:entry["observer_exit"]=observer.wait(timeout=10)
     except subprocess.TimeoutExpired:observer.kill();entry["observer_exit"]=observer.wait(timeout=10);entry["observer_killed"]=True
     stream.close()
    entry["peak"]=host.close();entry["process_exit"]=host.process.poll();emit(dict(kind="close",pid=host.process.pid,qpc=qpc(),exit=entry["process_exit"]))
   need(entry["process_exit"]==0 and entry.get("observer_exit")==0 and entry.get("observed"),"normal complete native capture")
   if kind=="shelf":shutil.copytree(profile,out/"reading-base")
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
