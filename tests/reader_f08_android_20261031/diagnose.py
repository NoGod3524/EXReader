"""Read-only Actions attribution of the pinned, failed-budget Android observation."""
import hashlib, importlib.util, io, json, os, stat, sys, zipfile
from pathlib import Path, PurePosixPath
from lane import ROOT, identity, need, save, sha, command
BASE="37cbd2566167f633fe70387eb4d0c139751a5b0b"
RUN=41181554393
ARTIFACT=13035511879
SIZE=43723256
DIGEST="1dceb5cf0f747d0226a15cc7c310eb8dd2f6f070b8e47af580b03f85dc4d4931"
OUT=ROOT/"build/f08-android-diagnosis"
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"audit source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
         {"tests/reader_f08_android_20261031/diagnose.py",".github/workflows/dot-f08-android-diagnose-20261031.yml"},"scope")
    OUT.mkdir(parents=True,exist_ok=False)
    api=lambda p:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+p]))
    producer=api("actions/runs/"+str(RUN));meta=api("actions/artifacts/"+str(ARTIFACT))
    save(OUT/"metadata.json",meta)
    need(producer["head_sha"]==BASE and producer["run_attempt"]==1 and producer["conclusion"]=="failure","failed-budget producer")
    need(meta["id"]==ARTIFACT and meta["name"]=="f08-android-"+str(RUN)+"-1" and not meta["expired"] and
         meta["size_in_bytes"]==SIZE and meta["digest"]=="sha256:"+DIGEST and
         meta["workflow_run"]["id"]==RUN and meta["workflow_run"]["head_sha"]==BASE,"artifact identity")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(ARTIFACT)+"/zip"])
    need(len(data)==SIZE and hashlib.sha256(data).hexdigest()==DIGEST,"ZIP identity")
    (OUT/"original.zip").write_bytes(data);raw=OUT/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=set();infos=archive.infolist()
        need(0<len(infos)<20000 and sum(x.file_size for x in infos)<2*1024**3,"ZIP bounds")
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and "\\" not in info.filename
                 and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key)
            need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
            if info.is_dir():continue
            destination=raw/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(archive.read(info))
    manifest=json.loads((raw/"manifest.json").read_text());ident={"source_sha":BASE,"run_id":str(RUN),"attempt":"1"}
    need(all(manifest.get(k)==v for k,v in ident.items()),"manifest producer")
    files={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    need(files==set(manifest["files"])|{"manifest.json"},"inventory")
    for name,item in manifest["files"].items():need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"file bytes")
    spec=importlib.util.spec_from_file_location("original_shelf",ROOT/"tools/run_reader_shelf_ui.py")
    sampler=importlib.util.module_from_spec(spec);spec.loader.exec_module(sampler)
    recomputed=sampler.analyze(raw/"execution",ident)
    result=json.loads((raw/"execution/result.json").read_text())
    need(result["accepted"] is True and all(result.get(k)==v for k,v in recomputed.items()),"original analysis differs")
    frames=[];closed=[]
    for path in sorted((raw/"execution/windows").glob("*.jsonl")):
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        ordinary=[r for r in rows if r.get("kind")=="frame" and r["first_draw"]==0]
        frames+=ordinary
        if rows[-1]["kind"]=="stop":closed+=ordinary
    segments={"all_ordinary":frames,"closed_window_ordinary":closed}
    ui=json.loads((raw/"execution/ui/validation.json").read_text())
    for interval in ui["intervals"]:
        segments[interval["name"]]=[r for r in frames if interval["started_elapsed_ns"]<=r["callback_elapsed_ns"]<=interval["finished_elapsed_ns"]]
    groups={}
    for name,rows in segments.items():
        stages={}
        for key in ("total_ns","input_ns","layout_measure_ns","draw_ns","sync_ns","gpu_ns","deadline_ns"):
            valid=[r[key]/1e6 for r in rows if type(r.get(key)) is int and r[key]>=0]
            stages[key.removesuffix("_ns")+"_ms"]={**sampler.summarize(valid),"unavailable":len(rows)-len(valid)}
        delay=[(r["vsync_ns"]-r["intended_vsync_ns"])/1e6 for r in rows
               if r["vsync_ns"]>=r["intended_vsync_ns"]>0]
        deadlines=[r for r in rows if r.get("deadline_ns",0)>0]
        gpu=[r for r in rows if r.get("gpu_ns",-1)>=0]
        groups[name]={"frames":len(rows),"stages":stages,"vsync_delay_ms":sampler.summarize(delay),
            "valid_deadlines":len(deadlines),"missed_deadlines":sum(r["total_ns"]>=r["deadline_ns"] for r in deadlines),
            "gpu_measured_frames":len(gpu),"gpu_at_least_80pct_of_total":sum(r["gpu_ns"]>=r["total_ns"]*.8 for r in gpu)}
    initial=ui["cases"][0]["detail"]["observation"]
    environment={}
    for name,terms in (("display.txt",("refresh","fps","mode","render")),("getprop.txt",("egl","vulkan","hwui","qemu","hardware","cpu","ro.build.version.sdk"))):
        lines=(raw/"environment"/name).read_text(errors="replace").splitlines()
        environment[name]=[line for line in lines if any(t in line.lower() for t in terms)][:80]
    report={**identity(),"producer":ident,"artifact_id":ARTIFACT,"original_sha256":DIGEST,
        "resampled":False,"groups":groups,"initial_observation":initial,"environment":environment,
        "longest_frames":sorted(frames,key=lambda r:r["total_ns"],reverse=True)[:20],
        "budget_evaluation":json.loads((raw/"evaluation.json").read_text()),
        "limits":["Stage durations can overlap and are not subtracted from total duration.",
                  "Vsync and intended-vsync are compared within their clock domain; callback elapsed time is not subtracted from vsync.",
                  "Two unclosed windows remain in all-frame results; the closed-window subset is separately reported.",
                  "Phase dominance alone does not distinguish emulator overhead from application causality."],"f08_accepted":False}
    save(OUT/"diagnosis.json",report)
    print("F08_ANDROID_PHASES",json.dumps(groups),flush=True)
    print("F08_ANDROID_INITIAL",json.dumps(initial),flush=True)
    print("F08_ANDROID_ENVIRONMENT",json.dumps(environment),flush=True)
    print("F08_ANDROID_DIAGNOSIS",json.dumps({"producer":ident,"artifact_id":ARTIFACT,"sha256":DIGEST,"resampled":False,"f08_accepted":False}),flush=True)
if __name__=="__main__":main()
