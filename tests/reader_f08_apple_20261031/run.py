"""Actions-only three-target measurements; all original shelf assertions stay intact."""
import argparse, importlib.util, json, os, plistlib, re, shutil, subprocess, sys, traceback
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity, need, save, sha, command
BASE="6c3c75bc793acb2bd369db7ea9d701fb87946a81"
ALLOWED={"tests/reader_f08_apple_20261031/run.py","tests/reader_f08_apple_20261031/audit.py",
         "tests/reader_f08_apple_20261031/Metrics.swift","tests/reader_f08_apple_20261031/profile.json",
         ".github/workflows/dot-f08-apple-20261031.yml"}
def guard():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==ALLOWED,"test-only scope")
def seal(kind):
    guard()
    sdk=kind in ("macos-sdk","iphonesimulator-sdk")
    root=ROOT/"build/raw3-ios-sdk"/kind.removesuffix("-sdk") if sdk else ROOT/"build/f08-apple"/kind/"evidence"
    root.mkdir(parents=True,exist_ok=True)
    paths=([*list((root/"sdk").rglob("*")),*list((root/"raw-products").rglob("*")),*list(root.glob("*.json"))]
           if sdk else list(root.rglob("*")))
    files={p.relative_to(root).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
           for p in sorted(paths) if p.is_file() and p.name!="f08-manifest.json"}
    save(root/"f08-manifest.json",{**identity(),"kind":kind,"files":files,"f08_accepted":False})
def authenticate_inputs():
    values={}
    for target in ("macos","iphonesimulator"):
        roots=list((ROOT/"sdk-input").glob("f08-apple-"+target+"-sdk-*"));need(len(roots)==1,"SDK artifact")
        root=roots[0];meta=json.loads((root/"sdk342-installed-identity.json").read_text())
        need(all(meta.get(k)==v for k,v in identity().items()) and meta["sdk_version"]=="3.42.0" and meta["target"]==target,"SDK identity")
        for key,folder in (("sdk_files","sdk"),("raw_files","raw-products")):
            actual={p.relative_to(root/folder).as_posix() for p in (root/folder).rglob("*") if p.is_file()}
            need(actual==set(meta[key]),"SDK inventory")
            for p,item in meta[key].items():need(sha(root/folder/p)==item["sha256"] and (root/folder/p).stat().st_size==item["bytes"],"SDK bytes")
        values[target]=root
    return values
def extract_metrics(metrics_result):
    raw_objects=[];metrics=[]
    def object_data(oid=None):
        args=["xcrun","xcresulttool","get","object","--legacy","--path",metrics_result,"--format","json"]
        if oid:args+=["--id",oid]
        data=json.loads(command(args));raw_objects.append({"id":oid,"object":data});return data
    def walk(value):
        if isinstance(value,dict):
            yield value
            for child in value.values():yield from walk(child)
        elif isinstance(value,list):
            for child in value:yield from walk(child)
    root=object_data()
    references={node["testsRef"]["id"]["_value"] for node in walk(root) if "testsRef" in node}
    for oid in sorted(references):
        plan=object_data(oid)
        summaries={node["summaryRef"]["id"]["_value"] for node in walk(plan) if "summaryRef" in node}
        for summary in sorted(summaries):
            data=object_data(summary)
            for node in walk(data):
                if "performanceMetrics" in node:metrics.extend(node["performanceMetrics"].get("_values",[]))
    return raw_objects,metrics

def native(platform):
    guard()
    out=ROOT/"build/f08-apple"/platform;evidence=out/"evidence";evidence.mkdir(parents=True)
    report={**identity(),"platform":platform,"collection_complete":False,"f08_accepted":False,"commands":[],"problems":[]}
    def run(args,role,required=True,timeout=3600):
        args=list(map(str,args));print("F08_APPLE_PHASE",platform,role,flush=True)
        with (evidence/(role+".log")).open("wb") as f:
            value=subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        report["commands"].append({"role":role,"argv":args,"returncode":value.returncode})
        if value.returncode:
            report["problems"].append(role+" exit "+str(value.returncode))
            print("\n".join((evidence/(role+".log")).read_text(errors="replace").splitlines()[-60:]),flush=True)
            if required:raise RuntimeError(role+" failed")
        return value.returncode==0
    failure=None
    try:
        installed=authenticate_inputs();mac=installed["macos"]/"sdk"
        target="macos" if platform=="macos" else "iphonesimulator"
        sdk=installed[target]/"sdk";products=installed[target]/"raw-products"
        resources=out/"resources"
        run([sys.executable,"tests/apple_host/prepare_fixtures.py","--resources",resources],"fixtures")
        helper=out/"shelf-review"
        run([sys.executable,"tools/apple_swift.py","--sdk",mac,"--","-swift-version","5","-parse-as-library","-O",
             "-I",mac/"include","-L",mac/"lib","-lexreader","-Xlinker","-rpath","-Xlinker",mac/"lib",
             "examples/apple/HostSDK.swift","examples/apple/HostModel.swift","examples/apple/HostCatalog.swift",
             "examples/apple/SelectableText.swift","tests/apple_host/shelf/ShelfReview.swift","-o",helper],"seed-build")
        seed=out/"seed";run([helper,resources,seed],"seed")
        seed_report=json.loads((seed/"shelf-seed.json").read_text())
        need(seed_report["accepted"] is True and seed_report["books"]==len(set(seed_report["source_keys"]))==2202,"real corpus")
        need(all(str(seed_report.get(k))==v for k,v in identity().items()),"seed source/run/attempt")
        for p in seed.glob("ShelfSeed-*"):shutil.copyfile(p,resources/p.name)
        shutil.copyfile(seed/"shelf-seed.json",resources/"shelf-seed.json")
        shutil.copyfile(seed/"shelf-seed.json",evidence/"shelf-seed.json")
        original=ROOT/"tests/apple_host/shelf/ui/ShelfUITests.swift";text=original.read_text()
        insertion=(HERE/"Metrics.swift").read_text();at=text.rfind("}")
        need(at>0 and "test08F08ScrollMetrics" not in text,"insertion boundary")
        tests=out/"shelf/ui";tests.mkdir(parents=True)
        candidate=tests/original.name;candidate.write_text(text[:at]+insertion+text[at:])
        save(evidence/"driver.json",{"original_sha256":sha(original),"candidate_sha256":sha(candidate),
            "insertion_sha256":sha(HERE/"Metrics.swift"),"original_cases_unchanged":True})
        shutil.copyfile(candidate,evidence/"ShelfUITests.swift")
        project=out/"project";derived=out/"derived"
        run(["ruby","tests/reader_team24_apple/make_project.rb",project,resources,tests,"wave3"],"project")
        schemes=sorted((project/"EXReaderHost.xcodeproj/xcshareddata/xcschemes").glob("*.xcscheme"))
        need(len(schemes)==2,"generated Apple schemes")
        for path in schemes:
            document=ET.parse(path)
            for tag in ("TestAction","LaunchAction"):
                action=document.getroot().find(tag);need(action is not None,"scheme action")
                action.attrib.update({"buildConfiguration":"Release","selectedDebuggerIdentifier":"",
                    "selectedLauncherIdentifier":"Xcode.IDEFoundation.Launcher.PosixSpawn",
                    "codeCoverageEnabled":"NO","disableMainThreadChecker":"YES",
                    "enableAddressSanitizer":"NO","enableThreadSanitizer":"NO","enableUBSanitizer":"NO"})
            document.write(path,encoding="utf-8",xml_declaration=True)
            (evidence/"schemes").mkdir(exist_ok=True)
            shutil.copyfile(path,evidence/"schemes"/path.name)
        configuration=json.loads(command(["ruby","-rxcodeproj","-rjson","-e",
            'p=Xcodeproj::Project.open(ARGV[0]);v={};p.targets.each{|t|next unless t.product_type=="com.apple.product-type.application";t.build_configurations.each{|c|v[t.name+"/"+c.name]=c.build_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"]}};puts JSON.generate(v)',
            project/"EXReaderHost.xcodeproj"],text=True))
        required={"EXR_APPLE_SHELF_REVIEW","EXR_APPLE_HOST_REVIEW","EXR_APPLE_RAW3","EXR_APPLE_WAVE3","EXR_APPLE_PAGE_THEME"}
        need(len(configuration)==4 and all(required<=set(value.split()) for value in configuration.values()),"shelf observation and full-feature flags")
        save(evidence/"project-configuration.json",configuration)
        if platform=="macos":
            destination="platform=macOS";device="macos";device_name="macOS host";runtime="macOS"
            scheme="EXReaderHost-macOS";suffix="Release";signing="YES";test_target="EXReaderHostUITests-macOS"
        else:
            choices=json.loads(command(["xcrun","simctl","list","devices","available","--json"]))
            prefix="iPhone" if platform=="iphone" else "iPad"
            runtime,device_name,device=max((rt,d["name"],d["udid"]) for rt,items in choices["devices"].items()
                for d in items if d.get("isAvailable") and d["name"].startswith(prefix))
            subprocess.run(["xcrun","simctl","shutdown",device],capture_output=True)
            run(["xcrun","simctl","erase",device],"erase")
            run(["xcrun","simctl","boot",device],"boot")
            run(["xcrun","simctl","bootstatus",device,"-b"],"boot-ready")
            destination="platform=iOS Simulator,id="+device;scheme="EXReaderHost-iOS"
            suffix="Release-iphonesimulator";signing="NO";test_target="EXReaderHostUITests-iOS"
        destination_file=evidence/"destination.txt";destination_file.write_text("\n".join((destination,device,device_name,runtime))+"\n")
        save(evidence/"environment.json",{"destination":destination,"device":device_name,"runtime":runtime,
            "xcode":command(["xcodebuild","-version"],text=True),"os":command(["sw_vers"],text=True),
            "arch":command(["uname","-m"],text=True),"runner_image":os.environ.get("ImageVersion")})
        original_result=evidence/"original.xcresult";metrics_result=evidence/"metrics.xcresult"
        build_options=["-project",project/"EXReaderHost.xcodeproj","-scheme",scheme,"-destination",destination,
                "-derivedDataPath",derived,"-configuration","Release",
                "EXR_SDK_DIR="+str(sdk),"EXR_PRODUCTS_DIR="+str(products),"CODE_SIGNING_ALLOWED="+signing,
                "SWIFT_OPTIMIZATION_LEVEL=-O","GCC_OPTIMIZATION_LEVEL=s","ONLY_ACTIVE_ARCH=YES"]
        common=[*build_options,"-enableCodeCoverage","NO","-enableAddressSanitizer","NO",
                "-enableThreadSanitizer","NO","-enableUndefinedBehaviorSanitizer","NO",
                "-parallel-testing-enabled","NO","-test-timeouts-enabled","YES",
                "-default-test-execution-time-allowance","2700","-maximum-test-execution-time-allowance","2700"]
        settings=json.loads(command(["xcodebuild","-showBuildSettings","-json",*build_options]))
        save(evidence/"build-settings.json",settings)
        targets=[row["buildSettings"] for row in settings if row.get("target")==scheme]
        need(len(targets)==1 and targets[0]["CONFIGURATION"]=="Release" and
             targets[0]["SWIFT_OPTIMIZATION_LEVEL"]=="-O" and targets[0]["ONLY_ACTIVE_ARCH"]=="YES","optimized product configuration")
        report["configuration"]="Release";report["build_settings_sha256"]=sha(evidence/"build-settings.json")
        run(["xcodebuild","test",*common,"-resultBundlePath",original_result,
             "-skip-testing:"+test_target+"/ShelfUITests/test08F08ScrollMetrics"],"original-seven",required=False)
        app=derived/"Build/Products"/suffix/"EXReaderHost.app"
        info=plistlib.loads((app/("Contents/Info.plist" if platform=="macos" else "Info.plist")).read_bytes())
        need(info["EXRSourceSHA"]==identity()["source_sha"] and info["EXRSDKVersion"]=="3.42.0","program identity")
        binary=app/("Contents/MacOS/EXReaderHost" if platform=="macos" else "EXReaderHost")
        architecture=command(["lipo","-archs",binary],text=True).split()
        need(architecture==[command(["uname","-m"],text=True).strip()],"native runner architecture")
        report["program_architecture"]=architecture
        before=sha(binary);shutil.copytree(app,evidence/"program/EXReaderHost.app")
        report["program_sha256"]=before
        (evidence/"program-dependencies.txt").write_text(command(["otool","-L",binary],text=True))
        if platform=="macos":container=Path.home()/"Library/Application Support/EXReader"
        else:
            container=command([sys.executable,"tests/apple_host/resolve_container.py","--udid",device,
                               "--output",evidence/"container.json"],text=True).strip()
        run([sys.executable,"tests/apple_host/shelf/collect_shelf_evidence.py","--platform",platform,
             "--xcresult",original_result,"--output",evidence/"original","--container",container,
             "--app",app,"--seed",seed/"shelf-seed.json","--sdk-root",sdk,
             "--sdk-identity",installed[target]/"sdk-identity.json","--destination",destination_file],
             "original-evidence",required=False,timeout=600)
        run(["xcodebuild","test-without-building",*common,"-resultBundlePath",metrics_result,
             "-only-testing:"+test_target+"/ShelfUITests/test08F08ScrollMetrics"],"scroll-metrics",required=False,timeout=1200)
        need(sha(binary)==before,"program changed between functional and performance tests")
        raw_objects,metrics=extract_metrics(metrics_result)
        save(evidence/"xcresult-objects.json",raw_objects)
        save(evidence/"performance-metrics.json",metrics)
        need(metrics,"no native performance metrics")
        report["metric_identifiers"]=[m.get("identifier",{}).get("_value") for m in metrics]
        source_report=evidence/"original/shelf-ui.json"
        need(source_report.is_file(),"original seven-case evidence absent")
        original_report=json.loads(source_report.read_text())
        report["original_ui_accepted"]=original_report.get("accepted") is True
        report["collection_complete"]=not report["problems"] and report["original_ui_accepted"]
        report["budget_evaluation"]="Native metric units and frame coverage await independent audit; F08 remains pending."
    except BaseException as error:
        failure=error;report["problems"].append(repr(error));report["traceback"]=traceback.format_exc()
    finally:
        save(evidence/"result.json",report)
        shutil.copyfile(HERE/"profile.json",evidence/"profile.json")
        print("F08_APPLE_RESULT",json.dumps(report),flush=True)
    if failure:raise failure
    need(report["collection_complete"],"incomplete Apple measurements")
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("guard","native","seal"))
    parser.add_argument("--platform",choices=("macos","iphone","ipad","macos-sdk","iphonesimulator-sdk"))
    args=parser.parse_args()
    if args.mode=="guard":guard()
    elif args.mode=="seal":seal(args.platform)
    else:native(args.platform)
