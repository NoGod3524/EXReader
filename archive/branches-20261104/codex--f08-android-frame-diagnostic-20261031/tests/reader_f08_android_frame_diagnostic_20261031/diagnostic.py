"""Bounded same-run Release ABBA diagnostic and independent authenticated audit."""
import argparse,hashlib,importlib.util,io,json,os,re,shutil,stat,subprocess,sys,time,urllib.request,zipfile
from pathlib import Path,PurePosixPath
from analyze import replay,parse_trace
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;OUT=ROOT/"build/f08-android"
BASE="03ecfa21f6cd8d8e354145d56ffdf24244ecbe61"
PREFIX="tests/reader_f08_android_frame_diagnostic_20261031/"
ALLOWED={".github/workflows/f08-android-frame-diagnostic-20261031.yml",
    "examples/android/app/src/main/java/org/exreader/host/ShelfWindowMetrics.java",
    "docs/reader-total-progress/F08_ANDROID_FRAME_DIAGNOSTIC_20261031.md",
    *(PREFIX+p for p in ("AndroidManifest.xml","diagnostic.init.gradle","trace.pftxt","java/org/exreader/host/FrameLayerTest.java","build.py","analyze.py","diagnostic.py"))}
APP="org.exreader.host";REMOTE="/sdcard/Android/data/"+APP+"/files/f08-frame-layer"
def need(value,message):
    if not value:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")
def identity():return {"source_sha":os.environ["GITHUB_SHA"],"run_id":os.environ["GITHUB_RUN_ID"],"attempt":os.environ["GITHUB_RUN_ATTEMPT"]}
def command(args,**kw):return subprocess.check_output(list(map(str,args)),cwd=ROOT,**kw)
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"checkout identity")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    changed=command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines();need(set(changed)==ALLOWED,"scope differs: "+str(changed))
    path="examples/android/app/src/main/java/org/exreader/host/ShelfWindowMetrics.java"
    original=command(["git","show",BASE+":"+path],text=True)
    needle='                        .put("input_ns",copy.getMetric(FrameMetrics.INPUT_HANDLING_DURATION))'
    additions=''.join('                        .put("'+name+'",copy.getMetric(FrameMetrics.'+metric+'))\n' for name,metric in
        (("unknown_ns","UNKNOWN_DELAY_DURATION"),("animation_ns","ANIMATION_DURATION"),("command_issue_ns","COMMAND_ISSUE_DURATION"),("swap_buffers_ns","SWAP_BUFFERS_DURATION")))
    need(original.count(needle)==1 and (ROOT/path).read_text()==original.replace(needle,additions+needle),"only four read-only metrics fields allowed in production")
    OUT.mkdir(parents=True,exist_ok=True);save(OUT/"source.json",{**identity(),"base_sha":BASE,"changed":changed,"f08_accepted":False})

def adb(*args,name=None,timeout=60,check=True):
    run=subprocess.run(["adb",*map(str,args)],cwd=ROOT,text=True,capture_output=True,timeout=timeout)
    with (OUT/"host-command-log.jsonl").open("a") as log:log.write(json.dumps({"host_mono_ns":time.monotonic_ns(),"args":list(map(str,args)),"exit_code":run.returncode,"stdout_sha256":hashlib.sha256(run.stdout.encode()).hexdigest()})+"\n")
    if name:(OUT/name).write_text(run.stdout+run.stderr)
    if check:need(run.returncode==0,"adb failed: "+str(args)+" "+run.stderr[-1000:])
    return run.stdout

def wait_remote(names,timeout,process):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        for name in names:
            run=subprocess.run(["adb","shell","test","-f",REMOTE+"/"+name],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if run.returncode==0:return name
        need(process.poll() is None,"instrumentation ended before "+str(names))
        time.sleep(.1)
    raise TimeoutError("Waiting for "+str(names))

def signatures():
    signer=Path(os.environ["ANDROID_HOME"])/"build-tools/35.0.0/apksigner";rows={}
    for name in ("app-debug.apk","app-debug-androidTest.apk"):
        text=command([signer,"verify","--print-certs",OUT/"packages"/name],text=True)
        (OUT/(name+".signing.txt")).write_text(text)
        values=re.findall(r"certificate SHA-256 digest: ([0-9a-fA-F]+)",text);need(len(values)==1,"single signer")
        rows[name]=values[0].lower()
    need(len(set(rows.values()))==1,"Release and instrumentation certificate mismatch")
    save(OUT/"package-signatures.json",rows)

def sample():
    guard();signatures();raw=OUT/"frame-layer";raw.mkdir()
    process=None;trace=None;problems=[];display_before={};report=None
    try:
        need(adb("shell","getprop","ro.build.version.sdk").strip()=="34","API34")
        need(adb("shell","getprop","ro.product.cpu.abi").strip()=="x86_64","x86_64")
        for key in ("window_animation_scale","transition_animation_scale","animator_duration_scale"):
            adb("shell","settings","put","global",key,"1",name="animation-"+key+".txt")
            need(float(adb("shell","settings","get","global",key).strip())==1.0,"original scale 1 profile")
        for name,args in {"getprop":["getprop"],"display":["dumpsys","display"],"size":["wm","size"],"density":["wm","density"],"perfetto-sources":["perfetto","--query"]}.items():
            value=adb("shell",*args,name="environment-"+name+".txt")
            if name in ("size","density"):display_before[name]=value
        shutil.copyfile(HERE/"trace.pftxt",raw/"trace.pftxt")
        capability=(HERE/"trace.pftxt").read_text().replace("duration_ms: 20000","duration_ms: 1000")
        # Perfetto's SELinux domain intentionally cannot read /data/local/tmp;
        # the documented -c - interface receives configuration on stdin.
        prereq=subprocess.run(["adb","shell","perfetto","--txt","-c","-","-o","/data/misc/perfetto-traces/f08-prereq.perfetto-trace"],
            cwd=ROOT,input=capability,text=True,capture_output=True,timeout=15)
        (OUT/"perfetto-capability.txt").write_text(prereq.stdout+prereq.stderr)
        need(prereq.returncode==0,"Perfetto stdin capability failed: "+prereq.stderr)
        adb("pull","/data/misc/perfetto-traces/f08-prereq.perfetto-trace",raw/"capability.perfetto-trace",name="pull-perfetto-capability.txt")
        need((raw/"capability.perfetto-trace").stat().st_size>0,"empty prerequisite trace")
        adb("install","-r","-t",OUT/"packages/app-debug.apk",name="install-release.txt")
        adb("install","-r","-t",OUT/"packages/app-debug-androidTest.apk",name="install-instrumentation.txt")
        listed=adb("shell","pm","list","instrumentation",name="instrumentation-list.txt")
        need(APP+".FrameLayerTest" in listed and APP+".ShelfCatalogTest" in listed,"two declared instrumentation nodes")
        adb("shell","pm","clear",APP,name="clear-before-original-seed.txt")
        ident=identity();args=[]
        for key,value in ident.items():args += ["-e",key,value]
        seeded=adb("shell","am","instrument","-w","-r","-e","phase","seed-ui",*args,APP+".test/"+APP+".ShelfCatalogTest",name="seed-instrumentation.txt",timeout=600)
        need("EXR_SHELF_SEEDED 2202" in seeded and "INSTRUMENTATION_CODE: -1" in seeded,"original public SDK seed")
        adb("pull","/sdcard/Android/data/"+APP+"/files/shelf-tests",raw/"seed",name="pull-seed.txt")
        adb("shell","am","force-stop",APP,name="stop-seeding-process.txt")
        installed=OUT/"installed";installed.mkdir()
        paths=[line.removeprefix("package:") for line in adb("shell","pm","path",APP).splitlines() if line.startswith("package:")]
        need(len(paths)==1,"single installed APK")
        adb("pull",paths[0],installed/"app-debug.apk",name="pull-installed-release.txt")
        need(sha(installed/"app-debug.apk")==sha(OUT/"packages/app-debug.apk"),"installed APK matches built Release")
        transcript=(OUT/"frame-layer-instrumentation.txt").open("w")
        process=subprocess.Popen(["adb","shell","am","instrument","-w","-r",*args,APP+".test/"+APP+".FrameLayerTest"],cwd=ROOT,stdout=transcript,stderr=subprocess.STDOUT,text=True)
        wait_remote(["ready.json","report.json"],90,process)
        need("pid" in adb("shell","cat",REMOTE+"/ready.json"),"runner ready")
        adb("shell","dumpsys","gfxinfo",APP,"framestats",name="frame-layer/gfxinfo-initial.txt")
        trace_log=(OUT/"perfetto-recording.txt").open("w")
        with (HERE/"trace.pftxt").open("rb") as config:
            trace=subprocess.Popen(["adb","shell","perfetto","--txt","-c","-","-o","/data/misc/perfetto-traces/f08-abba.perfetto-trace"],cwd=ROOT,stdin=config,stdout=trace_log,stderr=subprocess.STDOUT,text=True)
        time.sleep(.7);need(trace.poll() is None,"Perfetto exited before recording")
        adb("shell","touch",REMOTE+"/go",name="start-abba.txt")
        for slot in range(4):
            checkpoint=wait_remote(["checkpoint-"+str(slot)+".json","report.json"],15,process)
            if checkpoint=="report.json":break
            adb("shell","dumpsys","gfxinfo",APP,"framestats",name="frame-layer/gfxinfo-"+str(slot)+".txt")
            adb("shell","dumpsys","meminfo",APP,name="frame-layer/meminfo-"+str(slot)+".txt")
            adb("shell","touch",REMOTE+"/checkpoint-"+str(slot)+"-go")
        wait_remote(["report.json"],15,process)
        adb("shell","dumpsys","gfxinfo",APP,"framestats",name="frame-layer/gfxinfo-final.txt")
        adb("shell","pidof",APP,name="frame-layer/pid-final.txt")
        adb("pull",REMOTE+"/.",raw,name="pull-frame-layer.txt")
        adb("shell","touch",REMOTE+"/release")
        process.wait(timeout=15);transcript.close()
        trace.wait(timeout=25);trace_log.close()
        need(trace.returncode==0,"Perfetto recording failed")
        adb("pull","/data/misc/perfetto-traces/f08-abba.perfetto-trace",raw/"trace.perfetto-trace",name="pull-perfetto-trace.txt")
        shutil.copyfile(HERE/"trace.pftxt",raw/"trace.pftxt")
        for name,args2 in {"size":["wm","size"],"density":["wm","density"]}.items():
            need(adb("shell",*args2,name="environment-final-"+name+".txt")==display_before[name],"display configuration changed")
        need(process.returncode==0 and "F08_FRAME_LAYER_OK" in (OUT/"frame-layer-instrumentation.txt").read_text(),"ABBA instrumentation failed")
        summary=replay(raw,ident);save(OUT/"summary.json",summary)
        launcher=OUT/"trace_processor.py"
        with urllib.request.urlopen("https://get.perfetto.dev/trace_processor",timeout=60) as response:data=response.read(2*1024*1024)
        need(len(data)<2*1024*1024 and b"python" in data[:100],"official Trace Processor launcher")
        launcher.write_bytes(data)
        version=subprocess.run([sys.executable,str(launcher),"--version"],capture_output=True,text=True,timeout=120)
        (OUT/"trace-processor-version.txt").write_text(version.stdout+version.stderr);need(version.returncode==0,"Trace Processor preparation")
        save(OUT/"trace-processor-identity.json",{"url":"https://get.perfetto.dev/trace_processor","launcher_sha256":sha(launcher),"version":version.stdout})
        trace_summary=parse_trace(raw,launcher,OUT/"trace-analysis");save(OUT/"trace-summary.json",trace_summary)
        need(summary["diagnostic_complete"],"Incomplete callback diagnostic")
        need(trace_summary["trace_complete"],"Incomplete trace attribution")
        print("F08_ABBA_DIAGNOSTIC",json.dumps({"callbacks":summary["callbacks"],"pooled":summary["pooled"],"trace":{k:v for k,v in trace_summary.items() if k not in ("raw_token_joins","thread_states","markers")},"f08_accepted":False}),flush=True)
    except Exception as error:
        problems.append(type(error).__name__+": "+str(error));raise
    finally:
        if process is not None and process.poll() is None:
            try:
                adb("shell","touch",REMOTE+"/release",check=False)
                # Before go the bounded runner wait is 60 seconds; after go a
                # missing checkpoint times out in 10. Let it export partial rows.
                process.wait(timeout=70)
                adb("pull",REMOTE+"/.",raw,name="pull-frame-layer-on-failure.txt",check=False)
            except Exception as error:
                problems.append("instrumentation cleanup: "+str(error))
                adb("pull",REMOTE+"/.",raw,name="pull-frame-layer-after-cleanup-timeout.txt",check=False)
                process.terminate()
        if trace is not None and trace.poll() is None:
            try:trace.wait(timeout=25)
            except Exception as error:problems.append("trace cleanup: "+str(error));trace.terminate()
        if not (raw/"trace.perfetto-trace").exists():
            try:adb("pull","/data/misc/perfetto-traces/f08-abba.perfetto-trace",raw/"trace.perfetto-trace",name="pull-failed-trace.txt",check=False)
            except Exception as error:problems.append(str(error))
        try:adb("logcat","-d","-v","threadtime",name="logcat.txt",check=False)
        except Exception as error:problems.append(str(error))
        save(OUT/"sample-status.json",{**identity(),"problems":problems,"f08_accepted":False})

def seal():
    guard()
    logs=ROOT/"build/wave3/logs"
    if logs.exists():shutil.copytree(logs,OUT/"build-logs",dirs_exist_ok=True)
    files={p.relative_to(OUT).as_posix():{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(OUT.rglob("*")) if p.is_file() and p!=OUT/"manifest.json"}
    save(OUT/"manifest.json",{**identity(),"base_sha":BASE,"files":files,"f08_accepted":False})


PRODUCER={"source_sha":"090431814e327ac8afcb653102e1a1185823f6bd","run_id":"41243382222","attempt":"1"}
PRODUCER_ARTIFACT=13058890179
PRODUCER_DIGEST="5a22c2cb68f229614fcbfa75fa39b7d84c8464e45522ae5d5dbbb06f4447cbaf"
PRODUCER_BYTES=21383935
REUSE_PAYLOAD=("build.json","release-apk-badging.txt","build-adapter.json","gradle-command.json","fixtures.json","sdk-base.h",
    "packages/app-debug.apk","packages/app-debug-androidTest.apk","packages/uitest-debug.apk","packages/uitest-debug-androidTest.apk")
def fetch_built_pair():
    # This follow-up only changes host orchestration; the already compiled app,
    # runner, resources, flags and SDK inputs must remain byte-identical in Git.
    changed=command(["git","diff","--name-only",PRODUCER["source_sha"],"HEAD"],text=True).splitlines()
    allowed={PREFIX+"build.py",PREFIX+"diagnostic.py",PREFIX+"AndroidManifest.xml",".github/workflows/f08-android-frame-diagnostic-20261031.yml"}
    need(set(changed)==allowed,"compiled inputs changed after successful build: "+str(changed))
    meta=json.loads(command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(PRODUCER_ARTIFACT)]))
    need(meta["id"]==PRODUCER_ARTIFACT and not meta["expired"] and meta["workflow_run"]["head_sha"]==PRODUCER["source_sha"]
        and str(meta["workflow_run"]["id"])==PRODUCER["run_id"],"compiled producer identity")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(PRODUCER_ARTIFACT)+"/zip"])
    need(len(data)==PRODUCER_BYTES==meta["size_in_bytes"] and hashlib.sha256(data).hexdigest()==PRODUCER_DIGEST
        and meta["digest"]=="sha256:"+PRODUCER_DIGEST,"compiled producer ZIP size/digest")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos=archive.infolist();need(0<len(infos)<10000 and sum(i.file_size for i in infos)<1024**3,"producer ZIP bounds")
        names=set()
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(not path.is_absolute() and str(path)!="." and ".." not in path.parts and "\\" not in info.filename and ":" not in info.filename and key not in names,"producer ZIP path")
            names.add(key);need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"producer ZIP kind")
        manifest=json.loads(archive.read("manifest.json"))
        need(all(manifest.get(k)==v for k,v in PRODUCER.items()),"producer manifest identity")
        files={i.filename for i in infos if not i.is_dir()}
        need(files==set(manifest["files"])|{"manifest.json"},"producer complete inventory")
        for name,item in manifest["files"].items():
            value=archive.read(name);need(len(value)==item["bytes"] and hashlib.sha256(value).hexdigest()==item["sha256"],"producer payload "+name)
        build=json.loads(archive.read("build.json"));need(all(build.get(k)==v for k,v in PRODUCER.items()) and build["configuration"]=="Release" and build["debug"] is False and build["page_theme"] is True and build["sdk_version"]=="3.42.0","producer Release build")
        need(build["diagnostic_java_sha256"]==sha(HERE/"java/org/exreader/host/FrameLayerTest.java") and build["diagnostic_manifest_sha256"]==hashlib.sha256(command(["git","show",PRODUCER["source_sha"]+":"+PREFIX+"AndroidManifest.xml"])).hexdigest() and build["diagnostic_init_sha256"]==sha(HERE/"diagnostic.init.gradle"),"compiled test sources unchanged")
        payload={name:archive.read(name) for name in REUSE_PAYLOAD}
    receipt={**identity(),"producer":PRODUCER,"artifact_id":PRODUCER_ARTIFACT,"bytes":len(data),"sha256":PRODUCER_DIGEST,
        "production_and_test_dex_inputs_equal":True,"test_manifest_recompiled":True,"packaging_only_diff":changed,"producer_files_authenticated":len(files),"f08_accepted":False}
    return payload,meta,manifest,receipt


def apk_entries(data):
    signature=lambda name:name.upper()=="META-INF/MANIFEST.MF" or re.fullmatch(r"META-INF/[^/]+\.(SF|RSA|DSA|EC)",name.upper()) is not None
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist();need(len(names)==len(set(names)),"APK duplicate entry")
        return {name:archive.read(name) for name in names if not signature(name)}

def link_test_manifest(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    aapt=Path(os.environ["ANDROID_HOME"])/"build-tools/35.0.0/aapt2"
    output=directory/"linked-test-manifest.apk"
    command([aapt,"link","-I",Path(os.environ["ANDROID_HOME"])/"platforms/android-35/android.jar",
        "--manifest",HERE/"AndroidManifest.xml","--min-sdk-version","26","--target-sdk-version","35","-o",output])
    with zipfile.ZipFile(output) as archive:return archive.read("AndroidManifest.xml")

def verify_repackaged_pair(payload,directory,temporary):
    directory=Path(directory);compiled_manifest=link_test_manifest(temporary);packages={}
    for name in ("app-debug.apk","app-debug-androidTest.apk"):
        original=apk_entries(payload["packages/"+name]);measured=(directory/"packages"/name).read_bytes();actual=apk_entries(measured)
        expected=dict(original)
        if "androidTest" in name:expected["AndroidManifest.xml"]=compiled_manifest
        need(actual==expected,"APK non-signature payload changed: "+name)
        packages[name]={"sha256":hashlib.sha256(measured).hexdigest(),"bytes":len(measured),"payload_entries":len(actual),
            "payload_inventory_sha256":hashlib.sha256(json.dumps({k:hashlib.sha256(v).hexdigest() for k,v in actual.items()},sort_keys=True).encode()).hexdigest(),
            "only_payload_change":"test instrumentation manifest" if "androidTest" in name else "none"}
    return {"toolchain":"official aapt2/zipalign/apksigner with a shared ephemeral key", "release_recompiled":False,"sdk_recompiled":False,
        "test_dex_recompiled":False,"manifest_source_sha256":sha(HERE/"AndroidManifest.xml"),"compiled_manifest_sha256":hashlib.sha256(compiled_manifest).hexdigest(),
        "packages":packages,"f08_accepted":False}

def repackage_pair(payload):
    # Re-signing both APKs with one key preserves normal platform signature checks.
    # No app payload or compiled test DEX is rebuilt or changed.
    work=ROOT/"build/f08-frame-layer-packaging";work.mkdir(parents=True,exist_ok=False)
    compiled_manifest=link_test_manifest(work)
    original=zipfile.ZipFile(io.BytesIO(payload["packages/app-debug-androidTest.apk"]))
    unsigned=work/"test-unsigned.apk"
    with original,zipfile.ZipFile(unsigned,"w") as output:
        for info in original.infolist():
            if info.filename not in apk_entries(payload["packages/app-debug-androidTest.apk"]):continue
            output.writestr(info,compiled_manifest if info.filename=="AndroidManifest.xml" else original.read(info))
    tools=Path(os.environ["ANDROID_HOME"])/"build-tools/35.0.0"
    aligned=work/"test-aligned.apk";command([tools/"zipalign","-f","4",unsigned,aligned])
    key=work/"ephemeral-debug.jks"
    command(["keytool","-genkeypair","-noprompt","-keystore",key,"-alias","androiddebugkey","-keyalg","RSA","-keysize","2048","-validity","2",
        "-storepass","android","-keypass","android","-dname","CN=Android Debug,O=Android,C=US"],stderr=subprocess.STDOUT)
    for name,source in (("app-debug.apk",OUT/"packages/app-debug.apk"),("app-debug-androidTest.apk",aligned)):
        signed=work/("signed-"+name)
        command([tools/"apksigner","sign","--ks",key,"--ks-key-alias","androiddebugkey","--ks-pass","pass:android","--key-pass","pass:android","--out",signed,source])
        shutil.copyfile(signed,OUT/"packages"/name)
    key.unlink()
    report=verify_repackaged_pair(payload,OUT,work/"independent-manifest-link")
    xml=command([tools/"aapt2","dump","xmltree",OUT/"packages/app-debug-androidTest.apk","--file","AndroidManifest.xml"],text=True)
    need("org.exreader.host.FrameLayerTest" in xml and "org.exreader.host.ShelfCatalogTest" in xml,"both packaged instrumentation declarations")
    (OUT/"test-manifest-xmltree.txt").write_text(xml);save(OUT/"repackaging.json",report)
    return report

def audit():
    guard();target=ROOT/"build/f08-android-frame-diagnostic-audit";target.mkdir(parents=True,exist_ok=False)
    api=lambda suffix:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+suffix]))
    ident=identity();aid=int(os.environ["F08_ARTIFACT_ID"]);meta=api("actions/artifacts/"+str(aid));save(target/"metadata.json",meta)
    need(meta["id"]==aid and not meta["expired"] and meta["name"]=="f08-android-frame-diagnostic-"+ident["run_id"]+"-"+ident["attempt"],"artifact identity")
    need(str(meta["workflow_run"]["id"])==ident["run_id"] and meta["workflow_run"]["head_sha"]==ident["source_sha"],"same-run producer")
    run=api("actions/runs/"+ident["run_id"]);need(run["head_sha"]==ident["source_sha"] and str(run["run_attempt"])==ident["attempt"],"producer attempt")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(aid)+"/zip"]);digest=hashlib.sha256(data).hexdigest()
    need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest and os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest,"ZIP size/digest")
    raw=target/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos=archive.infolist();need(0<len(infos)<10000 and sum(i.file_size for i in infos)<1024**3,"ZIP bounds");names=set()
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(not path.is_absolute() and str(path)!="." and ".." not in path.parts and "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key);need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
            if info.is_dir():continue
            dest=raw/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.read(info))
    manifest=json.loads((raw/"manifest.json").read_text());need(all(manifest.get(k)==v for k,v in ident.items()) and manifest.get("f08_accepted") is False,"manifest identity")
    actual={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()};need(actual==set(manifest["files"])|{"manifest.json"},"manifest inventory")
    for name,item in manifest["files"].items():need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"manifest entry "+name)
    report={**ident,"artifact_id":aid,"bytes":len(data),"sha256":digest,"files":len(actual),"authenticated":True,"diagnostic_complete":False,"trace_complete":False,"f08_accepted":False}
    if (raw/"build.json").exists():
        build=json.loads((raw/"build.json").read_text())
        build_identity=ident
        if (raw/"build-reuse.json").exists():
            payload,producer_meta,producer_manifest,reuse=fetch_built_pair()
            need(reuse==json.loads((raw/"build-reuse.json").read_text()),"independent build reuse identity")
            for name,value in payload.items():
                if name not in ("packages/app-debug.apk","packages/app-debug-androidTest.apk"):need((raw/name).read_bytes()==value,"reused compiled payload differs: "+name)
            repackaged=verify_repackaged_pair(payload,raw,target/"independent-manifest-link")
            need(repackaged==json.loads((raw/"repackaging.json").read_text()),"independent non-signature payload and test manifest verification")
            report["repackaging"]=repackaged
            need(producer_meta==json.loads((raw/"producer-metadata.json").read_text()) and producer_manifest==json.loads((raw/"producer-manifest.json").read_text()),"compiled producer receipts")
            build_identity=PRODUCER;report["build_reuse"]=reuse
        need(all(build.get(k)==v for k,v in build_identity.items()) and build["debug"] is False and build["configuration"]=="Release" and build["page_theme"] is True and build["sdk_version"]=="3.42.0","complete-feature Release build")
        need(build["diagnostic_java_sha256"]==sha(HERE/"java/org/exreader/host/FrameLayerTest.java") and build["diagnostic_manifest_sha256"]==hashlib.sha256(command(["git","show",PRODUCER["source_sha"]+":"+PREFIX+"AndroidManifest.xml"])).hexdigest() and build["diagnostic_init_sha256"]==sha(HERE/"diagnostic.init.gradle"),"compiled diagnostic source")
        for name,item in build["packages"].items():
            expected=report["repackaging"]["packages"][name]["sha256"] if name in report.get("repackaging",{}).get("packages",{}) else item["sha256"]
            need(sha(raw/"packages"/name)==expected,"package bytes")
        with zipfile.ZipFile(raw/"packages/app-debug.apk") as package:
            need(b"Java_org_exreader_host_ProductFixture_" not in package.read("lib/x86_64/libexreader_product.so"),"Release fixture JNI absent")
        signer=Path(os.environ["ANDROID_HOME"])/"build-tools/35.0.0/apksigner";certificates={}
        for name in ("app-debug.apk","app-debug-androidTest.apk"):
            text=command([signer,"verify","--print-certs",raw/"packages"/name],text=True)
            values=re.findall(r"certificate SHA-256 digest: ([0-9a-fA-F]+)",text);need(len(values)==1,"one audited signer")
            certificates[name]=values[0].lower()
        need(len(set(certificates.values()))==1 and certificates==json.loads((raw/"package-signatures.json").read_text()),"independent same-certificate verification")
        aapt=Path(os.environ["ANDROID_HOME"])/"build-tools/35.0.0/aapt2"
        badging=command([aapt,"dump","badging",raw/"packages/app-debug.apk"],text=True)
        need("application-debuggable" not in badging and badging==(raw/"release-apk-badging.txt").read_text(),"non-debuggable Release")
    try:
        summary=replay(raw/"frame-layer",ident);need(summary==json.loads((raw/"summary.json").read_text()),"independent callback/gfxinfo replay")
        need(sha(raw/"installed/app-debug.apk")==sha(raw/"packages/app-debug.apk"),"installed product bytes")
        tool=json.loads((raw/"trace-processor-identity.json").read_text());need(tool["launcher_sha256"]==sha(raw/"trace_processor.py"),"trace processor identity")
        trace_summary=parse_trace(raw/"frame-layer",raw/"trace_processor.py",target/"independent-trace-analysis")
        need(trace_summary==json.loads((raw/"trace-summary.json").read_text()),"independent raw trace replay")
        report.update(diagnostic_complete=summary["diagnostic_complete"],trace_complete=trace_summary["trace_complete"],callbacks=summary["callbacks"],callback_drops=summary["callback_drops"],
            abba=summary["abba"],pooled=summary["pooled"],first_draw_frames=summary["first_draw_frames"],outside=summary["outside"],unavailable=summary["unavailable"],
            gfxinfo_join_counts=summary["gfxinfo_join_counts"],gfxinfo_total_exact_matches=summary["gfxinfo_total_exact_matches"],
            gfxinfo_total_mismatches=summary["gfxinfo_total_mismatches"],gfxinfo_breakdown_ms=summary["gfxinfo_breakdown_ms"],trace={k:v for k,v in trace_summary.items() if k not in ("raw_token_joins","thread_states","markers")})
        save(target/"summary.json",summary);save(target/"trace-summary.json",trace_summary)
    except Exception as error:report["observation_problem"]=str(error)
    save(target/"audit.json",report);print("F08_ABBA_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("guard","sample","seal","audit"));globals()[parser.parse_args().mode]()
