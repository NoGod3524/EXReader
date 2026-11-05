#!/usr/bin/env python3
"""Read only the four pinned F08 archives, inside Actions; never sample a product."""
import bisect, hashlib, importlib.util, io, json, math, os, stat, subprocess, sys, urllib.request, zipfile
from pathlib import Path, PurePosixPath
SOURCE="cfdaf6a4531548be63b4dd0c2bccd6b050a93124"
RUN=41155753132
ATTEMPT=1
REPO="NoGod3524/EXReader"
PINS={
 "frames":(13024799994,39891,"1c6559ced7a8330f3a829ca12fd2db7ed63245a86c37a354b22ae2fbe7f5c25d","f08-frameclock"),
 "raw":(13025103462,2639990,"d32c4b1664e32bad22e418499b1990f9c3dae7f5751eceb84ec9f11c99c2e47b","reader-product-perf-gtk"),
 "interaction":(13025038682,577568,"3c9b5f39a67fef4a9687b27dcb4bc12c12ff0a107ce0eeb9ca7f7bef3358ad09","reader-product-perf-gtk-interactions"),
 "verification":(13025023795,1236149,"d762ffd41387ae604f102cb32584f6e1e7cace061a37187cbd5d0fa53639002a","reader-product-perf-gtk-verification")}
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"build/f08-analysis"
class Refused(ValueError): pass
def need(ok,why):
    if not ok: raise Refused(why)
def digest(data): return hashlib.sha256(data).hexdigest()
def unique(pairs):
    out={}
    for k,v in pairs:
        need(k not in out,"duplicate_json_key")
        out[k]=v
    return out
def loads(data): return json.loads(data,object_pairs_hook=unique)
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
def api(path):
    raw=subprocess.check_output(["gh","api","repos/"+REPO+"/"+path],timeout=90)
    return loads(raw)
def scan(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist();need(0<len(infos)<=10000,"zip_count")
        names=set();canonical=set();total=0
        for info in infos:
            n=info.filename;p=PurePosixPath(n)
            need(n and not p.is_absolute() and ".." not in p.parts and "\\" not in n and ":" not in n and "\x00" not in n,"zip_path")
            norm=str(p).casefold()
            need(n not in names and norm not in canonical,"zip_collision")
            names.add(n);canonical.add(norm)
            need(stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"zip_kind")
            need(not info.flag_bits&1 and info.file_size<=32*1024*1024,"zip_entry_budget")
            total+=info.file_size
            need(total<=256*1024*1024,"zip_total_budget")
        return {i.filename:z.read(i) for i in infos if not i.is_dir()}
def member(files,suffix):
    names=[n for n in files if n==suffix or n.endswith("/"+suffix)]
    need(len(names)==1,"member:"+suffix)
    return files[names[0]]
def stats(values):
    need(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in values),"numeric")
    x=sorted(values)
    if not x: return dict(count=0,p50=None,p95=None,max=None,min=None)
    return dict(count=len(x),min=x[0],p50=x[math.ceil(.50*len(x))-1],
                p95=x[math.ceil(.95*len(x))-1],max=x[-1])
def overlap(doc):
    # Per-frame union overlap, never double-count simultaneous writes within one frame.
    # Multiple clocks are distinct surfaces: sums across clocks are not CPU utilization.
    writes=sorted((w["start_us"],w["end_us"]) for w in doc["writes"] if w["end_us"]>w["start_us"])
    merged=[]
    for a,b in writes:
        if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else: merged.append((a,b))
    ends=[b for a,b in merged]; rows=[]
    for f in doc["frames"]:
        a,b=f["before_us"],f["after_us"]
        if a<=0: continue
        i=bisect.bisect_right(ends,a);total=0
        while i<len(merged) and merged[i][0]<b:
            total+=max(0,min(b,merged[i][1])-max(a,merged[i][0]));i+=1
        rows.append(dict(clock=f["clock"],counter=f["counter"],phase_us=b-a,write_overlap_us=total))
    return rows
def local_controls():
    need(stats([1,2,999910])==dict(count=3,min=1,p50=2,p95=999910,max=999910),"long_frame_preserved")
    need(stats([])["p95"] is None,"empty_not_zero")
    d=dict(writes=[dict(start_us=10,end_us=30),dict(start_us=20,end_us=40)],
           frames=[dict(clock=0,counter=1,before_us=0,after_us=5),
                   dict(clock=0,counter=2,before_us=15,after_us=35),
                   dict(clock=0,counter=3,before_us=40,after_us=50)])
    need([r["write_overlap_us"] for r in overlap(d)]==[20,0],"union_overlap")
    negatives=[]
    for label,fn in [
        ("negative",lambda:stats([-1])),
        ("boolean",lambda:stats([True])),
        ("nan",lambda:stats([float("nan")])),
        ("duplicate_json",lambda:loads('{"x":1,"x":2}'))]:
        try: fn()
        except Refused: negatives.append(label)
        else: raise Refused("negative_not_refused:"+label)
    return dict(positive=3,negative=4,negative_names=negatives)
def acquire():
    run=api("actions/runs/"+str(RUN))
    need(run["head_sha"]==SOURCE and run["run_attempt"]==ATTEMPT and run["conclusion"]=="success","producer_run")
    need(run["path"].split("@")[0]==".github/workflows/dot-f08-gtk-frameclock-20261031.yml","producer_workflow")
    save("producer-run.json",run)
    result={}
    for label,(aid,size,sha,prefix) in PINS.items():
        meta=api("actions/artifacts/"+str(aid))
        need(meta["id"]==aid and meta["size_in_bytes"]==size and meta["digest"]=="sha256:"+sha and meta["expired"] is False,"artifact_metadata:"+label)
        need(meta["name"]==f"{prefix}-{RUN}-{ATTEMPT}" and meta["workflow_run"]["id"]==RUN and meta["workflow_run"]["head_sha"]==SOURCE,"artifact_identity:"+label)
        save(label+"-metadata.json",meta)
        path=OUT/(label+"-original.zip")
        with path.open("wb") as stream:
            subprocess.run(["gh","api","repos/"+REPO+"/actions/artifacts/"+str(aid)+"/zip"],stdout=stream,check=True,timeout=120)
        data=path.read_bytes()
        need(len(data)==size and digest(data)==sha,"artifact_bytes:"+label)
        result[label]=scan(data)
    return result
def identity(doc):
    need(doc["source_sha"]==SOURCE and str(doc["run_id"])==str(RUN) and str(doc["attempt"])==str(ATTEMPT),"raw_identity")
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions_only")
    OUT.mkdir(parents=True,exist_ok=True)
    save("analysis-controls.json",local_controls())
    # Import the exact unchanged original validator, not a new replacement oracle.
    spec=importlib.util.spec_from_file_location("frame_validator",ROOT/"tests/reader_f08_gtk_frameclock_20261031/verify.py")
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    save("original-controls-reexecuted.json",old.controls())
    files=acquire()
    original=loads(member(files["frames"],"summary.json"))
    controls=loads(member(files["frames"],"controls.json"))
    need(controls["positive"]==2 and controls["negative"]==24 and len(controls["results"])==24 and all(r["passed"] is True for r in controls["results"]),"original_controls")
    need(original["source"]==SOURCE and str(original["run"])==str(RUN) and str(original["attempt"])=="1","frame_identity")
    need(original["evidence_complete"] is True and original["F08_accepted"] is False and original["product_budget_ratified"] is False,"original_scope")
    need(original["executable_sha256"]=="1bc210ccef0a9bd9bc4b365cc0386e3127e1f0a52152b3487d1bd94ff2cdeeab","binary_pin")
    need(original["probe_sha256"]=="740f2ede8f395c8d53d145a453036af7802e24cf4b6c191784b33316d606029b","probe_pin")
    prior=loads(member(files["verification"],"verified.json"));identity(prior)
    need(prior["artifact"]["id"]==PINS["raw"][0] and prior["artifact"]["zip_sha256"]==PINS["raw"][2],"prior_verification")
    need(prior["report"]["accepted"] is True and prior["report"]["launches"]==32,"prior_report")
    oldrows=original["launches"]
    need(len(oldrows)==44,"original_launches")
    keyed={(r["cohort"],r["launch"]):r for r in oldrows}
    need(len(keyed)==44,"duplicate_launch")
    results=[];cohorts={};remaining=set(keyed)
    fields=("phase_us","presentation_latency_us","consecutive_counter_intervals_us","state_write_us")
    for label,cohort,nlaunch,nsample in [("raw","perf-evidence",32,520),("interaction","perf-interactions",12,240)]:
        f=files[label];launches=loads(member(f,"launches.json"))["launches"]
        samples=loads(member(f,"samples.json"));identity(samples)
        need(len(launches)==nlaunch and len(samples["samples"])==nsample and all(s["outcome"]=="ok" for s in samples["samples"]),"old_coverage")
        arrays={k:[] for k in fields};rss=[];frame_count=write_count=incomplete=gaps=0;overlaps=[]
        for launch in launches:
            need(launch["process_exit"]==0,"process_exit")
            key=(cohort,launch["launch"]);need(key in remaining,"launch_key");remaining.remove(key)
            suffix=f'raw/launch-{launch["launch"]:02d}/frameclock/{launch["pid"]}.json'
            rawbytes=member(f,suffix);raw=loads(rawbytes)
            calculated=old.check(raw,launch["pid"],SOURCE,str(RUN),str(ATTEMPT))
            expected=keyed[key]
            need(expected["pid"]==launch["pid"] and expected["raw_sha256"]==digest(rawbytes),"raw_hash")
            need(all(expected[k]==v for k,v in calculated.items()),"raw_summary_recomputed")
            ov=overlap(raw);overlaps.extend(ov)
            row=dict(cohort=cohort,launch=launch["launch"],pid=launch["pid"],raw_sha256=digest(rawbytes),
                     frames=calculated["frames"],writes=calculated["writes"],incomplete=calculated["incomplete"],
                     counter_gap_pairs=calculated["counter_gap_pairs"],write_failures=calculated["write_failures"],
                     metrics_us={k:stats(calculated[k]) for k in fields},
                     frame_phase_write_overlap_us=stats([r["write_overlap_us"] for r in ov]),
                     overlap_rows=ov)
            results.append(row)
            for k in fields: arrays[k].extend(calculated[k])
            frame_count+=calculated["frames"];write_count+=calculated["writes"]
            incomplete+=calculated["incomplete"];gaps+=calculated["counter_gap_pairs"]
            value=launch.get("vm_hwm_kb")
            if value is not None: rss.append(value)
        cohorts[cohort]=dict(launches=nlaunch,old_samples=nsample,frames=frame_count,writes=write_count,
            incomplete=incomplete,counter_gap_pairs=gaps,metrics_us={k:stats(v) for k,v in arrays.items()},
            instrumented_rss_kib=stats(rss),frame_phase_write_overlap_us=stats([r["write_overlap_us"] for r in overlaps]),
            frames_with_write_overlap=sum(r["write_overlap_us"]>0 for r in overlaps))
    need(not remaining,"missing_launch")
    save("launch-analysis.json",results)
    summary=dict(analysis_completed=True,source=SOURCE,run=RUN,attempt=ATTEMPT,launches=44,old_samples=760,
        original_controls=dict(positive=2,negative=24),analysis_controls=dict(positive=3,negative=4),
        cohorts=cohorts,budget_ratified=False,F08_accepted=False,physical_display_presented=False,
        limitations=["All consecutive-counter intervals retained, including long intervals; idle attribution unknown.",
          "Nearest-rank percentiles. Pooled cohort distributions weight events, not launches; per-launch values retained.",
          "GDK phases on Xvfb are not physical monitor scanout; incomplete/presentation-missing records remain explicit.",
          "Write/frame interval union overlap is correlation, not causation, CPU utilization or avoidable time.",
          "Multiple frame clocks can overlap; their durations must not be summed as wall time.",
          "Instrumentation changes memory and timing. RSS is instrumented high-water, not a clean product budget.",
          "No new product sample or approved numeric threshold. Formal score remains 95/108."])
    save("summary.json",summary)
    print("F08_ANALYSIS "+json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":
    try: main()
    except Exception as exc:
        OUT.mkdir(parents=True,exist_ok=True)
        save("failure.json",dict(analysis_completed=False,error=type(exc).__name__,message=str(exc),F08_accepted=False))
        raise
