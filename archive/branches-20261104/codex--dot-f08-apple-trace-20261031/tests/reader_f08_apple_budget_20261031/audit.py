"""Read-only budget assessment of the fixed Release Apple artifacts."""
import hashlib, io, json, math, os, plistlib, re, stat, sys, traceback, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_f08_apple_20261031"))
from run import identity, need, save, sha, command, extract_metrics
sys.path.insert(0,str(ROOT/"tests/apple_host/shelf"))
import collect_shelf_evidence as SHELF
BASE="ea3875a9fb96d9c5e4c79c058ffaacb1d1663c1b"
PRODUCER={"source_sha":BASE,"run_id":"41186932079","attempt":"1"}
OUT=ROOT/"build/f08-apple-budget"
def api(path):return json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+path]))
def finite(value,positive=False):
    return type(value) in (int,float) and math.isfinite(value) and (value>0 if positive else value>=0)
def archive(meta,target,manifest=False):
    need(not meta["expired"] and meta["workflow_run"]["head_sha"]==BASE and
         str(meta["workflow_run"]["id"])==PRODUCER["run_id"],"artifact producer")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(meta["id"])+"/zip"])
    digest=hashlib.sha256(data).hexdigest()
    need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest,"ZIP digest and size")
    target.mkdir(parents=True,exist_ok=False);save(target/"api-metadata.json",meta)
    raw=target/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        infos=source.infolist();need(0<len(infos)<100000 and sum(i.file_size for i in infos)<4*1024**3,"ZIP bounds")
        names=set()
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and
                 "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key)
            need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
            if info.is_dir():continue
            destination=raw/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(source.read(info))
    if manifest:
        record=json.loads((raw/"f08-manifest.json").read_text())
        need(all(record.get(k)==v for k,v in PRODUCER.items()) and record["f08_accepted"] is False,"native manifest")
        actual={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
        need(actual==set(record["files"])|{"f08-manifest.json"},"native inventory")
        for name,item in record["files"].items():
            need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"native payload")
    return raw,{"artifact_id":meta["id"],"bytes":len(data),"sha256":digest,"authenticated":True}
def measure_series(metrics,suffix,unit):
    selected=[x for x in metrics if x.get("identifier",{}).get("_value","").endswith(suffix)]
    if not selected:return None
    need(len(selected)==1 and selected[0]["unitOfMeasurement"]["_value"]==unit,"native metric unit/identity "+suffix)
    values=[float(v["_value"]) for v in selected[0]["measurements"]["_values"]]
    need(len(values)==5 and all(finite(v) for v in values),"native metric iterations "+suffix)
    return values
def assess(platform,meta,proven):
    folder=OUT/platform;raw,pin=archive(meta,folder,True)
    native=json.loads((raw/"result.json").read_text())
    need(all(native.get(k)==v for k,v in PRODUCER.items()) and native["platform"]==platform and
         native["collection_complete"] is True and not native["problems"],"complete native collection")
    need(proven["artifact_id"]==pin["artifact_id"] and proven["sha256"]==pin["sha256"] and proven["bytes"]==pin["bytes"]
         and proven["authenticated"] is True and proven["collection_complete"] is True,"original independent audit binding")
    profile_path=ROOT/"tests/reader_f08_apple_20261031/profile.json"
    need((raw/"profile.json").read_bytes()==profile_path.read_bytes(),"frozen profile")
    profile=json.loads(profile_path.read_text());budgets=profile["budgets"]
    need(native["configuration"]=="Release" and sha(raw/"build-settings.json")==native["build_settings_sha256"],"Release settings")
    app=raw/"program/EXReaderHost.app";binary=app/("Contents/MacOS/EXReaderHost" if platform=="macos" else "EXReaderHost")
    info=plistlib.loads((app/("Contents/Info.plist" if platform=="macos" else "Info.plist")).read_bytes())
    need(info["EXRSourceSHA"]==BASE and sha(binary)==native["program_sha256"]==proven["program_sha256"],"same executable")
    need(command(["lipo","-archs",binary],text=True).split()==native["program_architecture"],"native architecture")
    original=json.loads((raw/"original/shelf-ui.json").read_text())
    cases=SHELF.load_results(raw/"original.xcresult")
    need(original["accepted"] is True and original["cases"]==cases and
         len(cases)==7 and {SHELF.owner(c["name"]) for c in cases}==set(SHELF.CASES)
         and all(c["result"]=="Passed" for c in cases) and original["originals"]==2202,"original shelf cases")
    original_states=list(SHELF.states(original["observations"]))
    need(original_states and all(finite(s["process_peak_rss_bytes"],True) for s in original_states),"original native RSS")
    original_peak=max(s["process_peak_rss_bytes"] for s in original_states)
    need(original_peak==original["measurements"]["process_peak_rss_bytes"]==
         proven["native_measurements"]["process_peak_rss_bytes"],"recomputed original peak RSS")
    metric_cases=SHELF.load_results(raw/"metrics.xcresult")
    need(len(metric_cases)==1 and metric_cases[0]["result"]=="Passed" and
         "test08F08ScrollMetrics" in metric_cases[0]["name"],"native metric test")
    _,metrics=extract_metrics(raw/"metrics.xcresult")
    need(metrics==json.loads((raw/"performance-metrics.json").read_text())==proven["performance_metrics"],"native metric recomputation")
    attachments=folder/"metric-attachments"
    command(["xcrun","xcresulttool","export","attachments","--path",raw/"metrics.xcresult","--output-path",attachments])
    exported=json.loads((attachments/"manifest.json").read_text());payloads=[]
    for group in exported:
        need("test08F08ScrollMetrics" in (group.get("testIdentifier") or group.get("testName") or ""),"metric attachment owner")
        for item in group["attachments"]:
            name=item["exportedFileName"];need(Path(name).name==name,"attachment path")
            if not item["suggestedHumanReadableName"].startswith("shelf-observations-"):continue
            source=attachments/name;need(source.is_file() and 0<source.stat().st_size<16*1024**2,"metric observation bytes")
            payload=json.loads(source.read_text())
            need("test08F08ScrollMetrics" in payload["test"] and
                 [x["id"] for x in payload["observations"]]==["f08-scroll-metrics"],"metric named observation")
            payloads.append(payload)
    need(len(payloads)==1,"one metric observation attachment")
    metric_states=list(SHELF.states(payloads[0]))
    need(metric_states and all(finite(s["process_peak_rss_bytes"],True) for s in metric_states),"metric native RSS")
    metric_peak=max(s["process_peak_rss_bytes"] for s in metric_states);peak=max(original_peak,metric_peak)
    checks=[{"metric":"process_peak_rss_bytes","scope":"all original seven shelf cases and the five-iteration scroll case",
        "unit":"bytes","observed":peak,"maximum":budgets["process_peak_rss_bytes"],
        "status":"passed" if peak<=budgets["process_peak_rss_bytes"] else "failed",
        "original_case_peak":original_peak,"metric_case_peak":metric_peak,"native_state_count":len(original_states)+len(metric_states)}]
    count=measure_series(metrics,".animation.frame.count","frames")
    ratio=measure_series(metrics,".animation.hitch.time.ratio","ms per s")
    if count is not None and ratio is not None:
        need(all(v>0 and v.is_integer() for v in count),"positive actual frame coverage")
        checks.append({"metric":"animation_hitch_time_ratio_ms_per_s","scope":"forward shelf scrolling only",
            "unit":"ms per s","values":ratio,"frame_counts":count,"actual_frames":sum(count),
            "maximum":budgets["animation_hitch_time_ratio_ms_per_s"],"observed":max(ratio),
            "status":"passed" if max(ratio)<=budgets["animation_hitch_time_ratio_ms_per_s"] else "failed"})
    else:
        checks.append({"metric":"animation_hitch_time_ratio_ms_per_s","status":"unmeasured",
            "frame_count_available":count is not None,"hitch_ratio_available":ratio is not None,
            "maximum":budgets["animation_hitch_time_ratio_ms_per_s"],"observed":None,
            "reason":"Native xcresult does not provide both actual frame counts and hitch-time ratios."})
    checks.append({"metric":"first_interactive_ms","status":"unmeasured","observed":None,
        "maximum":budgets["first_interactive_ms"],"reason":"No first-interactive timing is recorded in this shelf lane."})
    result={"platform":platform,"pin":pin,"program_sha256":native["program_sha256"],"checks":checks,
        "profile_sha256":sha(profile_path),"all_shelf_budgets_passed":all(x["status"]=="passed" for x in checks),
        "individual_frame_distribution_available":False,"missing_scopes":profile["limits"],"f08_accepted":False}
    save(folder/"assessment.json",result);return result
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform=="darwin","macOS Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"assessment source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
         {"tests/reader_f08_apple_budget_20261031/audit.py",".github/workflows/dot-f08-apple-budget-20261031.yml"},"test-only scope")
    OUT.mkdir(parents=True,exist_ok=False)
    producer=api("actions/runs/"+PRODUCER["run_id"]+"/attempts/"+PRODUCER["attempt"])
    need(producer["head_sha"]==BASE and str(producer["run_attempt"])==PRODUCER["attempt"] and
         producer["status"]=="completed","completed fixed producer")
    listed=api("actions/runs/"+PRODUCER["run_id"]+"/artifacts?per_page=100")["artifacts"]
    def artifact(kind):
        name="f08-apple-"+kind+"-"+PRODUCER["run_id"]+"-"+PRODUCER["attempt"]
        matches=[x for x in listed if x["name"]==name];need(len(matches)==1,"artifact census "+name)
        return api("actions/artifacts/"+str(matches[0]["id"]))
    audit_raw,audit_pin=archive(artifact("audit"),OUT/"original-audit")
    original_audit=json.loads((audit_raw/"audit.json").read_text())
    need(all(original_audit.get(k)==v for k,v in PRODUCER.items()) and original_audit["authenticated"] is True
         and len(original_audit["archives"])==5,"original five-archive audit")
    proven={x["kind"]:x for x in original_audit["archives"]}
    need(set(proven)=={"macos-sdk","iphonesimulator-sdk","macos","iphone","ipad"},"original platform census")
    report={**identity(),"producer":PRODUCER,"original_audit":audit_pin,"platforms":[],"problems":[],"f08_accepted":False}
    for platform in ("macos","iphone","ipad"):
        try:entry=assess(platform,artifact(platform),proven[platform]);report["platforms"].append(entry)
        except BaseException as error:
            entry={"platform":platform,"assessment_complete":False,"error":repr(error),"traceback":traceback.format_exc(),"f08_accepted":False}
            report["platforms"].append(entry);report["problems"].append(platform+": "+repr(error))
        print("F08_APPLE_BUDGET_PLATFORM",json.dumps(entry),flush=True)
    report["assessment_complete"]=not report["problems"]
    save(OUT/"assessment.json",report);print("F08_APPLE_BUDGET",json.dumps(report),flush=True)
    need(report["assessment_complete"],"budget evidence assessment incomplete")
if __name__=="__main__":main()
