"""Build and observe the full Windows host through unchanged native helpers and samplers."""
import argparse, hashlib, importlib.util, json, math, os, shutil, subprocess, sys, traceback
from pathlib import Path
if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8",errors="backslashreplace")
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity, need, save, sha, command
BASE="fb1197d607a2d3401488427f8bfdfcaea32568bd"
OUT=ROOT/"build/f08-windows-product";EVIDENCE=OUT/"evidence"
FILES={"tests/reader_f08_windows_product_20261031/native_picker.py",
       "tests/reader_f08_windows_product_20261031/build.py","tests/reader_f08_windows_product_20261031/audit.py",
       "tests/reader_f08_windows_product_20261031/profile.json",".github/workflows/dot-f08-windows-product-20261031.yml"}
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"checkout source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==FILES,"test-only scope")
def budgets(summary,profile):
    need(summary["complete"] is True and not summary["problems"],"incomplete original observations")
    agg=summary["aggregates"];rows=[]
    for cohort in ("cold_shelf","warm_shelf"):
        metric=agg[cohort]["first_screen_interactive_ms"]
        need(metric["n"]==12,"planned launch count")
        value=metric["max"];limit=profile["budgets"]["first_interactive_max_ms"]
        need(type(value) in (float,int) and math.isfinite(value) and value>0,"first interaction")
        rows.append({"metric":cohort+"_first_interactive_max_ms","observed":value,"maximum":limit,"passed":value<=limit})
    peaks=[v["peak_working_set_bytes"]["max"] for v in agg.values() if "peak_working_set_bytes" in v]
    need(peaks and all(type(v) in (float,int) and math.isfinite(v) and v>0 for v in peaks),"working set")
    value=max(peaks);limit=profile["budgets"]["peak_working_set_bytes"]
    rows.append({"metric":"peak_working_set_bytes","observed":value,"maximum":limit,"passed":value<=limit})
    return {"checks":rows,"non_frame_budget_passed":all(r["passed"] for r in rows),"frame_budget_measured":False,"f08_accepted":False}
def build():
    guard();need(sys.platform=="win32","Windows build")
    OUT.mkdir(parents=True,exist_ok=False);EVIDENCE.mkdir();(OUT/"logs").mkdir()
    spec=importlib.util.spec_from_file_location("unchanged_c09",ROOT/"tests/reader_wave3_c09/build.py")
    W=importlib.util.module_from_spec(spec);spec.loader.exec_module(W)
    H=W.H;H.OUT=OUT
    installed_hash=OUT/"hash"
    H.configure(ROOT/"extras/opds",OUT/"hash-build",["-DEXREADER_OPDS_HASH_ONLY=ON","-DCMAKE_INSTALL_PREFIX="+str(installed_hash)],"hash")
    H.run(["cmake","--install",OUT/"hash-build"],"hash-install")
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"]=installed_hash.resolve().as_posix()
    sdk,product,stage=OUT/"sdk-stage",OUT/"product-stage",OUT/"raw-stage"
    prefix=";".join(map(str,(stage,product,sdk,installed_hash)))
    H.run(["cmake","--preset","reading-library","-B",OUT/"sdk-build","-DCMAKE_INSTALL_PREFIX="+str(sdk)],"sdk-configure")
    H.run(["cmake","--build",OUT/"sdk-build","--parallel","4"],"sdk-build")
    H.run(["cmake","--install",OUT/"sdk-build"],"sdk-install")
    H.configure(ROOT/"apps/reader/store/native",OUT/"product-build",
        ["-DCMAKE_INSTALL_PREFIX="+str(product),"-DREADER_ORIGINAL_HASH_PREFIX="+installed_hash.resolve().as_posix()],"product")
    H.run(["cmake","--install",OUT/"product-build"],"product-install")
    raw=set(H.RAW_MODULES)|W.RAW_NEW
    for module in tuple(H.MODULES)+W.NEW_MODULES:
        label=Path(module).name
        options=["-DCMAKE_INSTALL_PREFIX="+str(stage),"-DCMAKE_PREFIX_PATH="+prefix,"-DEXR_SDK="+str(sdk),
                 "-DEXR_SDK_VERSION=3.42.0","-DREADER_PRODUCT_PREFIX="+str(product),*W.EXTRA_FLAGS.get(label,[])]
        if label=="cloud-import":options.append("-DREADER_CLOUD_BUILD_CONTENT_BOUND=ON")
        if label in raw:options.append("-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON")
        directory=OUT/("module-"+label);H.configure(ROOT/module,directory,options,"module-"+label)
        H.run(["cmake","--install",directory],"module-"+label+"-install")
    host=OUT/"host"
    H.run(["cmake","-S",ROOT/"apps/reader/desktop","-B",host,"-G","Ninja","-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_PREFIX_PATH="+prefix,"-DEXR_SDK="+str(sdk),"-DEXR_SDK_VERSION=3.42.0",
        "-DREADER_METADATA_PREFIX="+str(stage),"-DREADER_ACCOUNT_PREFIX="+str(stage),
        "-DEXR_READER_WINDOWS_WAVE3=ON","-DEXR_READER_WINDOWS_CLOUD_CONTENT_BOUND=ON",
        "-DEXR_READER_WINDOWS_TXT_PROGRESS=ON","-DEXR_READER_WINDOWS_SHELF_TESTS=ON"],"host-configure")
    H.run(["cmake","--build",host,"--target","EXReaderWave3","reader-windows-shelf-seed","--parallel","4","--verbose"],"host-build")
    H.run([sys.executable,"tools/build_windows_host.py","--sdk",sdk,"--binary",host/"EXReaderWave3.exe",
           "--output",OUT/"package","--static-reading"],"package")
    manifest=json.loads((OUT/"package/build.json").read_text())
    need(manifest["passed"] is True and manifest["sdk_version"]=="3.42.0" and
         manifest["source_sha"]==identity()["source_sha"] and manifest["selftest_checks"]>=26,"actual package")
    shutil.copytree(OUT/"package/EXReader",EVIDENCE/"program")
    shutil.copyfile(OUT/"package/EXReader-Windows.zip",EVIDENCE/"program.zip")
    for name in ("build.json","report.json","page.png","application.log"):
        shutil.copyfile(OUT/"package"/name,EVIDENCE/("package-"+name))
    shutil.copyfile(host/"reader-windows-shelf-seed.exe",EVIDENCE/"seed.exe")
    shutil.copyfile(host/"CMakeCache.txt",EVIDENCE/"host-CMakeCache.txt")
    shutil.copyfile(host/"windows-host.map",EVIDENCE/"windows-host.map")
    sources=["tests/reader_wave3_c09/check_ui.py","tests/reader_windows_preferences/check_ui.py",
        "tests/reader_wave3_c09/build.py","tests/reader_windows_raw3/host_build.py",
        "tests/reader_perf_windows/perf_windows.py","tests/reader_perf_windows/diagnose_txt_import.py",
        "tests/reader_perf_windows/verify_composition.py","tests/reader_product_performance_handoff/sample_windows_interactions.py"]
    save(EVIDENCE/"build-identity.json",{**identity(),"sdk_version":"3.42.0","program_sha256":sha(EVIDENCE/"program/EXReader.exe"),
        "seed_sha256":sha(EVIDENCE/"seed.exe"),"package_sha256":sha(EVIDENCE/"program.zip"),
        "unchanged_helpers":{p:sha(ROOT/p) for p in sources},
        "sdk_files":{p.relative_to(sdk).as_posix():sha(p) for p in sdk.rglob("*") if p.is_file()},
        "components":{p:command(["git","rev-parse","HEAD:"+p],text=True).strip() for p in ("src","include","apps/reader","examples","tools")},
        "features":{"wave3":True,"raw_selector":True,"cloud_content_bound":True,"txt_progress":True},"f08_accepted":False})
def sample():
    guard();need(sys.platform=="win32","Windows sampling")
    profile=json.loads((HERE/"profile.json").read_text())
    report={**identity(),"collection_complete":False,"steps":[],"problems":[],"f08_accepted":False}
    def run(label,args,timeout=3600):
        with (EVIDENCE/(label+".log")).open("wb") as log:
            result=subprocess.run(list(map(str,args)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        report["steps"].append({"name":label,"exit":result.returncode})
        if result.returncode:
            report["problems"].append(label)
            print("\n".join((EVIDENCE/(label+".log")).read_text(encoding="utf-8",errors="replace").splitlines()[-50:]),flush=True)
        print("F08_WINDOWS_PHASE",label,result.returncode,flush=True)
        return result.returncode
    try:
        need(run("desktop",[sys.executable,"tests/reader_wave3_c09/desktop.py","--output",EVIDENCE/"desktop.json"],120)==0,"desktop")
        need(json.loads((EVIDENCE/"desktop.json").read_text())["after"]==[profile["screen_width"],profile["screen_height"]],"fixed display")
        common=["--package",EVIDENCE/"program","--seed",EVIDENCE/"seed.exe"]
        adapter=HERE/"native_picker.py"
        run("txt-diagnosis",[sys.executable,adapter,"diagnosis",*common,
            "--output",EVIDENCE/"txt","--runs","3"],1800)
        run("original-main",[sys.executable,adapter,"main",*common,
            "--output",EVIDENCE/"observations","--work",OUT/"observation-work",
            "--cohorts","cold_shelf,warm_shelf,reading,import,import_epub","--launches-per-cohort","12",
            "--txt-diagnostic",EVIDENCE/"txt/diagnosis.json"],3600)
        original_verify=run("original-verifier",[sys.executable,"tests/reader_perf_windows/verify_composition.py",
            "--summary",EVIDENCE/"observations/summary.json","--package",EVIDENCE/"program",
            "--start",identity()["source_sha"],"--launches","30","--per-cohort","10"],180)
        report["original_verify_passed"]=original_verify==0
        run("original-interactions",[sys.executable,adapter,"interactions",
            *common,"--output",EVIDENCE/"interactions","--work",OUT/"interaction-work",
            "--cohorts","warm_shelf,reading","--launches-per-cohort","5"],1800)
        report["collection_complete"]=not report["problems"]
        if report["collection_complete"]:
            report["budget_evaluation"]=budgets(json.loads((EVIDENCE/"observations/summary.json").read_text()),profile)
        need(report["collection_complete"],"original observation incomplete")
        need(report["budget_evaluation"]["non_frame_budget_passed"],"non-frame budget exceeded")
    except BaseException as error:
        report["problems"].append(repr(error));report["traceback"]=traceback.format_exc();raise
    finally:
        save(EVIDENCE/"sample-result.json",report)
        print("F08_WINDOWS_PRODUCT",json.dumps(report),flush=True)
def seal():
    guard();EVIDENCE.mkdir(parents=True,exist_ok=True)
    if (OUT/"logs").exists():shutil.copytree(OUT/"logs",EVIDENCE/"build-logs",dirs_exist_ok=True)
    shutil.copyfile(HERE/"profile.json",EVIDENCE/"profile.json")
    save(EVIDENCE/"manifest.json",{**identity(),"f08_accepted":False,
        "files":{p.relative_to(EVIDENCE).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
                 for p in sorted(EVIDENCE.rglob("*")) if p.is_file() and p!=EVIDENCE/"manifest.json"}})
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("build","sample","seal"))
    globals()[parser.parse_args().mode]()
