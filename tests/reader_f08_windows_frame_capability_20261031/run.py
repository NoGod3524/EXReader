#!/usr/bin/env python3
"""Actions-only GDI/DXGI capability check, not a product performance sample."""
import csv, ctypes, hashlib, json, math, os, platform, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"build/f08-windows-frame-capability"
URL="https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/PresentMon-2.6.0-x64.exe"
DIGEST="b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af"
BASE="8dbd61b5c3aebf17e178615763bf319d1c7e488b"
OWNED={
 ".github/workflows/dot-f08-windows-frame-capability-20261031.yml",
 "tests/reader_f08_windows_frame_capability_20261031/run.py",
}
def need(value,message):
    if not value:raise RuntimeError(message)
def save(path,value):path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")
def guard():
    git=lambda *a:subprocess.check_output(["git",*a],text=True).strip()
    need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform=="win32","Windows Actions only")
    need(git("rev-parse","HEAD")==os.environ["GITHUB_SHA"],"source")
    subprocess.run(["git","merge-base","--is-ancestor",BASE,"HEAD"],check=True)
    need(set(git("diff","--name-only",BASE,"HEAD").splitlines())==OWNED,"test-only scope")
def analyze_csv(path,pid):
    if not path.exists():return dict(rows=0,displayed_rows=0,columns=[],missing_csv=True)
    with path.open(encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle);columns=reader.fieldnames or [];rows=list(reader)
    if not rows:return dict(rows=0,displayed_rows=0,columns=columns,missing_csv=False)
    need("ProcessID" in columns and "CPUStartQPC" in columns,"CSV schema")
    need(all(int(row["ProcessID"])==pid for row in rows),"foreign PID")
    times=[int(row["CPUStartQPC"]) for row in rows]
    need(all(t>0 for t in times) and times==sorted(times),"CSV QPC")
    displayed=0
    for row in rows:
        value=row.get("DisplayedTime","NA")
        if value not in ("NA","N/A",""):
            duration=float(value);need(math.isfinite(duration) and duration>=0,"display duration")
            displayed+=duration>0
    return dict(rows=len(rows),displayed_rows=displayed,columns=columns,missing_csv=False)
def trace_ready(code,output):
    return code==0 and b"Running" in output and b"Microsoft-Windows-DXGI" in output
def controls():
    path=OUT/"control.csv";head="ProcessID,CPUStartQPC,DisplayedTime\n"
    path.write_text(head+"42,100,16.6667\n",encoding="utf-8")
    need(analyze_csv(path,42)["displayed_rows"]==1,"CSV positive")
    for data,reason in ((head+"43,100,16.6667\n","foreign PID"),
                        (head+"42,200,16.6667\n42,100,16.6667\n","CSV QPC")):
        path.write_text(data,encoding="utf-8");actual=None
        try:analyze_csv(path,42)
        except RuntimeError as exc:actual=str(exc)
        need(actual==reason,"CSV negative")
    path.write_text(head,encoding="utf-8");need(analyze_csv(path,42)["rows"]==0,"empty remains unsupported")
    need(trace_ready(0,b"Status: Running\nProvider: Microsoft-Windows-DXGI"),"ETW ready")
    need(not trace_ready(0,b"Status: Running"),"ETW missing provider")
    need(not trace_ready(1,b"Status: Running\nProvider: Microsoft-Windows-DXGI"),"ETW query failed")
    return dict(positive=3,negative=4)
def decoded(path):
    raw=path.read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else "utf-8",errors="replace")
def main():
    guard();OUT.mkdir(parents=True,exist_ok=False)
    result=dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],
        attempt=os.environ["GITHUB_RUN_ATTEMPT"],platform=platform.platform(),
        collector_url=URL,collector_sha256=DIGEST,controls=controls(),captures=[],
        product_measured=False,F08_accepted=False,physical_display_presented=False)
    save(OUT/"receipt.json",result)
    collector=OUT/"PresentMon.exe"
    with urllib.request.urlopen(URL,timeout=60) as response:data=response.read(2*1024*1024)
    need(len(data)==980320 and hashlib.sha256(data).hexdigest()==DIGEST,"collector identity")
    collector.write_bytes(data)
    binary=ROOT/"build/f08-win-control/Release/f08_frame_control.exe"
    result["control_sha256"]=hashlib.sha256(binary.read_bytes()).hexdigest()
    for name,command in (("help",[str(collector),"--help"]),
                         ("display",["powershell","-NoProfile","-Command","Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,CurrentHorizontalResolution,CurrentVerticalResolution | ConvertTo-Json"])):
        p=subprocess.run(command,capture_output=True,timeout=30)
        (OUT/(name+".txt")).write_bytes(p.stdout+p.stderr)
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.CreateEventW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_wchar_p]
    kernel.CreateEventW.restype=ctypes.c_void_p
    kernel.SetEvent.argtypes=[ctypes.c_void_p];kernel.SetEvent.restype=ctypes.c_int
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    result["display"]=decoded(OUT/"display.txt")
    for mode,profile in (("dxgi","display"),("gdi","display"),("dxgi","cpu_only"),("gdi","cpu_only")):
        label=profile+"_"+mode;folder=OUT/label;folder.mkdir()
        event_name="Local\\F08-"+os.environ["GITHUB_RUN_ID"]+"-"+label
        event=kernel.CreateEventW(None,True,False,event_name);need(event,"event")
        producer=trace=None
        try:
            with (folder/"control.jsonl").open("wb") as stream,(folder/"collector.log").open("wb") as log:
                producer=subprocess.Popen([str(binary),mode,event_name],stdout=stream,stderr=stream)
                session="F08-"+os.environ["GITHUB_RUN_ID"]+"-"+label
                command=[str(collector),"--process_id",str(producer.pid),"--session_name",session,
                    "--output_file",str(folder/"frames.csv"),"--qpc_time","--timed","12","--terminate_after_timed","--no_console_stats"]
                if profile=="cpu_only":command.extend(["--no_track_display","--no_track_gpu","--no_track_input"])
                save(folder/"command.json",command)
                trace=subprocess.Popen(command,stdout=log,stderr=log)
                deadline=time.monotonic()+10;started=False
                while time.monotonic()<deadline and trace.poll() is None:
                    p=subprocess.run(["logman","query",session,"-ets"],capture_output=True,timeout=5)
                    (folder/"session.txt").write_bytes(p.stdout+p.stderr)
                    if trace_ready(p.returncode,p.stdout):started=True;break
                    time.sleep(.2)
                need(started,"ETW session or DXGI provider not ready")
                need(kernel.SetEvent(event),"start signal")
                producer_code=producer.wait(timeout=10);trace_code=trace.wait(timeout=20)
            need(producer_code==0 and trace_code==0,"control or collector failed")
            lines=[json.loads(line) for line in (folder/"control.jsonl").read_text().splitlines()]
            need(lines[0]["kind"]=="start" and lines[-1]["kind"]=="stop" and lines[-1]["ticks"]==41,"control coverage")
            need(all(line["pid"]==producer.pid for line in lines),"control PID")
            paints=[line for line in lines if line["kind"] in ("gdi_paint","dxgi_present")]
            need(len(paints)>=35 and all(line["result"]==0 for line in paints),"control drawing")
            result["captures"].append(dict(mode=mode,profile=profile,pid=producer.pid,complete=True,draw_calls=len(paints),**analyze_csv(folder/"frames.csv",producer.pid)))
        except Exception as exc:
            result["captures"].append(dict(mode=mode,profile=profile,pid=producer.pid if producer else None,
                complete=False,error_type=type(exc).__name__,error=str(exc),rows=0,displayed_rows=0))
        finally:
            for process in (producer,trace):
                if process and process.poll() is None:process.terminate();process.wait(timeout=10)
            kernel.CloseHandle(event)
            if (folder/"collector.log").exists():
                result["captures"][-1]["collector_log"]=decoded(folder/"collector.log")
            save(OUT/"receipt.json",result)
    captures={(row["profile"],row["mode"]):row for row in result["captures"]}
    result.update(diagnostic_complete=all(row["complete"] for row in result["captures"]),dxgi_presentmon_observed=captures["display","dxgi"]["rows"]>0,
        gdi_presentmon_observed=captures["display","gdi"]["rows"]>0,
        gdi_display_timing_observed=captures["display","gdi"]["displayed_rows"]>0,
        dxgi_cpu_present_observed=captures["cpu_only","dxgi"]["rows"]>0,
        gdi_cpu_present_observed=captures["cpu_only","gdi"]["rows"]>0)
    result["files"]={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in OUT.rglob("*") if p.is_file() and p.name!="receipt.json"}
    save(OUT/"receipt.json",result);print("F08_WINDOWS_FRAME_CAPABILITY",json.dumps(result),flush=True)
    need(result["diagnostic_complete"],"incomplete capability control")
if __name__=="__main__":main()
