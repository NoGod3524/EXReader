# SPDX-License-Identifier: MIT
"""Actions-only bounded F05 Android bridge admission, runtime and evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback
D = Path(__file__).resolve().parent
ROOT = D.parents[2]
OUT = ROOT / "build/f05-bridge"
CONTRACT = json.loads((D / "contract.json").read_text())
IDENTITY = {k:os.environ.get(v,"") for k,v in (("source_sha","GITHUB_SHA"),("run_id","GITHUB_RUN_ID"),("attempt","GITHUB_RUN_ATTEMPT"))}
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def command(args, **kwargs): return subprocess.check_output(list(map(str,args)),cwd=ROOT,stderr=subprocess.STDOUT,**kwargs)
def write(name,value):
    path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+"\n")
def guard():
    assert os.environ.get("GITHUB_ACTIONS")=="true"
    assert os.environ["GITHUB_REF"]=="refs/heads/"+CONTRACT["branch"]
    assert os.environ["GITHUB_EVENT_NAME"]=="workflow_dispatch"
    assert IDENTITY["attempt"]=="1","No automatic rerun authorized"
    assert command(["git","rev-parse","HEAD"]).decode().strip()==IDENTITY["source_sha"]
def admission():
    guard()
    actual=command(["git","diff","--name-status",CONTRACT["parent"],"HEAD"]).decode().splitlines()
    assert sorted(actual)==sorted(CONTRACT["changes"]),(actual,CONTRACT["changes"])
    assert command(["git","rev-parse","HEAD^"]).decode().strip()==CONTRACT["parent"]
    command(["git","diff","--exit-code",CONTRACT["sdk_freeze"],"HEAD","--","src","include","bindings","cmake","CMakeLists.txt"])
    for path,digest in CONTRACT["production_sha256"].items(): assert sha(ROOT/path)==digest,path
    for path,blob in CONTRACT["original_blobs"].items():
        assert command(["git","hash-object",path]).decode().strip()==blob,path
    write("admission.json",{**IDENTITY,"accepted":True,"contract_sha256":sha(D/"contract.json"),"changes":actual,
        "files":{p:sha(ROOT/p) for p in CONTRACT["paths"]},"sdk_freeze":CONTRACT["sdk_freeze"]})
def xml_identity(text):
    nodes=[];stack=[]
    for line in text.splitlines():
        stripped=line.lstrip();indent=len(line)-len(stripped)
        if stripped.startswith("E: "):
            while stack and stack[-1][0]>=indent:stack.pop()
            tag=stripped[3:].split()[0];node={"tag":tag,"attrs":{}}
            nodes.append(node);stack.append((indent,node))
        elif stripped.startswith("A: ") and stack:
            match=re.match(r'A: ([^ (=]+)(?:\([^)]*\))?="([^"]*)"',stripped)
            if match:
                key,value=match.groups();attrs=stack[-1][1]["attrs"]
                assert key not in attrs,"Duplicate XML attribute"
                attrs[key]=value
    roots=[n for n in nodes if n["tag"]=="manifest"]
    runners=[n for n in nodes if n["tag"]=="instrumentation"]
    assert len(roots)==1,"Manifest root missing or repeated"
    return roots[0]["attrs"].get("package"),runners
def clean_error(value):
    text=str(value)
    text=re.sub(r"(?i)Basic\s+[A-Za-z0-9+/=]+","Basic <redacted>",text)
    text=re.sub(r"(?i)(password|authorization|access_token)[^A-Za-z0-9]{0,8}[A-Za-z0-9+/=_-]+",r"\1=<redacted>",text)
    return text[-3000:]
def digest(data): return hashlib.sha256(data).hexdigest()
def git(*args): return command(["git",*args]).decode().strip()
def write_report(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+"\n")

def installed_hash_prefix():
    prefix = ROOT / "build/f05-bridge/hash/android/stage"
    require(prefix == prefix.resolve() and not any(p.is_symlink() for p in [prefix, *prefix.parents]),
            "hash prefix and ancestors must be real canonical directories")
    return prefix

def hash_inventory(prefix):
    require(prefix.is_dir() and prefix == prefix.resolve(), "canonical installed hash prefix")
    result = {}
    for path in sorted(prefix.rglob("*")):
        require(not path.is_symlink() and path.resolve().is_relative_to(prefix), "hash owner alias or escape")
        if path.is_file():
            result[path.relative_to(prefix).as_posix()] = {"bytes": path.stat().st_size,
                                                         "sha256": digest(path.read_bytes())}
    required = {"lib/libopds_sha256_stream.a", "include/exreader-opds-hash/opds_sha256_stream.h",
                "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfig.cmake",
                "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfigVersion.cmake",
                "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashTargets.cmake"}
    require(required <= set(result), "installed hash owner incomplete")
    data = (prefix / "lib/libopds_sha256_stream.a").read_bytes()
    require(data.startswith(b"!<arch>\n"), "hash archive format")
    offset, members = 8, 0
    while offset < len(data):
        header = data[offset:offset + 60]
        require(len(header) == 60 and header[58:60] == b"\x60\n", "hash archive header")
        size = int(header[48:58].strip())
        body = data[offset + 60:offset + 60 + size]
        require(len(body) == size, "hash archive truncation")
        name = header[:16].decode("ascii").strip()
        if name not in ("/", "//", "/SYM64/"):
            require(body[:6] == b"\x7fELF\x02\x01" and len(body) >= 20 and
                    int.from_bytes(body[16:18], "little") == 1 and
                    int.from_bytes(body[18:20], "little") == 62, "hash owner must be x86_64 ELF64 relocatable objects")
            members += 1
        offset += 60 + size + size % 2
    require(offset == len(data) and members > 0, "hash archive members missing")
    return result

def prepare_hash_owner():
    admission()
    source = IDENTITY
    prefix = installed_hash_prefix()
    require(os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX") in (None, "", str(prefix)), "foreign hash environment")
    require(not os.environ.get("READER_ORIGINAL_HASH_PREFIX"), "conflicting hash selector")
    require(not prefix.exists(), "hash installation must be fresh in this run")
    prefix.mkdir(parents=True)
    home = Path(os.environ["ANDROID_HOME"])
    ndk = home / "ndk/27.0.12077973"
    toolchain = ndk / "build/cmake/android.toolchain.cmake"
    require(toolchain.is_file() and "Pkg.Revision = 27.0.12077973" in (ndk / "source.properties").read_text(),
            "exact approved NDK hash-owner compiler")
    build = prefix.parent / "build"
    arguments = ["cmake", "-S", str(ROOT / "extras/opds"), "-B", str(build), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
                 "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_INSTALL_PREFIX=" + str(prefix),
                 "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain), "-DANDROID_ABI=x86_64",
                 "-DANDROID_PLATFORM=android-26", "-DANDROID_STL=c++_static"]
    for command in (arguments, ["cmake", "--build", str(build), "--parallel", "4", "--target", "install"]):
        subprocess.run(command, cwd=ROOT, check=True)
    cache = build / "CMakeCache.txt"
    require("EXREADER_OPDS_HASH_ONLY:BOOL=ON" in cache.read_text(), "hash-only build identity")
    report = {k: source[k] for k in ("source_sha", "run_id", "attempt")}
    report.update(prefix=str(prefix), package="EXReaderOPDSHash", version="0.1.0",
                  owner_source_tree=git("rev-parse", "HEAD:extras/opds"),
                  configure=arguments, ndk="27.0.12077973", abi="x86_64", platform="android-26",
                  toolchain_sha256=digest(toolchain.read_bytes()), cache_sha256=digest(cache.read_bytes()),
                  files=hash_inventory(prefix))
    write_report(ROOT / "build/f05-bridge/hash-owner.json", report)
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = str(prefix)
    with open(os.environ["GITHUB_ENV"], "a") as stream:
        stream.write("EXREADER_ORIGINAL_HASH_PREFIX=" + str(prefix) + "\n")
    print(json.dumps({"hash_owner_installed": True, "prefix": str(prefix), "files": report["files"]}))

def hash_owner_proof():
    c = CONTRACT
    prefix = installed_hash_prefix()
    require(os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX") == str(prefix), "hash prefix lost or replaced in child process")
    require(git("rev-parse", "HEAD:extras/opds") == c["hash_source_tree"], "hash owner source changed")
    report = json.loads((ROOT / "build/f05-bridge/hash-owner.json").read_text())
    require(all(report.get(k) == os.environ[e] for k, e in
                (("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))),
            "hash owner belongs to another run")
    require(report.get("prefix") == str(prefix) and report.get("owner_source_tree") == c["hash_source_tree"] and
            report.get("version") == "0.1.0" and report.get("ndk") == "27.0.12077973" and
            report.get("abi") == "x86_64" and report.get("platform") == "android-26",
            "hash owner target identity")
    require(report.get("files") == hash_inventory(prefix), "installed hash owner bytes changed")
    cache = prefix.parent / "build/CMakeCache.txt"
    require(report["cache_sha256"] == digest(cache.read_bytes()), "hash owner configuration changed")
    toolchain = Path(os.environ["ANDROID_HOME"]) / "ndk/27.0.12077973/build/cmake/android.toolchain.cmake"
    require(report["toolchain_sha256"] == digest(toolchain.read_bytes()), "hash compiler toolchain changed")
    require(not os.environ.get("READER_ORIGINAL_HASH_PREFIX"), "conflicting hash selector")
    with (OUT / "hash-proof-calls.jsonl").open("a") as stream:
        stream.write(json.dumps(IDENTITY)+"\n")
    return report



def package():
    guard()
    apks=OUT/"apks";apks.mkdir(parents=True,exist_ok=True)
    source=ROOT/"examples/android/app/build/outputs/apk"
    assert sha(source/"debug/app-debug.apk")==sha(apks/"app-debug.apk"),"Canonical app APK changed during test APK build"
    assert sha(source/"release/app-release-unsigned.apk")==sha(apks/"app-release-unsigned.apk"),"Release APK changed during test APK build"
    aapt=Path(os.environ["ANDROID_HOME"])/"build-tools/35.0.0/aapt2"
    identities={}
    for name,runner in (("original-owner.apk","ProductOwnerTest"),("host-sync.apk","HostSyncTest"),("head-bridge.apk","HeadBridgeTest")):
        path=apks/name;xml=command([aapt,"dump","xmltree",path,"--file","AndroidManifest.xml"]).decode()
        (OUT/(name+".manifest.txt")).write_text(xml)
        test_package,runners=xml_identity(xml)
        assert test_package=="org.exreader.host.test" and len(runners)==1,("Instrumentation package/count",name)
        attrs=runners[0]["attrs"]
        assert attrs.get("android:name")=="org.exreader.host."+runner and attrs.get("android:targetPackage")=="org.exreader.host",("Exact runner/target",name)
        identities[name]={"sha256":sha(path),"bytes":path.stat().st_size,"runner":runner,"test_package":test_package,"target_package":attrs["android:targetPackage"],"manifest_sha256":sha(OUT/(name+".manifest.txt"))}
    for name in ("app-debug.apk","app-release-unsigned.apk"):
        path=apks/name;identities[name]={"sha256":sha(path),"bytes":path.stat().st_size}
    assert sha(source/"debug/app-debug.apk")==identities["app-debug.apk"]["sha256"]
    header=ROOT/"build/session-android/sdk-stage/include/exr/base.h"
    assert '#define EXR_VERSION "3.42.0"' in header.read_text()
    write("packages.json",{**IDENTITY,"apks":identities,"sdk_header_sha256":sha(header),"accepted":True})
def adb(*args,**kwargs):return command(["adb",*args],timeout=kwargs.pop("timeout",120),**kwargs)
def installed(package,expected):
    lines=adb("shell","pm","path",package).decode().splitlines()
    paths=[line[len("package:"):].strip() for line in lines if line.startswith("package:")]
    assert len(paths)==1,(package,paths)
    body=adb("exec-out","cat",paths[0])
    got=hashlib.sha256(body).hexdigest();assert got==expected,(package,got,expected)
    return {"package":package,"path":paths[0],"sha256":got,"bytes":len(body)}
def instrument(runner,report_name,output_name):
    args=["shell","am","instrument","-w","-r"]
    for key,value in IDENTITY.items():args+=["-e",key,value]
    args+=["-e","sdk_version","3.42.0","org.exreader.host.test/org.exreader.host."+runner]
    failure=None
    try:raw=adb(*args,timeout=600)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
        raw=error.output or b"";failure=error
    if isinstance(raw,str):raw=raw.encode()
    (OUT/(output_name+".instrumentation.txt")).write_bytes(raw)
    if failure is not None:
        write(output_name+".process-error.json",{"error":clean_error(failure),"stdout_bytes":len(raw)})
        print(output_name+" instrumentation process failed: "+clean_error(failure),flush=True)
        print(clean_error(raw.decode(errors="replace")),flush=True)
    try:
        body=adb("exec-out","run-as","org.exreader.host","cat","files/"+report_name)
        (OUT/(output_name+".json")).write_bytes(body);report=json.loads(body)
    except Exception:
        if failure is not None:raise RuntimeError(output_name+" instrumentation failed; retained stdout")
        raise
    if failure is not None:raise RuntimeError(output_name+" instrumentation process failed; retained report/stdout")
    assert all(str(report.get(k))==v for k,v in IDENTITY.items()),"Instrumentation source/run/attempt mismatch"
    assert report["api"]==34 and report["abi"]=="x86_64","Instrumentation API/ABI mismatch"
    return raw,report
def runtime():
    guard();pkg=json.loads((OUT/"packages.json").read_text());apks=OUT/"apks";stages={};installs=[]
    adb("install","-r","-t",apks/"app-debug.apk")
    installs.append(installed("org.exreader.host",pkg["apks"]["app-debug.apk"]["sha256"]))
    for kind,runner,apk,report in (
        ("original_owner","ProductOwnerTest","original-owner.apk","product-owner-report.json"),
        ("retained","HostSyncTest","host-sync.apk",None),
        ("bridge","HeadBridgeTest","head-bridge.apk","f05-head-bridge-report.json")):
        try:
            adb("shell","am","force-stop","org.exreader.host")
            adb("install","-r","-t",apks/apk)
            installs.append(installed("org.exreader.host.test",pkg["apks"][apk]["sha256"]))
            installs.append(installed("org.exreader.host",pkg["apks"]["app-debug.apk"]["sha256"]))
            if kind=="retained":
                retained_command=[sys.executable,D/"retained.py","retained","--fixture",ROOT/"build/webdav-android/fixture",
                    "--reading-fixtures",ROOT/"build/session-android/reading-fixtures","--output",OUT/"retained",
                    "--sdk-prefix",ROOT/"build/session-android/sdk-stage"]
                try:retained_output=command(retained_command,timeout=1800)
                except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
                    output=error.output or b""
                    if isinstance(output,str):output=output.encode()
                    (OUT/"retained-driver.txt").write_bytes(output)
                    print("retained group failed: "+clean_error(error),flush=True)
                    print(clean_error(output.decode(errors="replace")),flush=True)
                    raise
                (OUT/"retained-driver.txt").write_bytes(retained_output)
                proof=json.loads((OUT/"retained/adapter.json").read_text())
                assert proof["passed"] and proof["runtime_sdk_identity_verified"]
            else:
                raw,value=instrument(runner,report,kind)
                if kind=="original_owner":
                    assert value["count"]==18 and value["failed"]==0
                    assert [c["id"] for c in value["checks"]]==CONTRACT["original_owner_checks"]
                    assert all(c["pass"] is True for c in value["checks"])
                    assert b"OK (18 tests)" in raw and b"INSTRUMENTATION_CODE: -1" in raw
                else:
                    assert value["count"]==10 and value["failed"]==0 and value["accepted"] is True
                    assert [c["name"] for c in value["checks"]]==CONTRACT["bridge_checks"]
                    assert all(c["pass"] is True for c in value["checks"])
                    assert value["sdk_identity"][0]=="3.42.0"
                    assert b"F05_HEAD_BRIDGE_PASS" in raw and b"INSTRUMENTATION_CODE: -1" in raw
            stages[kind]={"passed":True}
        except Exception as error:
            # Preserve failure; later independent groups still run, never erase it.
            stages[kind]={"passed":False,"error":clean_error(error)}
            report_path=OUT/(kind+".json")
            if report_path.exists():
                try:
                    bad=[c for c in json.loads(report_path.read_text()).get("checks",[]) if c.get("pass") is not True]
                    print(kind+" failed checks: "+clean_error(json.dumps(bad)),flush=True)
                except Exception as reporting_error:print(kind+" report unreadable: "+clean_error(reporting_error),flush=True)
            raw_path=OUT/(kind+".instrumentation.txt")
            if raw_path.exists():print(clean_error(raw_path.read_text(errors="replace")),flush=True)
        print(kind+" outcome: "+json.dumps(stages[kind]),flush=True)
        write("runtime.json",{**IDENTITY,"stages":stages,"installed_apks":installs,
            "accepted":len(stages)==3 and all(s["passed"] for s in stages.values()),"f05_full_accepted":False,"ui_accepted":False})
    assert all(s["passed"] for s in stages.values()),stages
def collect():
    OUT.mkdir(parents=True,exist_ok=True)
    for name,path in (("build-logs","build/session-android/logs"),("host-native-audit","build/host-session-android/native"),
                      ("shadow","build/f05-driver/retained"),("dav-logs","build/webdav-android/logs")):
        src=ROOT/path
        if src.exists():shutil.copytree(src,OUT/name,dirs_exist_ok=True)
    write("completion.json",{**IDENTITY,"job_status":os.environ.get("F05_JOB_STATUS","unknown"),
        "scope":"Android read-only bridge; not whole F05",
        "not_executed":["sessionprobe SDK3.40-only side workflow","GTK/Apple/Windows F05","Opus conflict detail UI","real multihead conflict integration","4096 native boundary"]})
    print("F05 collect: runtime_report="+str((OUT/"runtime.json").exists())+", packages_report="+str((OUT/"packages.json").exists())+", job_status="+os.environ.get("F05_JOB_STATUS","unknown"),flush=True)
    # No fixture private directory or generated login data is included.
def require(ok,reason):
    if not ok:raise AssertionError(reason)
def identity(doc,label):
    require(all(str(doc.get(k))==v for k,v in IDENTITY.items()),label+" source/run/attempt mismatch")
def audit():
    guard()
    require(os.environ.get("F05_SOURCE_JOB_RESULT")=="success","Producer job did not succeed; retain its failure")
    require(os.environ.get("F05_SOURCE_ARTIFACT_ID","").isdigit(),"Exact producer artifact ID missing")
    hash_report=json.loads((OUT/"hash-owner.json").read_text());identity(hash_report,"OPDSHash owner")
    require(hash_report["owner_source_tree"]==CONTRACT["hash_source_tree"] and hash_report["package"]=="EXReaderOPDSHash" and hash_report["version"]=="0.1.0","Hash package/source identity")
    require(hash_report["ndk"]=="27.0.12077973" and hash_report["abi"]=="x86_64" and hash_report["platform"]=="android-26","Hash owner ABI/toolchain")
    require(hash_report["files"]==hash_inventory(OUT/"hash/android/stage"),"Hash artifact inventory changed")
    require(hash_report["cache_sha256"]==sha(OUT/"hash/android/build/CMakeCache.txt"),"Hash CMake configuration changed")
    calls=[json.loads(line) for line in (OUT/"hash-proof-calls.jsonl").read_text().splitlines()]
    require(len(calls)>=10 and all(all(str(row.get(k))==v for k,v in IDENTITY.items()) for row in calls),"Native/Gradle hash proof entries missing")
    names=["admission.json","packages.json","runtime.json","retained/adapter.json","retained/original-ui/result.json",
        "host-native-audit/result.json","original_owner.json","bridge.json","host-sync-source-sets.json",
        "bridge-source-sets.json","shadow/java-adapter.json","shadow/source-sets.json"]
    docs={}
    for name in names:
        require((OUT/name).is_file(),"Required evidence missing: "+name)
        docs[name]=json.loads((OUT/name).read_text())
    for name in ("admission.json","packages.json","runtime.json","host-native-audit/result.json"):
        identity(docs[name],name);require(docs[name]["accepted"] is True,name+" did not pass")
    require(set(docs["runtime.json"]["stages"])=={"original_owner","retained","bridge"},"Runtime stage set changed")
    require(all(v["passed"] is True for v in docs["runtime.json"]["stages"].values()),"Runtime stage failure retained")
    for filename,names_key,name_key,marker in (
        ("original_owner","original_owner_checks","id",b"OK (18 tests)"),
        ("bridge","bridge_checks","name",b"F05_HEAD_BRIDGE_PASS")):
        doc=docs[filename+".json"];identity(doc,filename)
        require(doc["api"]==34 and doc["abi"]=="x86_64",filename+" API/ABI mismatch")
        expected=CONTRACT[names_key]
        require(doc["count"]==len(expected) and doc["failed"]==0,filename+" count or failed check")
        require([c[name_key] for c in doc["checks"]]==expected,filename+" check name/order differs")
        require(all(c["pass"] is True for c in doc["checks"]),filename+" check did not pass")
        raw=(OUT/(filename+".instrumentation.txt")).read_bytes()
        require(marker in raw and b"INSTRUMENTATION_CODE: -1" in raw,filename+" completion marker missing")
    require(docs["bridge.json"]["accepted"] is True and docs["bridge.json"]["sdk_identity"][0]=="3.42.0","Bridge runtime SDK/acceptance")
    for claim in ("f05_full_accepted","ui_accepted","real_multihead_conflict_accepted","limit_4096_runtime_accepted"):
        require(docs["bridge.json"][claim] is False,"Out-of-scope claim changed: "+claim)
    original=docs["retained/original-ui/result.json"];identity(original,"retained")
    require(original["accepted"] is True and original["checks"]==16,"Retained sixteen did not pass")
    spec=CONTRACT["retained_suites"]["android-host-sync-16"]
    require([p["phase"] for p in original["phases"]]==list(spec["phases"]),"Original phase order")
    for phase in original["phases"]:
        identity(phase,"phase "+phase["phase"])
        require(phase["api"]==34 and phase["abi"]=="x86_64","Phase API/ABI")
        require(phase["expected_sdk_version"]=="3.42.0","Phase actual SDK version")
        require([c["name"] for c in phase["checks"]]==spec["phases"][phase["phase"]],"Original phase check order")
        require(phase["count"]==len(spec["phases"][phase["phase"]]) and all(c["pass"] is True for c in phase["checks"]),"Original phase assertion failure")
        raw=(OUT/"retained/original-ui"/(phase["phase"]+"-instrumentation.txt")).read_bytes()
        require(("HOST_SYNC_UI_PASS "+phase["phase"]).encode() in raw and b"INSTRUMENTATION_CODE: -1" in raw,"Retained phase completion marker")
    require(len({p["pid"] for p in original["phases"]})==4,"Four real PIDs missing")
    require([b["phase"] for b in original["boundaries"]]==["first","secure-reopen"],"Two original boundary order")
    require(all(b["real_request_blocked"] is True and b["ui_action_observed"] is True for b in original["boundaries"]),"Real cancellation/background boundary missing")
    adapter=docs["retained/adapter.json"]
    require(adapter["passed"] is True and adapter["runtime_sdk_identity_verified"] is True and adapter["original_file_unchanged"] is True,"Retained adapter did not pass")
    meta=docs["shadow/java-adapter.json"];identity(meta,"Java adapter")
    require(adapter["java_adapter"]==meta,"Runtime Java adapter does not match artifact")
    proof=docs["shadow/source-sets.json"]
    require(proof==docs["host-sync-source-sets.json"] and proof==adapter["source_sets"],"Canonical HostSync sourceSet proof differs")
    before,after=proof["before"],proof["after"];old=proof["original"];shadow=proof["shadow"]
    require(old==meta["original_directory"] and shadow==meta["shadow_directory"],"Java source directories differ")
    require(old.endswith("/tests/reader_host_session_android/java") and shadow.endswith("/build/f05-driver/retained/java"),"Unapproved Java source directory")
    require(before.count(old)==1 and shadow not in before and proof["exact_replacements"]==1,"SourceSet original count")
    require(after==[shadow if x==old else x for x in before],"SourceSet replacement changed unrelated directories")
    require(sha(OUT/"shadow/init.gradle")==meta["init_sha256"],"Retained init changed")
    source=ROOT/"tests/reader_host_session_android/java";copied=OUT/"shadow/java"
    inventory=meta["inventory"]
    require({p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}==set(inventory),"Original Java file set changed")
    require({p.relative_to(copied).as_posix() for p in copied.rglob("*") if p.is_file()}==set(inventory),"Shadow Java file set changed")
    for rel,row in inventory.items():
        original_bytes=(source/rel).read_bytes();adapted_bytes=(copied/rel).read_bytes()
        require(hashlib.sha256(original_bytes).hexdigest()==row["original_sha256"] and hashlib.sha256(adapted_bytes).hexdigest()==row["shadow_sha256"],"Java byte identity "+rel)
        if rel=="org/exreader/host/HostSyncTest.java":
            old_expr=b'expectedSdk.equals("3.40.0")||expectedSdk.equals("3.41.0")'
            new_expr=old_expr+b'||expectedSdk.equals("3.42.0")'
            require(original_bytes.count(old_expr)==1 and adapted_bytes==original_bytes.replace(old_expr,new_expr,1),"Java adapter exceeds approved expression")
        else:require(original_bytes==adapted_bytes,"Unrelated original Java changed")
    python_original=ROOT/"tests/reader_host_session_android/run_ui.py"
    python_shadow=OUT/"retained/original-runner-sdk342.py"
    old_cli=b"choices=('3.40.0','3.41.0')";new_cli=b"choices=('3.40.0','3.41.0','3.42.0')"
    require(python_original.read_bytes().count(old_cli)==1 and python_shadow.read_bytes()==python_original.read_bytes().replace(old_cli,new_cli,1),"Python CLI adapter differs")
    bridge=docs["bridge-source-sets.json"]
    require(bridge["before"]==after and bridge["after"]==after+[bridge["added"]],"Bridge sourceSet not one additive directory")
    require(bridge["added"].endswith("/tests/product/f05_android_head_bridge_20261103/java") and bridge["added"] not in after,"Bridge source directory differs")
    packages=docs["packages.json"]["apks"]
    for name,row in packages.items():require(sha(OUT/"apks"/name)==row["sha256"] and (OUT/"apks"/name).stat().st_size==row["bytes"],"APK artifact identity "+name)
    for name,runner in (("original-owner.apk","ProductOwnerTest"),("host-sync.apk","HostSyncTest"),("head-bridge.apk","HeadBridgeTest")):
        manifest=OUT/(name+".manifest.txt");require(sha(manifest)==packages[name]["manifest_sha256"],"Manifest report hash "+name)
        pkg,runners=xml_identity(manifest.read_text())
        require(pkg=="org.exreader.host.test" and len(runners)==1,"Manifest package/count "+name)
        attrs=runners[0]["attrs"]
        require(attrs.get("android:name")=="org.exreader.host."+runner and attrs.get("android:targetPackage")=="org.exreader.host","Manifest runner/target "+name)
    expected_installs=[("org.exreader.host","app-debug.apk"),("org.exreader.host.test","original-owner.apk"),
        ("org.exreader.host","app-debug.apk"),("org.exreader.host.test","host-sync.apk"),("org.exreader.host","app-debug.apk"),
        ("org.exreader.host.test","head-bridge.apk"),("org.exreader.host","app-debug.apk")]
    installs=docs["runtime.json"]["installed_apks"];require(len(installs)==len(expected_installs),"Installation evidence missing")
    for row,(pkg,name) in zip(installs,expected_installs):
        require(row["package"]==pkg and row["sha256"]==packages[name]["sha256"] and row["bytes"]==packages[name]["bytes"],"Installed package identity "+name)
    write("acceptance.json",{**IDENTITY,"artifact_id":os.environ["F05_SOURCE_ARTIFACT_ID"],"producer_job":"f05_android",
        "android_readonly_bridge_accepted":True,"original_owner":18,"retained":16,"distinct_pids":4,
        "blocked_boundaries":2,"bridge":10,"f05_full_accepted":False,"ui_accepted":False,"formal_accepted":False})
    print("F05 Android read-only bridge accepted: owner18 + retained16/4PID/2boundaries + bridge10; full F05 remains false",flush=True)
prepare_hash=prepare_hash_owner
hash_proof=hash_owner_proof

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("admission","prepare-hash","hash-proof","package","runtime","collect","audit"));mode=parser.parse_args().mode
    try:globals()[mode.replace("-","_")]()
    except Exception as error:
        reason=clean_error(type(error).__name__+": "+str(error)+"\n"+traceback.format_exc(limit=4))
        print("F05 "+mode+" failed: "+reason,flush=True)
        write(mode+"-failure.json",{**IDENTITY,"mode":mode,"accepted":False,"reason":reason})
        raise
