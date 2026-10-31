"""Actions-only native desktop duplication capability, not F08 acceptance."""
import json, os, shutil, subprocess, sys, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"build/f08-windows-duplication"
sys.path.insert(0,str(ROOT/"tests/reader_f08_windows_product_20261031"))
from build import identity, need, save, sha, command
BASE="f17e7df7502813493045912f23a336644665c38a"
FILES={"tests/reader_f08_windows_duplication_20261031/probe.cpp",
       "tests/reader_f08_windows_duplication_20261031/CMakeLists.txt",
       "tests/reader_f08_windows_duplication_20261031/run.py",
       ".github/workflows/dot-f08-windows-duplication-20261031.yml"}
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and os.name=="nt","Windows Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"source identity")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==FILES,"test-only scope")
    OUT.mkdir(parents=True,exist_ok=False)
    report={**identity(),"capability_complete":False,"product_sampled":False,"f08_accepted":False,"problems":[]}
    try:
        command([sys.executable,"tests/reader_wave3_c09/desktop.py","--output",OUT/"desktop.json"])
        desktop=json.loads((OUT/"desktop.json").read_text());need(desktop["accepted"] is True and desktop["after"]==[1280,800],"fixed desktop")
        binary=ROOT/"build/f08-duplication-build/Release/f08_duplication.exe"
        report["observer_sha256"]=sha(binary)
        shutil.copyfile(binary,OUT/"observer.exe")
        with (OUT/"native.jsonl").open("wb") as log:
            result=subprocess.run([str(binary)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        rows=[json.loads(line) for line in (OUT/"native.jsonl").read_text().splitlines()]
        report["native_returncode"]=result.returncode;report["native_records"]=len(rows)
        for row in rows:print("F08_DUPLICATION_NATIVE",json.dumps(row),flush=True)
        need(result.returncode==0 and rows[0]["kind"]=="start" and rows[0]["qpc_frequency"]>0,"native capability command")
        frames=[r for r in rows if r["kind"]=="desktop_frame"]
        matched=[r for r in frames if r["matched"]]
        need([r["requested_generation"] for r in matched]==list(range(1,9)),"all eight native content generations")
        for row in matched:
            generation=row["requested_generation"]
            need(row["pixel_read"] is True and row["protected_content"] is False and row["accumulated_frames"]>0 and
                 row["paint_start_qpc"]<=row["last_present_qpc"]<=row["acquired_qpc"]<=row["finished_qpc"] and
                 row["bgra"][:3]==[191-generation*11,37,generation*20],"native pixel and QPC correspondence")
        report.update(capability_complete=True,matched_generations=8,desktop_records=len(frames),
            accumulated_extra_frames=sum(max(0,r["accumulated_frames"]-1) for r in frames),
            pointer_only_records=sum(r["last_present_qpc"]==0 for r in frames),
            frame_budget_measured=False,physical_scanout_proven=False)
    except BaseException as error:
        report["problems"].append(repr(error));report["traceback"]=traceback.format_exc();raise
    finally:
        save(OUT/"result.json",report)
        save(OUT/"manifest.json",{**identity(),"f08_accepted":False,"files":{
            p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
            for p in sorted(OUT.rglob("*")) if p.is_file() and p!=OUT/"manifest.json"}})
        print("F08_DUPLICATION_CAPABILITY",json.dumps(report),flush=True)
if __name__=="__main__":main()
