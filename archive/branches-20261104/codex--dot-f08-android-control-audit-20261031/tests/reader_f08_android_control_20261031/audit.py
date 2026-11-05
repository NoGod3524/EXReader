"""Read-only Actions audit: authenticate and recompute the product and platform-control observations."""
import hashlib, io, json, os, stat, sys, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity, need, save, sha, command, load_sampler, evaluate
BASE="c759bf40e6d77253b6023e0e5c69cc08d50ebfc8"
OUT=ROOT/"build/f08-android-control-audit"
PINS={
 "product":{"source":"37cbd2566167f633fe70387eb4d0c139751a5b0b","run":41181554393,"artifact":13035511879,
    "name":"f08-android-41181554393-1","bytes":43723256,"sha256":"1dceb5cf0f747d0226a15cc7c310eb8dd2f6f070b8e47af580b03f85dc4d4931","conclusion":"failure"},
 "control":{"source":BASE,"run":41183221963,"artifact":13035905344,
    "name":"f08-android-control-41183221963-1","bytes":87683,"sha256":"8844af6405bfbe52a45ed1f846f88068c52617fff6ed7553c8c662c9bed0616d","conclusion":"success"}}
def fetch(kind,pin):
    api=lambda path:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+path]))
    meta=api("actions/artifacts/"+str(pin["artifact"]));producer=api("actions/runs/"+str(pin["run"]))
    need(producer["head_sha"]==pin["source"] and producer["run_attempt"]==1 and
         producer["conclusion"]==pin["conclusion"],"producer "+kind)
    need(meta["id"]==pin["artifact"] and meta["name"]==pin["name"] and not meta["expired"]
         and meta["size_in_bytes"]==pin["bytes"] and meta["digest"]=="sha256:"+pin["sha256"]
         and meta["workflow_run"]["id"]==pin["run"] and meta["workflow_run"]["head_sha"]==pin["source"],"artifact "+kind)
    folder=OUT/kind;folder.mkdir();save(folder/"metadata.json",meta)
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(pin["artifact"])+"/zip"])
    need(len(data)==pin["bytes"] and hashlib.sha256(data).hexdigest()==pin["sha256"],"ZIP bytes "+kind)
    (folder/"original.zip").write_bytes(data);raw=folder/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos=archive.infolist();need(0<len(infos)<20000 and sum(i.file_size for i in infos)<2*1024**3,"ZIP bounds")
        names=set()
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and
                 "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key)
            need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
            if info.is_dir():continue
            destination=raw/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(archive.read(info))
    manifest=json.loads((raw/"manifest.json").read_text())
    need(manifest["source_sha"]==pin["source"] and manifest["run_id"]==str(pin["run"]) and
         manifest["attempt"]=="1" and manifest["f08_accepted"] is False,"manifest")
    files={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    need(files==set(manifest["files"])|{"manifest.json"},"inventory")
    for name,item in manifest["files"].items():
        need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"payload bytes")
    return raw
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"audit source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
        {"tests/reader_f08_android_control_20261031/audit.py",".github/workflows/dot-f08-android-control-audit-20261031.yml"},"audit scope")
    OUT.mkdir(parents=True,exist_ok=False)
    roots={kind:fetch(kind,pin) for kind,pin in PINS.items()}
    product,control=roots["product"],roots["control"];sampler=load_sampler()
    profile=json.loads((product/"profile.json").read_text())
    need((product/"profile.json").read_bytes()==(control/"profile.json").read_bytes(),"same frozen profile")
    need(sha(product/"profile.json")=="f289d1e695af4c53cd9e0e11c4d67b76536bc134c6feed1245def50d7212a215","profile SHA")
    ident={"source_sha":PINS["product"]["source"],"run_id":str(PINS["product"]["run"]),"attempt":"1"}
    original=json.loads((product/"execution/result.json").read_text())
    need(all(original.get(k)==v for k,v in sampler.analyze(product/"execution",ident).items()),"product raw observations")
    budget=evaluate(original,profile);saved=json.loads((product/"evaluation.json").read_text())
    need(all(saved.get(k)==v for k,v in budget.items()) and budget["shelf_budget_accepted"] is False,"failed product budget preserved")
    receipt=json.loads((control/"result.json").read_text());build=json.loads((control/"build.json").read_text())
    need(receipt["synthetic_only"] is True and receipt["product_measured"] is False and
         receipt["diagnostic_complete"] is True and receipt["f08_accepted"] is False,"control scope")
    need(sha(control/"control.apk")==sha(control/"installed.apk")==receipt["apk_sha256"]==build["apk_sha256"],"control installed binary")
    need(build["collector_sha256"]==build["collector_copy_sha256"]==
         sha(ROOT/"examples/android/app/src/main/java/org/exreader/host/ShelfWindowMetrics.java"),"unchanged Window collector")
    phase_paths=list((control/"raw").rglob("phases.jsonl"));window_paths=list((control/"raw").rglob("window-*.jsonl"))
    need(len(phase_paths)==len(window_paths)==1,"one control Window and phase trace")
    phases=[json.loads(line) for line in phase_paths[0].read_text().splitlines()]
    need(phases==receipt["phases"] and [p["phase"] for p in phases]==
         ["forward_start","forward_end","reverse_start","reverse_end","complete"],"phase history")
    need(all(a["elapsed_ns"]<=b["elapsed_ns"] for a,b in zip(phases,phases[1:])),"phase ordering")
    by={p["phase"]:p for p in phases}
    need(by["forward_end"]["first_visible"]>by["forward_start"]["first_visible"] and
         by["reverse_end"]["first_visible"]<by["reverse_start"]["first_visible"],"actual scroll transitions")
    rows=[json.loads(line) for line in window_paths[0].read_text().splitlines()]
    need(rows[0]["kind"]=="start" and rows[-1]["kind"]=="stop" and all(r["kind"]=="frame" for r in rows[1:-1]),"closed trace")
    frames=rows[1:-1]
    need(len(frames)==rows[-1]["frames"] and [r["sequence"] for r in frames]==list(range(1,len(frames)+1))
         and rows[-1]["dropped"]==sum(r["drop_count"] for r in frames)==0,"frame census")
    need(all(r["pid"]==rows[0]["pid"] and r["window_id"]==rows[0]["window_id"] for r in frames),"Window identity")
    ordinary=[r for r in frames if r["first_draw"]==0];groups={}
    for name in ("all","forward","reverse"):
        subset=ordinary if name=="all" else [r for r in ordinary if
            by[name+"_start"]["elapsed_ns"]<=r["callback_elapsed_ns"]<=by[name+"_end"]["elapsed_ns"]]
        need(len(subset)>=100,"control sample size")
        groups[name]={"frames":len(subset)}
        for key in ("total_ns","draw_ns","layout_measure_ns","gpu_ns"):
            values=[r[key]/1e6 for r in subset if type(r.get(key)) is int and r[key]>=0]
            groups[name][key.removesuffix("_ns")+"_ms"]={**sampler.summarize(values),"unavailable":len(subset)-len(values)}
    need(groups==receipt["groups"],"control raw observations")
    result={**identity(),"authenticated":True,"pins":PINS,"profile_sha256":sha(product/"profile.json"),
        "product":{"frames":original["completed_window_frame_ms"],"budget":budget},"control":groups,
        "baseline_60hz_target_met":all(g["total_ms"]["p95"]<=profile["budgets"]["ordinary_window_frame_p95_ms"] and
            g["total_ms"]["p99"]<=profile["budgets"]["ordinary_window_frame_p99_ms"] for g in groups.values()),
        "same_runner_instance":False,"application_causality_established":False,"f08_accepted":False}
    save(OUT/"audit.json",result);print("F08_ANDROID_CONTROL_AUDIT",json.dumps(result),flush=True)
if __name__=="__main__":main()
