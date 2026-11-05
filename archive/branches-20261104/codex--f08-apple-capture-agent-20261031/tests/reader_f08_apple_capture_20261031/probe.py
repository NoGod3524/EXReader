"""Authenticate the existing Release product, then inspect native display-frame access."""
import hashlib, io, json, os, plistlib, signal, stat, subprocess, sys, time, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE="ea3875a9fb96d9c5e4c79c058ffaacb1d1663c1b"
PRODUCER=41186932079
ARTIFACTS={"macos":(13037818282,"7f2693fa03351b6dea5a87583bdc8a257ce6a00e5a609bafe17f69c21c7f32e0"),
    "iphone":(13038628059,"0f91591435e2636f15d4b2821dc45e1628e27acb7eb4c9c02b9d851b53c92f49"),
    "ipad":(13039480840,"9e47d8391f0055ceb973f6e3ccbe0d5dcb4de7906790a1c1911bb9f41cb90c00")}
def command(args,timeout=120):return subprocess.check_output(list(map(str,args)),cwd=ROOT,timeout=timeout)
def api(path):return json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+path]))
def digest(data):return hashlib.sha256(data).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
def main(kind):
    assert os.environ.get("GITHUB_ACTIONS")=="true"
    out=ROOT/"build"/("f08-apple-capture-"+kind);out.mkdir(parents=True)
    report={"source_sha":os.environ["GITHUB_SHA"],"run_id":os.environ["GITHUB_RUN_ID"],"attempt":os.environ["GITHUB_RUN_ATTEMPT"],"platform":kind,"f08_accepted":False,"capability_complete":False}
    process=None
    try:
        aid,expected=ARTIFACTS[kind]
        source,producer=SOURCE,PRODUCER
        if kind=="macos":
            source,producer="f48e433abeeb0487c7967f9f096a89771b86f4cf",41239022325
            aid,expected=13057210599,"e8cf0aca9141244cf52fb406cd5cd19b67144ec650272d3464a3878bb1a3ab17"
        meta=api("actions/artifacts/"+str(aid));data=command(["gh","api",f"repos/NoGod3524/EXReader/actions/artifacts/{aid}/zip"])
        assert not meta["expired"] and meta["workflow_run"]["id"]==producer and meta["workflow_run"]["head_sha"]==source
        assert digest(data)==expected and meta["digest"]=="sha256:"+expected and len(data)==meta["size_in_bytes"]
        save(out/"producer-metadata.json",meta);(out/"producer.zip").write_bytes(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest=json.loads(archive.read("f08-manifest.json"));assert manifest["source_sha"]==source and manifest["run_id"]==str(producer) and manifest["attempt"]=="1" and manifest["kind"]==kind
            files={name:item for name,item in manifest["files"].items() if name.startswith("program/EXReaderHost.app/")}
            assert files
            for name,item in files.items():
                path=PurePosixPath(name);assert ".." not in path.parts and not path.is_absolute() and "\\" not in name and ":" not in name
                b=archive.read(name);assert digest(b)==item["sha256"] and len(b)==item["bytes"]
                p=out/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        report["producer"]={"source_sha":source,"run_id":producer,"attempt":1,"artifact_id":aid,"zip_sha256":expected}
        app=out/"program/EXReaderHost.app";binary=app/("Contents/MacOS/EXReaderHost" if kind=="macos" else "EXReaderHost");binary.chmod(0o755)
        info=plistlib.loads((app/("Contents/Info.plist" if kind=="macos" else "Info.plist")).read_bytes());assert info["EXRSourceSHA"]==source and info["EXRSDKVersion"]=="3.42.0"
        report["program_sha256"]=digest(binary.read_bytes())
        if kind=="macos":
            process=subprocess.Popen([str(binary),"-EXRShelfSeed"],cwd=ROOT,stdout=(out/"app.log").open("wb"),stderr=subprocess.STDOUT)
            report["target_pid"]=process.pid;bundle="org.exreader.host";title=[]
        else:
            sdk=command(["xcrun","--sdk","iphonesimulator","--show-sdk-version"]).decode().strip()
            choices=json.loads(command(["xcrun","simctl","list","devices","available","--json"]))["devices"]
            prefix="iPhone" if kind=="iphone" else "iPad";suffix=".iOS-"+sdk.replace(".","-")
            types=json.loads(command(["xcrun","simctl","list","devicetypes","--json"]))
            save(out/"device-types.json",types)
            by_id={item["identifier"]:item for item in types["devicetypes"]}
            candidates=[]
            for rt,items in choices.items():
                if not rt.endswith(suffix):continue
                for d in items:
                    if not d.get("isAvailable") or not d["name"].startswith(prefix):continue
                    item=by_id[d["deviceTypeIdentifier"]]
                    assert isinstance(item.get("minRuntimeVersion"),int),"Missing native device introduction version"
                    candidates.append({"runtime":rt,"name":d["name"],"udid":d["udid"],"device_type":item["identifier"],
                        "min_runtime_version":item["minRuntimeVersion"],"min_runtime_version_string":item.get("minRuntimeVersionString")})
            assert candidates,"No matching native device"
            selected=max(candidates,key=lambda item:(item["min_runtime_version"],item["name"],item["udid"]))
            report["selection"]={"policy":"Native SDK-matching runtime, then latest device introduction version from simctl devicetypes, with stable name/UDID tie-break","candidates":candidates,"selected":selected}
            rt,name,device=selected["runtime"],selected["name"],selected["udid"]
            report["destination"]={"runtime":rt,"device":name,"udid":device,"simulator_sdk":sdk}
            subprocess.run(["xcrun","simctl","shutdown",device],capture_output=True)
            command(["xcrun","simctl","erase",device]);command(["xcrun","simctl","boot",device]);command(["xcrun","simctl","bootstatus",device,"-b"],timeout=180)
            command(["open","-a","Simulator","--args","-CurrentDeviceUDID",device])
            # A bootstatus return does not prove the installation daemon or the visible simulator surface is ready.
            screenshot=command(["xcrun","simctl","io",device,"screenshot",out/"pre-install.png"],timeout=45)
            report["pre_install_surface_sha256"]=digest((out/"pre-install.png").read_bytes())
            deadline=time.monotonic()+60;ready=False
            while time.monotonic()<deadline:
                listing=command(["xcrun","simctl","spawn",device,"launchctl","list"],timeout=15).decode()
                (out/"pre-install-services.log").write_text(listing)
                matches=[line.split() for line in listing.splitlines() if line.split() and line.split()[-1].endswith(".installd")]
                if any(row[0].isdigit() and int(row[0])>0 for row in matches):ready=True;break
                time.sleep(2)
            report["installation_daemon_ready"]=ready
            assert ready,"Native simulator installd did not become ready within the declared preflight"
            command(["xcrun","simctl","install",device,app]);report["launch"]=command(["xcrun","simctl","launch",device,"org.exreader.host","-EXRShelfSeed"],timeout=60).decode().strip()
            report["destination"]={"runtime":rt,"device":name,"udid":device,"simulator_sdk":sdk};bundle="com.apple.iphonesimulator";title=[name]
        time.sleep(4)
        report["environment"]={"xcode":command(["xcodebuild","-version"]).decode(),"os":command(["sw_vers"]).decode()}
        helper=out/"capture-probe"
        architecture=command(["uname","-m"]).decode().strip()
        command(["xcrun","swiftc","-O","-parse-as-library","-target",architecture+"-apple-macosx15.0",HERE/"Capture.swift","-o",helper],timeout=120)
        report["probe_sha256"]=digest(helper.read_bytes())
        command([helper,out,bundle,*title],timeout=30)
        capture=json.loads((out/"capture.json").read_text());report["capability_complete"]=capture["capability_complete"];report["capture"]=capture
        if kind=="macos":
            report["argument_cases"]=[]
            for label,extra in (("numeric-values",["-EXRFreshState","1"]),("boolean-flags",["-EXRFreshState"]),
                                ("extended-native-task",["-EXRFreshState","1","-EXRF08Launch"]),
                                ("reader-fixtures",["-EXRFreshState","1","-EXRUITestFixtures","1"])):
                process.terminate();process.wait(timeout=15)
                case=out/label;case.mkdir()
                argv=[str(binary),"-EXRShelfSeed",*extra]
                process=subprocess.Popen(argv,cwd=ROOT,stdout=(case/"app.log").open("wb"),stderr=subprocess.STDOUT)
                time.sleep(4)
                command([helper,case,"org.exreader.host"],timeout=30)
                report["argument_cases"].append({"label":label,"argv":argv,"pid":process.pid,"capture":json.loads((case/"capture.json").read_text())})
    except BaseException as e:report["error"]=repr(e)
    finally:
        if process is not None:process.terminate();process.wait(timeout=15)
        save(out/"result.json",report);print("F08_APPLE_CAPTURE",json.dumps(report),flush=True)
    assert report["capability_complete"],"Native screen capture capability unavailable"
if __name__=="__main__":main(sys.argv[1])
