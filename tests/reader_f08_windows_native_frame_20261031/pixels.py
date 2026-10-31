"""Replay actual owned-window capture bytes. No frame-budget acceptance is inferred."""
import hashlib
from PIL import Image
from pathlib import Path

def analyze(folder, entry, P):
    native=P.rows(folder/"native.jsonl"); driver=P.rows(folder/"driver.jsonl")
    P.need(native and native[0]["kind"]=="start" and native[-1]["kind"]=="summary","capture endpoints")
    first,last=native[0],native[-1];freq=entry["frequency"];pid=entry["pid"]
    P.need(first["api"]=="Windows.Graphics.Capture" and first["product_pid"]==pid and
           first["root_hwnd"]==entry["hwnd"] and first["observer_pid"]==entry["observer_pid"] and
           first["frequency"]==freq and 0<first["qpc"]<last["qpc"],"native identities")
    P.need(not last["failed"] and not last["deadline_expired"] and not last["target_closed"] and
           not any(r["kind"] in ("callback_error","fatal") for r in native),"native errors")
    P.need(driver[0]["kind"]=="process" and driver[-1]["kind"]=="close" and
           driver[0]["pid"]==driver[-1]["pid"]==pid and driver[0]["exe_sha256"]==entry["program_sha256"] and
           driver[0]["qpc"]<=first["qpc"]<last["qpc"]<=driver[-1]["qpc"],"product lifetime")
    ready=[r for r in native if r["kind"]=="ready"]
    P.need(len(ready)==1 and ready[0]["capture_scope"]=="owned_window" and
           ready[0]["cursor_capture"] is False and ready[0]["frame_pool_buffers"]==8,"capture configuration")
    frames=[r for r in native if r["kind"]=="frame"]
    P.need([r["index"] for r in frames]==list(range(1,len(frames)+1)) and len(frames)==last["frames"],"callback accounting")
    images={};loaded_name=None;pixels=None;changed={119:[],123:[]};invalid={119:0,123:0};previous={};whole=None
    previous_time=-1;whole_changes=0;phase=[];callback_lags=[];uniform={119:[],123:[]}
    for r in frames:
        P.need(first["qpc"]<=r["callback_qpc"]<=r["copy_qpc"]<=r["map_start_qpc"]<=r["map_end_qpc"]<=
               r["readback_finished_qpc"]<=last["qpc"],"readback chronology")
        native_time=r["system_relative_100ns"]
        P.need(isinstance(native_time,int) and 0<native_time and previous_time<native_time,"native timestamp sequence")
        previous_time=native_time
        name=r["image"];P.need(name.endswith(".png") and name[:-4].isdigit() and 0<int(name[:-4])<=r["index"],"image path")
        if name!=loaded_name:
            path=folder/"images"/name
            with Image.open(path) as picture:
                P.need(picture.format=="PNG" and picture.mode=="RGBA","native PNG format")
                width,height=picture.size
                pixels=picture.tobytes("raw","BGRA")
            P.need(len(pixels)==width*height*4 and all(a==255 for a in pixels[3::4]),"opaque lossless pixels")
            images[name]={"sha256":P.sha(path),"width":width,"height":height,
                          "bgr_sha256":hashlib.sha256(pixels).hexdigest(),"bytes":path.stat().st_size}
            loaded_name=name
        info=images[name]
        P.need(info["width"]==r["width"]==ready[0]["width"] and info["height"]==r["height"]==ready[0]["height"],"frame dimensions")
        key=info["bgr_sha256"];actual=whole!=key
        P.need(r["changed"]==actual and (not actual or int(name[:-4])==r["index"]),"whole-image changes")
        whole=key;whole_changes+=actual
        P.need([v["control_id"] for v in r["regions"]]==[119,123],"product region inventory")
        for region in r["regions"]:
            control=region["control_id"]
            if not region["valid"]:
                invalid[control]+=1
                continue
            x0,y0,x1,y1=region["crop"]
            P.need(region["pid"]==pid and region["hwnd"]>0 and region["visible"] and region["geometry_stable"] and
                   0<=x0<x1<=r["width"] and 0<=y0<y1<=r["height"],"owned visible crop")
            crop=b"".join(pixels[(y*r["width"]+x0)*4:(y*r["width"]+x1)*4] for y in range(y0,y1))
            nonuniform=any(len(set(crop[c::4]))>1 for c in range(3))
            if not nonuniform:
                uniform[control].append({"index":r["index"],"bgra":list(crop[:4]),
                                         "classification":"uniform_pixels_cause_unknown"})
            digest=hashlib.sha256(crop).hexdigest();key=(x1-x0,y1-y0,digest)
            if previous.get(control)!=key:
                changed[control].append({"index":r["index"],"system_relative_100ns":native_time,"image":name,
                                         "region_sha256":digest,"crop":region["crop"],"nonuniform":nonuniform})
            previous[control]=key
        phase.append((r["readback_finished_qpc"]-r["copy_qpc"])*1000/freq)
        callback_lags.append(r["callback_qpc"]*1000/freq-native_time/10000)
    P.need(set(images)=={p.name for p in (folder/"images").glob("*")} and whole_changes==last["changed_images"],"raw image accounting")
    P.need(sum(info["width"]*info["height"]*4 for info in images.values())==last["saved_pixel_bytes"],"native pixel byte accounting")
    P.need(sum(info["bytes"] for info in images.values())==last["saved_file_bytes"],"encoded image byte accounting")
    inputs=[r for r in driver if r["kind"]=="input"]
    for event in inputs:
        P.need(event["pid"]==pid and driver[0]["qpc"]<=event["start_qpc"]<=event["end_qpc"]<=driver[-1]["qpc"],"input chronology")
    result={"native_frames":len(frames),"native_input_dispatches":len(inputs),
            "distinct_content_frames":{key:sum(r["nonuniform"] for r in value) for key,value in changed.items()},"content_frames":changed,
            "invalid_regions":invalid,"uniform_regions":uniform,"images":images,"readback_ms":phase,"callback_lag_ms":callback_lags,
            "timestamps_after_callback":sum(value<0 for value in callback_lags),
            "native_timestamp_order_confirmed":all(value>=0 for value in callback_lags),
            "frame_census_complete":False,"application_paint_generation_bound":False,
            "frame_budget_measured":False,"physical_scanout_proven":False,"f08_accepted":False}
    P.save(folder/"analysis.json",result);return result


# This driver records a send-attempt interval, not an exact dispatch timestamp.
# Reuse the retained lossless pixel checks without inventing the missing point.
def main():
    import argparse,json,types
    parser=argparse.ArgumentParser();parser.add_argument("run");parser.add_argument("--output",required=True);args=parser.parse_args()
    root=Path(args.run);out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    report=json.loads((root/"result.json").read_text());summary={"source_sha":report["source_sha"],"captures":[]}
    def need(value,reason):
        if not value:raise ValueError(reason)
    def rows(path):return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    for entry in report["captures"]:
        folder=root/entry["folder"];native=rows(folder/"native.jsonl")
        expected={**entry,"program_sha256":report["program_sha256"],"observer_pid":native[0]["observer_pid"]}
        save=lambda unused,value:(out/(entry["folder"]+"-pixels.json")).write_text(json.dumps(value,indent=2)+"\n")
        P=types.SimpleNamespace(rows=rows,need=need,sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),save=save)
        value=analyze(folder,expected,P)
        value["driver_dispatch_timestamp_available"]=False
        value["observer_pid_binding"]="observer self-report; parent process handle PID was not persisted"
        save(None,value)
        summary["captures"].append({"kind":entry["kind"],**{k:value[k] for k in ("native_frames","native_input_dispatches","distinct_content_frames","timestamps_after_callback","native_timestamp_order_confirmed")},"encoded_image_bytes":sum(v["bytes"] for v in value["images"].values()),"uniform_regions":{k:len(v) for k,v in value["uniform_regions"].items()},"frame_budget_measured":False})
    (out/"pixels-summary.json").write_text(json.dumps(summary,indent=2)+"\n");print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
