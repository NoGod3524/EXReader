"""Probe process-scoped Instruments frames on authenticated Release programs."""
import argparse, importlib.util, json, os, plistlib, re, subprocess, sys, time, traceback
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE="4157a6d02e9ccc47e7fe0986e45663e6f4784ce0"
spec=importlib.util.spec_from_file_location("apple_budget_archive",ROOT/"tests/reader_f08_apple_budget_20261031/audit.py")
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
need,save,sha,command,identity=B.need,B.save,B.sha,B.command,B.identity
PINS={
 "macos":{"id":13037818282,"bytes":64814306,"digest":"7f2693fa03351b6dea5a87583bdc8a257ce6a00e5a609bafe17f69c21c7f32e0","program":"cd525be98547cde693c57213b48a14b028eac544b3c9aeb0c5513d3fc2614390"},
 "iphone":{"id":13038628059,"bytes":72986478,"digest":"0f91591435e2636f15d4b2821dc45e1628e27acb7eb4c9c02b9d851b53c92f49","program":"1ae6631ae98e357e0b853d6fb429dab62cc9245e1d87d7f328be89fe2a923b0f"},
 "ipad":{"id":13039480840,"bytes":74777837,"digest":"9e47d8391f0055ceb973f6e3ccbe0d5dcb4de7906790a1c1911bb9f41cb90c00","program":"93ee13a042c3407dea214083ee58a03954404a3ff482fbd3cf8b4ba0e81a6647"}}
def main(platform):
    need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform=="darwin","macOS Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"checkout")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
         {"tests/reader_f08_apple_trace_20261031/probe.py",".github/workflows/dot-f08-apple-trace-20261031.yml"},"test-only scope")
    out=ROOT/("build/f08-apple-trace-"+platform);out.mkdir(parents=True,exist_ok=False)
    report={**identity(),"platform":platform,"scope":"Native Instruments capability on the already-launched product process, not startup timing or workload acceptance",
            "probe_complete":False,"f08_accepted":False,"frame_budget_measured":False,"first_interactive_measured":False,
            "commands":[],"problems":[]}
    app_process=None;trace_process=None;device=None;trace_log=None;app_log=None
    def run(label,args,timeout=180,required=True):
        args=list(map(str,args))
        started=time.monotonic()
        try:
            result=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        except subprocess.TimeoutExpired as error:
            output=error.output or b""
            if isinstance(output,str):output=output.encode("utf-8")
            (out/(label+".log")).write_bytes(output)
            report["commands"].append({"label":label,"argv":args,"timeout_seconds":timeout,
                "elapsed_seconds":time.monotonic()-started,"timed_out":True})
            raise
        (out/(label+".log")).write_bytes(result.stdout)
        report["commands"].append({"label":label,"argv":args,"returncode":result.returncode,
            "elapsed_seconds":time.monotonic()-started})
        if required:need(result.returncode==0,label+" failed: "+result.stdout.decode("utf-8",errors="replace")[-2000:])
        return result
    try:
        developer=Path("/Applications/Xcode_26.2.app/Contents/Developer")
        report["available_xcodes"]=sorted(str(path) for path in Path("/Applications").glob("Xcode*.app"))
        report["requested_developer_dir"]=str(developer)
        need(developer.is_dir(),"fixed Xcode 26.2 tracing toolchain unavailable")
        os.environ["DEVELOPER_DIR"]=str(developer)
        version=run("selected-xcode",["xcodebuild","-version"]).stdout.decode("utf-8",errors="replace")
        need(version.splitlines()[0]=="Xcode 26.2","fixed tracing tool version")
        sdk=run("selected-simulator-sdk",["xcrun","--sdk","iphonesimulator","--show-sdk-version"]).stdout.decode().strip()
        need(sdk=="26.2","tracing SDK matches the fixed iOS 26.2 runtime")
        report["tracing_toolchain"]={"xcode":"26.2","simulator_sdk":sdk,"developer_dir":str(developer)}
        run("trace-tool",["xcrun","--find","xctrace"])
        run("developer-security",["/usr/sbin/DevToolsSecurity","-status"],required=False)
        run("user-groups",["id"])
        producer=B.api("actions/runs/"+B.PRODUCER["run_id"])
        need(producer["status"]=="completed" and producer["conclusion"]=="success" and
             producer["head_sha"]==B.PRODUCER["source_sha"] and str(producer["run_attempt"])=="1","completed Release producer")
        pin=PINS[platform];meta=B.api("actions/artifacts/"+str(pin["id"]))
        need(meta["id"]==pin["id"] and meta["size_in_bytes"]==pin["bytes"] and meta["digest"]=="sha256:"+pin["digest"],"pinned native archive")
        raw,verified=B.archive(meta,ROOT/("build/f08-apple-trace-input-"+platform),True)
        save(out/"producer.json",verified)
        native=json.loads((raw/"result.json").read_text())
        app=raw/"program/EXReaderHost.app";binary=app/("Contents/MacOS/EXReaderHost" if platform=="macos" else "EXReaderHost")
        info=plistlib.loads((app/("Contents/Info.plist" if platform=="macos" else "Info.plist")).read_bytes())
        need(native["collection_complete"] is True and native["configuration"]=="Release" and
             sha(binary)==pin["program"]==native["program_sha256"] and info["EXRSourceSHA"]==B.BASE,"same Release program")
        need(command(["lipo","-archs",binary],text=True).split()==["arm64"],"fixed native architecture")
        report["program_sha256"]=sha(binary);report["producer"]=B.PRODUCER
        binary.chmod(0o755)
        run("xcode",["xcodebuild","-version"]);run("os",["sw_vers"])
        templates=run("templates",["xcrun","xctrace","list","templates"]).stdout.decode("utf-8",errors="replace")
        run("record-help",["xcrun","xctrace","help","record"],required=False)
        need("Animation Hitches" in templates,"native Animation Hitches template unavailable")
        if platform!="macos":
            choices=json.loads(run("simulators",["xcrun","simctl","list","devices","available","--json"]).stdout)
            runtime="com.apple.CoreSimulator.SimRuntime.iOS-26-2"
            name="iPhone SE (3rd generation)" if platform=="iphone" else "iPad mini (A17 Pro)"
            matches=[d for d in choices["devices"].get(runtime,[]) if d.get("isAvailable") and d["name"]==name]
            need(len(matches)==1,"same fixed simulator profile");device=matches[0]["udid"]
            report["destination"]={"runtime":runtime,"name":name,"udid":device}
            run("shutdown-before",["xcrun","simctl","shutdown",device],required=False)
            run("erase",["xcrun","simctl","erase",device])
            run("boot",["xcrun","simctl","boot",device])
            run("boot-ready",["xcrun","simctl","bootstatus",device,"-b"],timeout=600)
            run("install",["xcrun","simctl","install",device,app])
        else:report["destination"]={"name":"native macOS runner","arch":command(["uname","-m"],text=True).strip()}
        run("trace-devices",["xcrun","xctrace","list","devices"])
        report["launch_started_uptime"]=time.monotonic()
        if device:
            launched=run("launch",["xcrun","simctl","launch",device,info["CFBundleIdentifier"],"-EXRShelfSeed"])
            matched=re.search(r":\s*(\d+)\s*$",launched.stdout.decode("utf-8",errors="replace").strip())
            need(matched is not None,"native simulator PID");report["app_pid"]=int(matched.group(1))
        else:
            app_log=(out/"application.log").open("wb")
            app_process=subprocess.Popen([str(binary),"-EXRShelfSeed"],stdout=app_log,stderr=subprocess.STDOUT)
            report["app_pid"]=app_process.pid
        report["launch_returned_uptime"]=time.monotonic()
        run("target-process",["ps","-p",str(report["app_pid"]),"-o","pid=,ppid=,comm="])
        trace=out/"animation.trace"
        args=["xcrun","xctrace","record","--template","Animation Hitches","--time-limit","60s",
              "--attach",str(report["app_pid"]),"--output",str(trace),"--no-prompt"]
        if device:args.extend(["--device",device])
        save(out/"trace-command.json",args)
        trace_log=(out/"record.log").open("wb")
        trace_process=subprocess.Popen(args,cwd=ROOT,stdout=trace_log,stderr=subprocess.STDOUT)
        report["trace_started_uptime"]=time.monotonic()
        report["trace_process_pid"]=trace_process.pid
        report["trace_scope"]="exact already-launched product PID"
        try:code=trace_process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            report["record_timeout_seconds"]=180
            # Diagnostic work follows the failed deadline and cannot convert the run to a pass.
            for label,argv in (
                ("recorder-process",["ps","-p",str(trace_process.pid),"-o","pid=,ppid=,etime=,command="]),
                ("recorder-stack",["sample",str(trace_process.pid),"3","-file",str(out/"recorder-stack.txt")]),
                ("target-process-after-timeout",["ps","-p",str(report["app_pid"]),"-o","pid=,ppid=,etime=,comm="])):
                try:run(label,argv,timeout=15,required=False)
                except Exception as error:report["problems"].append("diagnostic "+label+": "+repr(error))
            raise
        trace_log.close();trace_log=None
        report["record_returncode"]=code
        need(code==0 and trace.is_dir(),"native Instruments recording failed")
        run("export-toc",["xcrun","xctrace","export","--input",trace,"--toc","--output",out/"toc.xml"])
        toc=ET.parse(out/"toc.xml")
        tables=[dict(node.attrib) for node in toc.getroot().iter("table")]
        report["native_tables"]=tables
        candidates=sorted({t["schema"] for t in tables if "schema" in t and
            any(term in t["schema"].lower() for term in ("frame","hitch","animation","display","process"))})
        need(len(candidates)<=20,"bounded table inventory")
        report["exported_tables"]=[]
        for index,schema in enumerate(candidates):
            need("'" not in schema,"native schema XPath")
            path=out/("table-%02d.xml"%index)
            selected="/trace-toc/run/data/table[@schema='"+schema+"']"
            result=run("export-%02d"%index,["xcrun","xctrace","export","--input",trace,"--xpath",selected,"--output",path],required=False)
            report["exported_tables"].append({"schema":schema,"path":path.name,"exit":result.returncode,
                "bytes":path.stat().st_size if path.exists() else None})
        report["program_sha256_after"]=sha(binary)
        need(report["program_sha256_after"]==pin["program"],"program bytes changed")
        report["probe_complete"]=True
        report["target_process_frame_attribution"]="unverified; process-scoped recording still requires independent PID-aware table validation"
    except BaseException as error:
        report["problems"].append(repr(error));report["traceback"]=traceback.format_exc();raise
    finally:
        if trace_process is not None and trace_process.poll() is None:
            trace_process.terminate()
            try:trace_process.wait(timeout=30)
            except subprocess.TimeoutExpired:trace_process.kill();trace_process.wait(timeout=30)
        if trace_log is not None:trace_log.close()
        if app_process is not None and app_process.poll() is None:
            app_process.terminate()
            try:app_process.wait(timeout=30)
            except subprocess.TimeoutExpired:app_process.kill();app_process.wait(timeout=30)
        if app_log is not None:app_log.close()
        if device:
            try:run("shutdown-after",["xcrun","simctl","shutdown",device],timeout=120,required=False)
            except Exception as error:report["problems"].append("cleanup: "+repr(error))
        save(out/"result.json",report)
        save(out/"manifest.json",{**identity(),"f08_accepted":False,"files":{
            p.relative_to(out).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
            for p in sorted(out.rglob("*")) if p.is_file() and p!=out/"manifest.json"}})
        print("F08_APPLE_TRACE_CAPABILITY",json.dumps(report),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("platform",choices=tuple(PINS));main(p.parse_args().platform)
