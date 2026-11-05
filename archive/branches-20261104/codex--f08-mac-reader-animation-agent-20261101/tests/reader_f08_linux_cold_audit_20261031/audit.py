"""Actions-only replay of retained full-product startup evidence."""
import importlib.util, json, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE="2c6adb62585331264892c2f2d2e08a6e62d7bd61"
OUT=ROOT/"build/f08-linux-cold-audit"
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
S=module("shelf_archive","tests/reader_f08_shelf_content_20261031/run.py")
F=module("frozen_frames","tests/reader_f08_gtk_frameclock_20261031/verify.py")
def main():
    S.need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    S.need(S.command(["git","rev-parse","HEAD"],text=True).strip()==S.identity()["source_sha"],"audit source")
    S.command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    S.need(set(S.command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
        {"tests/reader_f08_linux_cold_audit_20261031/audit.py",".github/workflows/dot-f08-linux-cold-audit-20261031.yml"},"test-only audit")
    OUT.mkdir(parents=True,exist_ok=False)
    producer={"source_sha":BASE,"run_id":"41224385272","attempt":"1"}
    raw,pin=S.archive(producer,"f08-linux-product-41224385272-1",OUT/"input",13051587875)
    S.need(pin["bytes"]==49861625 and pin["sha256"]=="8ec746fc23c5e649419cfb812578c3862fd94c5b38286e13940f3899fb3d98a7","fixed full evidence")
    saved=S.load(raw/"sample-result.json")
    S.need(saved["collection_complete"] is True and saved["evaluation"]["non_frame_budget_passed"] is False,"preserve budget failure")
    records=S.load(raw/"perf-evidence/launches.json")["launches"]
    samples=S.load(raw/"perf-evidence/samples.json")["samples"]
    S.need(len(records)==32 and len(samples)==520 and all(s["outcome"]=="ok" for s in samples),"all original samples")
    selected=[s for s in samples if s["metric"]=="shelf_selection_move"]
    S.need(len(selected)==16,"all original first selection responses")
    rows=[]
    for sample in selected:
        record=records[sample["launch"]];index=record["launch"]
        S.need(index==sample["launch"],"launch identity")
        folder=raw/"perf-evidence/raw"/("launch-%02d"%index)
        entry=S.load(folder/"compact-resume.json");clock=S.load(folder/"frameclock"/(str(record["pid"])+".json"))
        F.check(clock,record["pid"],BASE,producer["run_id"],producer["attempt"])
        S.need(entry["pid"]==record["pid"] and entry["stage"]=="shelf_unchanged","unchanged Library startup")
        start=entry["launch_start"]
        writes=[{"start_ms":(w["start_us"]-start)/1000,"duration_ms":(w["end_us"]-w["start_us"])/1000,
                 "frames_seen":w["frames_seen"],"ok":w["ok"]} for w in clock["writes"]]
        frames=[f for f in clock["frames"] if f["before_us"]>0]
        row={"launch":index,"pid":record["pid"],"kind":record["kind"],"cache":record["cache"],
             "first_write_ms":min(w["start_ms"] for w in writes),
             "first_paint_phase_ms":min((f["before_us"]-start)/1000 for f in frames),
             "initial_writes":writes[:12],
             "samples":[{k:s[k] for k in ("metric","start_ms","end_ms","latency_ms","outcome","note")}
                        for s in samples if s["launch"]==index and s["metric"] in
                        ("startup_shelf_rows","startup_key_response","shelf_selection_move")]}
        if record["cache"]["effective"]=="cold":
            row["application_log"]=(folder/"application.log").read_text(errors="replace")[:6000]
        rows.append(row);print("F08_COLD_STARTUP",json.dumps(row),flush=True)
    cold=[r for r in rows if r["cache"]["effective"]=="cold"]
    S.need(len(cold)==4,"all four original cold selection launches")
    report={**S.identity(),"producer":pin,"authenticated":True,"original_budget_checks":saved["evaluation"]["checks"],
            "original_problems":saved["problems"],"launches":rows,"frame_budget_measured":False,"f08_accepted":False}
    S.save(OUT/"audit.json",report)
    print("F08_COLD_AUDIT",json.dumps({k:v for k,v in report.items() if k!="launches"}),flush=True)
if __name__=="__main__":main()
