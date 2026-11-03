"""Actions-only retained builds. No production/source rewrite and no automatic CI submission."""
import argparse
import hashlib
import json
import plistlib
import uuid
import importlib.abc
import importlib.util
import os
from pathlib import Path
import runpy
import subprocess
import sys
from identity import ROOT, SCOPE, identity, require, write_json, same_identity, read_snapshot, TABLES, canonical, digest, retain_database

class SDK342Loader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Version-only in-memory adapter; recorded source remains byte-for-byte unmodified."""
    def __init__(self, audit):
        self.audit = audit
        self.target = ROOT / "tests/reader_windows_raw3/host_build.py"
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "host_build":
            return importlib.util.spec_from_file_location(fullname, self.target, loader=self)
        return None
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        text = self.target.read_text(encoding="utf-8")
        require("3.41.0" in text, "frozen Windows helper version no longer matches")
        adapted = text.replace("3.41.0", SCOPE["sdk_version"])
        self.audit.append({"path": str(self.target.relative_to(ROOT)),
                           "original_sha256": hashlib.sha256(text.encode()).hexdigest(),
                           "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
                           "replacement": ["3.41.0", SCOPE["sdk_version"]],
                           "occurrences": text.count("3.41.0")})
        exec(compile(adapted, str(self.target), "exec"), module.__dict__)

def prepare_hash(host, environment, audit):
    """Build the frozen product dependency for the same target, without replacing its owner."""
    prefix = (ROOT / "build/dot-f03-hash" / host / "stage").resolve()
    build = prefix.parent / "build"
    argv = ["cmake", "-S", str(ROOT / "extras/opds"), "-B", str(build), "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
            "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_INSTALL_PREFIX=" + str(prefix)]
    if host == "android":
        toolchain = environment.get("C11_TOOLCHAIN")
        require(toolchain and Path(toolchain).is_file(), "installed matching Android toolchain required")
        argv += ["-DCMAKE_TOOLCHAIN_FILE=" + toolchain, "-DANDROID_ABI=x86_64",
                 "-DANDROID_PLATFORM=android-26", "-DANDROID_STL=c++_static"]
    subprocess.run(argv, cwd=ROOT, env=environment, check=True)
    subprocess.run(["cmake", "--build", str(build), "--parallel", "4", "--target", "install"],
                   cwd=ROOT, env=environment, check=True)
    require(prefix.is_dir() and prefix == prefix.resolve(), "canonical installed hash prefix required")
    environment["EXREADER_ORIGINAL_HASH_PREFIX"] = prefix.as_posix()
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = prefix.as_posix()
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
        stream.write("EXREADER_ORIGINAL_HASH_PREFIX=" + prefix.as_posix() + "\n")
    audit.append({"dependency": "EXReaderOPDSHash 0.1.0", "target": host,
                  "source": "extras/opds", "configure": argv, "prefix": str(prefix)})

def build_linux_recipe(host, audit):
    """Actions executes named original build steps; only explicit SDK version pins change."""
    import yaml
    if host == "gtk":
        workflow = ROOT / ".github/workflows/windows-gtk-organization-interop.yml"
        job = "gtk-first"
        names = ["Build installed SDK, catalog, account modules and real GTK host"]
    else:
        workflow = ROOT / ".github/workflows/android-organization-sync.yml"
        job = "android"
        names = ["Prepare existing C11 candidate test sources",
                 "Install the Android platform CMake NDK and API34 image",
                 "Build and install the frozen 3.41 SDK for x86_64",
                 "Install the raw0.2 product and reviewed wave3 packages into one prefix",
                 "Author the deterministic fixtures and the bundled font",
                 "Build the real wave3 host with search directory reading settings and sync",
                 "Build independent organization sync instrumentation",
                 "Build unchanged original sync UI runner", "Build strict 3.41 sync UI adapter"]
    recipe = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    steps = recipe["jobs"][job]["steps"]
    environment = dict(os.environ)
    environment.update({k: str(v) for k, v in recipe.get("env", {}).items()})
    environment.update({k: str(v) for k, v in recipe["jobs"][job].get("env", {}).items()})
    if host == "gtk":
        prepare_hash(host, environment, audit)
    for name in names:
        if host == "android" and name == "Install the raw0.2 product and reviewed wave3 packages into one prefix":
            prepare_hash(host, environment, audit)
        choices = [step for step in steps if step.get("name") == name]
        require(len(choices) == 1 and "run" in choices[0], "original recipe missing: " + name)
        original = choices[0]["run"]
        adapted = original.replace("3.41.0", SCOPE["sdk_version"])
        require("$" + "{{" not in adapted, "unresolved Actions expression")
        audit.append({"workflow": str(workflow.relative_to(ROOT)), "step": name,
                      "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
                      "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
                      "replacement": ["3.41.0", SCOPE["sdk_version"]],
                      "occurrences": original.count("3.41.0")})
        subprocess.run(["bash", "-euo", "pipefail", "-c", adapted], cwd=ROOT,
                       env=environment, check=True)
        env_file = Path(environment["GITHUB_ENV"])
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and (key.startswith("C11_") or key in ("ANDROID_HOME", "ANDROID_SDK_ROOT")):
                    environment[key] = value
        sdk_root = environment.get("ANDROID_SDK_ROOT")
        if sdk_root:
            environment["PATH"] = str(Path(sdk_root) / "platform-tools") + os.pathsep + environment["PATH"]


def receive_apple(a, stamp):
    """Actual XCTest session under fixture TLS; no lower-level revision application."""
    require(sys.platform == "darwin" and a.host in ("macos","iphone","ipad"), "Apple runner required")
    require(all(value is not None for value in
                (a.wire,a.expectations,a.projection_expectations,a.program,a.destination)),
            "exact Apple receiver inputs required")
    from android import wire_server
    fixture_spec=importlib.util.spec_from_file_location("f03_apple_tls_prepare",
        ROOT/"tests/webdav_android/fixture.py")
    module=importlib.util.module_from_spec(fixture_spec);fixture_spec.loader.exec_module(module)
    folder=a.output.parent / (a.output.stem + "-receiver")
    folder.mkdir(parents=True,exist_ok=False)
    fixture=folder/"fixture"
    expected_receipt=json.loads(a.projection_expectations.read_text(encoding="utf-8"))
    same_identity(expected_receipt,stamp)
    require(expected_receipt.get("sdk_version")==SCOPE["sdk_version"],"author SDK differs")
    expected=expected_receipt["snapshot"]
    server=None; trusted_fingerprint=None; clone=None
    try:
        module.prepare(fixture)
        if a.host=="macos":
            fingerprint=subprocess.check_output(["openssl","x509","-in",str(fixture/"public/ca.crt"),
                "-noout","-fingerprint","-sha1"],text=True).strip().split("=",1)[1].replace(":","")
            require(len(fingerprint)==40 and all(c in "0123456789ABCDEFabcdef" for c in fingerprint),
                    "invalid fixture fingerprint")
            trusted_fingerprint=fingerprint
            subprocess.run(["sudo","security","add-trusted-cert","-d","-r","trustRoot",
                "-k","/Library/Keychains/System.keychain",str(fixture/"public/ca.crt")],
                check=True,capture_output=True)
        else:
            require(a.udid is not None,"exact source simulator UDID required")
            # Trust only a receiver-owned clone; never reset the owner's simulator keychain.
            created=subprocess.check_output(["xcrun","simctl","clone",a.udid,
                "F03-"+stamp["run_id"]+"-"+stamp["attempt"]+"-"+a.host],text=True).strip()
            clone=str(uuid.UUID(created))
            require(clone.lower() != a.udid.lower(),"receiver simulator ownership unavailable")
            subprocess.run(["xcrun","simctl","boot",clone],check=True)
            subprocess.run(["xcrun","simctl","bootstatus",clone,"-b"],check=True)
            subprocess.run(["xcrun","simctl","keychain",clone,"add-root-cert",
                str(fixture/"public/ca.crt")],check=True)
            a.destination="platform=iOS Simulator,id="+clone
        relay,server,config=wire_server(a.wire,fixture)
        if a.host=="macos":
            # HEAD has no revision/body side effect and the retained DAV handler
            # does not count it as an authenticated product request. Observe
            # system trust independently; native XCTest remains the actual gate.
            probe=subprocess.run(["/usr/bin/curl","--head","--silent","--show-error","--max-time","10",
                                  config["root"]],capture_output=True,text=True)
            write_json(folder/"system-trust-observation.json",{
                "exit_code":probe.returncode,"stdout":probe.stdout[-2000:],"stderr":probe.stderr[-2000:]})
        work=ROOT/"build/dot-f03-native"/a.host
        scheme="EXReaderHost-macOS" if a.host=="macos" else "EXReaderHost-iOS"
        environment=dict(os.environ)
        environment.update({"TEST_RUNNER_F03_EXPECTED_GROUPS":a.expectations.read_text(encoding="utf-8"),
            "TEST_RUNNER_F03_DAV_ROOT":config["root"],
            "TEST_RUNNER_F03_DAV_USERNAME":config["user"],
            "TEST_RUNNER_F03_DAV_PASSWORD":config["password"]})
        test_target="EXReaderHostUITests-" + ("macOS" if a.host=="macos" else "iOS")
        plist=a.program.parent.parent/"Info.plist" if a.host=="macos" else a.program.parent/"Info.plist"
        package_identity=plistlib.loads(plist.read_bytes())
        require(package_identity.get("CFBundleIdentifier")=="org.exreader.host" and
                package_identity.get("EXRSourceSHA")==stamp["source_sha"] and
                package_identity.get("EXRSDKVersion")==SCOPE["sdk_version"],"actual Apple bundle identity differs")
        argv=["xcodebuild","test-without-building","-project",str(work/"project/EXReaderHost.xcodeproj"),
              "-scheme",scheme,"-destination",a.destination,"-derivedDataPath",str(work/"derived"),
              "-resultBundlePath",str(folder/"receiver.xcresult"),
              "-only-testing:"+test_target+"/AppleOrganizationInteropTests/testF03ReceivedOrganizationVisibleAfterRestart"]
        result=subprocess.run(argv,cwd=ROOT,env=environment,capture_output=True,timeout=1500)
        raw=result.stdout+result.stderr
        require(config["password"].encode() not in raw,"fixture secret appeared in XCTest output")
        (folder/"xcodebuild.log").write_bytes(raw)
        attachments=folder/"attachments"
        subprocess.run(["xcrun","xcresulttool","export","attachments","--path",
                        str(folder/"receiver.xcresult"),"--output-path",str(attachments)],check=True)
        require(result.returncode==0,"actual XCTest receiver failed")
        sys.path.insert(0,str(ROOT/"tests/apple_host"))
        from collect_evidence import load_results
        cases=load_results(folder/"receiver.xcresult")
        require(len(cases)==1 and cases[0]["result"]=="Passed" and
                "testF03ReceivedOrganizationVisibleAfterRestart" in cases[0]["name"],
                "actual receiver XCTest missing, failed or skipped")
        attachment_manifest=json.loads((attachments/"manifest.json").read_text())
        steps=[]
        for group in attachment_manifest:
            for item in group["attachments"]:
                if item["suggestedHumanReadableName"].startswith("organization-steps-"):
                    filename=item["exportedFileName"]
                    require(Path(filename).name==filename,"unsafe attachment path")
                    steps.append(json.loads((attachments/filename).read_text())["steps"])
        require(steps==[["f03-native-https-received","f03-received-groups-visible",
                         "f03-received-groups-persisted"]],"actual native receiver steps incomplete")
        require(any(r["method"]=="GET" and "/revisions/" in r["path"] and r["authenticated"]
                    for r in server.requests),"actual native revision receive missing")
        if a.host=="macos":
            profile_root=Path.home()/"Library/Application Support/EXReader"
        else:
            container=Path(subprocess.check_output(["xcrun","simctl","get_app_container",clone,
                "org.exreader.host","data"],text=True).strip()).resolve(strict=True)
            profile_root=container/"Library/Application Support/EXReader"
        profiles=json.loads((profile_root/"accounts.json").read_text(encoding="utf-8"))
        matches=[entry for entry in profiles if entry["root"]==config["root"]]
        require(len(matches)==1,"actual bundle fixture account not unique")
        identifier=matches[0]["id"]
        require(isinstance(identifier,str) and identifier and Path(identifier).name==identifier,
                "unsafe actual profile identity")
        database=(profile_root/"accounts"/identifier/"reader-catalog.db").resolve(strict=True)
        require(database.is_relative_to((profile_root/"accounts").resolve()),"profile DB escaped app account")
        if a.database is not None:
            require(a.database.resolve(strict=True)==database,"caller DB not current native account")
        actual=read_snapshot(database)
        retain_database(database, folder / "native-catalog", actual)
        for table in TABLES:
            require(actual[table]==expected[table],"Apple projection differs: "+table)
        original={r["id"]:r["body"] for r in expected["revisions"]}
        received={r["id"]:r["body"] for r in actual["revisions"]}
        require(all(received.get(k)==v for k,v in original.items()),"Apple exact revisions differ")
        write_json(folder/"projection.json",{**stamp,"host":a.host,"sdk_version":SCOPE["sdk_version"],
            "program_sha256":digest(a.program),"native_sync_completed":True,"restart_verified":True,
            "snapshot":actual,"snapshot_sha256":hashlib.sha256(canonical(actual)).hexdigest(),
            "complete_product_accepted":False})
        relay.save(server,folder/"wire","f03-"+a.host+"-receive",{"projection":"../projection.json"})
        server=None
    finally:
        active_failure=sys.exc_info()[0] is not None
        failures=[]
        def cleanup(label, action):
            try: action()
            except Exception as error: failures.append({"action":label,"error":str(error)})
        if server is not None:
            cleanup("requests",lambda:write_json(folder/"failed-requests.json",server.requests))
            cleanup("server-stop",server.server.shutdown)
            cleanup("server-close",server.server.server_close)
        if trusted_fingerprint is not None:
            cleanup("remove-owned-trust",lambda:subprocess.run(["sudo","security","delete-certificate",
                "-Z",trusted_fingerprint,"/Library/Keychains/System.keychain"],check=True,capture_output=True))
        if clone is not None:
            cleanup("stop-owned-simulator",lambda:subprocess.run(["xcrun","simctl","shutdown",clone],
                check=True,capture_output=True))
            cleanup("delete-owned-simulator",lambda:subprocess.run(["xcrun","simctl","delete",clone],
                check=True,capture_output=True))
        import shutil
        cleanup("fixture-private",lambda:shutil.rmtree(fixture/"private"))
        def invalidate_receipt():
            receipt=folder/"projection.json"
            if receipt.exists():
                receipt.rename(folder/"projection-before-failed-cleanup.json")
        if active_failure or failures:
            invalidate_receipt()
        try:
            write_json(folder/"cleanup.json",{"passed":not active_failure and not failures,"errors":failures})
        except Exception:
            invalidate_receipt()
            if not active_failure:raise
            print("Unable to write Apple cleanup evidence; native receiver remains failed",file=sys.stderr)
        if failures and not active_failure:
            raise RuntimeError("receiver fixture cleanup failed")


def android_environment():
    base=SCOPE["baseline"]
    os.environ["ANDROID_CANDIDATE_SDK_BASE"]=base
    os.environ["ANDROID_OWNERSHIP_HEAD"]=base
    os.environ["ORG_GRADLE_PROJECT_exrSdkVersion"]=SCOPE["sdk_version"]
    stage=(ROOT/"stage/android-product").resolve()
    sdk=(ROOT/"stage/android-x86_64").resolve()
    values={"exrSync":"true","exrSdk":str(sdk),"exrProduct":str(stage),
            "exrDav":str(stage),"exrSideload":str(stage)}
    for key,value in values.items():os.environ["ORG_GRADLE_PROJECT_"+key]=value
    home=(ROOT/"build/f03-gradle-home").resolve()
    init=home/"init.d/f03.gradle";init.parent.mkdir(parents=True,exist_ok=True)
    source=(ROOT/"tests/dot_f03_same_source_20261031/android").as_posix()
    init.write_text("gradle.beforeProject { p -> if (p.path == ':uitest') { "
        "p.pluginManager.withPlugin('com.android.application') { "
        "p.android.sourceSets.androidTest.java.srcDir new File('"+source+"') } } }\n",encoding="utf-8")
    os.environ["GRADLE_USER_HOME"]=str(home)
    with Path(os.environ["GITHUB_ENV"]).open("a",encoding="utf-8") as stream:
        for key in ["ANDROID_CANDIDATE_SDK_BASE","ANDROID_OWNERSHIP_HEAD","GRADLE_USER_HOME",
                    "ORG_GRADLE_PROJECT_exrSdkVersion",*["ORG_GRADLE_PROJECT_"+k for k in values]]:
            stream.write(key+"="+os.environ[key]+"\n")
    return stage,sdk

def build_android_owner(audit):
    """Original builder emits its own evidence; only declared candidate build options extend it."""
    stage,sdk=android_environment()
    (ROOT/"build/shelf-android").mkdir(parents=True,exist_ok=True)
    (ROOT/"build/owner-android").mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,"tests/reader_catalog/check_schema.py","--output",
                    "build/shelf-android/schema.json"],cwd=ROOT,check=True)
    subprocess.run([sys.executable,"tests/reader_catalog/check_assets.py"],cwd=ROOT,check=True)
    android_home=os.environ.get("ANDROID_HOME",os.environ.get("ANDROID_SDK_ROOT",""))
    toolchain=Path(android_home)/"ndk/27.0.12077973/build/cmake/android.toolchain.cmake"
    require(toolchain.is_file(),"pinned Android NDK missing")
    os.environ["C11_TOOLCHAIN"]=str(toolchain)
    prepare_hash("android",os.environ,audit)
    fixture=ROOT/"build/wave3/network-fixture"
    subprocess.run([sys.executable,"tests/webdav_android/fixture.py","prepare",
                    "--output",str(fixture)],cwd=ROOT,check=True)
    import shutil
    ca=ROOT/"tests/reader_host_session_android/debug/res/raw/host_sync_fixture_ca.crt"
    ca.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(fixture/"public/ca.crt",ca)
    sys.path.insert(0,str(ROOT/"tools"))
    spec=importlib.util.spec_from_file_location("f03_original_android_builder",
                                               ROOT/"tools/build_android_host.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original_product=module.build_product
    def product_with_sync(product_stage,build):
        original_product(product_stage,build)
        for name,path in [("webdav","extras/webdav"),("sideload","extras/sideload"),
                          ("sync","apps/reader/sync"),("session","apps/reader/session")]:
            location=build/("f03-"+name)
            argv=["cmake","-S",str(ROOT/path),"-B",str(location),"-G","Ninja",
                "-DCMAKE_TOOLCHAIN_FILE="+str(toolchain),"-DANDROID_ABI=x86_64",
                "-DANDROID_PLATFORM=android-26","-DANDROID_STL=c++_static",
                "-DCMAKE_BUILD_TYPE=Release","-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
                "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH",
                "-DEXR_SDK="+str(sdk),"-DEXR_SDK_VERSION="+SCOPE["sdk_version"],
                "-DREADER_PRODUCT_PREFIX="+str(product_stage),
                "-DCMAKE_PREFIX_PATH="+str(product_stage)+";"+str(sdk),
                "-DCMAKE_INSTALL_PREFIX="+str(product_stage)]
            subprocess.run(argv,cwd=ROOT,check=True)
            subprocess.run(["cmake","--build",str(location),"--parallel","4","--target","install"],
                           cwd=ROOT,check=True)
            audit.append({"additional_original_module":path,"configure":argv})
    module.build_product=product_with_sync
    sys.argv=[str(ROOT/"tools/build_android_host.py"),"--stage",str(sdk),
              "--build-dir","build/android-host","--gradle","gradle"]
    module.main()
    subprocess.run(["gradle","-p","examples/android","--no-daemon","--stacktrace",
                    ":app:assembleRelease","-PexrSdk="+str(sdk)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,"tools/check_reader_owner_android.py","--evidence",
                    "build/owner-android","--collect-native"],cwd=ROOT,check=True)
    subprocess.run([sys.executable,"tools/check_android_host.py","--repo","."],cwd=ROOT,check=True)
    mapping=ROOT/"examples/android/app/src/androidTest/assets/mapping"
    mapping.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/"build/android-host/fixtures/Sample.epub",mapping/"Sample.epub")
    for folder in ("build/shelf-android","build/owner-android"):
        path=ROOT/folder;path.mkdir(parents=True,exist_ok=True)
        (path/"source.txt").write_text(os.environ["GITHUB_SHA"]+"\n")
    audit.append({"original_builder":"tools/build_android_host.py",
        "original_builder_sha256":digest(ROOT/"tools/build_android_host.py"),
        "candidate_admission":True,"product_baseline":SCOPE["baseline"],
        "sdk_freeze":SCOPE["sdk_source"],"historical_owner_guard_reexecuted":False,
        "historical_owner_evidence_ref":SCOPE["historical_owner_evidence_ref"],
        "unchanged_original_checker_environment":{
            "ANDROID_CANDIDATE_SDK_BASE":SCOPE["baseline"],"ANDROID_OWNERSHIP_HEAD":SCOPE["baseline"]}})

def run_android_retained():
    """Execute preserved device script and every original final gate, preserving every outcome."""
    import yaml
    android_environment()
    original=ROOT/".github/workflows/reader-organization-android.yml"
    steps=yaml.safe_load(original.read_text())["jobs"]["android-shelf"]["steps"]
    device=next(s for s in steps if s.get("id")=="emulator")
    results=[]
    def run_step(name,command,environment=None):
        process=subprocess.run(["bash","-euo","pipefail","-c",command],cwd=ROOT,
                               env=environment or os.environ,check=False)
        results.append({"name":name,"exit_code":process.returncode,
                        "original_command_sha256":hashlib.sha256(command.encode()).hexdigest()})
        return process.returncode
    device_exit=run_step(device["name"],device["with"]["script"])
    env=dict(os.environ)
    env["ANDROID_HOST_UPSTREAM"]=json.dumps({"build":"success","static":"success",
                                             "emulator":"success" if device_exit==0 else "failure"})
    gate_outcomes={}
    for step in steps[steps.index(device)+1:]:
        if "run" not in step:continue
        command=step["run"]
        env["ANDROID_GATE_OUTCOME"]=gate_outcomes.get("gate_review","failure")
        env["ANDROID_BOUNDED_GATE_OUTCOME"]=gate_outcomes.get("bounded_gate","failure")
        require("$"+"{{" not in command,"original gate command has unresolved expression")
        status=run_step(step["name"],command,env)
        if "id" in step:gate_outcomes[step["id"]]="success" if status==0 else "failure"
    write_json(ROOT/"build/f03-android-original-steps.json",
               {**identity(),"original_workflow":str(original.relative_to(ROOT)),
                "original_workflow_sha256":digest(original),"steps":results,
                "accepted":all(r["exit_code"]==0 for r in results),
                "historical_owner_guard_reexecuted":False})
    require(all(r["exit_code"]==0 for r in results),"original Android suite/gate failure retained")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", choices=["windows", "gtk", "macos", "iphone", "ipad", "android"], required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--native-tests", action="store_true")
    p.add_argument("--android-retained", action="store_true")
    p.add_argument("--apple-receive", action="store_true")
    for name in ("wire","expectations","projection-expectations","database","program"):
        p.add_argument("--"+name,type=Path)
    p.add_argument("--udid")
    p.add_argument("--sdk", type=Path)
    p.add_argument("--products", type=Path)
    p.add_argument("--resources", type=Path)
    p.add_argument("--destination")
    a = p.parse_args()
    stamp = identity()
    require(a.host in SCOPE["active_hosts"], "host outside approved partial suite")
    changes = []
    accepted = False
    try:
        if a.android_retained:
            require(a.host == "android", "Android only")
            run_android_retained()
        elif a.apple_receive:
            receive_apple(a,stamp)
        elif a.native_tests:
            require(a.sdk is not None and a.products is not None, "installed SDK/products required")
            work = ROOT / "build/dot-f03-native" / a.host
            work.mkdir(parents=True, exist_ok=False)
            if a.host == "android":
                init = work / "f03.init.gradle"
                path = (Path(__file__).resolve().parent / "android").as_posix()
                init.write_text("gradle.beforeProject { p -> if (p.path == ':uitest') { "
                                "p.pluginManager.withPlugin('com.android.application') { "
                                "p.android.sourceSets.androidTest.java.srcDir new File('"
                                + path + "') } } }\n", encoding="utf-8")
                subprocess.run(["gradle", "-p", str(ROOT / "examples/android"), "--no-daemon",
                                "--stacktrace", "-I", str(init),
                                "-PexrSdk=" + str(a.sdk.resolve()),
                                "-PexrProduct=" + str(a.products.resolve()),
                                ":uitest:assembleDebug", ":uitest:assembleDebugAndroidTest"],
                               cwd=ROOT, check=True)
            else:
                require(a.host in ("macos", "iphone", "ipad"), "unsupported native target")
                require(a.resources is not None and a.resources.is_dir(), "original fixtures required")
                require(a.destination is not None, "exact actual device destination required")
                os.environ["EXR_APPLE_SDK_VERSION"] = SCOPE["sdk_version"]
                project = work / "project"
                subprocess.run(["ruby", "tests/reader_team24_apple/make_project.rb", str(project),
                                str(a.resources.resolve()), str(Path(__file__).resolve().parent), "base"],
                               cwd=ROOT, check=True)
                scheme = "EXReaderHost-macOS" if a.host == "macos" else "EXReaderHost-iOS"
                subprocess.run(["xcodebuild", "build-for-testing", "-project",
                                str(project / "EXReaderHost.xcodeproj"), "-scheme", scheme,
                                "-destination", a.destination, "-derivedDataPath", str(work / "derived"),
                                "EXR_SDK_DIR=" + str(a.sdk.resolve()),
                                "EXR_PRODUCTS_DIR=" + str(a.products.resolve()),
                                "CODE_SIGNING_ALLOWED=" + ("YES" if a.host == "macos" else "NO")],
                               cwd=ROOT, check=True)
        elif a.host in ("android", "gtk"):
            require(sys.platform.startswith("linux"), "Linux runner required")
            if a.host == "android":build_android_owner(changes)
            else:build_linux_recipe(a.host, changes)
        elif a.host == "windows":
            require(os.name == "nt", "Windows build requires Windows runner")
            prepare_hash("windows", os.environ, changes)
            loader = SDK342Loader(changes)
            sys.meta_path.insert(0, loader)
            path = ROOT / "tests/reader_wave3_c09/build.py"
            text = path.read_text(encoding="utf-8")
            require("3.41.0" in text, "frozen C09 version no longer matches")
            adapted = text.replace("3.41.0", SCOPE["sdk_version"])
            changes.append({"path": str(path.relative_to(ROOT)),
                            "original_sha256": hashlib.sha256(text.encode()).hexdigest(),
                            "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
                            "replacement": ["3.41.0", SCOPE["sdk_version"]],
                            "occurrences": text.count("3.41.0")})
            sys.argv = [str(path)]
            exec(compile(adapted, str(path), "exec"),
                 {"__name__": "__main__", "__file__": str(path), "__package__": None})
        else:
            require(sys.platform == "darwin", "Apple build requires macOS runner")
            os.environ["EXR_APPLE_SDK_VERSION"] = SCOPE["sdk_version"]
            target = "macos" if a.host == "macos" else "iphonesimulator"
            path = ROOT / "tests/apple_sdk342_host/build.py"
            sys.argv = [str(path), "--target", target]
            runpy.run_path(str(path), run_name="__main__")
        accepted = True
    finally:
        write_json(a.output, {**stamp, "host": a.host, "operation_completed": accepted,
                              "operation": "android-retained" if a.android_retained else ("apple-receive" if a.apple_receive else "build"),
                              "sdk_version": SCOPE["sdk_version"], "sdk_source": SCOPE["sdk_source"],
                              "in_memory_adapters": changes,
                              "product_source_changed": False, "complete_product_accepted": False})
if __name__ == "__main__":
    main()
