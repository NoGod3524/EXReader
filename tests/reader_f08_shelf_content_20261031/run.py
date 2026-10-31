"""Reuse the exact full Linux product; add only the content-bearing draw observer."""
import argparse, hashlib, importlib.util, io, json, os, shutil, stat, subprocess, sys, traceback, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"build/f08-shelf-content"
BASE="2bd45f2f764b4cba33037d3366baea3adee1086b"
PRODUCER={"source_sha":"1c39ec9f0b5015d3aa1f12c0a39bcfa4719568b2","run_id":"41196829037","attempt":"1"}
FILES={"tests/reader_f08_causal_frame_20261031/probe.c","tests/reader_f08_causal_frame_20261031/verify.py",
       "tests/reader_f08_causal_frame_20261031/draw_control.c","tests/reader_f08_causal_frame_20261031/shelf_content.h",
       "tests/reader_f08_shelf_content_20261031/run.py",".github/workflows/dot-f08-shelf-content-20261031.yml",
       "tests/reader_f08_compact_resume_20261031/adapter.py","tests/reader_f08_compact_resume_20261031/controls.py"}
sys.path.insert(0,str(ROOT/"tests/reader_f08_causal_frame_20261031"))
import driver as D
_verify_spec=importlib.util.spec_from_file_location("f08_causal_verifier",ROOT/"tests/reader_f08_causal_frame_20261031/verify.py")
V=importlib.util.module_from_spec(_verify_spec);_verify_spec.loader.exec_module(V)
sys.path.insert(0,str(ROOT/"tests/reader_f08_compact_resume_20261031"))
import adapter as A
spec=importlib.util.spec_from_file_location("linux_full_product",ROOT/"tests/reader_f08_linux_product_20261031/run.py")
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
need,save,sha,command,identity,load=R.need,R.save,R.sha,R.command,R.identity,R.load
def api(path):return json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+path]))
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform.startswith("linux"),"Linux Actions only")
    need(Path(V.__file__).resolve()==ROOT/"tests/reader_f08_causal_frame_20261031/verify.py" and callable(getattr(V,"verify",None)),"explicit causal verifier import")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"source identity")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==FILES,"test-only scope")
def archive(ident,name,destination,artifact_id=None):
    run=api("actions/runs/"+ident["run_id"])
    need(run["head_sha"]==ident["source_sha"] and str(run["run_attempt"])==ident["attempt"],"producer run")
    if artifact_id is None:
        need(run["status"]=="completed","fixed product producer still running")
        rows=api("actions/runs/"+ident["run_id"]+"/artifacts?per_page=100")["artifacts"]
        matches=[x for x in rows if x["name"]==name];need(len(matches)==1,"unique fixed artifact")
        meta=matches[0]
    else:meta=api("actions/artifacts/"+str(artifact_id))
    need(not meta["expired"] and meta["name"]==name and
         str(meta["workflow_run"]["id"])==ident["run_id"] and meta["workflow_run"]["head_sha"]==ident["source_sha"],"artifact identity")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(meta["id"])+"/zip"])
    digest=hashlib.sha256(data).hexdigest()
    need(0<len(data)<=1024**3 and len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest,"original ZIP identity")
    destination.mkdir(parents=True,exist_ok=False);(destination/"original.zip").write_bytes(data)
    raw=destination/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist();need(0<len(infos)<20000 and sum(x.file_size for x in infos)<4*1024**3,"ZIP bounds")
        names=set()
        for item in infos:
            p=PurePosixPath(item.filename);key=str(p).casefold()
            need(str(p)!="." and not p.is_absolute() and ".." not in p.parts and
                 "\\" not in item.filename and ":" not in item.filename and key not in names,"ZIP path")
            names.add(key)
            need(not item.flag_bits&1 and stat.S_IFMT(item.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
            if item.is_dir():continue
            target=raw/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(item))
    manifest=load(raw/"manifest.json")
    need(all(manifest.get(k)==v for k,v in ident.items()) and manifest["f08_accepted"] is False,"manifest identity")
    actual={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    need(actual==set(manifest["files"])|{"manifest.json"},"complete inventory")
    for name,item in manifest["files"].items():
        need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"file: "+name)
    return raw,{"producer":ident,"artifact_id":meta["id"],"bytes":len(data),"sha256":digest,
                "run_conclusion":run["conclusion"],"authenticated":True}
def product(raw):
    built=load(raw/"build-identity.json")
    need(all(built.get(k)==v for k,v in PRODUCER.items()) and built["sdk_version"]=="3.42.0","full build identity")
    need(R.compiled_features((raw/"host-CMakeCache.txt").read_text(),load(raw/"host-compile_commands.json"))==
         built["compiled_options"],"full compiler options")
    for path,blob in built["components"].items():
        need(command(["git","rev-parse","HEAD:"+path],text=True).strip()==blob,"unchanged production tree")
    need(set(built["helpers"])==set(R.FROZEN),"original helper coverage")
    for path,digest in built["helpers"].items():
        need(hashlib.sha256(command(["git","show",BASE+":"+path])).hexdigest()==digest,"original helper bytes")
    package=load(raw/"perf-package/build.json");payload=raw/"perf-package/EXReader-Linux"
    need(package["source_sha"]==PRODUCER["source_sha"] and package["sdk_version"]=="3.42.0" and package["abi"]==1,"fixed package")
    files={p.relative_to(payload).as_posix():sha(p) for p in payload.rglob("*") if p.is_file()}
    need(files==package["files"] and sha(payload/"bin/exreader-linux")==built["program_sha256"],"exact complete payload")
    seed=raw/"perf-probe/seed_library";need(sha(seed)==built["probes"]["perf-probe/seed_library"],"original corpus seed")
    return built
def coverage(summary):
    need(summary["passed"] is True and summary["new_launches"]==6 and summary["new_actions"]==18,"six original causal launches")
    actions=[a for row in summary["results"] if row["kind"]=="shelf" for a in row["actions"]]
    need(len(actions)==6 and all(a["causal_attribution"] in ("input_and_observed_shelf_content_at_draw_entry","input_and_observed_shelf_viewport_composition") and
         type(a["event_to_content_draw_entry_us"]) is int and a["event_to_content_draw_entry_us"]>=0 for a in actions),
         "all six shelf actions bound to native content")
    need(summary["draw_control"].get("shelf_content_control") is True and
         summary["draw_control"].get("clip_rejected") is True and summary["draw_control"].get("missing_id_rejected") is True,
         "native content control")
    need(summary["draw_control"].get("viewport_composition_control") is True and
         summary["draw_control"].get("viewport_pixels_equal") is True and
         summary["draw_control"].get("cached_list_draws")==0,"cached viewport native control")
    need(summary["settlement_controls"]==V.settlement_regressions(),"separate paint and completion controls")
    need(summary["F08_accepted"] is False and summary["physical_display_presented"] is False,"bounded claims")
    return {"shelf_actions":len(actions),"shelf_attributions":[a["causal_attribution"] for a in actions],"content_draw_entry_us":[a["event_to_content_draw_entry_us"] for a in actions],
            "content_frame_end_us":[a["event_to_content_frame_end_us"] for a in actions],
            "physical_presentation_proven":False,"frame_budget_measured":False,"f08_accepted":False}
def startup_coverage(root,top,ident=None):
    import configparser
    continued=0
    for row in top["cohorts"]:
        folder=root/("launch-%02d"%row["launch"])
        receipt=load(folder/"compact-resume.json")
        need(receipt["identity"]==(V.identity() if ident is None else ident),"startup receipt identity")
        settings=(folder/"startup-settings.ini").read_text()
        need(hashlib.sha256(settings.encode()).hexdigest()==receipt["settings_sha256"],"original startup settings")
        config=configparser.ConfigParser(interpolation=None);config.read_string(settings)
        need(config.getint("reader","book")==receipt["requested_book"],"requested native book")
        A.verify(receipt,row)
        want="shelf_unchanged" if row["kind"]=="shelf" else "continued"
        need(receipt["stage"]==want,"native startup route")
        continued+=receipt["stage"]=="continued"
    need(len(top["cohorts"])==6 and continued==4,"four Continue inputs and two unchanged Library entries")
    return {"continued":continued,"shelf_unchanged":2,"shared_startup_limit_seconds":600,
            "automatic_restore_measured":False}
def capture():
    guard();OUT.mkdir(parents=True,exist_ok=False)
    report={**identity(),"collection_complete":False,"problems":[],"f08_accepted":False}
    try:
        raw,pin=archive(PRODUCER,"f08-linux-product-"+PRODUCER["run_id"]+"-1",ROOT/"build/f08-shelf-product-input")
        built=product(raw);report["product"]=pin;report["program_sha256"]=built["program_sha256"]
        shutil.copytree(raw/"perf-package",ROOT/"build/perf-package")
        seed=ROOT/"build/perf-probe/seed_library";seed.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(raw/"perf-probe/seed_library",seed);seed.chmod(0o755)
        (ROOT/"build/perf-package/EXReader-Linux/bin/exreader-linux").chmod(0o755)
        A.install();D.main();V.verify()
        summary=load(ROOT/"build/f08-causal/summary.json")
        need(summary["host_sha256"]==built["program_sha256"],"same product after sampling")
        report.update(coverage(summary),collection_complete=True,
            startup=startup_coverage(ROOT/"build/f08-causal",load(ROOT/"build/f08-causal/driver.json")))
    except BaseException as error:
        report["problems"].append(repr(error));report["traceback"]=traceback.format_exc();raise
    finally:
        save(OUT/"result.json",report);seal()
        print("F08_SHELF_CONTENT",json.dumps(report),flush=True)
def seal():
    guard();OUT.mkdir(parents=True,exist_ok=True)
    for folder in ("f08-causal","f08-causal-control"):
        if (ROOT/"build"/folder).exists():
            shutil.copytree(ROOT/"build"/folder,OUT/folder,dirs_exist_ok=True)
    if not (OUT/"result.json").exists():
        save(OUT/"result.json",{**identity(),"collection_complete":False,
            "problems":["capture interrupted before final result"],"f08_accepted":False})
    save(OUT/"manifest.json",{**identity(),"f08_accepted":False,"files":{
        p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
        for p in sorted(OUT.rglob("*")) if p.is_file() and p!=OUT/"manifest.json"}})
def audit():
    guard();ident=identity()
    raw,pin=archive(ident,"f08-shelf-content-"+ident["run_id"]+"-"+ident["attempt"],
        ROOT/"build/f08-shelf-audit-input",int(os.environ["F08_ARTIFACT_ID"]))
    need(pin["sha256"]==os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:"),"same-run upload digest")
    saved=load(raw/"result.json");need(all(saved.get(k)==v for k,v in ident.items()),"capture identity")
    report={**ident,"artifact":pin,"authenticated":True,"collection_complete":False,"sample_problems":saved["problems"],"f08_accepted":False}
    if saved["collection_complete"] is True:
        original,original_pin=archive(PRODUCER,"f08-linux-product-"+PRODUCER["run_id"]+"-1",ROOT/"build/f08-shelf-audit-product")
        need(original_pin==saved["product"],"same original native ZIP")
        built=product(original);top=load(raw/"f08-causal/driver.json");summary=load(raw/"f08-causal/summary.json")
        need(sha(raw/"f08-causal/host.bin")==built["program_sha256"]==saved["program_sha256"]==top["host_sha256"],"exact unchanged product")
        need(sha(raw/"f08-causal/module.so")==top["module_sha256"],"observer bytes")
        vident=V.identity();V.verify_top(top,vident)
        need(summary["identity"]==vident and summary["controls"]==V.controls() and
             summary["regressions"]==V.regressions() and summary["content_controls"]==V.content_regressions() and
             summary["settlement_controls"]==V.settlement_regressions(),"independent controls")
        need(len(summary["results"])==6,"all analyzed launches")
        for row in top["cohorts"]:
            observations=load(raw/("f08-causal/launch-%02d/%d.json"%(row["launch"],row["pid"])))
            need(observations.get("shelf_content_version")==2,"native snapshot schema")
            result=V.analyze(observations,row,vident)
            previous=summary["results"][row["launch"]]
            need(all(previous[k]==row[k] for k in ("launch","pid","kind")),"result launch identity")
            need(all(previous[k]==v for k,v in result.items()),"raw content recomputation")
        checked=coverage(summary)
        checked["startup"]=startup_coverage(raw/"f08-causal",top)
        need(all(saved[k]==v for k,v in checked.items()),"coverage recomputation")
        report.update(checked,collection_complete=True,program_sha256=built["program_sha256"])
    dest=ROOT/"build/f08-shelf-content-audit";dest.mkdir()
    save(dest/"audit.json",report);print("F08_SHELF_CONTENT_AUDIT",json.dumps(report),flush=True)
def replay():
    # The producer completed all six native launches. Its wrong verifier import
    # failed before analysis; replay that immutable raw record without resampling.
    guard();dest=ROOT/"build/f08-shelf-replay"
    producer={"source_sha":"622a29b3bb4b0f4e8a579f870718f2935d9dbf9d","run_id":"41221687229","attempt":"1"}
    report={**identity(),"replay_complete":False,"problems":[],"f08_accepted":False}
    try:
        raw,pin=archive(producer,"f08-shelf-content-41221687229-1",dest,13049843291)
        need(pin["bytes"]==5073776 and pin["sha256"]=="30a403187a9aeb73af483f9867c3775f4d1909492ba0595d7b5653ea9c9f22b3","fixed native archive")
        report["producer_artifact"]=pin
        previous=load(raw/"result.json")
        need(previous["collection_complete"] is False,"preserve original analysis failure")
        report["original_problems"]=previous["problems"]
        original,original_pin=archive(PRODUCER,"f08-linux-product-"+PRODUCER["run_id"]+"-1",ROOT/"build/f08-replay-product-input")
        built=product(original);report["product"]=original_pin
        verifier="tests/reader_f08_causal_frame_20261031/verify.py"
        need(sha(ROOT/verifier)==hashlib.sha256(command(["git","show",producer["source_sha"]+":"+verifier])).hexdigest(),"same causal analysis code")
        ident=dict(GITHUB_SHA=producer["source_sha"],GITHUB_RUN_ID=producer["run_id"],GITHUB_RUN_ATTEMPT=producer["attempt"])
        top=load(raw/"f08-causal/driver.json");V.verify_top(top,ident)
        need(sha(raw/"f08-causal/host.bin")==built["program_sha256"]==previous["program_sha256"]==top["host_sha256"],"same full product binary")
        need(sha(raw/"f08-causal/module.so")==top["module_sha256"],"native observer bytes")
        control=load(raw/"f08-causal-control/draw.json")
        need(control.get("passed") is True and control.get("hook_only")==0 and control.get("with_handler")==1 and
             control.get("callbacks")==1 and control.get("pixels_equal") is True and control.get("nonempty") is True,"native draw control")
        results=[];diagnostics=[]
        for row in top["cohorts"]:
            observations=load(raw/("f08-causal/launch-%02d/%d.json"%(row["launch"],row["pid"])))
            need(observations.get("shelf_content_version")==1,"native shelf content schema")
            need(observations["executable"]==str((ROOT/"build/perf-package/EXReader-Linux/bin/exreader-linux").resolve()),"native executable path")
            try:analyzed=V.analyze(observations,row,ident)
            except V.Invalid as error:
                detail={key:row[key] for key in ("launch","pid","kind")}
                detail.update(error=str(error),draw_counts={str(kind):sum(d["kind"]==kind for d in observations["draws"]) for kind in (1,2)},actions=[])
                for action in row["actions"]:
                    item={key:action[key] for key in ("id","field","before","expected","book","previous_generation","previous_sequence","inject_start","inject_end","effect_at","done")}
                    try:V.analyze(observations,{**row,"actions":[action]},ident);item["passed"]=True
                    except V.Invalid as failure:item.update(passed=False,error=str(failure))
                    start,end=action["inject_start"],action["done"]+250000
                    # Extra 250 ms is diagnostic context only; V.analyze's strict window is unchanged.
                    item["context_end"]=end
                    for name in ("inputs","states","draws"):
                        rows=[value for value in observations[name] if start<=value["at"]<=end]
                        item[name+"_count"]=len(rows);item[name]=rows[:128]
                    frames=[value for value in observations["frames"] if value["before"]<=end and value["after"]>=start]
                    item["frame_count"]=len(frames);item["frames"]=frames[:128]
                    detail["actions"].append(item)
                diagnostics.append(detail)
                print("F08_CAUSAL_DIAGNOSTIC",json.dumps(detail),flush=True)
            else:results.append({**{key:row[key] for key in ("launch","pid","kind")},**analyzed})
        report["launch_failures"]=[{key:item[key] for key in ("launch","pid","kind","error","draw_counts")} for item in diagnostics]
        save(dest/"diagnostics.json",diagnostics)
        need(not diagnostics,"all six native causal joins")
        summary={"passed":True,"new_launches":6,"new_actions":18,"results":results,"draw_control":control,
                 "physical_display_presented":False,"F08_accepted":False}
        report.update(coverage(summary),replay_complete=True,program_sha256=built["program_sha256"],
            startup=startup_coverage(raw/"f08-causal",top,ident),
            controls={"original":V.controls(),"predicate":V.regressions(),"content":V.content_regressions()})
        save(dest/"analysis.json",summary)
    except BaseException as error:
        report["problems"].append(repr(error));report["traceback"]=traceback.format_exc();raise
    finally:
        dest.mkdir(parents=True,exist_ok=True);save(dest/"replay.json",report)
        print("F08_SHELF_CONTENT_REPLAY",json.dumps(report),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("guard","capture","audit","seal","replay"))
    globals()[parser.parse_args().mode]()
