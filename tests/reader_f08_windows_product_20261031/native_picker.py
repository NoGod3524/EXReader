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
        W.fill_system_dialog(adapter,path)
        if W.system_dialog(adapter):raise P.MeasurementFault("native picker remained open")
        entry["completed"]=True
    except BaseException as error:
        entry["error"]=repr(error);raise
    finally:
        entry["ended_ms"]=P.now_ms();print("F08_NATIVE_PICKER",json.dumps(entry),flush=True)
P.Host.click=click
SCRIPTS={"diagnosis":"tests/reader_perf_windows/diagnose_txt_import.py",
    "main":"tests/reader_perf_windows/perf_windows.py",
    "interactions":"tests/reader_product_performance_handoff/sample_windows_interactions.py"}
if __name__=="__main__":
    mode=sys.argv[1];script=ROOT/SCRIPTS[mode];sys.argv=[str(script),*sys.argv[2:]]
    print("F08_ORIGINAL_SAMPLER",json.dumps({"mode":mode,"path":str(script.relative_to(ROOT)),
        "sha256":hashlib.sha256(script.read_bytes()).hexdigest(),
        "picker_driver_sha256":hashlib.sha256((ROOT/"tests/reader_wave3_c09/check_ui.py").read_bytes()).hexdigest()}),flush=True)
    if mode=="main":raise SystemExit(P.main())
    runpy.run_path(str(script),run_name="__main__")
