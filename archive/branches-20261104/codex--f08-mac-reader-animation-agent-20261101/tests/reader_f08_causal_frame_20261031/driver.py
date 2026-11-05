#!/usr/bin/env python3
"""Actions-only additional six-launch cohort. Frozen 44/760 are run separately."""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_perf_gtk"))
from observe import Host, Watch, SampleError
from sample import settled, shelf_ready
OUT=ROOT/"build/f08-causal"
def now():return time.monotonic_ns()//1000
def save(path,value):path.write_text(json.dumps(value,indent=2)+"\n")
def wait(watch,predicate,since=0,timeout=180):
    index,event=watch.wait(predicate,timeout,since)
    if index is None:raise SampleError(str(event))
    return event
STATE_KEYS=("sequence","painted_generation","book","page","font","busy","saving",
            "reader_visible","shelf_top_id","shelf_loading","shelf_restoring")
def action_complete(state,action):
    h=state["host"];field=action["field"];shelf=field=="shelf_top_id"
    required=(field,"book","sequence","busy","saving","shelf_loading")
    required+=("shelf_restoring",) if shelf else ("painted_generation","reader_visible")
    if not all(type(h.get(k)) is int and h[k]>=0 for k in required):return False
    effect=h[field]!=action["before"] if shelf else h[field]==action["expected"]
    ready=not h["shelf_restoring"] if shelf else h["reader_visible"]==1 and h["painted_generation"]>action["previous_generation"]
    return effect and ready and h["book"]==action["book"] and h["sequence"]>action["previous_sequence"] and settled(state) and not h["shelf_loading"]
def main():
    if os.environ.get("GITHUB_ACTIONS")!="true":raise RuntimeError("Actions only")
    OUT.mkdir(parents=True,exist_ok=False)
    binary=(ROOT/"build/perf-package/EXReader-Linux/bin/exreader-linux").resolve()
    font=binary.parent.parent/"Reader.otf"
    module=(ROOT/"build/f08-causal-probe/libexreader_f08_causal.so").resolve()
    import hashlib
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    shutil.copyfile(module,OUT/"module.so");shutil.copyfile(binary,OUT/"host.bin")
    identity={k:os.environ[k] for k in ("GITHUB_SHA","GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT")}
    receipt=dict(identity=identity,host_sha256=digest(binary),module_sha256=digest(module),
        cohorts=[],planned_launches=6,planned_actions=18,accepted=False,
        physical_display_presented=False,F08_accepted=False,clock="CLOCK_MONOTONIC microseconds")
    commands=[["pkg-config","--modversion","gtk+-3.0","glib-2.0"],["openbox","--version"],["xdpyinfo"],
              ["xprop","-root","_NET_SUPPORTING_WM_CHECK","_NET_SUPPORTED"]]
    environment=[]
    for command in commands:
        p=subprocess.run(command,capture_output=True,text=True,timeout=30)
        environment.append(dict(command=command,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
    save(OUT/"environment.json",environment)
    with tempfile.TemporaryDirectory(prefix="f08-causal-") as temporary:
        private=Path(temporary);seed=private/"seed";seed.mkdir()
        subprocess.run([str(ROOT/"build/perf-probe/seed_library"),str(seed/"library.sqlite"),
                        str(private/"corpus.json")],check=True,timeout=3600,capture_output=True)
        corpus=json.loads((private/"corpus.json").read_text())
        if corpus["books"]!=2202:raise RuntimeError("original corpus count")
        book=corpus["originals"][0]["id"]
        save(OUT/"corpus-identity.json",dict(books=2202,long_book_id=book,
             seed_sha256=digest(ROOT/"build/perf-probe/seed_library"),
             corpus_sha256=digest(private/"corpus.json")))
        for number,kind in enumerate(("page","font","shelf","page","font","shelf")):
            folder=OUT/("launch-%02d"%number);folder.mkdir()
            profile=private/("profile-%02d"%number);shutil.copytree(seed,profile)
            (profile/"reader.ini").write_text("[reader]\nbook=%d\nfont=24\nzoom=100\n[shelf]\nquery=\ntop_key=\nselected_key=\ntop_offset=0\n"%(0 if kind=="shelf" else book))
            runtime=private/("runtime-%02d"%number);runtime.mkdir()
            hostenv=dict(os.environ)
            hostenv.update(HOME=str(runtime),XDG_CONFIG_HOME=str(runtime/"config"),
                XDG_CACHE_HOME=str(runtime/"cache"),XDG_RUNTIME_DIR=str(runtime/"xdg"),
                GDK_BACKEND="x11",LANG="C.UTF-8",LC_ALL="C.UTF-8",
                LD_PRELOAD=str(module),GTK_MODULES=str(module),EXR_F08_CAUSAL_OUTPUT=str(folder))
            for name in ("XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_RUNTIME_DIR"):
                Path(hostenv[name]).mkdir(mode=0o700)
            watch=Watch(runtime);host=Host(binary,font,profile,runtime,hostenv)
            row=dict(launch=number,kind=kind,actions=[],quiet=[],preparation=[],passed=False,
                     host_sha256=digest(binary),module_sha256=digest(module))
            def quiet():
                begin=now();time.sleep(2);row["quiet"].append(dict(start=begin,end=now()))
            try:
                host.launch();row["pid"]=host.pid
                wait(watch,shelf_ready if kind=="shelf" else
                     lambda s:s["host"].get("book")==book and s["host"].get("reader_visible")==1 and settled(s),
                     timeout=600)
                host.find_window();host.activate();host.resize(1040,820)
                wait(watch,lambda s:settled(s),timeout=180)
                if kind=="shelf":
                    geo=host.geometry()
                    subprocess.run(["xdotool","mousemove","--window",str(host.window),
                        str(geo["WIDTH"]//3),str(geo["HEIGHT"]//2)],check=True,timeout=30)
                    # Declared bounded preparation, not a retried measured sample.
                    for step in range(24):
                        h=watch.latest()["state"]["host"]
                        if h.get("shelf_before") and h.get("shelf_after"):break
                        if not h.get("shelf_after"):raise SampleError("no shelf interior")
                        start=now();since=watch.mark();old=h.get("shelf_top_id")
                        subprocess.run(["xdotool","click","--repeat","4","--delay","0","5"],check=True,timeout=30)
                        wait(watch,lambda s:settled(s) and s["host"].get("shelf_top_id")!=old,since)
                        row["preparation"].append(dict(start=start,end=now(),step=step))
                        time.sleep(.35)
                    else:raise SampleError("bounded preparation exhausted")
                quiet()
                for slot in range(3):
                    baseline=watch.latest()["state"]["host"];since=watch.mark()
                    field="page" if kind=="page" else "font" if kind=="font" else "shelf_top_id"
                    old=baseline[field]
                    key="F4" if kind=="page" else ("F6" if slot==1 else "F5")
                    code=65473 if kind=="page" else (65475 if slot==1 else 65474)
                    expected=old+1 if kind=="page" else old+(-2 if slot==1 else 2)
                    action=dict(id="%02d-%d"%(number,slot),slot=slot,type=2 if kind=="shelf" else 1,
                        code=(0 if slot==1 else 1) if kind=="shelf" else code,
                        field=field,before=old,book=baseline["book"],expected=None if kind=="shelf" else expected,
                        previous_generation=baseline.get("painted_generation",0),
                        previous_sequence=baseline["sequence"],inject_start=now())
                    row["actions"].append(action)
                    if kind=="shelf":
                        subprocess.run(["xdotool","click","4" if slot==1 else "5"],check=True,timeout=30)
                    else:host.press(key)
                    action["inject_end"]=now()
                    action["wait_start"]=now();action["evaluations"]=[]
                    def changed(s):
                        passed=action_complete(s,action)
                        if len(action["evaluations"])>=65536:raise SampleError("predicate evidence capacity")
                        action["evaluations"].append(dict(at=now(),passed=passed,
                            host={k:s["host"].get(k) for k in STATE_KEYS}))
                        return passed
                    try:effect=wait(watch,changed,since)
                    finally:action["wait_end"]=now()
                    action.update(effect_at=int(effect["at"]*1000000),done=now(),
                        observed={k:effect["state"]["host"].get(k) for k in
                                  STATE_KEYS})
                    quiet()
                row["passed"]=True
            except Exception as exc:
                row["error_type"]=type(exc).__name__;row["error_stage"]="causal_driver"
            finally:
                try:row["exit"]=host.close()
                except Exception as exc:
                    row["exit"]=None;row["close_error"]=type(exc).__name__;host.kill()
                host.close_log();watch.close()
                row["watcher_events"]=[dict(at=int(e["at"]*1000000),
                    host={k:e["state"]["host"].get(k) for k in STATE_KEYS}) for e in watch.events]
                row["observation_failure"]=watch.failure
                row["passed"]=row["passed"] and row["exit"]==0 and not watch.failure
                row["host_sha256_after"]=digest(binary)
                save(folder/"driver.json",row);receipt["cohorts"].append(row)
                print("F08_CAUSAL_DRIVER",json.dumps(dict(launch=number,kind=kind,pid=row.get("pid"),passed=row["passed"],actions=len(row["actions"]))),flush=True)
                save(OUT/"driver.json",receipt)
    receipt["accepted"]=len(receipt["cohorts"])==6 and all(r["passed"] and len(r["actions"])==3 for r in receipt["cohorts"])
    save(OUT/"driver.json",receipt)
    if not receipt["accepted"]:raise RuntimeError("six-launch causal driver incomplete")
if __name__=="__main__":main()
