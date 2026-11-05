#!/usr/bin/env python3
"""F08 additive frame evidence; execution only in Actions."""
import copy, hashlib, json, os, runpy, sys
from pathlib import Path
BASE="c1de24844830e5f389c37a4cfe744ed60e2d0b51"
ROOT=Path(__file__).resolve().parents[2]
class Invalid(ValueError): pass
def need(ok, why):
    if not ok: raise Invalid(why)
def integer(x, lower=0):
    return type(x) is int and lower <= x < 2**63
def load(path):
    def unique(pairs):
        obj={}
        for k,v in pairs:
            need(k not in obj,"duplicate_json_key");obj[k]=v
        return obj
    return json.loads(Path(path).read_text(),object_pairs_hook=unique)
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check(doc,pid,source,run,attempt):
    need(doc.get("schema")==1,"schema")
    need(integer(doc.get("pid"),1) and doc["pid"]==pid,"pid")
    need(doc.get("source")==source,"source")
    need(doc.get("run")==run,"run")
    need(doc.get("attempt")==attempt,"attempt")
    need(doc.get("executable")=="/synthetic/exreader-linux" or
         str(doc.get("executable","")).endswith("/bin/exreader-linux"),"executable")
    need(doc.get("overflow")==0,"overflow")
    need(doc.get("capacity")==65536,"capacity")
    need(integer(doc.get("clock_count"),1) and doc["clock_count"]<=64,"clocks")
    need(integer(doc.get("probe_static_bytes"),1),"probe_bytes")
    frames=doc.get("frames");writes=doc.get("writes")
    need(type(frames) is list and 0<len(frames)<=65536,"frames_count")
    need(type(writes) is list and 0<len(writes)<=65536,"writes_count")
    last={}; phases=[]; presentation=[]; active=[]; idle=0; incomplete=0
    for f in frames:
        need(integer(f.get("clock")) and f["clock"]<doc["clock_count"],"clock")
        need(integer(f.get("counter")),"counter")
        need(type(f.get("complete")) is bool,"complete_type")
        for k in ("before_us","after_us","frame_time_us","predicted_presentation_us","refresh_interval_us"):
            need(integer(f.get(k)), "time_integer")
        need(f["after_us"]>=f["before_us"],"phase_order")
        present=f.get("presentation_us")
        need(present is None or integer(present,1),"presentation_type")
        need(present is None or present>=f["frame_time_us"],"presentation_order")
        previous=last.get(f["clock"])
        if previous:
            need(f["counter"]>previous["counter"],"counter_order")
            need(f["frame_time_us"]>=previous["frame_time_us"],"frame_order")
            delta=f["frame_time_us"]-previous["frame_time_us"]
            # Counter adjacency alone selects intervals; a long interval may be a
            # genuine slow frame. Do not censor it by refresh/latency thresholds.
            if f["counter"]==previous["counter"]+1:
                active.append(delta)
            else: idle+=1
        last[f["clock"]]=f
        if not f["complete"]: incomplete+=1
        if f["before_us"]>0: phases.append(f["after_us"]-f["before_us"])
        if f["complete"] and present is not None: presentation.append(present-f["frame_time_us"])
    durations=[]
    for w in writes:
        need(integer(w.get("start_us"),1) and integer(w.get("end_us"),1),"write_time")
        need(w["end_us"]>=w["start_us"],"write_order")
        need(integer(w.get("bytes"),1),"write_bytes")
        need(type(w.get("ok")) is bool,"write_ok")
        need(integer(w.get("frames_seen")) and w["frames_seen"]<=len(frames),"write_frame")
        durations.append(w["end_us"]-w["start_us"])
    return dict(frames=len(frames),writes=len(writes),incomplete=incomplete,phase_us=phases,
                presentation_latency_us=presentation,consecutive_counter_intervals_us=active,
                counter_gap_pairs=idle,idle_attribution="unknown; no interval classified idle by duration",state_write_us=durations,
                state_write_total_us=sum(durations),write_failures=sum(not w["ok"] for w in writes))
def controls():
    frame=dict(clock=0,counter=1,before_us=100,after_us=200,complete=True,
               frame_time_us=90,presentation_us=220,predicted_presentation_us=210,refresh_interval_us=16667)
    good=dict(schema=1,pid=42,source="a"*40,run="1",attempt="1",executable="/synthetic/exreader-linux",
              overflow=0,capacity=65536,clock_count=1,probe_static_bytes=1,frames=[frame],
              writes=[dict(start_us=110,end_us=120,bytes=40,ok=True,frames_seen=1)])
    args=(42,"a"*40,"1","1")
    check(good,*args)
    cases=[
      ("schema","schema",lambda d:d.update(schema=2)),
      ("pid","pid",lambda d:d.update(pid=43)),
      ("source","source",lambda d:d.update(source="b"*40)),
      ("run","run",lambda d:d.update(run="2")),
      ("attempt","attempt",lambda d:d.update(attempt="2")),
      ("exe","executable",lambda d:d.update(executable="/wrong")),
      ("overflow","overflow",lambda d:d.update(overflow=1)),
      ("capacity","capacity",lambda d:d.update(capacity=65537)),
      ("clock_count","clocks",lambda d:d.update(clock_count=0)),
      ("probe_bytes","probe_bytes",lambda d:d.update(probe_static_bytes=0)),
      ("no_frames","frames_count",lambda d:d.update(frames=[])),
      ("no_writes","writes_count",lambda d:d.update(writes=[])),
      ("clock","clock",lambda d:d["frames"][0].update(clock=2)),
      ("counter_bool","counter",lambda d:d["frames"][0].update(counter=True)),
      ("complete","complete_type",lambda d:d["frames"][0].update(complete=1)),
      ("negative_time","time_integer",lambda d:d["frames"][0].update(before_us=-1)),
      ("overflow_time","time_integer",lambda d:d["frames"][0].update(after_us=2**63)),
      ("phase","phase_order",lambda d:d["frames"][0].update(after_us=99)),
      ("present_bool","presentation_type",lambda d:d["frames"][0].update(presentation_us=True)),
      ("present_order","presentation_order",lambda d:d["frames"][0].update(presentation_us=80)),
      ("duplicate_counter","counter_order",lambda d:d["frames"].append(copy.deepcopy(d["frames"][0]))),
      ("write_order","write_order",lambda d:d["writes"][0].update(end_us=109)),
      ("write_bytes","write_bytes",lambda d:d["writes"][0].update(bytes=True)),
      ("write_frame","write_frame",lambda d:d["writes"][0].update(frames_seen=2)),
    ]
    receipt=[]
    for name,expected,mutate in cases:
        d=copy.deepcopy(good);mutate(d);actual=None
        try: check(d,*args)
        except Invalid as e: actual=str(e)
        receipt.append(dict(name=name,expected=expected,actual=actual,passed=actual==expected))
    need(len(receipt)==24 and all(x["passed"] for x in receipt),"controls")
    idle=copy.deepcopy(good);idle["frames"].append(dict(frame,counter=2,frame_time_us=1000000,
            before_us=1000010,after_us=1000020,presentation_us=None,complete=True))
    idle["frames"].append(dict(frame,counter=4,frame_time_us=2000000,
            before_us=2000010,after_us=2000020,presentation_us=None,complete=False))
    result=check(idle,*args)
    need(result["consecutive_counter_intervals_us"]==[999910] and result["counter_gap_pairs"]==1,
         "long_adjacent_interval_retained_gap_not_joined")
    return dict(positive=2,negative=24,results=receipt)
def run_sampler(args):
    # Only extend the child's environment. Existing sampler and all test bodies remain unchanged.
    script=Path(args[0]).resolve()
    allowed={ROOT/"tests/reader_perf_gtk/sample.py",
             ROOT/"tests/reader_product_performance_handoff/sample_gtk_interactions.py"}
    need(script in allowed,"sampler_path")
    sys.path.insert(0,str(ROOT/"tests/reader_perf_gtk"))
    import observe
    original=observe.Host.__init__
    module=str((ROOT/"build/f08-probe/libexreader_f08.so").resolve())
    def init(self,binary,font,profile,folder,environment,tag=""):
        environment=dict(environment)
        out=Path(folder).resolve()/"frameclock"
        out.mkdir(parents=True,exist_ok=True)
        environment.update(LD_PRELOAD=module,GTK_MODULES=module,EXR_F08_OUTPUT=str(out),
            GITHUB_SHA=os.environ["GITHUB_SHA"],GITHUB_RUN_ID=os.environ["GITHUB_RUN_ID"],
            GITHUB_RUN_ATTEMPT=os.environ["GITHUB_RUN_ATTEMPT"])
        original(self,binary,font,profile,folder,environment,tag)
    observe.Host.__init__=init
    sys.argv=[str(script)]+args[1:]
    runpy.run_path(str(script),run_name="__main__")
def verify():
    output=ROOT/"build/f08-result";output.mkdir(parents=True,exist_ok=True)
    (output/"controls.json").write_text(json.dumps(controls(),indent=2)+"\n")
    source=os.environ["GITHUB_SHA"];run=os.environ["GITHUB_RUN_ID"];attempt=os.environ["GITHUB_RUN_ATTEMPT"]
    binary=ROOT/"build/perf-package/EXReader-Linux/bin/exreader-linux"
    reports=[]
    for folder,count,samples_count in (("perf-evidence",32,520),("perf-interactions",12,240)):
        root=ROOT/"build"/folder
        launches=load(root/"launches.json")["launches"]
        samples=load(root/"samples.json")
        need(samples["source_sha"]==source and str(samples["run_id"])==run and str(samples["attempt"])==attempt,"sample_identity")
        need(len(launches)==count,"launch_count")
        need(len(samples["samples"])==samples_count and all(s["outcome"]=="ok" for s in samples["samples"]),"old_coverage")
        for launch in launches:
            need(launch.get("process_exit")==0,"host_exit")
            pid=launch["pid"]
            directory=root/"raw"/("launch-%02d"%launch["launch"])/"frameclock"
            paths=list(directory.glob("*.json"))
            need(len(paths)==1 and paths[0].name==str(pid)+".json","pid_file")
            raw=load(paths[0]);r=check(raw,pid,source,run,attempt)
            need(Path(raw["executable"]).resolve()==binary.resolve(),"actual_executable")
            r.update(cohort=folder,launch=launch["launch"],pid=pid,raw_sha256=digest(paths[0]))
            reports.append(r)
    receipt=dict(source=source,run=run,attempt=attempt,executable_sha256=digest(binary),
      probe_sha256=digest(ROOT/"build/f08-probe/libexreader_f08.so"),launches=reports,
      evidence_complete=True,product_budget_ratified=False,F08_accepted=False,
      instrumentation_changes_memory_and_timing=True,physical_display_presented=False,
      interpretation="GDK phase and state-file-write durations; not monitor scanout, not a proven production bottleneck")
    (output/"summary.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({k:v for k,v in receipt.items() if k!="launches"}))
    print("F08_COUNTS launches=44 old_samples=760 controls=2+24")
if __name__=="__main__":
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    if sys.argv[1:2]==["run"]: run_sampler(sys.argv[2:])
    else: verify()
