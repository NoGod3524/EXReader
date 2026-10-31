"""Build the full GTK product and run frozen samplers in Actions."""
import argparse, importlib.util, json, math, os, re, shutil, signal, subprocess, sys, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity, need, save, sha, command
BASE="a2d3bdd6f7258b6c27188093b253dcad3038c6ca"
OUT=ROOT/"build/f08-linux-product";EVIDENCE=OUT/"evidence"
FILES={"tests/reader_f08_linux_product_20261031/run.py",
       ".github/workflows/dot-f08-linux-product-20261031.yml"}
ADAPTERS=("tests/reader_f08_compact_resume_20261031/adapter.py","tests/reader_f08_compact_resume_20261031/controls.py")
COHORTS=("perf-evidence","perf-interactions")
TREES=(*COHORTS,"perf-package","perf-guards","f08-result","f08-causal","f08-causal-control")
PROBES=("perf-probe/seed_library","f08-probe/libexreader_f08.so","f08-causal-probe/libexreader_f08_causal.so")
FROZEN=("tests/reader_gtk_raw_wave3/run.py","tools/build_linux_host.py","tests/reader_perf_gtk/sample.py",
        "tests/reader_perf_gtk/observe.py","tests/reader_perf_gtk/composition/summarize.py",
        "tests/reader_product_performance_handoff/sample_gtk_interactions.py",
        "tests/reader_f08_gtk_frameclock_20261031/verify.py","tests/reader_f08_gtk_frameclock_20261031/probe.c",
        "tests/reader_f08_causal_frame_20261031/driver.py","tests/reader_f08_causal_frame_20261031/verify.py",
        "tests/reader_f08_causal_frame_20261031/probe.c")
OPTIONS=("EXR_READER_BUILD_GTK","EXR_READER_GTK_COMPACT","EXR_READER_PAGE_BACKGROUND",
         "EXR_READER_GTK_ACCOUNT","EXR_READER_GTK_READING_RECORDS","EXR_READER_GTK_SEARCH",
         "EXR_READER_GTK_NAVIGATION","EXR_READER_GTK_WAVE3","EXR_READER_GTK_RAW3",
         "EXR_READER_GTK_PREFERENCES","EXR_READER_GTK_BATCH_IMPORT","EXR_READER_GTK_DROP_IMPORT")
DEFINES=("EXR_READER_GTK_COMPACT","EXR_READER_PAGE_BACKGROUND","EXR_READER_PRODUCT_CATALOG",
         "EXR_READER_DESKTOP_METADATA","EXR_READER_ACCOUNT","EXR_READER_READING_RECORDS_UI",
         "EXR_READER_SEARCH_UI","EXR_READER_NAVIGATION_UI","EXR_READER_WAVE3_UI","EXR_READER_GTK_RAW3",
         "EXR_READER_PREFERENCES_UI","EXR_READER_BATCH_IMPORT_UI","EXR_READER_DROP_IMPORT_UI")
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform.startswith("linux"),"Linux Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"checkout identity")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==FILES,"test-only changes")
def load(path):return json.loads(Path(path).read_text())
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def compiled_features(cache,commands):
    values=dict(re.findall(r"^([^/#\n:]+):[^=\n]+=([^\n]*)$",cache,re.M))
    need(values.get("CMAKE_BUILD_TYPE")=="Release","release host")
    need(all(values.get(k)=="ON" for k in OPTIONS),"complete host options")
    rows=[x for x in commands if x["file"].replace("\\","/").endswith("/examples/linux/reader.c")]
    need(len(rows)==1,"actual product translation unit")
    flags=rows[0]["command"].split()
    need(all("-D"+d+"=1" in flags for d in DEFINES),"actual full-feature compiler flags")
    return {k:values[k] for k in OPTIONS}
def build():
    guard();OUT.mkdir(parents=True,exist_ok=False);EVIDENCE.mkdir()
    R=module("full_gtk_helpers","tests/reader_gtk_raw_wave3/run.py");R.OUT=OUT/"logs"
    sdk=ROOT/"build/reading-library/stage";prefix=OUT/"raw-stage";hashed=OUT/"hash-stage"
    def cmake(label,source,binary,extra=(),install=False,targets=()):
        options=["-DCMAKE_PREFIX_PATH="+str(prefix)+";"+str(sdk)+";"+str(hashed),
            "-DCMAKE_INSTALL_PREFIX="+str(prefix),"-DREADER_PRODUCT_PREFIX="+str(prefix),
            "-DEXR_SDK="+str(sdk),"-DEXR_SDK_VERSION=3.42.0",
            "-DREADER_ORIGINAL_HASH_PREFIX="+str(hashed)]
        R.run(label+"-configure",["cmake","-S",source,"-B",binary,"-G","Ninja","-DCMAKE_BUILD_TYPE=Release",*options,*extra])
        R.run(label+"-build",["cmake","--build",binary,"--parallel","4",*(["--target",*targets] if targets else [])])
        if install:R.run(label+"-install",["cmake","--install",binary])
    cmake("hash",ROOT/"extras/opds",OUT/"hash-build",
          ["-DEXREADER_OPDS_HASH_ONLY=ON","-DCMAKE_INSTALL_PREFIX="+str(hashed)],True)
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"]=str(hashed.resolve())
    R.run("sdk-configure",["cmake","--preset","reading-library"])
    R.run("sdk-build",["cmake","--build","--preset","reading-library","--parallel","4"])
    R.run("sdk-install",["cmake","--install","build/reading-library"])
    modules=R.COMMON+R.HOST_MODULES+[("preferences","apps/reader/preferences"),
        ("batch-import","apps/reader/batch-import"),("desktop-drop","extras/desktop-drop")]
    for name,source in modules:
        extra=[]
        if name in R.RAW_MODULES:extra.append("-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON")
        if name=="reading-state":extra.append("-DEXR_READER_PURE_CAPTURE_CANDIDATE=ON")
        if name=="font-library":extra.append("-DREADER_FONT_LIBRARY_BUILD=ON")
        if name=="annotation-import":extra.append("-DREADER_ANNOTATION_IMPORT_BUILD=ON")
        cmake("module-"+name,ROOT/source,OUT/("module-"+name),extra,True)
    host=OUT/"host"
    prefixes=("READER_METADATA_PREFIX","READER_ACCOUNT_PREFIX","READER_READING_RECORDS_PREFIX",
        "READER_SEARCH_PREFIX","READER_NAVIGATION_PREFIX","READER_WAVE3_PREFIX","READER_GTK_RAW3_PREFIX",
        "READER_PREFERENCES_PREFIX","READER_BATCH_IMPORT_PREFIX","READER_DESKTOP_DROP_PREFIX")
    cmake("host",ROOT/"apps/reader/desktop",host,
        ["-D"+k+"=ON" for k in OPTIONS]+["-D"+k+"="+str(prefix) for k in prefixes]+
        ["-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"],targets=("exreader-linux",))
    cmake("corpus",ROOT/"tests/reader_product_performance_handoff/gtk_probe",ROOT/"build/perf-probe")
    cmake("frameclock",ROOT/"tests/reader_f08_gtk_frameclock_20261031",ROOT/"build/f08-probe")
    cmake("causal",ROOT/"tests/reader_f08_causal_frame_20261031",ROOT/"build/f08-causal-probe")
    R.run("package",[sys.executable,"tools/build_linux_host.py","--sdk",sdk,"--sdk-version","3.42.0",
        "--binary",host/"gtk-host/exreader-linux","--output",ROOT/"build/perf-package"])
    package=load(ROOT/"build/perf-package/build.json")
    need(package["source_sha"]==identity()["source_sha"] and package["sdk_version"]=="3.42.0" and package["abi"]==1,"package")
    compiled=compiled_features((host/"CMakeCache.txt").read_text(),load(host/"compile_commands.json"))
    for name in ("CMakeCache.txt","compile_commands.json"):
        shutil.copyfile(host/name,EVIDENCE/("host-"+name))
    trees={p:command(["git","rev-parse","HEAD:"+p],text=True).strip() for p in ("src","include","apps/reader","examples","tools")}
    save(ROOT/"build/perf-guards/guards.json",{"head":identity()["source_sha"],"github_sha":identity()["source_sha"],"components":trees})
    save(EVIDENCE/"build-identity.json",{**identity(),"sdk_version":"3.42.0","compiled_options":compiled,
        "program_sha256":sha(ROOT/"build/perf-package/EXReader-Linux/bin/exreader-linux"),
        "helpers":{p:sha(ROOT/p) for p in FROZEN},"components":trees,
        "test_adapters":{p:sha(ROOT/p) for p in ADAPTERS},
        "installed_family":{p.relative_to(prefix).as_posix():sha(p) for p in prefix.rglob("*") if p.is_file()},
        "probes":{p:sha(ROOT/"build"/p) for p in PROBES},"f08_accepted":False})
def verify_commands():
    return [
        ("original-summary",[sys.executable,"tests/reader_perf_gtk/composition/summarize.py",
             "--output","build/perf-evidence","--guards","build/perf-guards/guards.json"]),
        ("frameclock-verify",[sys.executable,"tests/reader_f08_gtk_frameclock_20261031/verify.py"]),
        ("causal-verify",[sys.executable,"tests/reader_f08_causal_frame_20261031/verify.py","verify"])]
def startup_coverage(raw,records):
    import configparser
    sys.path.insert(0,str(ROOT/"tests/reader_f08_compact_resume_20261031"))
    import adapter as A
    wanted={k:os.environ[k] for k in ("GITHUB_SHA","GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT")}
    cohorts=[(name,rows) for name,rows in records.items()]
    cohorts.append(("f08-causal",load(raw/"f08-causal/driver.json")["cohorts"]))
    counts={};legacy=[]
    for name,rows in cohorts:
        continued=0
        for row in rows:
            folder=raw/name/("launch-%02d"%row["launch"]) if name=="f08-causal" else raw/name/"raw"/("launch-%02d"%row["launch"])
            receipt=load(folder/"compact-resume.json")
            need(receipt["identity"]==wanted and receipt["pid"]==row["pid"],"native startup identity")
            settings=(folder/"startup-settings.ini").read_text()
            need(sha(folder/"startup-settings.ini")==receipt["settings_sha256"],"native startup settings bytes")
            config=configparser.ConfigParser(interpolation=None);config.read_string(settings)
            need(config.getint("reader","book")==receipt["requested_book"],"native startup requested book")
            A.verify(receipt,row if name=="f08-causal" else None)
            reading=row["kind"] in ("resume_turn","reader_interact","page","font")
            need(receipt["stage"]==("continued" if reading else "shelf_unchanged"),"declared startup route")
            if name=="perf-evidence":need(row["entry_book"]==receipt["requested_book"],"original main entry book")
            if name=="perf-interactions" and row["entry_book"]!=receipt["requested_book"]:
                legacy.append({"cohort":name,"launch":row["launch"],"kind":row["kind"],
                               "original_entry_book":row["entry_book"],"actual_settings_book":receipt["requested_book"]})
            continued+=reading
        counts[name]={"continued":continued,"shelf_unchanged":len(rows)-continued}
    need(counts=={"perf-evidence":{"continued":8,"shelf_unchanged":24},
                  "perf-interactions":{"continued":6,"shelf_unchanged":6},
                  "f08-causal":{"continued":4,"shelf_unchanged":2}},"all 50 native startup routes")
    need(len(legacy)==6 and all(x["kind"]=="reader_interact" and x["original_entry_book"]==0 for x in legacy),
         "unchanged interaction sampler's inherited entry labels")
    return {"cohorts":counts,"shared_startup_limit_seconds":600,"automatic_restore_measured":False,
            "legacy_entry_metadata_mismatches":legacy,
            "resume_latency_includes_native_continue_preparation":True}
def evaluate(raw,profile):
    records={name:load(raw/name/"launches.json")["launches"] for name in COHORTS}
    need([len(records[k]) for k in COHORTS]==[32,12],"all original launches")
    startup=startup_coverage(raw,records)
    original=load(raw/"perf-evidence/report.json")
    need(original["accepted"] is True and not original["problems"],"original coverage")
    interaction=load(raw/"perf-interactions/interaction-summary.json")
    need(interaction["launches"]==12 and not interaction["problems"],"interaction coverage")
    peaks=[r["vm_hwm_kb"]*1024 for rows in records.values() for r in rows]
    need(all(type(v) is int and v>0 for v in peaks),"all native RSS peaks")
    samples=load(raw/"perf-evidence/samples.json")["samples"]
    readiness=[s for s in samples if s["metric"]=="shelf_selection_move"]
    need(len(readiness)==original["metrics"]["shelf_selection_move"]["expected"]>0,"all first selection responses")
    by_launch={r["launch"]:r for r in records["perf-evidence"]}
    for s in readiness:
        need(s["outcome"]=="ok" and all(type(s[k]) in (int,float) and math.isfinite(s[k]) for k in ("start_ms","end_ms"))
             and 0<=s["start_ms"]<=s["end_ms"],"native first selection response")
    checks=[{"metric":"peak_rss_bytes","launches":len(peaks),"observed":max(peaks),
             "maximum":profile["budgets"]["peak_rss_bytes"],"passed":max(peaks)<=profile["budgets"]["peak_rss_bytes"]}]
    for cache in ("cold","warm"):
        values=[s["end_ms"] for s in readiness if by_launch[s["launch"]]["cache"]["effective"]==cache]
        need(values and all(v>0 for v in values),"fixed cache cohort first selection response")
        limit=profile["budgets"]["first_verified_selection_response_max_ms"]
        checks.append({"metric":cache+"_first_verified_selection_response_max_ms","launches":len(values),
                       "observed":max(values),"maximum":limit,"passed":max(values)<=limit})
    frames=load(raw/"f08-result/summary.json")
    need(frames["evidence_complete"] is True and len(frames["launches"])==44,"native frame coverage")
    causal=load(raw/"f08-causal/summary.json")
    need(causal["passed"] is True and causal["new_launches"]==6 and causal["new_actions"]==18,"causal coverage")
    shelf=[action for row in causal["results"] if row["kind"]=="shelf" for action in row["actions"]]
    need(len(shelf)==6 and all(action["causal_attribution"] in ("input_and_observed_shelf_content_at_draw_entry","input_and_observed_shelf_viewport_composition") and
         type(action["event_to_content_draw_entry_us"]) is int and action["event_to_content_draw_entry_us"]>=0
         for action in shelf),"six native shelf content bindings")
    need(causal["draw_control"].get("viewport_composition_control") is True and
         causal["draw_control"].get("viewport_pixels_equal") is True and
         causal["draw_control"].get("cached_list_draws")==0,"native cached composition control")
    return {"startup":startup,"checks":checks,"non_frame_budget_passed":all(c["passed"] for c in checks),
        "native_frame_records":sum(r["frames"] for r in frames["launches"]),
        "native_frame_incomplete":sum(r["incomplete"] for r in frames["launches"]),
        "causal_launches":6,"causal_actions":18,"shelf_content_actions":6,
        "shelf_attributions":[action["causal_attribution"] for action in shelf],
        "shelf_content_draw_entry_us":[action["event_to_content_draw_entry_us"] for action in shelf],
        "frame_budget_measured":False,
        "physical_presentation_proven":False,"f08_accepted":False}
def sample():
    guard();profile=load(HERE/"profile.json")
    report={**identity(),"collection_complete":False,"steps":[],"problems":[],"f08_accepted":False}
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    def execute(label,args,timeout=3600):
        try:
            with (EVIDENCE/(label+".log")).open("wb") as log:
                p=subprocess.Popen(list(map(str,args)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:code=p.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    code=124
                    try:os.killpg(p.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(p.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        p.wait(timeout=5)
                finally:
                    if p.poll() is None:
                        try:os.killpg(p.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        p.wait(timeout=5)
        except subprocess.TimeoutExpired:code=124
        report["steps"].append({"name":label,"exit":code})
        if code:report["problems"].append(label)
        print("F08_LINUX_PHASE",label,code,flush=True)
        if code:print("\n".join((EVIDENCE/(label+".log")).read_text(errors="replace").splitlines()[-40:]),flush=True)
        return code
    try:
        execute("causal-predicates",[sys.executable,"tests/reader_f08_causal_frame_20261031/verify.py","preflight"],180)
        code=execute("draw-control",[ROOT/"build/f08-causal-probe/f08_draw_control"],30)
        if code==0:save(ROOT/"build/f08-causal-control/draw.json",load(EVIDENCE/"draw-control.log"))
        common=["--payload","build/perf-package/EXReader-Linux","--tarball",ROOT/"build/perf-package/EXReader-Linux.tar.gz",
                "--seed","build/perf-probe/seed_library"]
        execute("original-main",[sys.executable,ROOT/ADAPTERS[0],"tests/reader_f08_gtk_frameclock_20261031/verify.py","run",
            "tests/reader_perf_gtk/sample.py",*common,"--output","build/perf-evidence","--launches","32"],3600)
        execute("original-interactions",[sys.executable,ROOT/ADAPTERS[0],"tests/reader_f08_gtk_frameclock_20261031/verify.py","run",
            "tests/reader_product_performance_handoff/sample_gtk_interactions.py",*common,
            "--output","build/perf-interactions","--launches","12"],1800)
        execute("causal",[sys.executable,ROOT/ADAPTERS[0],"tests/reader_f08_causal_frame_20261031/driver.py"],900)
        for label,args in verify_commands():execute(label,args,180)
        report["collection_complete"]=not report["problems"]
        need(report["collection_complete"],"original observations incomplete")
        report["evaluation"]=evaluate(ROOT/"build",profile)
        need(report["evaluation"]["non_frame_budget_passed"],"predeclared non-frame budget exceeded")
    except BaseException as error:
        report["problems"].append(repr(error));report["traceback"]=traceback.format_exc();raise
    finally:
        save(EVIDENCE/"sample-result.json",report);print("F08_LINUX_PRODUCT",json.dumps(report),flush=True)
def seal():
    guard();EVIDENCE.mkdir(parents=True,exist_ok=True)
    for name in TREES:
        path=ROOT/"build"/name
        if path.exists():shutil.copytree(path,EVIDENCE/name,dirs_exist_ok=True)
    for name in PROBES:
        path=ROOT/"build"/name
        if path.is_file():
            dest=EVIDENCE/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    if (OUT/"logs").exists():shutil.copytree(OUT/"logs",EVIDENCE/"build-logs",dirs_exist_ok=True)
    shutil.copyfile(HERE/"profile.json",EVIDENCE/"profile.json")
    save(EVIDENCE/"manifest.json",{**identity(),"f08_accepted":False,"files":{
        p.relative_to(EVIDENCE).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
        for p in sorted(EVIDENCE.rglob("*")) if p.is_file() and p!=EVIDENCE/"manifest.json"}})
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=("build","sample","seal"));globals()[p.parse_args().mode]()
