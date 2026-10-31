#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only production Apple host build and real app-UID admission exercise."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
from build import current, sha, run, SDK_SHA
sys.path.insert(0,str(ROOT/"tools"))
from apple_swift import flags

CORE = {"clean-admits-before-sdk","pending-refuses-before-sdk","missing-binding-refuses-before-sdk",
        "last-borrow-blocks-owner","final-borrow-release-allows-owner","fresh-process-pending-refusal"}
BUNDLE = "org.exreader.c02qualification"
SOURCES = ("examples/apple/HostSDK.swift","examples/apple/HostModel.swift","examples/apple/HostViews.swift",
           "examples/apple/HostC02Admission.swift","tools/apple_swift.py","tools/build_apple_host.py","tools/build_apple_product.py")
PHASES = ("enrollment-crash","pending-crash","baseline","fresh","fresh-preserve")

def native_identity(path):
    descriptor = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        value = os.fstat(descriptor)
        row = dict(device=value.st_dev,inode=value.st_ino,mode=value.st_mode,uid=value.st_uid,
                   nlink=value.st_nlink,size=value.st_size,euid=os.geteuid())
        if stat.S_ISREG(value.st_mode):
            digest = hashlib.sha256()
            while True:
                data = os.read(descriptor,65536)
                if not data:
                    break
                digest.update(data)
            row["sha256"] = digest.hexdigest()
        return row
    finally:
        os.close(descriptor)

def retain_native(home,evidence,phase):
    mappings = []
    roots = (("authority",home/".exreader-c02-admission"),
             ("libraries",home/"Library/Application Support/EXReaderC02Review"),
             ("model",home/"Library/Application Support/EXReader"))
    for kind,root in roots:
        if not root.exists():
            continue
        destination = evidence/"native"/phase/kind
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(root,destination)
        entries = {".":native_identity(root)}
        for path in sorted(root.rglob("*")):
            entries[path.relative_to(root).as_posix()] = native_identity(path)
        mappings.append(dict(kind=kind,actual_root=str(root),archive_root=destination.relative_to(evidence).as_posix(),
                             fstat=entries))
    output = home/"Documents/c02-evidence"
    if output.exists():
        shutil.copytree(output,evidence/"runtime"/phase)
    (evidence/(phase+"-native-map.json")).write_text(json.dumps(
        dict(scope=native_identity(home),canonical_home=str(home.resolve()),mappings=mappings),indent=2)+"\n")

def authenticate_install(prefix,identity_name,target,source):
    identity = json.loads((prefix/identity_name).read_text())
    assert identity["source"] == source and identity["frozen_sdk"] == SDK_SHA and identity["target"] == target
    assert identity["run"] == os.environ["GITHUB_RUN_ID"] and identity["attempt"] == os.environ["GITHUB_RUN_ATTEMPT"]
    for name,digest in identity["files"].items():
        assert sha(prefix/name) == digest,name

def build_apps(target,out,sdk,product,evidence,source):
    platform = "macos" if target == "macos" else "simulator"
    run(sys.executable,"tools/build_apple_host.py","--sdk",sdk,"--sdk-version","3.42.0",
        "--product-prefix",product,"--platform",platform,"--output",out/"host")
    production = out/"host/EXReader.app"
    production_binary = production/("Contents/MacOS/EXReader" if target == "macos" else "EXReader")
    run("codesign","--verify","--deep","--strict",production)
    installed = json.loads((out/"host/build.json").read_text())
    assert installed["c02_admission"] is True and installed["source_sha"] == source
    app = out/"Runtime.app"
    mobile = target != "macos"
    binary = app/("C02Runtime" if mobile else "Contents/MacOS/C02Runtime")
    resources = app if mobile else app/"Contents/Resources"
    frameworks = app/("Frameworks" if mobile else "Contents/Frameworks")
    for path in (binary.parent,resources,frameworks):
        path.mkdir(parents=True,exist_ok=True)
    original_resources = production if mobile else production/"Contents/Resources"
    for name in ("Sample.epub","Sample.pdf","Reader.otf","reader-catalog-v1.sql"):
        shutil.copyfile(original_resources/name,resources/name)
    native_sdk = "macosx" if not mobile else "iphonesimulator"
    sysroot = subprocess.check_output(["xcrun","--sdk",native_sdk,"--show-sdk-path"],text=True).strip()
    architecture = "arm64" if mobile else subprocess.check_output(["uname","-m"],text=True).strip()
    triple = architecture+("-apple-ios15.0-simulator" if mobile else "-apple-macosx12.0")
    core = ("HostSDK.swift","HostC02Admission.swift","HostModel.swift","HostCatalog.swift","HostAccount.swift",
            "HostSearch.swift","HostNavigation.swift","HostReadingRecords.swift","HostOrganization.swift")
    swift_sources = [ROOT/"examples/apple"/name for name in core]
    command = ["xcrun","--sdk",native_sdk,"swiftc","-swift-version","5","-O","-parse-as-library",
               "-D","EXR_APPLE_C02_REVIEW","-sdk",sysroot,"-target",triple,"-I",sdk/"include",
               "-L",sdk/"lib","-lexreader",*flags(sdk,product,c02_prefix=product),
               "-Xlinker","-rpath","-Xlinker","@executable_path/Frameworks" if mobile else "@executable_path/../Frameworks",
               ROOT/"bindings/swift/EXReader.swift",*swift_sources,
               ROOT/"tests/migration/apple_c02_host_20261031/HostC02Runtime.swift","-o",binary,
               "-Xlinker","-map","-Xlinker",evidence/"runtime-link.map"]
    run(*command)
    for library in (sdk/"lib").glob("libexreader*.dylib"):
        shutil.copyfile(library,frameworks/library.name)
        run("codesign","--force","--sign","-",frameworks/library.name)
    info = dict(CFBundleExecutable="C02Runtime",CFBundleIdentifier=BUNDLE,CFBundleName="C02Runtime",
                CFBundlePackageType="APPL",CFBundleVersion="1",CFBundleShortVersionString="1.0",
                EXRSourceSHA=source,EXRRun=os.environ["GITHUB_RUN_ID"],EXRAttempt=os.environ["GITHUB_RUN_ATTEMPT"])
    if mobile:
        info.update(MinimumOSVersion="15.0",LSRequiresIPhoneOS=True,UIDeviceFamily=[1,2],UILaunchScreen={},
                    CFBundleSupportedPlatforms=["iPhoneSimulator"])
    else:
        info["LSMinimumSystemVersion"] = "12.0"
    plist = app/("Info.plist" if mobile else "Contents/Info.plist")
    plist.write_bytes(plistlib.dumps(info))
    run("codesign","--force","--deep","--sign","-",app)
    run("codesign","--verify","--deep","--strict",app)
    symbols = subprocess.check_output(["nm","-g",str(binary)],text=True)
    (evidence/"runtime-symbols.txt").write_text(symbols)
    assert "_pc02_scope_create" in symbols if mobile else "_pc02_sdk_open_user" in symbols
    assert "_pc02_check" in symbols and "_pc02_close" in symbols
    shutil.copyfile(out/"host/product-link.json",evidence/"production-product-link.json")
    shutil.copytree(production,evidence/"bundles/production.app")
    shutil.copytree(app,evidence/"bundles/runtime.app")
    (evidence/"build.json").write_text(json.dumps(installed,indent=2)+"\n")
    installed_root = evidence/"installed"
    for name in installed["c02_installed_files"]:
        destination = installed_root/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(product/name,destination)
        assert sha(destination) == installed["c02_installed_files"][name]
    shutil.copyfile(sdk/"c02-sdk-identity.json",installed_root/"c02-sdk-identity.json")
    shutil.copyfile(product/"c02-product-identity.json",installed_root/"c02-product-identity.json")
    return app,binary,dict(production=sha(production_binary),runtime=sha(binary),command=list(map(str,command)))

def simulator():
    devices = json.loads(subprocess.check_output(["xcrun","simctl","list","devices","available","--json"],text=True))
    candidates = [(runtime,device) for runtime,rows in devices["devices"].items() for device in rows
                  if "iOS" in runtime and device["name"].startswith("iPhone") and device.get("isAvailable",False)]
    assert candidates,"no actual available iPhone simulator"
    _,device = sorted(candidates,key=lambda row:(row[0],row[1]["name"]),reverse=True)[0]
    udid = device["udid"]
    if device["state"] != "Booted":
        run("xcrun","simctl","boot",udid)
    subprocess.run(["xcrun","simctl","bootstatus",udid,"-b"],check=True,timeout=180)
    return udid

def wait_file(path,process,timeout=60):
    limit = time.monotonic()+timeout
    while time.monotonic()<limit:
        if path.is_file():
            return
        if process.poll() is not None:
            raise AssertionError("app exited before actual marker: "+str(path)+" exit="+str(process.returncode))
        time.sleep(0.2)
    raise AssertionError("actual app marker deadline: "+str(path))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target",choices=("macos","iphonesimulator"),required=True)
    args = parser.parse_args()
    source = current()
    out = ROOT/"build/apple-c02"/args.target
    evidence = out/"evidence"
    evidence.mkdir(parents=True,exist_ok=False)
    sdk,product = out/"sdk",out/"products"
    home = None
    receipt = dict(source=source,run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                   platform=args.target,full_c02_acceptance=False,actual_sdk=True,passed=False)
    try:
        authenticate_install(sdk,"c02-sdk-identity.json",args.target,source)
        authenticate_install(product,"c02-product-identity.json",args.target,source)
        qualified_sources = list(SOURCES)
        for folder in ("extras/migration/posix_c02_admission_20261031","extras/migration/posix_c02_sdk_admission_20261031"):
            qualified_sources += [path.relative_to(ROOT).as_posix() for path in (ROOT/folder).rglob("*") if path.is_file()]
        (evidence/"source-files.json").write_text(json.dumps(
            {name:dict(bytes=(ROOT/name).stat().st_size,sha256=sha(ROOT/name)) for name in qualified_sources},indent=2)+"\n")
        for name in qualified_sources:
            destination = evidence/"source"/name
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,destination)
        app,binary,build = build_apps(args.target,out,sdk,product,evidence,source)
        receipt["binaries"] = build
        udid = None
        if args.target == "iphonesimulator":
            udid = simulator()
            run("xcrun","simctl","install",udid,app)
            home = Path(subprocess.check_output(["xcrun","simctl","get_app_container",udid,BUNDLE,"data"],text=True).strip())
        else:
            home = Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve()
        phase_results = []
        for phase in PHASES:
            arguments = ["--phase",phase]+(["-EXRFreshState"] if phase == "fresh-preserve" else [])
            command = (["xcrun","simctl","launch","--console",udid,BUNDLE,*arguments] if udid
                       else [str(binary),*arguments])
            log = evidence/(phase+".log")
            with log.open("wb") as stream:
                process = subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
                try:
                    runtime = home/"Documents/c02-evidence"
                    marker = runtime/(phase+"-barrier.json" if phase.endswith("-crash") else phase+".json")
                    wait_file(marker,process)
                    if phase.endswith("-crash"):
                        reached = json.loads(marker.read_text())
                        expected = 1002 if phase == "enrollment-crash" else 1102
                        assert reached["phase"] == expected and reached["source"] == source and reached["uid"] == os.geteuid()
                        if udid:
                            run("xcrun","simctl","terminate",udid,BUNDLE)
                        else:
                            os.kill(process.pid,signal.SIGKILL)
                        status = process.wait(timeout=30)
                        if not udid:
                            assert status == -signal.SIGKILL
                        phase_results.append(dict(phase=phase,barrier=reached,exit=status,
                                                  kill_method="simctl terminate" if udid else "SIGKILL"))
                    else:
                        status = process.wait(timeout=60)
                        assert status == 0,(phase,status,log.read_text())
                        report = json.loads(marker.read_text())
                        assert report["complete"] is True and report["passed"] is True
                        assert report["source"] == source and report["platform"] == args.target
                        assert report["run"] == receipt["run"] and report["attempt"] == receipt["attempt"]
                        assert all(row["passed"] is True for row in report["cases"])
                        if udid and phase != "fresh-preserve":
                            assert report["scope_factory"] and all(row["fd_cloexec"] and
                                row["device"] == row["expected_device"] and row["inode"] == row["expected_inode"]
                                for row in report["scope_factory"])
                        phase_results.append(dict(phase=phase,report=report,exit=status))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=30)
                    retain_native(home,evidence,phase)
        rows = [row for phase in phase_results if "report" in phase for row in phase["report"]["cases"]]
        assert len({row["name"] for row in rows}) == len(rows)
        core = [row for row in rows if row["name"] in CORE]
        assert {row["name"] for row in core} == CORE
        fresh = next(row["observation"] for row in core if row["name"] == "fresh-process-pending-refusal")
        pending = next(row["observation"] for row in core if row["name"] == "pending-refuses-before-sdk")
        assert fresh["pid"] != pending["pid"]
        admission = dict(schema="c02-host-admission-v1",source=source,run=receipt["run"],attempt=receipt["attempt"],
                         platform=args.target,actual_sdk=True,complete=True,passed=True,cases=core,
                         extended_cases=[row for row in rows if row["name"] not in CORE],phases=phase_results)
        (evidence/"admission.json").write_text(json.dumps(admission,indent=2)+"\n")
        (evidence/"observations.log").write_text("".join("C02-HOST-OBS "+json.dumps(row["observation"],sort_keys=True)+"\n" for row in core))
        receipt.update(passed=True,runtime_cases=len(rows),actual_app_uid=os.geteuid(),scope_home=str(home),
                       producer_native_map="*-native-map.json")
    except BaseException as error:
        receipt["error"] = type(error).__name__+":"+str(error)
        if home is not None:
            for path in (home/"Documents/c02-evidence/failure.json",
                         home/"Library/Application Support/EXReader/host-log.txt"):
                if path.is_file():
                    print(json.dumps(dict(diagnostic=str(path),text=path.read_text(errors="backslashreplace")[-24000:])),flush=True)
        for path in sorted(evidence.glob("*.log")):
            print(json.dumps(dict(diagnostic=path.name,text=path.read_text(errors="backslashreplace")[-16000:])),flush=True)
        raise
    finally:
        (evidence/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
        files = [path for path in sorted(evidence.rglob("*")) if path.is_file() and path.name != "file-hashes.json"]
        (evidence/"file-hashes.json").write_text(json.dumps([
            dict(path=path.relative_to(evidence).as_posix(),bytes=path.stat().st_size,sha256=sha(path))
            for path in files],indent=2)+"\n")

if __name__ == "__main__":
    main()
