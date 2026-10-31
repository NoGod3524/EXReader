"""Actions-only sampling, predeclared budgets and authenticated same-run ZIP audit."""
import argparse, hashlib, importlib.util, io, json, math, os, shutil, stat, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/"build/f08-android"
BASE="22b207d142bf11de35aa5ffd0c64d7935ea3e6a9"
ALLOWED={"tests/reader_f08_android_20261031/build.py","tests/reader_f08_android_20261031/lane.py",
         "tests/reader_f08_android_20261031/profile.json",".github/workflows/dot-f08-android-20261031.yml"}
def need(value,message):
    if not value:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8")
def identity():
    return {"source_sha":os.environ["GITHUB_SHA"],"run_id":os.environ["GITHUB_RUN_ID"],"attempt":os.environ["GITHUB_RUN_ATTEMPT"]}
def command(args,**kwargs):
    return subprocess.check_output(list(map(str,args)),cwd=ROOT,**kwargs)
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"checkout differs")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    changed=command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines()
    need(set(changed)==ALLOWED,"scope differs: "+str(changed))
    OUT.mkdir(parents=True,exist_ok=True)
    save(OUT/"source.json",{**identity(),"base_sha":BASE,"changed":changed})
def load_sampler():
    spec=importlib.util.spec_from_file_location("frozen_shelf_sampler",ROOT/"tools/run_reader_shelf_ui.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
def evaluate(result,profile):
    need(result.get("accepted") is True and not result.get("problems"),"measurement incomplete")
    need(result.get("ui_passed")==10 and result.get("ui_failed")==0 and result.get("ui_skipped")==0,"UI cases")
    need(result.get("real_sdk_sources")==2202 and result.get("callback_drops")==0,"corpus/callback coverage")
    frames=result["completed_window_frame_ms"];memory=result["total_pss_kib"]
    need(frames["count"]>=100 and memory["samples"]>=10,"insufficient measurement")
    observed={"ordinary_window_frame_p95_ms":frames["p95"],"ordinary_window_frame_p99_ms":frames["p99"],
              "first_interactive_ms":result["first_interactive_ms"],"sampled_peak_pss_kib":memory["sampled_peak"]}
    rows=[]
    for name,limit in profile["budgets"].items():
        value=observed[name]
        need(type(value) in (float,int) and math.isfinite(value) and value>0,"invalid metric "+name)
        rows.append({"metric":name,"observed":value,"maximum":limit,"passed":value<=limit})
    segments=result["scroll_segments"]
    need([x["name"] for x in segments]==["forward_scroll","reverse_scroll"],"scroll intervals")
    for segment in segments:
        need(segment["completed_frame_ms"]["count"]>=50,"insufficient scroll frames")
        for percentile in ("p95","p99"):
            value=segment["completed_frame_ms"][percentile]
            need(type(value) in (int,float) and math.isfinite(value) and value>0,"invalid scroll metric")
            limit=profile["budgets"]["ordinary_window_frame_"+percentile+"_ms"]
            rows.append({"metric":segment["name"]+"_"+percentile+"_ms","observed":value,"maximum":limit,"passed":value<=limit})
    return {"checks":rows,"shelf_budget_accepted":all(x["passed"] for x in rows),"f08_accepted":False}
def controls():
    import copy
    profile=json.loads((HERE/"profile.json").read_text())
    good={"accepted":True,"problems":[],"ui_passed":10,"ui_failed":0,"ui_skipped":0,"real_sdk_sources":2202,
          "callback_drops":0,"completed_window_frame_ms":{"count":100,"p95":16.67,"p99":33.34},
          "first_interactive_ms":2000,"total_pss_kib":{"samples":10,"sampled_peak":524288},
          "scroll_segments":[{"name":name,"completed_frame_ms":{"count":50,"p95":16.67,"p99":33.34}}
                             for name in ("forward_scroll","reverse_scroll")]}
    need(evaluate(good,profile)["shelf_budget_accepted"],"inclusive budget control")
    bad=copy.deepcopy(good);bad["completed_window_frame_ms"]["p95"]=16.68
    need(not evaluate(bad,profile)["shelf_budget_accepted"],"over-budget control")
    mutations=[lambda x:x.update(accepted=False),lambda x:x.update(callback_drops=1),
        lambda x:x["completed_window_frame_ms"].update(count=0),
        lambda x:x["completed_window_frame_ms"].update(p99=float("nan")),
        lambda x:x["total_pss_kib"].update(samples=9),lambda x:x.update(first_interactive_ms=True),
        lambda x:x.update(real_sdk_sources=2201),lambda x:x.update(ui_skipped=1),lambda x:x.update(scroll_segments=[])]
    for mutate in mutations:
        value=copy.deepcopy(good);mutate(value)
        try:evaluate(value,profile)
        except ValueError:continue
        raise ValueError("negative coverage control accepted")
    return {"positive":1,"over_budget":1,"invalid":len(mutations)}
def sample():
    guard()
    profile=json.loads((HERE/"profile.json").read_text());save(OUT/"profile.json",profile)
    save(OUT/"controls.json",controls())
    env=OUT/"environment";env.mkdir()
    def adb(*args):return command(["adb",*map(str,args)],text=True)
    for key in ("window_animation_scale","transition_animation_scale","animator_duration_scale"):
        adb("shell","settings","put","global",key,str(profile["animation_scale"]))
        need(float(adb("shell","settings","get","global",key).strip())==profile["animation_scale"],"animation profile")
    need(adb("shell","getprop","ro.build.version.sdk").strip()==str(profile["api"]),"API profile")
    need(adb("shell","getprop","ro.product.cpu.abi").strip()==profile["abi"],"ABI profile")
    for name,args in {"getprop":["getprop"],"display":["dumpsys","display"],"size":["wm","size"],
                      "density":["wm","density"],"global-settings":["settings","list","global"]}.items():
        (env/(name+".txt")).write_text(adb("shell",*args))
    save(env/"runner.json",{k:os.environ.get(k) for k in
        ("RUNNER_OS","RUNNER_ARCH","RUNNER_NAME","ImageOS","ImageVersion","C11_NDK")})
    (env/"cpu.txt").write_bytes(command(["lscpu"]))
    (env/"emulator.txt").write_bytes(command(["emulator","-version"],stderr=subprocess.STDOUT))
    run=subprocess.run([sys.executable,"tools/run_reader_shelf_ui.py","--output",str(OUT/"execution")],cwd=ROOT)
    installed=OUT/"installed";installed.mkdir()
    try:
        paths=[line.removeprefix("package:") for line in adb("shell","pm","path","org.exreader.host").splitlines() if line.startswith("package:")]
        need(len(paths)==1,"installed APK path")
        command(["adb","pull",paths[0],installed/"app-debug.apk"],stderr=subprocess.STDOUT)
        need(sha(installed/"app-debug.apk")==sha(OUT/"packages/app-debug.apk"),"installed host bytes differ")
        save(installed/"identity.json",{**identity(),"sha256":sha(installed/"app-debug.apk"),"package_path":paths[0]})
        original=json.loads((OUT/"execution/result.json").read_text())
        result={**identity(),"profile_sha256":sha(HERE/"profile.json"),**evaluate(original,profile)}
        save(OUT/"evaluation.json",result)
        print("F08_ANDROID_EVALUATION",json.dumps(result),flush=True)
    except Exception as error:
        save(OUT/"evaluation.json",{**identity(),"shelf_budget_accepted":False,"f08_accepted":False,"problem":str(error)})
        raise
    need(run.returncode==0,"original sampler failed")
    need(result["shelf_budget_accepted"],"predeclared shelf budget exceeded")
def seal():
    guard()
    logs=ROOT/"build/wave3/logs"
    if logs.exists():shutil.copytree(logs,OUT/"build-logs",dirs_exist_ok=True)
    save(OUT/"profile.json",json.loads((HERE/"profile.json").read_text()))
    files={p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
           for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="manifest.json"}
    save(OUT/"manifest.json",{**identity(),"files":files,"f08_accepted":False})
def audit():
    guard();controls()
    target=ROOT/"build/f08-android-audit";target.mkdir(parents=True,exist_ok=False)
    api=lambda path:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+path]))
    artifact=int(os.environ["F08_ARTIFACT_ID"]);meta=api("actions/artifacts/"+str(artifact))
    save(target/"metadata.json",meta)
    ident=identity()
    need(meta["id"]==artifact and meta["name"]=="f08-android-"+ident["run_id"]+"-"+ident["attempt"] and not meta["expired"],"artifact identity")
    need(str(meta["workflow_run"]["id"])==ident["run_id"] and meta["workflow_run"]["head_sha"]==ident["source_sha"],"producer source/run")
    run=api("actions/runs/"+ident["run_id"])
    need(run["head_sha"]==ident["source_sha"] and str(run["run_attempt"])==ident["attempt"],"producer attempt")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(artifact)+"/zip"])
    digest=hashlib.sha256(data).hexdigest()
    need(meta["size_in_bytes"]==len(data) and meta["digest"]=="sha256:"+digest
         and os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest,"ZIP bytes/digest")
    (target/"original.zip").write_bytes(data)
    raw=target/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos=archive.infolist()
        need(0<len(infos)<20000 and sum(i.file_size for i in infos)<2*1024**3,"ZIP bounds")
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
    need(all(manifest.get(k)==v for k,v in ident.items()) and manifest["f08_accepted"] is False,"manifest identity")
    files={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    need(files==set(manifest["files"])|{"manifest.json"},"complete inventory")
    for name,entry in manifest["files"].items():
        need(sha(raw/name)==entry["sha256"] and (raw/name).stat().st_size==entry["bytes"],"payload differs: "+name)
    need((raw/"profile.json").read_bytes()==(HERE/"profile.json").read_bytes(),"profile changed")
    report={**ident,"artifact_id":artifact,"bytes":len(data),"sha256":digest,"files":len(files),
            "authenticated":True,"observation_complete":False,"shelf_budget_accepted":False,"f08_accepted":False}
    if (raw/"build.json").exists():
        build=json.loads((raw/"build.json").read_text())
        need(all(build.get(k)==v for k,v in ident.items()) and build["sdk_version"]=="3.42.0","build identity")
        for name,entry in build["packages"].items():need(sha(raw/"packages"/name)==entry["sha256"],"APK hash")
        for path,digest in build["frozen_sampler_files"].items():need(sha(ROOT/path)==digest,"original sampler modified")
    if (raw/"execution/result.json").exists():
        result=json.loads((raw/"execution/result.json").read_text())
        need(all(result.get(k)==v for k,v in ident.items()),"sample identity")
        report["sampler_problems"]=result.get("problems")
        if result.get("accepted") is True:
            recomputed=load_sampler().analyze(raw/"execution",ident)
            need(all(result.get(k)==v for k,v in recomputed.items()),"raw analysis differs")
            need(sha(raw/"installed/app-debug.apk")==sha(raw/"packages/app-debug.apk"),"installed payload differs")
            evaluation=evaluate(result,json.loads((HERE/"profile.json").read_text()))
            recorded=json.loads((raw/"evaluation.json").read_text())
            need(all(recorded.get(k)==v for k,v in evaluation.items()),"budget evaluation differs")
            report.update(evaluation,observation_complete=True)
    save(target/"audit.json",report)
    print("F08_ANDROID_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":
    action=argparse.ArgumentParser();action.add_argument("mode",choices=("guard","sample","seal","audit","controls"))
    mode=action.parse_args().mode
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    if mode=="controls":print(json.dumps(controls()))
    else:globals()[mode]()
