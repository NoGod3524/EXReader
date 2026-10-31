"""Read-only replay of all retained product ETLs; no process is resampled."""
import hashlib, json, os, sys, traceback
from pathlib import Path
import frames as F
from frames import ROOT, need, save, sha, command, identity
BASE="eda058002d64fa9669a5851b788b37c4a5741e98"
PIN={"source_sha":BASE,"run_id":"41188810230","attempt":"1","artifact":13037284729,
     "bytes":94582950,"digest":"df169d65fc42640349da522f50f938a30e2208365ebeefcd7c1edbb19001d81a"}
OUT=ROOT/"build/f08-windows-product-replay"
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true" and os.name=="nt","Windows Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"replay source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
         {"tests/reader_f08_windows_product_frames_20261031/replay.py",".github/workflows/dot-f08-windows-product-replay-20261031.yml"},"test-only replay scope")
    OUT.mkdir(parents=True,exist_ok=False)
    meta=F.api("actions/artifacts/"+str(PIN["artifact"]))
    producer=F.api("actions/runs/"+PIN["run_id"]+"/attempts/"+PIN["attempt"])
    need(producer["head_sha"]==BASE and str(producer["run_attempt"])==PIN["attempt"],"producer")
    need(meta["id"]==PIN["artifact"] and not meta["expired"] and meta["size_in_bytes"]==PIN["bytes"]
         and meta["digest"]=="sha256:"+PIN["digest"] and meta["workflow_run"]["head_sha"]==BASE and
         str(meta["workflow_run"]["id"])==PIN["run_id"],"artifact metadata")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(PIN["artifact"])+"/zip"])
    need(len(data)==PIN["bytes"] and hashlib.sha256(data).hexdigest()==PIN["digest"],"ZIP bytes")
    save(OUT/"metadata.json",meta);raw=OUT/"raw"
    F.extract(data,raw,"manifest.json",{k:PIN[k] for k in ("source_sha","run_id","attempt")})
    source=json.loads((raw/"result.json").read_text())
    need(all(source.get(k)==PIN[k] for k in ("source_sha","run_id","attempt")) and source["f08_accepted"] is False,"capture identity")
    _,product=F.product(OUT/"verified-product",(raw/"product/original.zip").read_bytes())
    need(product==source["product"],"product binding")
    report={**identity(),"pin":PIN,"authenticated":True,"resampled":False,"original_capture_complete":source["capture_complete"],
        "original_problems":source["problems"],"product":product,"captures":[],"problems":[],
        "frame_budget_measured":False,"application_paint_generation_bound":False,"f08_accepted":False}
    seen=set()
    try:
        need(len(source["captures"])==12,"preserved planned trace census")
        for original in source["captures"]:
            name=original["folder"];need(name=="trace-%03d"%original["index"] and name not in seen,"trace identity")
            seen.add(name);folder=OUT/name;folder.mkdir();source_folder=raw/name
            entry={"index":original["index"],"pid":original["pid"],"complete":False,"original_error":original.get("error"),
                "etl_sha256":sha(source_folder/"raw.etl"),"native_sha256":sha(source_folder/"native.jsonl")}
            report["captures"].append(entry)
            try:
                # tracerpt explicitly rejects combining raw timestamps with summary.
                F.execute(["tracerpt",source_folder/"raw.etl","-rts","-of","XML","-o",folder/"events.xml","-y"],folder/"tracerpt.log")
                entry["analysis"]=F.analyze(folder,original["pid"],original["frequency"],source_folder/"native.jsonl")
                composition=entry["analysis"]["composition"]
                need(composition["target_window_cycles"]>0 and
                     composition["retirement_join"]["valid_frame_id_retirement_joins"]>0,"no product frame completion")
                entry["complete"]=True
            except BaseException as error:
                entry["error"]=repr(error);entry["traceback"]=traceback.format_exc()
                report["problems"].append(name+": "+repr(error))
            print("F08_PRODUCT_REPLAY_TRACE",json.dumps({k:v for k,v in entry.items() if k!="analysis"}),flush=True)
        records=json.loads((raw/"observations/per-launch.json").read_text())
        interactions=json.loads((raw/"observations/interactions.json").read_text())
        need(len(records)==10 and {r["cohort"] for r in records}=={"warm_shelf","reading"},"original launch census")
        need(not interactions["faults"] and len(interactions["font_order"])==5,"original interactions")
        for name,count in {"shelf_scroll_up":15,"shelf_scroll_down":15,"font_bigger":10,"font_smaller":10}.items():
            need(len(interactions[name])==count,"original interaction sample census")
        by_pid={e["pid"]:e for e in report["captures"]}
        need(len(by_pid)==len(report["captures"]),"PID reuse")
        report["measured_processes"]=[{"launch_id":r["launch_id"],"pid":r["pid"],"trace_complete":by_pid.get(r["pid"],{}).get("complete",False)}
            for r in records]
        need(all(x["trace_complete"] for x in report["measured_processes"]),"all measured process traces")
        need(all(e["complete"] for e in report["captures"]) and not report["problems"],"all retained traces")
        report["replay_complete"]=True
    except BaseException as error:
        report["replay_complete"]=False;report["problems"].append(repr(error));report["traceback"]=traceback.format_exc()
    finally:
        save(OUT/"result.json",report)
        compact={k:v for k,v in report.items() if k!="captures"}
        compact["captures"]=[{**{k:v for k,v in e.items() if k not in ("analysis","traceback")},
            "composition":e.get("analysis",{}).get("composition")} for e in report["captures"]]
        print("F08_PRODUCT_REPLAY",json.dumps(compact),flush=True)
    need(report["replay_complete"],"retained ETL replay incomplete")
if __name__=="__main__":main()
