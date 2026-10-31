"""Drive the complete host's native import picker while retaining the original sampler bodies."""
import hashlib, importlib.util, json, os, runpy, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if os.environ.get("GITHUB_ACTIONS")!="true" or os.name!="nt":raise RuntimeError("Windows Actions only")
sys.path.insert(0,str(ROOT/"tests/reader_perf_windows"))
import perf_windows as P
spec=importlib.util.spec_from_file_location("f08_original_wave3_ui",ROOT/"tests/reader_wave3_c09/check_ui.py")
W=importlib.util.module_from_spec(spec);spec.loader.exec_module(W)
class PickerHost:
    def __init__(self,host):
        self.host=host;self.window=host.window;self.process=host.process
    def wait(self,predicate,timeout=30):
        return self.host.poll(predicate,timeout,interval=0.02)
class PickerClock:
    """Keep the original retry delay unless the observed modal window has closed."""
    def __init__(self,clock):
        self.clock=clock;self.dialog=None
    def __getattr__(self,name):return getattr(self.clock,name)
    def sleep(self,seconds):
        if seconds!=0.4 or self.dialog is None:return self.clock.sleep(seconds)
        deadline=self.clock.monotonic()+seconds
        while W.U.IsWindow(self.dialog):
            remaining=deadline-self.clock.monotonic()
            if remaining<=0:return
            self.clock.sleep(min(0.001,remaining))
original_click=P.Host.click
def click(host,name,timeout=2000):
    if name!="import":return original_click(host,name,timeout)
    path=Path(host.text(host.control("path")))
    if not path.is_file():raise P.MeasurementFault("native picker input file missing")
    entry={"pid":host.process.pid,"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
           "started_ms":P.now_ms(),"completed":False}
    adapter=PickerHost(host)
    try:
        if W.system_dialog(adapter):raise P.MeasurementFault("unexpected pre-existing native dialog")
        # BM_CLICK enters a modal native picker in the compact product. Post the
        # real button click so the driver can operate that dialog while it is open.
        W.post_click(host.window,P.IDS["import"])
        old_clock,old_post=W.time,W.post_click
        clock=PickerClock(old_clock)
        def post(dialog,identifier):
            old_post(dialog,identifier)
            if identifier==1:
                clock.dialog=dialog
                entry.setdefault("accept_posts_ms",[]).append(P.now_ms())
        W.time,W.post_click=clock,post
        try:W.fill_system_dialog(adapter,path)
        finally:W.time,W.post_click=old_clock,old_post
        if W.system_dialog(adapter):raise P.MeasurementFault("native picker remained open")
        entry["completed"]=True
    except BaseException as error:
        entry["error"]=repr(error);raise
    finally:
        entry["ended_ms"]=P.now_ms();print("F08_NATIVE_PICKER",json.dumps(entry),flush=True)
P.Host.click=click
def prepare_scroll_origin():
    import ctypes as C
    from ctypes import wintypes as T
    original=P.op_shelf_next_page
    def prepared(host,*args,**kwargs):
        result=original(host,*args,**kwargs)
        lines=T.UINT()
        P.U.SystemParametersInfoW.argtypes=[T.UINT,T.UINT,T.LPVOID,T.UINT]
        P.U.SystemParametersInfoW.restype=T.BOOL
        if not P.U.SystemParametersInfoW(0x0068,0,C.byref(lines),0) or not 0<lines.value<100:
            raise P.MeasurementFault("unsupported native wheel-scroll profile")
        # The unchanged interaction suite performs three four-notch upward moves.
        required=3*4*lines.value
        entry={"pid":host.process.pid,"wheel_scroll_lines":lines.value,"required_top":required,
               "start_top":host.lb_top(),"preparation_only":True}
        deadline=P.now_ms()+15000
        while host.lb_top()<required:
            if P.now_ms()>=deadline:raise P.MeasurementFault("insufficient shelf scroll origin")
            host.wheel(4)
            P.time.sleep(0.02)
        entry.update(end_top=host.lb_top(),rows=host.lb_count())
        print("F08_SCROLL_PREPARATION",json.dumps(entry),flush=True)
        return result
    P.op_shelf_next_page=prepared
SCRIPTS={"diagnosis":"tests/reader_perf_windows/diagnose_txt_import.py",
    "main":"tests/reader_perf_windows/perf_windows.py",
    "interactions":"tests/reader_product_performance_handoff/sample_windows_interactions.py"}
if __name__=="__main__":
    mode=sys.argv[1];script=ROOT/SCRIPTS[mode];sys.argv=[str(script),*sys.argv[2:]]
    print("F08_ORIGINAL_SAMPLER",json.dumps({"mode":mode,"path":str(script.relative_to(ROOT)),
        "sha256":hashlib.sha256(script.read_bytes()).hexdigest(),
        "picker_driver_sha256":hashlib.sha256((ROOT/"tests/reader_wave3_c09/check_ui.py").read_bytes()).hexdigest()}),flush=True)
    if mode=="main":raise SystemExit(P.main())
    if mode=="interactions":prepare_scroll_origin()
    runpy.run_path(str(script),run_name="__main__")
