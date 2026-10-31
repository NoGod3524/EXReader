#!/usr/bin/env python3
"""Strict causal evidence, not a throughput/physical-presentation acceptance gate."""
import copy, hashlib, importlib.util, io, json, os, stat, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"build/f08-causal"
class Invalid(ValueError):pass
def need(ok,why):
    if not ok:raise Invalid(why)
def sha(b):return hashlib.sha256(b).hexdigest()
def identity():return {k:os.environ[k] for k in ("GITHUB_SHA","GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT")}
def load(p):return json.loads(Path(p).read_text())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+"\n")
def guard():
    lock=load(Path(__file__).with_name("source_lock.json"))
    git=lambda *a:subprocess.check_output(["git",*a],cwd=ROOT,text=True).strip()
    need(git("rev-parse","HEAD")==os.environ["GITHUB_SHA"],"source")
    subprocess.run(["git","merge-base","--is-ancestor",lock["base"],"HEAD"],cwd=ROOT,check=True)
    need(set(git("diff","--name-only",lock["base"],"HEAD").splitlines())==set(lock["owned"]),"test_scope")
    for path,blob in lock["frozen"].items():need(git("rev-parse","HEAD:"+path)==blob,"frozen:"+path)
def integer(x):return type(x) is int and 0<=x<2**63
def intervals(raw):
    previous={};rows=[]
    for f in raw["frames"]:
        old=previous.get(f["clock"]);previous[f["clock"]]=f
        if old:
            need(f["counter"]>old["counter"] and f["frame_time"]>=old["frame_time"],"counter")
            rows.append(dict(clock=f["clock"],previous=old["counter"],counter=f["counter"],
                start=old["before"],end=f["before"],delta_frame_us=f["frame_time"]-old["frame_time"],
                counter_gap=f["counter"]!=old["counter"]+1))
    return rows
def complete_intervals(result,raw):
    expected=intervals(raw)
    got=[{k:r[k] for k in e} for r,e in zip(result["intervals"],expected)]
    need(len(result["intervals"])==len(expected) and got==expected,"all_intervals_retained")
def analyze(raw,driver,ident):
    need(raw.get("pid")==driver.get("pid") and type(raw.get("pid")) is int and raw["pid"]>0,"pid")
    need(raw.get("source")==ident["GITHUB_SHA"] and raw.get("run")==ident["GITHUB_RUN_ID"] and raw.get("attempt")==ident["GITHUB_RUN_ATTEMPT"],"identity")
    need(raw.get("schema")==1 and raw.get("capacity")==65536,"schema")
    need(raw.get("overflow")==0,"overflow")
    need(raw.get("event_hook")==1 and raw.get("draw_hook")==1,"hooks")
    need(integer(raw.get("clock_count")) and 0<raw["clock_count"]<=64,"clocks")
    if any(a["field"]=="shelf_top_id" for a in driver["actions"]):
        need(integer(raw.get("list_draw_handlers")) and raw["list_draw_handlers"]>0,"list_draw_handler")
    for collection in ("states","inputs","draws","frames"):
        need(type(raw.get(collection)) is list and 0<len(raw[collection])<=65536,"rows:"+collection)
    for e in raw["inputs"]:
        need(all(integer(e.get(k)) for k in ("at","server_ms","type","code","hardware","clock")),"input_schema")
    for d in raw["draws"]:
        need(all(integer(d.get(k)) for k in ("at","clock","counter","kind")) and d["clock"]<raw["clock_count"],"draw_schema")
    for s in raw["states"]:
        need(all(integer(s.get(k)) for k in ("at","end","sequence")) and s["end"]>=s["at"] and type(s.get("ok")) is bool,"state_schema")
        need(all(type(s.get(k)) is int and -1<=s[k]<2**63 for k in ("painted_generation","book","page","font","busy","saving","shelf_top_id","shelf_loading","shelf_restoring","reader_visible")),"state_availability")
    for f in raw["frames"]:
        need(all(integer(f.get(k)) for k in ("clock","counter","before","after","frame_time","predicted","refresh")),"frame_time")
        need(f["clock"]<raw["clock_count"] and 0<f["before"]<=f["after"],"phase")
        need(type(f.get("complete")) is bool,"complete")
        need(f.get("presentation") is None or (integer(f["presentation"]) and f["presentation"]>0),"presentation")
    all_intervals=intervals(raw)
    joined=[]
    actions=driver["actions"]
    need(len({a["id"] for a in actions})==len(actions),"action_ids")
    for prior,current in zip(actions,actions[1:]):
        need(prior["done"]<current["inject_start"],"single_inflight")
    for action in actions:
        need(all(integer(action.get(k)) for k in ("inject_start","inject_end","effect_at","done")),"action_time")
        need(action["inject_start"]<=action["inject_end"]<=action["done"] and action["inject_start"]<=action["effect_at"]<=action["done"],"action_order")
        candidates=[e for e in raw["inputs"] if action["inject_start"]<=e["at"]<=action["done"]
                    and e["type"]==action["type"] and e["code"]==action["code"]]
        # Propagation of one GDK event across widgets stays in raw rows; never count it as another injection.
        groups={}
        for e in candidates:groups.setdefault((e["server_ms"],e["type"],e["code"],e["hardware"]),[]).append(e)
        need(len(groups)>0,"missing_input");need(len(groups)==1,"ambiguous_input")
        event=min(next(iter(groups.values())),key=lambda x:x["at"])
        need(event["clock"]<raw["clock_count"],"event_clock")
        field=action["field"]
        def effect(s):
            if not all(integer(s.get(k)) for k in (field,"book","sequence","busy","saving")):return False
            if s["book"]!=action["book"]:return False
            if not integer(s.get("shelf_loading")) or s["shelf_loading"]:return False
            if field=="shelf_top_id":
                if not integer(s.get("shelf_restoring")) or s["shelf_restoring"]:return False
            elif not integer(s.get("painted_generation")) or s.get("reader_visible")!=1:return False
            changed=s[field]!=action["before"] if action["expected"] is None else s[field]==action["expected"]
            generation=field=="shelf_top_id" or s["painted_generation"]>action["previous_generation"]
            return s["ok"] and changed and generation and s["sequence"]>action["previous_sequence"] and not s["busy"] and not s["saving"]
        states=[s for s in raw["states"] if event["at"]<=s["at"]<=action["done"] and effect(s)]
        need(states,"generation")
        paint=[]
        for d in raw["draws"]:
            if d["clock"]!=event["clock"] or d["kind"]!=(2 if field=="shelf_top_id" else 1):continue
            if not event["at"]<=d["at"]<=action["done"]:continue
            for f in raw["frames"]:
                if f["clock"]==d["clock"] and f["counter"]==d["counter"] and f["before"]<=d["at"]<=f["after"]:
                    linked=[s for s in states if s["at"]>=d["at"] and
                            (field=="shelf_top_id" or s["at"]<=f["after"])]
                    if linked:paint.append((f,d,linked[0]))
        need(paint,"matching_paint")
        # Shelf publication is delayed: choose the nearest preceding target paint only as a temporal candidate.
        f,d,state=(max(paint,key=lambda x:x[1]["at"]) if field=="shelf_top_id" else min(paint,key=lambda x:x[0]["after"]))
        joined.append(dict(id=action["id"],inject_start=action["inject_start"],active_end=max(action["done"],f["after"]),
            host_event_us=event["at"],state_us=state["at"],paint_end_us=f["after"],clock=f["clock"],counter=f["counter"],
            inject_to_event_us=event["at"]-action["inject_start"],
            event_to_matching_paint_us=None if field=="shelf_top_id" else f["after"]-event["at"],
            event_to_candidate_paint_us=f["after"]-event["at"] if field=="shelf_top_id" else None,
            causal_attribution="unknown_temporal_candidate" if field=="shelf_top_id" else "same_frame_state_generation",
            shelf_publication_may_follow_paint=field=="shelf_top_id",
            evidence="input/state + nearest preceding list draw (not causal proof)" if field=="shelf_top_id" else "single input + state generation in target draw frame"))
    for r in all_intervals:
        active=[a for a in joined if a["inject_start"]<=r["start"] and r["end"]<=a["active_end"]]
        touched=[a for a in joined if a["inject_start"]<r["end"] and a["active_end"]>r["start"]]
        quiet=[q for q in driver["quiet"] if q["start"]<=r["start"] and r["end"]<=q["end"]]
        r["classification"]="active" if active else "mixed" if touched else "driver_quiet_background" if quiet else "unknown"
    windows=[]
    for q in driver["quiet"]:
        need(integer(q["start"]) and integer(q["end"]) and q["end"]>=q["start"],"quiet")
        counts={k:sum(q["start"]<=x["at"]<=q["end"] for x in raw[k]) for k in ("inputs","states","draws")}
        windows.append(dict(**q,counts=counts,classification="background" if any(counts.values()) else "driver_quiet_no_observed_activity"))
    result=dict(actions=joined,intervals=all_intervals,quiet_windows=windows,
        phases_us=[f["after"]-f["before"] for f in raw["frames"]],
        state_write_us=[s["end"]-s["at"] for s in raw["states"]],
        presentation_count=sum(f["complete"] and f["presentation"] is not None for f in raw["frames"]),
        incomplete=sum(not f["complete"] for f in raw["frames"]),
        physical_display_presented=False,F08_accepted=False)
    complete_intervals(result,raw)
    return result
def fixture():
    ident=dict(GITHUB_SHA="a"*40,GITHUB_RUN_ID="1",GITHUB_RUN_ATTEMPT="1")
    f=dict(clock=0,counter=1,before=100,after=200,frame_time=90,predicted=0,refresh=0,complete=True,presentation=None)
    state=dict(at=150,end=160,ok=True,sequence=2,painted_generation=2,book=1,page=2,font=24,busy=0,saving=0,shelf_top_id=1,shelf_loading=0,shelf_restoring=1,reader_visible=1)
    raw=dict(schema=1,pid=42,source="a"*40,run="1",attempt="1",capacity=65536,overflow=0,event_hook=1,draw_hook=1,clock_count=1,
        frames=[f,dict(f,counter=2,before=1000100,after=1000200,frame_time=1000090)],
        inputs=[dict(at=120,server_ms=10,type=1,code=65473,hardware=70,clock=0)],
        draws=[dict(at=130,clock=0,counter=1,kind=1)],states=[state])
    driver=dict(pid=42,quiet=[],actions=[dict(id="a",inject_start=90,inject_end=125,effect_at=180,done=1000300,
        type=1,code=65473,field="page",before=1,expected=2,book=1,previous_generation=1,previous_sequence=1)])
    return raw,driver,ident
def controls():
    raw,driver,ident=fixture()
    good=analyze(raw,driver,ident);need(good["intervals"][0]["delta_frame_us"]==1000000 and good["intervals"][0]["classification"]=="active","long_active_positive")
    q=copy.deepcopy(driver);q["quiet"]=[dict(start=2000000,end=4000000)]
    need(analyze(raw,q,ident)["quiet_windows"][0]["classification"]=="driver_quiet_no_observed_activity","quiet_positive")
    cases=[("pid",lambda r:r.update(pid=43)),("rows:inputs",lambda r:r.update(inputs=[])),
           ("ambiguous_input",lambda r:r["inputs"].append(dict(r["inputs"][0],server_ms=11,at=121))),
           ("generation",lambda r:r["states"][0].update(painted_generation=1)),
           ("counter",lambda r:r["frames"][1].update(counter=0)),
           ("overflow",lambda r:r.update(overflow=1)),
           ("presentation",lambda r:r["frames"][0].update(presentation=0))]
    results=[]
    for expected,change in cases:
        r=copy.deepcopy(raw);change(r);actual=None
        try:analyze(r,driver,ident)
        except Invalid as e:actual=str(e)
        need(actual==expected,"control:"+expected);results.append(dict(expected=expected,actual=actual))
    missing=copy.deepcopy(good);missing["intervals"]=[];actual=None
    try:complete_intervals(missing,raw)
    except Invalid as e:actual=str(e)
    need(actual=="all_intervals_retained","control:long_gap")
    results.append(dict(expected="all_intervals_retained",actual=actual))
    need(len(results)==8,"control_count")
    return dict(positive=2,negative=8,results=results)

def regressions():
    from driver import action_complete
    raw,driver,ident=fixture();action=driver["actions"][0]
    host=dict(raw["states"][0])
    positive=[];negative=[]
    for field,before,expected in (("page",1,2),("font",22,24)):
        a=dict(action,field=field,before=before,expected=expected)
        need(action_complete({"host":host},a),"wait:"+field)
        positive.append(field+"_hidden_shelf_restoring")
    shelf=dict(action,field="shelf_top_id",before=0,expected=None)
    need(action_complete({"host":dict(host,shelf_restoring=0,reader_visible=0)},shelf),"wait:shelf")
    positive.append("shelf_ready")
    for name,change in (("wrong_effect",dict(page=3)),("wrong_book",dict(book=2)),
        ("old_generation",dict(painted_generation=1)),("old_sequence",dict(sequence=1)),
        ("busy",dict(busy=1)),("saving",dict(saving=1)),("hidden_reader",dict(reader_visible=0)),
        ("shelf_loading",dict(shelf_loading=1)),("unknown_page",dict(page=-1))):
        need(not action_complete({"host":dict(host,**change)},action),"reject:"+name)
        negative.append(name)
    need(not action_complete({"host":host},shelf),"reject:shelf_restoring")
    negative.append("shelf_restoring")
    for field,value in (("shelf_restoring",-1),("busy",None),("reader_visible",None)):
        h=dict(host);h[field]=value
        a=shelf if field=="shelf_restoring" else action
        need(not action_complete({"host":h},a),"reject:unavailable_"+field)
        negative.append("unavailable_"+field)
    raw["list_draw_handlers"]=1
    raw["inputs"][0].update(type=2,code=1,hardware=0)
    raw["draws"][0]["kind"]=2
    raw["states"][0].update(at=250,end=260,shelf_restoring=0,reader_visible=0)
    driver["actions"][0].update(type=2,code=1,field="shelf_top_id",before=0,expected=None,effect_at=270)
    result=analyze(raw,driver,ident)
    joined=result["actions"][0]
    need(joined["causal_attribution"]=="unknown_temporal_candidate" and joined["event_to_matching_paint_us"] is None,"shelf_not_promoted")
    positive.append("delayed_shelf_paint_candidate")
    for name,expected,change in (
        ("missing_list_handler","list_draw_handler",lambda r:r.update(list_draw_handlers=0)),
        ("missing_list_draw","matching_paint",lambda r:r["draws"][0].update(kind=1)),
        ("wrong_draw_clock","matching_paint",lambda r:(r.update(clock_count=2),r["draws"][0].update(clock=1))),
        ("shelf_still_restoring","generation",lambda r:r["states"][0].update(shelf_restoring=1))):
        r=copy.deepcopy(raw);change(r);actual=None
        try:analyze(r,driver,ident)
        except Invalid as e:actual=str(e)
        need(actual==expected,"regression:"+name);negative.append(name)
    return dict(positive=len(positive),negative=len(negative),passed=positive+negative)
def preflight():
    print("F08_PREFLIGHT",json.dumps(dict(original=controls(),regressions=regressions())),flush=True)

def verify_top(top,ident):
    need(top.get("identity")==ident and top.get("accepted") is True,"driver")
    need(top.get("planned_launches")==6 and top.get("planned_actions")==18,"plan")
    for name in ("host_sha256","module_sha256"):
        value=top.get(name,"");need(len(value)==64 and all(c in "0123456789abcdef" for c in value),"hash")
    rows=top.get("cohorts",[])
    need(len(rows)==6 and [r.get("launch") for r in rows]==list(range(6)),"launches")
    need([r.get("kind") for r in rows]==["page","font","shelf","page","font","shelf"],"kinds")
    ids=[]
    for r in rows:
        need(r.get("passed") is True and r.get("exit")==0 and not r.get("observation_failure") and len(r.get("actions",[]))==3,"coverage")
        need(r.get("host_sha256")==r.get("host_sha256_after")==top["host_sha256"] and r.get("module_sha256")==top["module_sha256"],"binary_hash")
        from driver import action_complete
        for action in r["actions"]:
            evaluations=action.get("evaluations",[])
            need(evaluations and len(evaluations)<=65536 and evaluations[-1]["passed"] is True,"predicate_evidence")
            need(action["inject_end"]<=action["wait_start"]<=action["wait_end"]<=action["done"],"wait_bounds")
            for evaluation in evaluations:
                need(action["wait_start"]<=evaluation["at"]<=action["wait_end"] and
                     evaluation["passed"]==action_complete({"host":evaluation["host"]},action),"predicate_recompute")
            need(evaluations[-1]["host"]==action["observed"],"observed_predicate")
        ids.extend(a["id"] for a in r["actions"])
    need(len(ids)==18 and len(set(ids))==18,"action_ids")
    return rows

def verify():
    top=load(OUT/"driver.json");verify_top(top,identity())
    need(sha((OUT/"module.so").read_bytes())==top["module_sha256"] and sha((OUT/"host.bin").read_bytes())==top["host_sha256"],"retained_binaries")
    results=[]
    for row in top["cohorts"]:
        folder=OUT/("launch-%02d"%row["launch"]);raw=load(folder/(str(row["pid"])+".json"))
        need(row["passed"] and row["exit"]==0 and len(row["actions"])==3,"coverage")
        need(row["host_sha256"]==row["host_sha256_after"]==top["host_sha256"],"host_hash")
        need(row["module_sha256"]==top["module_sha256"],"module_hash")
        need(Path(raw["executable"]).resolve()==(ROOT/"build/perf-package/EXReader-Linux/bin/exreader-linux").resolve(),"exe")
        result=analyze(raw,row,identity());result.update(launch=row["launch"],pid=row["pid"],kind=row["kind"])
        results.append(result)
    receipt=dict(identity=identity(),passed=True,new_launches=6,new_actions=18,
        host_sha256=top["host_sha256"],module_sha256=top["module_sha256"],results=results,
        controls=controls(),regressions=regressions(),draw_control=load(ROOT/"build/f08-causal-control/draw.json"),old_counts=dict(launches=44,samples=760,positive=2,negative=24),
        physical_display_presented=False,F08_accepted=False,not_product_performance_acceptance=True)
    need(receipt["draw_control"].get("passed") is True and receipt["draw_control"].get("pixels_equal") is True,"draw_control")
    save(OUT/"summary.json",receipt)
    bundle={str(p.relative_to(OUT)):sha(p.read_bytes()) for p in OUT.rglob("*") if p.is_file() and p.name!="bundle.json"}
    save(OUT/"bundle.json",dict(identity=identity(),files=bundle))
    print("F08_CAUSAL accepted=true launches=6 actions=18 controls=2+8 physical=false",flush=True)
def audit():
    """Original verifier remains unchanged; this adds same-run original-ZIP identity for the new cohort."""
    run=os.environ["GITHUB_RUN_ID"];attempt=os.environ["GITHUB_RUN_ATTEMPT"]
    api=lambda path:json.loads(subprocess.check_output(["gh","api","repos/"+os.environ["GITHUB_REPOSITORY"]+"/"+path]))
    meta=api("actions/runs/"+run)
    need(meta["head_sha"]==os.environ["GITHUB_SHA"] and str(meta["run_attempt"])==attempt,"run")
    listing=api("actions/runs/"+run+"/artifacts?per_page=100")["artifacts"]
    found=[a for a in listing if a["name"]=="f08-causal-"+run+"-"+attempt]
    need(len(found)==1,"artifact_unique");a=found[0]
    need(not a["expired"] and a["workflow_run"]["id"]==int(run) and a["workflow_run"]["head_sha"]==os.environ["GITHUB_SHA"],"artifact_source")
    need(0<a["size_in_bytes"]<=128*1024*1024,"zip_budget")
    data=subprocess.check_output(["gh","api","repos/"+os.environ["GITHUB_REPOSITORY"]+"/actions/artifacts/"+str(a["id"])+"/zip"])
    need(len(data)==a["size_in_bytes"] and "sha256:"+sha(data)==a["digest"],"zip_digest")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist();need(0<len(infos)<1000 and sum(i.file_size for i in infos)<256*1024*1024,"members")
        names=set()
        for i in infos:
            p=PurePosixPath(i.filename);normal=str(p).casefold()
            need(i.filename and str(p)!="." and not p.is_absolute() and ".." not in p.parts and "\\" not in i.filename and ":" not in i.filename and normal not in names,"path")
            names.add(normal);need(not i.flag_bits&1 and i.file_size<=64*1024*1024 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"kind")
        files={i.filename:z.read(i) for i in infos if not i.is_dir()}
    bundle=json.loads(files.pop("bundle.json"));need(bundle["identity"]==identity(),"bundle")
    need(set(files)==set(bundle["files"]) and all(sha(b)==bundle["files"][n] for n,b in files.items()),"inventory")
    summary=json.loads(files["summary.json"]);need(summary["identity"]==identity() and summary["passed"] is True and summary["new_launches"]==6 and summary["new_actions"]==18,"summary")
    need(summary["controls"]["positive"]==2 and summary["controls"]["negative"]==8 and summary["physical_display_presented"] is False and summary["F08_accepted"] is False,"claims")
    top=json.loads(files["driver.json"])
    verify_top(top,identity())
    need(sha(files["module.so"])==top["module_sha256"] and sha(files["host.bin"])==top["host_sha256"],"retained_binaries")
    need(summary["host_sha256"]==top["host_sha256"] and summary["module_sha256"]==top["module_sha256"],"summary_hash")
    need(summary["controls"]==controls(),"controls_recompute")
    need(summary["regressions"]==regressions(),"regressions_recompute")
    draw_control=summary["draw_control"]
    need(draw_control.get("passed") is True and draw_control.get("hook_only")==0 and
         draw_control.get("with_handler")==1 and draw_control.get("callbacks")==1 and
         draw_control.get("pixels_equal") is True and draw_control.get("nonempty") is True,"draw_control")
    need(len(summary["results"])==6 and [r["launch"] for r in summary["results"]]==list(range(6)),"summary_coverage")
    for row in top["cohorts"]:
        raw=json.loads(files["launch-%02d/%d.json"%(row["launch"],row["pid"])])
        need(raw["executable"]==str((ROOT/"build/perf-package/EXReader-Linux/bin/exreader-linux").resolve()),"exe")
        recomputed=analyze(raw,row,identity())
        saved=summary["results"][row["launch"]]
        need(all(saved[k]==v for k,v in recomputed.items()),"recompute")
    dest=ROOT/"build/f08-causal-audit";dest.mkdir(parents=True,exist_ok=True)
    save(dest/"receipt.json",dict(identity=identity(),artifact_id=a["id"],bytes=len(data),sha256=sha(data),passed=True))
    print("F08_CAUSAL_AUDIT",a["id"],sha(data),"passed",flush=True)
if __name__=="__main__":
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    {"guard":guard,"preflight":preflight,"verify":verify,"audit":audit}[sys.argv[1]]()
