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
    write("admission.json",{**IDENTITY,"accepted":True,"manifest_parser_regression":manifest_parser_regression(),"contract_sha256":sha(D/"contract.json"),"changes":actual,
        "files":{p:sha(ROOT/p) for p in CONTRACT["paths"]},"sdk_freeze":CONTRACT["sdk_freeze"]})
def xml_identity(text):
    android_uri="http://schemas.android.com/apk/res/android"
    nodes=[];stack=[];namespaces={}
    for line in text.splitlines():
        stripped=line.lstrip();indent=len(line)-len(stripped)
        if stripped.startswith("N: "):
            match=re.fullmatch(r"N: ([A-Za-z_][A-Za-z0-9_.-]*)=([^\s]+)(?: \(line=\d+\))?",stripped)
            assert match,"Malformed namespace declaration"
            prefix,uri=match.groups()
            assert prefix not in namespaces,"Repeated namespace declaration"
            namespaces[prefix]=uri
        elif stripped.startswith("E: "):
            while stack and stack[-1][0]>=indent:stack.pop()
            tag=stripped[3:].split()[0]
            node={"tag":tag,"attrs":{},"parent":stack[-1][1] if stack else None}
            nodes.append(node);stack.append((indent,node))
        elif stripped.startswith("A: "):
            assert stack and indent>stack[-1][0],"Attribute outside element"
            match=re.fullmatch(r'A: ([^ (=]+)(?:\([^)]*\))?=(.+)',stripped)
            assert match,"Malformed XML attribute"
            key,raw_value=match.groups()
            if key.startswith(android_uri+":"):
                key="android:"+key[len(android_uri)+1:]
            elif ":" in key:
                prefix,local=key.split(":",1)
                assert namespaces.get(prefix)==android_uri,"Unexpected XML attribute namespace"
                key="android:"+local
            attrs=stack[-1][1]["attrs"]
            assert key not in attrs,"Duplicate canonical XML attribute"
            quoted=re.fullmatch(r'"([^"]*)"(?: \(Raw: "([^"]*)"\))?',raw_value)
            if key in ("package","android:name","android:targetPackage"):
                assert quoted,"Identity XML attribute must have a complete quoted value"
            if quoted:
                value,raw_copy=quoted.groups()
                assert raw_copy is None or raw_copy==value,"Conflicting XML raw value"
                attrs[key]=value
            else:
                attrs[key]=raw_value
    roots=[n for n in nodes if n["tag"]=="manifest"]
    assert len(roots)==1 and roots[0]["parent"] is None,"Manifest root missing, nested or repeated"
    runners=[n for n in nodes if n["tag"]=="instrumentation"]
    assert all(n["parent"] is roots[0] for n in runners),"Instrumentation must be direct manifest child"
    return roots[0]["attrs"].get("package"),runners
def require_manifest(text,runner):
    package,runners=xml_identity(text)
    assert package=="org.exreader.host.test" and len(runners)==1,"Instrumentation package/count"
    attrs=runners[0]["attrs"]
    assert attrs.get("android:name")=="org.exreader.host."+runner,"Exact instrumentation runner"
    assert attrs.get("android:targetPackage")=="org.exreader.host","Exact instrumentation target"
    return package,runners
def manifest_parser_regression():
    uri="http://schemas.android.com/apk/res/android"
    template='''N: android=http://schemas.android.com/apk/res/android (line=2)
  E: manifest (line=2)
    A: http://schemas.android.com/apk/res/android:compileSdkVersion(0x01010572)=35
    A: http://schemas.android.com/apk/res/android:compileSdkVersionCodename(0x01010573)="15" (Raw: "15")
    A: package="org.exreader.host.test" (Raw: "org.exreader.host.test")
    A: platformBuildVersionCode=35
    A: platformBuildVersionName=15
      E: uses-sdk (line=5)
        A: http://schemas.android.com/apk/res/android:minSdkVersion(0x0101020c)=26
        A: http://schemas.android.com/apk/res/android:targetSdkVersion(0x01010270)=35
      E: instrumentation (line=9)
        A: http://schemas.android.com/apk/res/android:label(0x01010001)="Tests for org.exreader.host" (Raw: "Tests for org.exreader.host")
        A: http://schemas.android.com/apk/res/android:name(0x01010003)="org.exreader.host.RUNNER" (Raw: "org.exreader.host.RUNNER")
        A: http://schemas.android.com/apk/res/android:targetPackage(0x01010021)="org.exreader.host" (Raw: "org.exreader.host")
        A: http://schemas.android.com/apk/res/android:handleProfiling(0x01010022)=false
        A: http://schemas.android.com/apk/res/android:functionalTest(0x01010023)=false
      E: application (line=16)
        A: http://schemas.android.com/apk/res/android:debuggable(0x0101000f)=true
        A: http://schemas.android.com/apk/res/android:extractNativeLibs(0x010104ea)=false
          E: uses-library (line=19)
            A: http://schemas.android.com/apk/res/android:name(0x01010003)="android.test.runner" (Raw: "android.test.runner")
'''
    actual=[]
    expected=[
        ("ProductOwnerTest","b3beaf7e3e67b075c6326131f396b6a6db42c84b28175fadc83ade473646a22b"),
        ("HostSyncTest","51bdd2b4334306b850d3cecabd3ad262cb86714189f0a4c2533880e014c0a8ad"),
        ("HeadBridgeTest","673fd08e72a813259a266395bb3fc72bc42fa0badd5400938c0c870878e7fadf")]
    checks=[]
    for runner,expected_hash in expected:
        text=template.replace("RUNNER",runner)
        assert hashlib.sha256(text.encode()).hexdigest()==expected_hash,"Actual manifest fixture changed"
        require_manifest(text,runner);actual.append(text)
        checks.append({"name":"actual_"+runner,"passed":True,"sha256":expected_hash,"expected":"accept"})
    text=actual[0]
    short=text.replace("A: "+uri+":","A: android:")
    require_manifest(short,"ProductOwnerTest")
    checks.append({"name":"equivalent_bound_short_prefix","passed":True,"expected":"accept"})
    name_line='        A: '+uri+':name(0x01010003)="org.exreader.host.ProductOwnerTest" (Raw: "org.exreader.host.ProductOwnerTest")\n'
    duplicate=name_line+'        A: android:name(0x01010003)="org.exreader.host.ProductOwnerTest" (Raw: "org.exreader.host.ProductOwnerTest")\n'
    negatives=[
        ("wrong_namespace",text.replace(uri+":name",uri+"/impostor:name")),
        ("duplicate_canonical_alias",text.replace(name_line,duplicate)),
        ("wrong_runner",text.replace("org.exreader.host.ProductOwnerTest","org.exreader.host.WrongRunner")),
        ("wrong_target",text.replace(':targetPackage(0x01010021)="org.exreader.host"',':targetPackage(0x01010021)="org.exreader.other"')),
        ("nested_name_cannot_supply_runner",text.replace(name_line,"").replace('"android.test.runner"','"org.exreader.host.ProductOwnerTest"')),
        ("duplicate_instrumentation",text+'      E: instrumentation (line=99)\n'+name_line)]
    for name,negative in negatives:
        variants=[negative]
        if name=="duplicate_canonical_alias":
            variants.append(text.replace(name_line,name_line+'        A: android:name(0x01010003)=123\n'))
        elif name=="wrong_namespace":
            variants.append(text.replace(name_line,'        A: '+uri+'/impostor:name(0x01010003)=123\n'))
        for variant in variants:
            try:require_manifest(variant,"ProductOwnerTest")
            except AssertionError:pass
            else:raise AssertionError("Malformed manifest accepted: "+name)
        checks.append({"name":name,"passed":True,"expected":"reject","variants":len(variants)})
    assert [row["name"] for row in checks]==CONTRACT["manifest_parser_checks"] and len(checks)==10
    return {"checks":checks,"count":10,"passed":True,"actual_manifest_source_run":41602795048,"actual_manifest_source_artifact":13215501646,"runtime_accepted":False}
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
        test_package,runners=require_manifest(xml,runner)
        attrs=runners[0]["attrs"]
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
def instrument(runner,report_name,output_name,timeout=600):
    args=["shell","am","instrument","-w","-r"]
    for key,value in IDENTITY.items():args+=["-e",key,value]
    args+=["-e","sdk_version","3.42.0","org.exreader.host.test/org.exreader.host."+runner]
    failure=None
    try:raw=adb(*args,timeout=timeout)
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
        "scope":"Android read-only bridge plus isolated conflict boundary; not whole F05",
        "not_executed":["sessionprobe SDK3.40-only side workflow","GTK/Apple/Windows F05","Opus conflict detail UI"]})
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
    require(docs["admission.json"].get("manifest_parser_regression")==manifest_parser_regression(),"Parser regression evidence missing or changed")
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
        require_manifest(manifest.read_text(),runner)
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



def boundary_build():
    guard();hash_owner_proof()
    stage=ROOT/"build/f05-boundary-stage"
    require(not stage.exists(),"Boundary isolated stage must be fresh")
    prefixes=("examples/android/","tests/reader_host_session_android/","tests/product/f05_android_head_bridge_20261103/","extras/webdav/android/webdav/","extras/credentials/android/credentials/","extras/android-import-entry/android/importentry/")
    files=[p for p in git("ls-files").splitlines() if p.startswith(prefixes)]
    inventory={}
    for name in files:
        source=ROOT/name
        require(source.is_file() and not source.is_symlink(),"Only regular tracked stage source: "+name)
        target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        inventory[name]=sha(source)
    generated={};generated_directories={}
    for name in ("examples/android/app/src/main/assets","examples/android/app/src/main/jniLibs","tests/reader_host_session_android/debug/res/raw"):
        source=ROOT/name;require(source.is_dir() and not source.is_symlink(),"Generated canonical inputs missing: "+name)
        generated_directories[name]=sorted(p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file())
        require(bool(generated_directories[name]),"Generated directory must not be empty: "+name)
        for p in source.rglob("*"):
            if not p.is_file():continue
            require(not p.is_symlink(),"Generated input symlink")
            rel=p.relative_to(ROOT).as_posix();target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
            generated[rel]=sha(p)
            archived=OUT/"boundary-generated"/rel;archived.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,archived)
            require(sha(target)==generated[rel] and sha(archived)==generated[rel],"Generated input copy changed")
    overlay=CONTRACT["boundary_overlay"]
    original=ROOT/overlay["path"];base=original.read_bytes();addition=(D/"cpp/conflict_boundary_probe.inc").read_bytes()
    require(sha(original)==overlay["base_sha256"],"Original Debug review include changed")
    modified=stage/overlay["path"];modified.write_bytes(base+b"\n"+addition)
    (OUT/"boundary-probe-base.inc").write_bytes(base);(OUT/"boundary-probe-actual.inc").write_bytes(modified.read_bytes())
    baseline={name:sha(OUT/"apks"/name) for name in ("app-debug.apk","app-release-unsigned.apk","original-owner.apk","host-sync.apk","head-bridge.apk")}
    arguments=["gradle","-p",stage/"examples/android","--no-daemon","--stacktrace",
        "-I",D/"bridge.init.gradle","-Pf05Boundary=true","-Pf05EvidenceDir="+str(OUT),
        "-PexrSdk="+str(ROOT/"build/session-android/sdk-stage"),"-PexrSdkVersion=3.42.0",
        "-PexrProduct="+str(ROOT/"build/session-android/product-stage"),"-PexrSync=true","-PexrPageTheme=false",
        "-PexrDav="+str(ROOT/"build/webdav-android/stage-release"),"-PexrSideload="+str(ROOT/"build/session-android/sideload-stage"),
        "-PexrTestRunner=org.exreader.host.ConflictBoundaryTest",":app:assembleDebug",":app:assembleDebugAndroidTest"]
    write("boundary-build.json",{**IDENTITY,"accepted":False,"argv":list(map(str,arguments)),"baseline_apks":baseline,
        "source_inventory":inventory,"generated_inputs":generated,"generated_directories":generated_directories,"overlay_path":overlay["path"],
        "base_sha256":sha(original),"suffix_sha256":sha(D/"cpp/conflict_boundary_probe.inc"),"overlay_sha256":sha(modified)})
    try:raw=command(arguments,timeout=1800)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
        raw=error.output or b""
        if isinstance(raw,str):raw=raw.encode()
        (OUT/"boundary-build.log").write_bytes(raw)
        print("Boundary build failed: "+clean_error(error)+"\n"+clean_error(raw.decode(errors="replace")),flush=True)
        raise
    (OUT/"boundary-build.log").write_bytes(raw)
    for name,digest in inventory.items():
        if name==overlay["path"]:require((stage/name).read_bytes()==base+b"\n"+addition,"Overlay is not original prefix plus probe")
        else:require(sha(stage/name)==digest,"Staged tracked source changed: "+name)
    require(all(sha(OUT/"apks"/name)==digest for name,digest in baseline.items()),"Original APK changed")
    for name,entries in generated_directories.items():
        for location in (ROOT,stage,OUT/"boundary-generated"):
            require(sorted(p.relative_to(location/name).as_posix() for p in (location/name).rglob("*") if p.is_file())==entries,"Generated input file set changed")
    for rel,digest_value in generated.items():
        require(all(sha(location/rel)==digest_value for location in (ROOT,stage,OUT/"boundary-generated")),"Generated input bytes changed after build")

    for name,path in (("boundary-app.apk","debug/app-debug.apk"),("conflict-boundary.apk","androidTest/debug/app-debug-androidTest.apk")):
        shutil.copyfile(stage/"examples/android/app/build/outputs/apk"/path,OUT/"apks"/name)
    aapt=Path(os.environ["ANDROID_HOME"])/"build-tools/35.0.0/aapt2"
    text=command([aapt,"dump","xmltree",OUT/"apks/conflict-boundary.apk","--file","AndroidManifest.xml"]).decode()
    require_manifest(text,"ConflictBoundaryTest");(OUT/"conflict-boundary.apk.manifest.txt").write_text(text)
    app_text=command([aapt,"dump","xmltree",OUT/"apks/boundary-app.apk","--file","AndroidManifest.xml"]).decode()
    app_package,app_runners=xml_identity(app_text);require(app_package=="org.exreader.host" and not app_runners,"Boundary target application identity")
    (OUT/"boundary-app.apk.manifest.txt").write_text(app_text)
    packages={name:{"sha256":sha(OUT/"apks"/name),"bytes":(OUT/"apks"/name).stat().st_size,
        "manifest_sha256":sha(OUT/(name+".manifest.txt"))} for name in ("boundary-app.apk","conflict-boundary.apk")}
    write("boundary-packages.json",{**IDENTITY,"accepted":True,"apks":packages})
    report=json.loads((OUT/"boundary-build.json").read_text());report["accepted"]=True
    report["tracked_stage_verified"]=True;report["original_apks_unchanged"]=True;report["generated_inputs_producer_verified"]=True;write("boundary-build.json",report)

def boundary_runtime():
    guard();packages=json.loads((OUT/"boundary-packages.json").read_text());installs=[]
    identity(packages,"Boundary packages");require(packages["accepted"] is True,"Boundary packages incomplete")
    try:
        adb("shell","am","force-stop","org.exreader.host")
        for package,name in (("org.exreader.host","boundary-app.apk"),("org.exreader.host.test","conflict-boundary.apk")):
            adb("install","-r","-t",OUT/"apks"/name)
            installs.append(installed(package,packages["apks"][name]["sha256"]))
        installs.append(installed("org.exreader.host",packages["apks"]["boundary-app.apk"]["sha256"]))
        raw,report=instrument("ConflictBoundaryTest","f05-conflict-boundary-report.json","boundary",timeout=1800)
        require(report["count"]==8 and report["failed"]==0 and report["accepted"] is True,"Boundary eight checkpoints did not all pass")
        require([c["name"] for c in report["checks"]]==CONTRACT["boundary_checks"] and all(c["pass"] is True for c in report["checks"]),"Boundary check identity/failure")
        require(b"F05_CONFLICT_BOUNDARY_PASS" in raw and b"INSTRUMENTATION_CODE: -1" in raw,"Boundary completion marker")
        write("boundary-runtime.json",{**IDENTITY,"accepted":True,"installed_apks":installs})
    except Exception as error:
        print("Boundary runtime failed: "+clean_error(error),flush=True)
        if (OUT/"boundary.json").exists():
            try:print(clean_error(json.dumps([c for c in json.loads((OUT/"boundary.json").read_text()).get("checks",[]) if c.get("pass") is not True])),flush=True)
            except Exception:pass
        write("boundary-runtime.json",{**IDENTITY,"accepted":False,"installed_apks":installs,"error":clean_error(error)})
        raise

def runtime_all():
    failures=[]
    for label,action in (("original_groups",runtime),("conflict_boundary",boundary_runtime)):
        try:action()
        except Exception as error:failures.append(label+": "+clean_error(error))
    require(not failures,"; ".join(failures))

def audit_all():
    audit()
    names=("boundary-build.json","boundary-packages.json","boundary-runtime.json","boundary.json")
    docs={name:json.loads((OUT/name).read_text()) for name in names}
    for name,value in docs.items():identity(value,name);require(value["accepted"] is True,name+" not accepted")
    build=docs["boundary-build.json"];overlay=CONTRACT["boundary_overlay"]
    base=(OUT/"boundary-probe-base.inc").read_bytes();actual=(OUT/"boundary-probe-actual.inc").read_bytes();suffix=(D/"cpp/conflict_boundary_probe.inc").read_bytes()
    require(base==(ROOT/overlay["path"]).read_bytes() and digest(base)==overlay["base_sha256"],"Overlay base identity")
    require(actual==base+b"\n"+suffix and digest(actual)==build["overlay_sha256"] and digest(suffix)==build["suffix_sha256"],"Native Debug overlay exact suffix")
    require(build["base_sha256"]==digest(base) and build["overlay_path"]==overlay["path"],"Native overlay path binding")
    require(build["tracked_stage_verified"] is True and build["original_apks_unchanged"] is True,"Staged source/original APK proof")
    prefixes=("examples/android/","tests/reader_host_session_android/","tests/product/f05_android_head_bridge_20261103/","extras/webdav/android/webdav/","extras/credentials/android/credentials/","extras/android-import-entry/android/importentry/")
    expected={p:sha(ROOT/p) for p in git("ls-files").splitlines() if p.startswith(prefixes)}
    require(build["source_inventory"]==expected,"Exact staged source set")
    require(set(build["baseline_apks"])=={"app-debug.apk","app-release-unsigned.apk","original-owner.apk","host-sync.apk","head-bridge.apk"},"Exactly five original baseline APKs")
    for name,digest_value in build["baseline_apks"].items():require(sha(OUT/"apks"/name)==digest_value,"Original APK overwritten")
    require(build["generated_inputs_producer_verified"] is True,"Generated inputs were not verified before/after the build")
    dirs=build["generated_directories"]
    require(set(dirs)=={"examples/android/app/src/main/assets","examples/android/app/src/main/jniLibs","tests/reader_host_session_android/debug/res/raw"},"Generated input directories differ")
    generated=build["generated_inputs"];archive=OUT/"boundary-generated"
    require({p.relative_to(archive).as_posix() for p in archive.rglob("*") if p.is_file()}==set(generated),"Archived generated input set")
    for name,entries in dirs.items():
        require(bool(entries) and sorted(p.relative_to(archive/name).as_posix() for p in (archive/name).rglob("*") if p.is_file())==entries,"Archived generated directory contents")
    for rel,digest_value in generated.items():
        require(not (archive/rel).is_symlink() and sha(archive/rel)==digest_value,"Archived generated input digest")
    # The auditor rechecks the archived original bytes; the isolated build tree is producer-only.

    packages=docs["boundary-packages.json"]["apks"];require(set(packages)=={"boundary-app.apk","conflict-boundary.apk"},"Boundary APK set")
    for name,row in packages.items():
        require(sha(OUT/"apks"/name)==row["sha256"] and (OUT/"apks"/name).stat().st_size==row["bytes"],"Boundary APK bytes")
        require(sha(OUT/(name+".manifest.txt"))==row["manifest_sha256"],"Boundary manifest digest")
    require_manifest((OUT/"conflict-boundary.apk.manifest.txt").read_text(),"ConflictBoundaryTest")
    pkg,runners=xml_identity((OUT/"boundary-app.apk.manifest.txt").read_text());require(pkg=="org.exreader.host" and not runners,"Boundary app manifest")
    installed_rows=docs["boundary-runtime.json"]["installed_apks"]
    mapping=[("org.exreader.host","boundary-app.apk"),("org.exreader.host.test","conflict-boundary.apk"),("org.exreader.host","boundary-app.apk")]
    require(len(installed_rows)==len(mapping),"Boundary actual installation proof")
    for row,(pkg,name) in zip(installed_rows,mapping):
        require(row["package"]==pkg and row["sha256"]==packages[name]["sha256"] and row["bytes"]==packages[name]["bytes"],"Boundary installed identity")
    source_sets=json.loads((OUT/"boundary-source-sets.json").read_text())
    require(source_sets["after"]==source_sets["before"]+[source_sets["added"]] and source_sets["added"] not in source_sets["before"],"Boundary unique additive sourceSet")
    require(source_sets["added"].endswith("/build/f05-boundary-stage/tests/product/f05_android_head_bridge_20261103/java"),"Boundary isolated source root")
    report=docs["boundary.json"]
    require(report["api"]==34 and report["abi"]=="x86_64" and report["sdk_identity"][0]=="3.42.0" and report["sdk_identity"][1]==report["sdk_identity"][2],"Boundary actual SDK/API/ABI")
    require(report["count"]==8 and report["failed"]==0 and [r["name"] for r in report["checks"]]==CONTRACT["boundary_checks"] and all(r["pass"] is True for r in report["checks"]),"Eight exact actual checkpoints")
    provider=report["provider"];require(len(provider)==4 and provider[0]==provider[1] and "libexreader_product.so" in provider[0] and provider[2]=="4096","Actual native revision provider")
    raw=(OUT/"boundary.instrumentation.txt").read_bytes()
    require(b"F05_CONFLICT_BOUNDARY_PASS" in raw and b"INSTRUMENTATION_CODE: -1" in raw,"Boundary instrumentation complete")
    for flag in ("f05_full_accepted","ui_accepted","transport_end_to_end_accepted"):require(report[flag] is False,"Out-of-scope acceptance")
    require(report["multihead_product_commands"] is True and report["boundary_fixture"]=="public revision API, not SQL writes","Fixture provenance")
    write("conflict-acceptance.json",{**IDENTITY,"artifact_id":os.environ["F05_SOURCE_ARTIFACT_ID"],"accepted":True,
        "original_owner":18,"retained":16,"bridge":10,"parser_controls":10,"new_checkpoints":8,"generated_inputs_audit":"archived bytes rechecked; stage before/after checks certified by producer",
        "android_non_ui_multihead":True,"legal_revision_limit":4096,"f05_full_accepted":False,"ui_accepted":False,"formal_accepted":False})
    print("F05 actual Android conflict and history boundary accepted; original18/16/10 and parser10 preserved; fullF05/UI remain false",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("admission","prepare-hash","hash-proof","package","runtime","runtime-all","boundary-build","boundary-runtime","collect","audit","audit-all"));mode=parser.parse_args().mode
    try:globals()[mode.replace("-","_")]()
    except Exception as error:
        reason=clean_error(type(error).__name__+": "+str(error)+"\n"+traceback.format_exc(limit=4))
        print("F05 "+mode+" failed: "+reason,flush=True)
        write(mode+"-failure.json",{**IDENTITY,"mode":mode,"accepted":False,"reason":reason})
        raise
