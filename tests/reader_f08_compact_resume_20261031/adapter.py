"""Native compact Continue input around frozen GTK samplers; Actions only."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_perf_gtk"))
import observe as O

def need(ok,why):
    if not ok:raise O.SampleError("compact startup: "+why)

def now():return time.monotonic_ns()//1000

def save(path,value):path.write_text(json.dumps(value,indent=2)+"\n")

def ready(state):
    h=state["host"]
    return all(h.get(k)==0 for k in ("busy","saving","shelf_loading","shelf_restoring"))

def initial(h,book):
    need(type(book) is int and book>0,"requested book")
    need(h.get("compact")==1 and h.get("book")==0 and h.get("reader_visible")==0,"native Library entry")
    need(h.get("compact_resume")==book,"native resume book differs from profile")
    need(ready({"host":h}) and h.get("books",0)>0,"Library not settled")

def control(value,pid):
    need(value.get("pid")==pid and type(pid) is int and pid>0,"native control PID")
    need(value.get("name")=="Continue reading" and value.get("role")=="push button","native Continue identity")
    need(all(value.get("states",{}).get(k) is True for k in ("showing","sensitive","enabled")),"Continue unavailable")
    box=value.get("bounds",{})
    need(all(type(box.get(k)) is int for k in ("x","y","width","height")) and
         box["width"]>0 and box["height"]>0,"Continue geometry")

def remaining(deadline,stamp=None):
    value=(deadline-(now() if stamp is None else stamp))/1000000
    need(value>0,"original startup deadline exhausted")
    return value

def verify(receipt,driver=None):
    need(receipt["schema"]==1 and receipt["stage"] in ("shelf_unchanged","continued"),"complete receipt")
    if driver is not None:need(receipt["pid"]==driver["pid"],"driver PID")
    if receipt["stage"]=="shelf_unchanged":
        need(receipt["requested_book"]==0 and "input_start" not in receipt,"shelf route unchanged")
        return
    initial(receipt["before"],receipt["requested_book"])
    control(receipt["control"],receipt["pid"])
    need(receipt["deadline"]-receipt["wait_start"]==600000000,"shared original 600-second limit")
    need(receipt["launch_start"]<=receipt["wait_start"]<=receipt["input_start"]
         <=receipt["input_end"]<=receipt["wait_end"]<=receipt["deadline"] and
         receipt["launch_start"]<=receipt["before_at"]<=receipt["input_start"],"startup input chronology")
    need(receipt["input_start"]<=receipt["after_at"]<=receipt["wait_end"],"post-input observation")
    after=receipt["after"]
    need(after.get("book")==receipt["requested_book"] and after.get("reader_visible")==1 and
         after.get("busy")==0 and after.get("saving")==0 and
         after.get("sequence",0)>receipt["before"]["sequence"],"native reader response")
    need(receipt["active_window"]==receipt["window"] and receipt["window_pid"]==receipt["pid"],"active product window")
    if driver is not None:
        need(any(e["at"]==receipt["after_at"] and e["host"].get("sequence")==after["sequence"] and
                 e["host"].get("book")==after["book"] and e["host"].get("reader_visible")==1
                 for e in driver["watcher_events"]),"independent original watcher response")

def click_continue(host,deadline,row):
    sys.path.insert(0,str(ROOT/"tests/reader_a11y_gtk"))
    import atspi_client as bus
    need(bus.init()[0],"accessibility bus unavailable")
    bus.Atspi.set_timeout(800,0)
    def command(*args):
        return O.command(*args,timeout=min(30,remaining(deadline)))
    # Use the real process-bound accessibility control, then real X11 input.
    host.find_window(timeout=min(60,remaining(deadline)))
    command("xdotool","windowactivate","--sync",host.window)
    row["window"]=int(host.window)
    row["window_pid"]=int(command("xdotool","getwindowpid",host.window))
    row["active_window"]=int(command("xdotool","getactivewindow"))
    need(row["window_pid"]==host.pid and row["active_window"]==row["window"],"product window ownership")
    node=None
    while node is None:
        remaining(deadline);host.require_alive("finding native Continue")
        apps=[app for app in bus.applications() if bus._safe(lambda:app.get_process_id())==host.pid]
        need(len(apps)<=1,"ambiguous accessibility process")
        if apps:
            found=[item for item in bus.walk(apps[0]) if bus.name(item)=="Continue reading" and
                   bus.role(item)=="push button" and bus.states(item).get("showing")]
            need(len(found)<=1,"ambiguous Continue control")
            if found:node=found[0]
        if node is None:time.sleep(min(.05,remaining(deadline)))
    row["control"]={"pid":node.get_process_id(),"name":bus.name(node),"role":bus.role(node),
                    "states":bus.states(node),"bounds":bus.extents(node)}
    control(row["control"],host.pid)
    box=row["control"]["bounds"];x=box["x"]+box["width"]//2;y=box["y"]+box["height"]//2
    command("xdotool","mousemove","--sync",x,y)
    remaining(deadline);row["input_start"]=now()
    command("xdotool","click","1")
    row["input_end"]=now()

def install():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(os.environ.get("DBUS_SESSION_BUS_ADDRESS"),"explicit desktop bus session required")
    need(not getattr(O.Host,"_f08_compact_adapter",False),"adapter already installed")
    launch,wait,close_log=O.Host.launch,O.Watch.wait,O.Host.close_log
    pending={}
    def launch_native(host):
        settings=(host.profile/"reader.ini").read_text()
        config=configparser.ConfigParser(interpolation=None);config.read_string(settings)
        book=config.getint("reader","book",fallback=0)
        host.environment["DBUS_SESSION_BUS_ADDRESS"]=os.environ["DBUS_SESSION_BUS_ADDRESS"]
        host.environment["NO_AT_BRIDGE"]="0"
        started=launch(host)
        dest=Path(host.environment.get("EXR_F08_CAUSAL_OUTPUT",str(host.folder)))
        dest.mkdir(parents=True,exist_ok=True)
        row={"schema":1,"pid":host.pid,"requested_book":book,"launch_start":int(started*1000000),
             "stage":"pending" if book else "shelf_unchanged",
             "route":"Library then native Continue" if book else "Library",
             "identity":{k:os.environ[k] for k in ("GITHUB_SHA","GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT")},
             "settings_sha256":hashlib.sha256(settings.encode()).hexdigest()}
        (dest/"startup-settings.ini").write_text(settings)
        host._f08_resume=(dest,row)
        if book:pending[str(host.folder.resolve())]=host
        save(dest/"compact-resume.json",row)
        return started
    def wait_native(watch,predicate,timeout,since=0):
        host=pending.pop(str(watch.folder.resolve()),None)
        if host is None:return wait(watch,predicate,timeout,since)
        dest,row=host._f08_resume
        row.update(wait_start=now())
        row["deadline"]=row["wait_start"]+int(timeout*1000000)
        try:
            need(timeout==600 and since==0,"original initial wait contract")
            index,event=wait(watch,lambda state:ready(state) and state["host"].get("books",0)>0,
                             remaining(row["deadline"]),since)
            need(index is not None,"initial native state: "+str(event) if index is None else "")
            remaining(row["deadline"])
            row.update(before=event["state"]["host"],before_at=int(event["at"]*1000000))
            initial(row["before"],row["requested_book"])
            mark=watch.mark()
            click_continue(host,row["deadline"],row)
            index,event=wait(watch,predicate,remaining(row["deadline"]),mark)
            need(index is not None,"original reader predicate: "+str(event) if index is None else "")
            remaining(row["deadline"])
            row.update(after=event["state"]["host"],after_at=int(event["at"]*1000000),stage="continued",wait_end=now())
            verify(row)
            return index,event
        except BaseException as error:
            row.update(stage="failed",error=repr(error),wait_end=now())
            raise
        finally:
            save(dest/"compact-resume.json",row)
            print("F08_COMPACT_STARTUP",json.dumps({k:row.get(k) for k in
                  ("pid","requested_book","stage","input_start","input_end","error")}),flush=True)
    def close_native(host):
        close_log(host)
        if hasattr(host,"_f08_resume"):
            dest,row=host._f08_resume
            for src,name in ((host.state_path,"native-final-state.ini"),(host.log_path,"application.log")):
                if src.is_file() and src.resolve()!=(dest/name).resolve():shutil.copyfile(src,dest/name)
            pending.pop(str(host.folder.resolve()),None)
    O.Host.launch,O.Watch.wait,O.Host.close_log=launch_native,wait_native,close_native
    O.Host._f08_compact_adapter=True

if __name__=="__main__":
    install();target=sys.argv[1];sys.argv=sys.argv[1:];runpy.run_path(target,run_name="__main__")
