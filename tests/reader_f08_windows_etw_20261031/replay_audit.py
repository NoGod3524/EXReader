"""Read-only Actions audit of the pinned raw ETL; no new sampling."""
import csv, hashlib, io, json, os, stat, subprocess, sys, urllib.request, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
from lane import identity, need, save, sha, command
BASE="b81c45d5a1fa05ef84786cf0ef10cfebca350d81"
RUN=41181893762
ARTIFACT=13035192429
SIZE=3446781
DIGEST="80c64d7dbb756611fcfaa81ad5200f23be191c7a71ffc37085f714b549429a84"
OUT=ROOT/"build/f08-windows-etw-inspect"
PM_SHA="b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af"
def events(path):
    for _,node in ET.iterparse(path,events=("end",)):
        if node.tag.rsplit("}",1)[-1]!="Event":continue
        values={x.tag.rsplit("}",1)[-1]:x for x in node}
        system={x.tag.rsplit("}",1)[-1]:x for x in values.get("System",[])}
        provider=system.get("Provider");execution=system.get("Execution");clock=system.get("TimeCreated")
        data={x.attrib.get("Name",""):x.text for x in values.get("EventData",[])}
        rendered={x.tag.rsplit("}",1)[-1]:x.text for x in values.get("RenderingInfo",[])}
        yield {"provider":provider.attrib.get("Name",provider.attrib.get("Guid","")) if provider is not None else "",
            "event":system["EventID"].text if "EventID" in system else None,
            "execution":dict(execution.attrib) if execution is not None else {},
            "clock":dict(clock.attrib) if clock is not None else {},"data":data,"labels":rendered}
        node.clear()
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    need(command(["git","rev-parse","HEAD"],text=True).strip()==identity()["source_sha"],"audit source")
    command(["git","merge-base","--is-ancestor",BASE,"HEAD"])
    need(set(command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==
         {"tests/reader_f08_windows_etw_20261031/replay_audit.py",".github/workflows/dot-f08-windows-etw-inspect-20261031.yml"},"audit scope")
    OUT.mkdir(parents=True,exist_ok=False)
    api=lambda p:json.loads(command(["gh","api","repos/NoGod3524/EXReader/"+p]))
    meta=api("actions/artifacts/"+str(ARTIFACT));save(OUT/"metadata.json",meta)
    producer=api("actions/runs/"+str(RUN))
    need(producer["head_sha"]==BASE and producer["run_attempt"]==1 and producer["conclusion"]=="success","producer")
    need(meta["id"]==ARTIFACT and meta["name"]=="f08-windows-etw-"+str(RUN)+"-1" and not meta["expired"]
         and meta["size_in_bytes"]==SIZE and meta["digest"]=="sha256:"+DIGEST
         and meta["workflow_run"]["id"]==RUN and meta["workflow_run"]["head_sha"]==BASE,"artifact")
    data=command(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(ARTIFACT)+"/zip"])
    need(len(data)==SIZE and hashlib.sha256(data).hexdigest()==DIGEST,"original ZIP")
    (OUT/"original.zip").write_bytes(data);raw=OUT/"raw";raw.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=set();infos=archive.infolist()
        need(0<len(infos)<100 and sum(x.file_size for x in infos)<2*1024**3,"bounds")
        for info in infos:
            path=PurePosixPath(info.filename);key=str(path).casefold()
            need(str(path)!="." and not path.is_absolute() and ".." not in path.parts and "\\" not in info.filename
                 and ":" not in info.filename and key not in names,"ZIP path")
            names.add(key);need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"ZIP kind")
            if info.is_dir():continue
            destination=raw/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(archive.read(info))
    receipt=json.loads((raw/"receipt.json").read_text())
    need(receipt["source_sha"]==BASE and receipt["run_id"]==str(RUN) and receipt["attempt"]=="1"
         and receipt["diagnostic_complete"] is True and receipt["f08_accepted"] is False,"receipt")
    actual={p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}
    need(actual==set(receipt["files"])|{"receipt.json"},"inventory")
    for name,item in receipt["files"].items():need(sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"file bytes")
    pm=OUT/"PresentMon-2.6.0-x64.exe"
    with urllib.request.urlopen("https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/PresentMon-2.6.0-x64.exe",timeout=60) as response:
        pm.write_bytes(response.read())
    need(pm.stat().st_size==980320 and sha(pm)==PM_SHA,"pinned PresentMon")
    report={**identity(),"producer_source":BASE,"producer_run":RUN,"artifact_id":ARTIFACT,"original_sha256":DIGEST,
            "resampled":False,"captures":[],"f08_accepted":False}
    for capture in receipt["captures"]:
        mode=capture["mode"];pid=capture["pid"];folder=OUT/mode;folder.mkdir()
        etl=raw/mode/"raw.etl"
        command(["tracerpt",etl,"-rts","-of","XML","-o",folder/"raw-timestamps.xml","-y"])
        rows=list(events(folder/"raw-timestamps.xml"))
        updates=[r for r in rows if r["execution"].get("ProcessID")==str(pid) and
                 r["provider"]=="Microsoft-Windows-Win32k" and r["event"] in ("41","42")]
        handles={r["data"].get("hwnd","").strip().casefold() for r in updates}-{""}
        links=[r for r in rows if any(("wnd" in key.casefold() or "window" in key.casefold()) and
               (value or "").strip().casefold() in handles for key,value in r["data"].items())]
        save(folder/"window-links.json",links)
        save(folder/"render-updates.json",updates)
        linked_types={}
        for row in links:
            key=row["provider"]+"/"+str(row["event"])+"/"+str(row["labels"].get("Task"))
            linked_types[key]=linked_types.get(key,0)+1
        entry={"mode":mode,"pid":pid,"handles":sorted(handles),"render_updates":len(updates),
               "update_clock_examples":[r["clock"] for r in updates[:3]],"linked_types":linked_types,
               "external_window_links":[r for r in links if r["execution"].get("ProcessID")!=str(pid)][:12],
               "trace_headers":[r for r in rows if r["provider"].startswith("{9e814aad")][:2],
               "replays":[]}
        print("F08_RAW_TIMESTAMPS",json.dumps(entry),flush=True)
        for profile,flags in (("display",[]),("display_no_gpu",["--no_track_gpu"]),("cpu",["--no_track_display","--no_track_gpu","--no_track_input"])):
            output=folder/(profile+".csv")
            args=[str(pm),"--etl_file",str(etl),"--process_id",str(pid),"--output_file",str(output),
                  "--no_console_stats","--qpc_time",*flags]
            with (folder/(profile+".log")).open("wb") as log:result=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=180)
            save(folder/(profile+"-command.json"),args)
            parsed=list(csv.DictReader(output.open(encoding="utf-8-sig",newline=""))) if output.exists() else []
            need(all(row.get("ProcessID")==str(pid) for row in parsed),"replay PID")
            replay={"profile":profile,"exit":result.returncode,"rows":len(parsed),"columns":list(parsed[0]) if parsed else [],
                    "first_rows":parsed[:2]}
            entry["replays"].append(replay);print("F08_ETL_REPLAY",mode,json.dumps(replay),flush=True)
        report["captures"].append(entry)
    report["files"]={p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
                     for p in OUT.rglob("*") if p.is_file() and "raw" not in p.relative_to(OUT).parts}
    save(OUT/"result.json",report)
    print("F08_ETL_INSPECTION",json.dumps({k:v for k,v in report.items() if k not in ("files","captures")}),flush=True)
if __name__=="__main__":main()
