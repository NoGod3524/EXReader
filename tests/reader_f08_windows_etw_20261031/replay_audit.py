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
def element_payload(node):
    return {"tag":node.tag.rsplit("}",1)[-1],"attributes":dict(node.attrib),
            "text":node.text,"children":[element_payload(child) for child in node]}
def leaf_texts(node):
    if node.get("text") and node["text"].strip():yield node["text"].strip()
    for child in node.get("children",[]):yield from leaf_texts(child)
def unsigned(value):
    try:
        value=str(value).strip()
        return int(value,16 if value.lower().startswith("0x") else 10)
    except (TypeError,ValueError):return None
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
            "clock":dict(clock.attrib) if clock is not None else {},"data":data,"labels":rendered,
            "event_data":[element_payload(x) for x in values.get("EventData",[])],
            "version":system["Version"].text if "Version" in system else None,
            "opcode":system["Opcode"].text if "Opcode" in system else None}
        node.clear()
def inspect_window(rows, updates, links, native_path, folder, pid):
    native=[json.loads(line) for line in native_path.read_text().splitlines()]
    need(native[0]["kind"]=="start" and native[-1]["kind"]=="stop","native endpoints")
    frequency=native[0]["qpc_frequency"]
    headers=[r for r in rows if r["provider"].startswith("{9e814aad") and "PerfFreq" in r["data"]]
    need(len(headers)==1 and int(headers[0]["data"]["PerfFreq"].strip())==frequency,"same QPC frequency")
    need(int(headers[0]["data"]["EventsLost"].strip())==0 and int(headers[0]["data"]["BuffersLost"].strip())==0,"ETW losses")
    draws=[r for r in native if r["kind"] in ("gdi_paint","dxgi_present")]
    associations=[];unmatched=[];ambiguous=[]
    for event in updates:
        point=int(event["clock"]["RawTime"])
        matches=[i for i,draw in enumerate(draws) if draw["start_qpc"]<=point<=draw["end_qpc"]]
        record={"event":event,"paint_indexes":matches}
        associations.append(record)
        if not matches:unmatched.append(record)
        elif len(matches)>1:ambiguous.append(record)
    joined=[]
    for i,draw in enumerate(draws):
        matches=[x["event"] for x in associations if x["paint_indexes"]==[i]]
        joined.append({"native":draw,"render_events":matches,"duration_ms":1000*(draw["end_qpc"]-draw["start_qpc"])/frequency})
    native_summary={"draws":len(draws),"events":len(updates),"unmatched_events":len(unmatched),
        "ambiguous_events":len(ambiguous),"draws_with_event":sum(bool(x["render_events"]) for x in joined),
        "draws_without_event":sum(not x["render_events"] for x in joined),
        "by_event":{key:sum(x["event"]["event"]==key and len(x["paint_indexes"])==1 for x in associations) for key in ("41","42")},
        "native_duration_ms":{"min":min(x["duration_ms"] for x in joined),"max":max(x["duration_ms"] for x in joined)},
        "qpc_frequency":frequency,"physical_presentation_proven":False}
    save(folder/"native-paint-join.json",{"summary":native_summary,"draws":joined,"unmatched":unmatched,"ambiguous":ambiguous})
    dwm=[r for r in rows if r["provider"]=="Microsoft-Windows-Dwm-Core"]
    direct=[r for r in links if r["provider"]=="Microsoft-Windows-Dwm-Core"]
    binding=[r for r in direct if r["event"]=="84"]
    sprite_tokens={str(value).strip().casefold() for row in binding for key,value in row["data"].items()
                   if "sprite" in key.casefold() and value and str(value).strip().casefold() not in ("0","0x0")}
    sprite_links=[r for r in dwm if any(str(value).strip().casefold() in sprite_tokens for value in r["data"].values())]
    types={}
    for row in dwm:
        key=str(row["event"])+"/"+str(row["labels"].get("Task"))+"/"+str(row["labels"].get("Opcode"))
        entry=types.setdefault(key,{"count":0,"first":row});entry["count"]+=1
    direct_examples={}
    for row in direct:direct_examples.setdefault(row["event"],[]).append(row)
    save(folder/"dwm-types.json",types);save(folder/"dwm-window-links.json",direct);save(folder/"dwm-sprite-links.json",sprite_links)
    print("F08_NATIVE_PAINT_JOIN",folder.name,json.dumps(native_summary),flush=True)
    print("F08_DWM_WINDOW",folder.name,json.dumps({key:value[:4] for key,value in direct_examples.items()}),flush=True)
    print("F08_DWM_TYPES",folder.name,json.dumps(types),flush=True)
    return {"native_paint_join":native_summary,"sprite_tokens":sorted(sprite_tokens),"sprite_link_count":len(sprite_links),
            "dwm_window_event_count":len(direct),"dwm_types":{key:value["count"] for key,value in types.items()},
            "physical_presentation_proven":False}

def inspect_composition(rows, handles, pid, folder):
    dwm=[r for r in rows if r["provider"]=="Microsoft-Windows-Dwm-Core"]
    live={};cycles=[];unfinished=[]
    for row in dwm:
        key=(row["execution"].get("ProcessID"),row["execution"].get("ThreadID"))
        if row["event"]=="10":
            if key in live:unfinished.append(live.pop(key))
            live[key]=[]
        if key in live:
            live[key].append(row)
            if row["event"]=="12":cycles.append(live.pop(key))
    unfinished.extend(live.values())
    selected=[]
    for cycle in cycles:
        updates=[r for r in cycle if r["event"]=="46" and
                 (r["data"].get("hWnd") or "").strip().casefold() in handles]
        if not updates:continue
        attribution=[]
        for row in cycle:
            if row["event"]!="387":continue
            values=[unsigned(v) for datum in row["event_data"]
                    if datum["attributes"].get("Name")=="CompositorRendered" for v in leaf_texts(datum)]
            attribution.append({"event":row,"rendered_pids":[v for v in values if v is not None]})
        selected.append({"start_qpc":unsigned(cycle[0]["clock"].get("RawTime")),
            "end_qpc":unsigned(cycle[-1]["clock"].get("RawTime")),"updates":updates,"attribution":attribution,
            "present_start_count":sum(r["event"]=="15" for r in cycle),
            "present_succeeded_count":sum(r["event"]=="141" for r in cycle),
            "process_frame_info":[r for r in cycle if r["event"]=="11"],
            "all_events":cycle,"paint_generation_link":"unknown","physical_presentation_proven":False})
    frame_info=[r for r in dwm if r["event"] in ("1","202")]
    save(folder/"composition-cycles.json",{"target_cycles":selected,"unfinished_cycles":unfinished,"frame_info":frame_info})
    duplicate_names=sum(len([x["attributes"].get("Name") for x in row["event_data"]])!=
        len(set(x["attributes"].get("Name") for x in row["event_data"])) for row in rows)
    nested=sum(any(x["children"] for x in row["event_data"]) for row in rows)
    result={"complete_dwm_cycles":len(cycles),"unfinished_dwm_cycles":len(unfinished),"target_window_cycles":len(selected),
        "target_window_updates_in_complete_cycles":sum(len(x["updates"]) for x in selected),
        "target_cycles_with_present_succeeded":sum(x["present_succeeded_count"]>0 for x in selected),
        "target_cycles_with_process_attribution":sum(any(pid in a["rendered_pids"] for a in x["attribution"]) for x in selected),
        "repeated_event_data_names_preserved":duplicate_names,"events_with_nested_data_preserved":nested,
        "first_target_cycle":{"events":[{"event":r["event"],"qpc":r["clock"].get("RawTime"),
             "task":r["labels"].get("Task"),"data":r["data"],"event_data":r["event_data"]}
             for r in selected[0]["all_events"] if r["event"] in ("10","11","12","46","87","100","15","16","141","387","114")]} if selected else None,
        "frame_info_examples":frame_info[:4],"paint_generation_link":"unknown","physical_presentation_proven":False}
    print("F08_COMPOSITION_CONTEXT",folder.name,json.dumps(result),flush=True)
    return {k:v for k,v in result.items() if k not in ("first_target_cycle","frame_info_examples")}

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
        entry["window_analysis"]=inspect_window(rows,updates,links,raw/mode/"control.jsonl",folder,pid)
        entry["replays_not_repeated"]=True
        entry["composition_context"]=inspect_composition(rows,handles,pid,folder)
        report["captures"].append(entry)
    report["files"]={p.relative_to(OUT).as_posix():{"sha256":sha(p),"bytes":p.stat().st_size}
                     for p in OUT.rglob("*") if p.is_file() and "raw" not in p.relative_to(OUT).parts}
    save(OUT/"result.json",report)
    print("F08_ETL_INSPECTION",json.dumps({k:v for k,v in report.items() if k not in ("files","captures")}),flush=True)
if __name__=="__main__":main()
