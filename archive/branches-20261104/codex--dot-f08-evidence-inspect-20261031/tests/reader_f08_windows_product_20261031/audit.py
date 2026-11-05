"""Authenticate the complete same-run ZIP and independently check the original Windows observations."""
import hashlib, io, json, math, os, stat, subprocess, sys, zipfile
from pathlib import Path, PurePosixPath
import build as B
from build import identity, need, save, sha, command
ROOT=B.ROOT;OUT=ROOT/"build/f08-windows-product-audit"
def entries(archive):
    infos=archive.infolist()
    need(0<len(infos)<20000 and sum(i.file_size for i in infos)<4*1024**3,"ZIP bounds")
    names=set()
    for info in infos:
        path=PurePosixPath(info.filename);key=str(path).casefold()
        need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and
             "\\" not in info.filename and ":" not in info.filename and key not in names,"ZIP path")
        names.add(key)
        need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
    return infos
def raw_budgets(raw,summary,profile):
    records=json.loads((raw/"observations/per-launch.json").read_text())
    need(records and all(r["ok"] is True for r in records),"complete raw launches")
    agg=summary["aggregates"]
    for cohort in ("cold_shelf","warm_shelf"):
        selected=[r for r in records if r["cohort"]==cohort]
        values=[r["ops"]["first_screen"]["first_screen_interactive_ms"] for r in selected]
        need(len(values)==12 and all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in values),"raw first interaction")
        need(agg[cohort]["first_screen_interactive_ms"]["n"]==len(values) and
             agg[cohort]["first_screen_interactive_ms"]["max"]==max(values),"raw first-interaction maximum")
    need(set(agg)=={r["cohort"] for r in records},"raw cohorts")
    for cohort in agg:
        values=[r["peak"]["peak_working_set_bytes"] for r in records if r["cohort"]==cohort]
        need(values and all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in values),"raw memory")
        need(agg[cohort]["peak_working_set_bytes"]["n"]==len(values) and
             agg[cohort]["peak_working_set_bytes"]["max"]==max(values),"raw peak working set")
    return B.budgets(summary,profile)
def main():
    B.guard();OUT.mkdir(parents=True,exist_ok=False)
    ident=identity();api=lambda p:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+p]))
    artifact=int(os.environ["F08_ARTIFACT_ID"]);meta=api("actions/artifacts/"+str(artifact))
    save(OUT/"metadata.json",meta)
    need(meta["id"]==artifact and not meta["expired"] and
         meta["name"]=="f08-windows-product-"+ident["run_id"]+"-"+ident["attempt"],"artifact identity")
    need(str(meta["workflow_run"]["id"])==ident["run_id"] and meta["workflow_run"]["head_sha"]==ident["source_sha"],"artifact producer")
    producer=api("actions/runs/"+ident["run_id"])
    need(producer["head_sha"]==ident["source_sha"] and str(producer["run_attempt"])==ident["attempt"],"producer attempt")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(artifact)+"/zip"])
    digest=hashlib.sha256(data).hexdigest()
    need(len(data)==meta["size_in_bytes"] and meta["digest"]=="sha256:"+digest and
         os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest,"ZIP digest/bytes")
    (OUT/"original.zip").write_bytes(data);raw=OUT/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in entries(archive):
            if info.is_dir():continue
            path=raw/PurePosixPath(info.filename);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(archive.read(info))
    manifest=json.loads((raw/"manifest.json").read_text())
    need(all(manifest.get(k)==v for k,v in ident.items()) and manifest["f08_accepted"] is False,"manifest identity")
    files={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    need(files==set(manifest["files"])|{"manifest.json"},"complete inventory")
    for name,item in manifest["files"].items():
        need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"file bytes: "+name)
    need((raw/"profile.json").read_bytes()==(B.HERE/"profile.json").read_bytes(),"frozen profile")
    profile=json.loads((raw/"profile.json").read_text())
    report={**ident,"artifact_id":artifact,"artifact_bytes":len(data),"artifact_sha256":digest,"files":len(files),
        "authenticated":True,"build_complete":False,"collection_complete":False,
        "non_frame_budget_passed":False,"frame_budget_measured":False,"f08_accepted":False}
    if (raw/"build-identity.json").is_file():
        build=json.loads((raw/"build-identity.json").read_text())
        need(all(build.get(k)==v for k,v in ident.items()) and build["sdk_version"]=="3.42.0","build identity")
        for name,digest in build["unchanged_helpers"].items():need(sha(ROOT/name)==digest,"unchanged helper")
        for name,digest in build["components"].items():
            need(command(["git","rev-parse","HEAD:"+name],text=True).strip()==digest,"production tree")
        need(build["features"]=={"wave3":True,"raw_selector":True,"cloud_content_bound":True,"txt_progress":True},"features")
        need(sha(raw/"program/EXReader.exe")==build["program_sha256"] and sha(raw/"seed.exe")==build["seed_sha256"]
             and sha(raw/"program.zip")==build["package_sha256"],"installed binaries")
        package=json.loads((raw/"package-build.json").read_text());checks=json.loads((raw/"package-report.json").read_text())
        need(package["passed"] is True and package["source_sha"]==ident["source_sha"] and
             package["sdk_version"]=="3.42.0" and package["linkage"]=="static-reading","package identity")
        need(checks["passed"] is True and checks["engine_version"]=="3.42.0" and
             package["selftest_checks"]==checks["checks"]>=26,"unchanged native checks")
        need(package["report_sha256"]==sha(raw/"package-report.json") and
             package["image_sha256"]==sha(raw/"package-page.png"),"native report/image")
        payload={p.relative_to(raw/"program").as_posix():sha(p) for p in (raw/"program").rglob("*") if p.is_file()}
        need(payload==package["files"],"payload inventory")
        with zipfile.ZipFile(raw/"program.zip") as archive:
            zipped={i.filename:hashlib.sha256(archive.read(i)).hexdigest() for i in entries(archive) if not i.is_dir()}
        need(zipped==payload,"original ZIP roundtrip")
        report.update(build_complete=True,program_sha256=build["program_sha256"],selftest_checks=checks["checks"])
    sample=None
    if (raw/"sample-result.json").is_file():
        sample=json.loads((raw/"sample-result.json").read_text())
        need(all(sample.get(k)==v for k,v in ident.items()) and sample["f08_accepted"] is False,"sample identity")
        report["sample_problems"]=sample["problems"];report["steps"]=sample["steps"]
    if (raw/"observations/summary.json").is_file():
        original_verification=json.loads((raw/"observations/verification.json").read_text()) if (raw/"observations/verification.json").exists() else None
        with (OUT/"original-verifier.log").open("wb") as log:
            verified=subprocess.run([sys.executable,str(ROOT/"tests/reader_perf_windows/verify_composition.py"),
                "--summary",str(raw/"observations/summary.json"),"--package",str(raw/"program"),
                "--start",ident["source_sha"],"--launches","30","--per-cohort","10"],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        verification=json.loads((raw/"observations/verification.json").read_text())
        report["original_verifier"]=verification
        if original_verification is not None:need(verification==original_verification,"independent original verifier")
        if sample is not None and "original_verify_passed" in sample:
            need(sample["original_verify_passed"]==(verified.returncode==0),"recorded original verdict")
        if sample is not None and sample["collection_complete"] is True:
            need(report["build_complete"] and verified.returncode==0,"complete package and original observations")
            desktop=json.loads((raw/"desktop.json").read_text())
            need(desktop["accepted"] is True and desktop["after"]==[profile["screen_width"],profile["screen_height"]],"fixed display")
            interactions=json.loads((raw/"interactions/interactions.json").read_text())
            need(not interactions["faults"] and len(interactions["font_order"])==5,"interaction coverage")
            for name,count in {"shelf_scroll_down":15,"shelf_scroll_up":15,"font_bigger":10,"font_smaller":10}.items():
                values=interactions[name]
                need(len(values)==count and all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in values),"interaction samples")
            summary=json.loads((raw/"observations/summary.json").read_text())
            evaluated=raw_budgets(raw,summary,profile)
            need(evaluated==sample["budget_evaluation"],"independent budget verdict")
            report.update(evaluated,collection_complete=True)
    if sample is not None and sample["collection_complete"] is True:
        need(report["collection_complete"],"complete producer evidence")
    save(OUT/"audit.json",report);print("F08_WINDOWS_PRODUCT_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":main()
