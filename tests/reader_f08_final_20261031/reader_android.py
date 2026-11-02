"""Separate 2202+1 Release reader cohort; exact bitmap-paint / Window FrameMetrics replay."""
import collections
import hashlib
import json
import math
import re
import secrets
import sys
import threading
import time
import traceback
from pathlib import Path, PurePosixPath

SAMPLE={"size":2419,"sha256":"9d6464c0f15bfe5b970dd7168aa3162d46e3a64f8f0f049801e7b8651fab3f76"}

CASES=("open","page_forward","page_backward","font_increase","font_decrease",
       "search_found_select","body_applicability","return_shelf")
RENDER_CASES=CASES[:6]
IDENTITY=("source_sha","run_id","attempt")
BINDING_STRATEGY="unique-native-draw-interval-v1"
SNAPSHOT=("snapshot_identity","book_id","page_index","page_count","part","start","end",
          "font","zoom","fixed","source_key","bitmap_width","bitmap_height")


def need(value,message):
    if not value:raise ValueError(message)


def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def summary(values):
    values=sorted(values)
    return {"count":len(values),"p95":values[math.ceil(len(values)*.95)-1] if values else None,
            "p99":values[math.ceil(len(values)*.99)-1] if values else None,"max":max(values,default=None)}


def frame_summary(frames):
    values=[frame.get("total_ns") for frame in frames]
    invalid=sum(type(value) is not int or value<0 for value in values)
    return {"count":len(values),"invalid_total_count":invalid,"p95":None,"p99":None,"max":None} if invalid else {
        **summary([value/1e6 for value in values]),"invalid_total_count":0}


def associate(events,frames):
    """Exact CLOCK_MONOTONIC DRAW containment; no nearest-time/offset/invalid-candidate filtering."""
    problems=[];accepts={};latest={};last_generation={};draws=[];sets={};active={};ranges=[]
    for event in events:
        owner=(event["pid"],event["window_id"]);kind=event["kind"]
        if kind=="page_set":
            sets[owner]=event
            if not event["page_present"] and owner in active:
                ranges.append((*owner,active.pop(owner),event["mono_ns"]))
            latest.pop(owner,None)
        elif kind=="accept":
            key=(*owner,event["accept_id"])
            previous=sets.pop(owner,None)
            if key in accepts or not previous or not previous["page_present"] or any(
                    previous.get(k)!=event.get(k) for k in SNAPSHOT):problems.append("unpaired/duplicate accept: "+str(key))
            if not event.get("same_current_page") or not event.get("page_present") or event.get("request_generation",-1)<0:
                problems.append("missing accepted generation: "+str(key))
            old=last_generation.get(owner,-1)
            if event["request_generation"]<=old:problems.append("old request generation: "+str(key))
            last_generation[owner]=event["request_generation"]
            accepts[key]=event;latest[owner]=event
            active.setdefault(owner,event["mono_ns"])
        elif kind=="bitmap_draw":
            draw=dict(event);current=latest.get(owner)
            draw["generation_valid"]=bool(current and event.get("accepted_snapshot") and
                event.get("accept_id")==current["accept_id"] and
                event.get("request_generation")==current["request_generation"] and
                all(event.get(k)==current.get(k) for k in SNAPSHOT))
            draws.append(draw)
        elif kind=="no_bitmap" and owner in latest:problems.append("null bitmap for accepted generation: "+str(owner))
        elif kind=="error":problems.append("reader observer error: "+str(event.get("detail")))
    for owner,event in sets.items():
        if event["page_present"]:problems.append("page set without accepted generation: "+str(owner))
    for owner,start in active.items():
        ranges.append((*owner,start,None));problems.append("reader not cleared before trace end: "+str(owner))
    natives=[];keys=collections.Counter();sequences=collections.Counter();bad_owner=set()
    for index,frame in enumerate(frames):
        owner=(frame.get("pid"),frame.get("window_id"));reasons=[];start=end=None
        stages=("unknown_ns","input_ns","animation_ns","layout_measure_ns","draw_ns")
        clocks=("intended_vsync_ns","vsync_ns")
        if any(type(frame.get(k)) is not int or frame[k]<=0 for k in ("pid","window_id","sequence",*clocks)) or any(
                type(frame.get(k)) is not int or frame[k]<0 for k in stages):
            reasons.append("missing/negative/non-integer native clock/stage")
            bad_owner.add(owner)
        else:
            start=frame["intended_vsync_ns"]+sum(frame[k] for k in stages[:-1]);end=start+frame["draw_ns"]
            if not frame["intended_vsync_ns"]<=frame["vsync_ns"]<=start<=end:
                reasons.append("native clock order invalid");bad_owner.add(owner)
        # Bad total/drop/first-draw and duplicates stay in the candidate census.
        if type(frame.get("total_ns")) is not int or frame["total_ns"]<0:reasons.append("invalid native TOTAL")
        elif end is not None and end>frame["intended_vsync_ns"]+frame["total_ns"]:reasons.append("native DRAW exceeds frame completion")
        if type(frame.get("drop_count")) is not int or frame["drop_count"]!=0:reasons.append("dropped native callback")
        if type(frame.get("first_draw")) is not int or frame["first_draw"] not in (0,1):reasons.append("invalid native first-draw flag")
        key=(*owner,frame.get("vsync_ns"));sequence=(*owner,frame.get("sequence"));keys[key]+=1;sequences[sequence]+=1
        natives.append({"index":index,"frame":frame,"owner":owner,"key":key,"sequence":sequence,
                        "start":start,"end":end,"reasons":reasons})
    for native in natives:
        if keys[native["key"]]!=1 or sequences[native["sequence"]]!=1:native["reasons"].append("duplicate native key/sequence")
        if native["reasons"]:problems.append("native callback "+str(native["sequence"])+": "+", ".join(native["reasons"]))
    candidates=[];usage=collections.Counter()
    for draw in draws:
        owner=(draw["pid"],draw["window_id"]);begin=draw.get("draw_begin_mono_ns");end=draw.get("draw_end_mono_ns");reasons=[]
        if "frame_time_ns" in draw or "frame_time_status" in draw:reasons.append("legacy getter mode is not new interval evidence")
        valid_clock=type(begin) is int and type(end) is int and 0<begin<end
        if not valid_clock:reasons.append("missing/non-integer/non-positive bitmap draw span")
        matches=[native for native in natives if valid_clock and native["owner"]==owner and native["start"] is not None
                 and native["start"]<=begin<end<=native["end"]]
        if not draw["generation_valid"]:reasons.append("old/missing accepted generation")
        if not all(draw.get(k) is True for k in ("painted","page_present","bitmap_present","same_current_page","same_window","attached","shown")):
            reasons.append("paint/Window unavailable")
        if draw.get("bitmap_recycled"):reasons.append("recycled bitmap")
        if owner in bad_owner:reasons.append("unusable native clock/stage in same Window census")
        if len(matches)!=1:reasons.append("missing/ambiguous exact native DRAW containment")
        if len(matches)==1:
            reasons.extend(matches[0]["reasons"]);usage[matches[0]["index"]]+=1
        candidates.append((draw,matches,reasons))
    bindings=[];painted_accepts=set();matched_indices=set()
    reader_indices={native["index"] for _,matches,_ in candidates for native in matches}
    for draw,matches,reasons in candidates:
        if len(matches)==1 and usage[matches[0]["index"]]!=1:reasons.append("more than one reader draw in native frame")
        row={"pid":draw["pid"],"window_id":draw["window_id"],"draw_id":draw["draw_id"],"accept_id":draw["accept_id"],
             "request_generation":draw["request_generation"],"binding_strategy":BINDING_STRATEGY,
             "vsync_source":"FrameMetrics.VSYNC_TIMESTAMP from unique native DRAW interval",
             "status":"missing" if reasons else "complete","reasons":reasons,
             "candidate_native_sequences":[native["frame"].get("sequence") for native in matches],
             "snapshot":{k:draw.get(k) for k in SNAPSHOT}}
        if len(matches)==1:
            native=matches[0];frame=native["frame"]
            row.update(native_draw_start_ns=native["start"],native_draw_end_ns=native["end"],
                       native_sequence=frame["sequence"],native_vsync_ns=frame["vsync_ns"],native_intended_vsync_ns=frame["intended_vsync_ns"])
        if not reasons:
            frame=matches[0]["frame"];row.update(total_ns=frame["total_ns"],first_draw=frame["first_draw"])
            painted_accepts.add((draw["pid"],draw["window_id"],draw["accept_id"]));matched_indices.add(matches[0]["index"])
        else:problems.append("draw "+str(draw["draw_id"])+": "+", ".join(reasons))
        bindings.append(row)
    for key in accepts:
        if key not in painted_accepts:problems.append("accepted generation has no unique completed reader frame: "+str(key))
    census=[]
    for index,frame in enumerate(frames):
        key=(frame.get("pid"),frame.get("window_id"),frame.get("vsync_ns"))
        reader_active=index in reader_indices or any(key[:2]==(pid,window) and type(key[2]) is int and start<=key[2] and (end is None or key[2]<=end)
                          for pid,window,start,end in ranges)
        state="reader_paint" if index in matched_indices else "no_new_reader_draw" if reader_active else "outside_reader"
        census.append({"pid":key[0],"window_id":key[1],"sequence":frame.get("sequence"),"vsync_ns":key[2],
                       "total_ns":frame.get("total_ns"),"first_draw":frame.get("first_draw"),"reader_active":reader_active,"status":state})
    return {"problems":problems,"bindings":bindings,"callback_census":census,"binding_strategy":BINDING_STRATEGY,
            "accepted_generations":len(accepts),"bitmap_draws":len(draws),"binding_complete":bool(accepts) and not problems,
            "all_native_frames_ms":frame_summary(frames),
            "reader_phase_frames_ms":frame_summary([frame for frame,row in zip(frames,census) if row["reader_active"]]),
            "reader_first_draw_frames_ms":frame_summary([frame for frame,row in zip(frames,census) if row["reader_active"] and frame.get("first_draw")==1])}


def reader_header(header):
    need(header.get("schema")==2 and header.get("signal")=="ReaderView.canvas.drawBitmap" and
         header.get("binding_strategy")==BINDING_STRATEGY and header.get("clock")=="System.nanoTime",
         "reader raw schema/binding strategy")


def jsonl(path):
    raw=path.read_bytes();need(raw.endswith(b"\n"),"truncated trace: "+str(path))
    rows=[json.loads(line) for line in raw.splitlines()]
    need(len(rows)>=2 and rows[0]["kind"]=="start" and rows[-1]["kind"]=="stop","trace header/footer: "+str(path))
    return rows


def validate_case_clocks(cases):
    need([c["id"] for c in cases]==list(CASES),"fixed ordered reader actions")
    previous=-1
    for case in cases:
        start,end=case["started_elapsed_ns"],case["finished_elapsed_ns"]
        need(type(start) is int and type(end) is int and 0<=start<end and previous<=start,"reader case clock overlap/order")
        previous=end
        for item in case["detail"]["inputs"]:
            a,b=item["started_elapsed_ns"],item["finished_elapsed_ns"]
            need(type(a) is int and type(b) is int and start<=a<=b<=end,"public input outside actual action")


def verified_image(root,value,reader_required):
    """Recompute the helper's PNG crop and ARGB summary outside the measured app."""
    from PIL import Image
    image=value["reader_image"]
    def payload(name,digest):
        path=PurePosixPath(name)
        need(not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name,"image path")
        target=root/"ui"/path
        need(hashlib.sha256(target.read_bytes()).hexdigest()==digest,"image bytes: "+name)
        return target
    full=payload(image["screenshot_path"],image["screenshot_sha256"])
    clocks=(image["capture_started_elapsed_ns"],image["capture_finished_elapsed_ns"])
    need(image["screenshot_captured"] is True and all(type(v) is int and v>=0 for v in clocks)
         and clocks[0]<=clocks[1],"screenshot capture")
    with Image.open(full) as raw:screen=raw.convert("RGBA")
    if image["status"]!="captured":
        need(not reader_required and image["status"]=="missing","required reader image unavailable")
        return None
    bounds=image["bounds"];box=tuple(bounds[k] for k in ("left","top","right","bottom"))
    need(all(type(v) is int for v in box) and 0<=box[0]<box[2]<=screen.width and 0<=box[1]<box[3]<=screen.height,"reader image bounds")
    need(type(bounds["width"]) is int and type(bounds["height"]) is int and
         (bounds["width"],bounds["height"])==(box[2]-box[0],box[3]-box[1]),"reader bounds dimensions")
    need(bounds==image["bounds_after_capture"]==value["reader_view"]["bounds"]==value["public_after_capture"]["reader_view"]["bounds"]
         and value["reader_view"]["visible"] is True and value["public_after_capture"]["reader_view"]["visible"] is True,
         "public visible reader bounds changed or mismatched")
    post=value["public_after_capture"]
    need(all(value[k]==post[k] for k in ("page_label","font_label","book_title")),"public target changed during screenshot")
    crop_file=payload(image["crop_path"],image["crop_sha256"])
    with Image.open(crop_file) as raw:crop=raw.convert("RGBA")
    need(crop.size==(box[2]-box[0],box[3]-box[1])==(image["width"],image["height"]),"reader crop dimensions")
    need(crop.tobytes()==screen.crop(box).tobytes(),"reader crop differs from actual screen")
    rgba=crop.tobytes();argb=bytearray(len(rgba))
    argb[0::4]=rgba[3::4];argb[1::4]=rgba[0::4];argb[2::4]=rgba[1::4];argb[3::4]=rgba[2::4]
    colors=[int.from_bytes(argb[i:i+4],"big") for i in range(0,len(argb),4)]
    expected={"algorithm":"argb8888-be-v1","sha256":hashlib.sha256(argb).hexdigest(),
              "distinct_at_least_two":min(colors)!=max(colors),"min_argb":min(colors),"max_argb":max(colors),"pixels":len(colors)}
    need(image["pixel_summary"]==expected and expected["distinct_at_least_two"],"reader pixel summary/uniform content")
    return {"bounds":list(box),"pixel_sha256":expected["sha256"],"capture_finished_elapsed_ns":image["capture_finished_elapsed_ns"]}


def image_effects(images):
    checks=[]
    def compare(name,left,right,equal):
        a=images[left[0]][left[1]];b=images[right[0]][right[1]]
        same_bounds=bool(a and b and a["bounds"]==b["bounds"])
        same_pixels=bool(same_bounds and a["pixel_sha256"]==b["pixel_sha256"])
        checks.append({"check":name,"same_bounds":same_bounds,"expected_equal":equal,
                       "passed":same_bounds and same_pixels==equal})
    for name in ("page_forward","page_backward","font_increase","font_decrease","search_found_select"):
        compare(name+"_changes_visible_reader",(name,"before"),(name,"after"),False)
    compare("page_backward_restores_forward_origin",("page_forward","before"),("page_backward","after"),True)
    compare("font_decrease_restores_original",("font_increase","before"),("font_decrease","after"),True)
    return checks


def analyze(root,identity,fixture,pss_total):
    """All callback totals remain in the denominator; paint times never replace TOTAL_DURATION."""
    root=Path(root);problems=[];frames=[];events=[];windows=[]
    if list((root/"windows").glob("*-capture-error.json")):problems.append("post-seal collector failure")
    stop_rows=[]
    for path in sorted((root/"windows").glob("*.jsonl")):
        try:
            rows=jsonl(path);header=rows[0];body=rows[1:-1]
            frames.extend(r for r in body if r.get("kind")=="frame")
            need(header["schema"]==1 and all(r["kind"]=="frame" and r["pid"]==header["pid"] and
                r["window_id"]==header["window_id"] and r["sequence"]==i+1 and r["drop_count"]==0 and
                r["total_ns"]>=0 and r["vsync_ns"]>0 and r["first_draw"] in (0,1) for i,r in enumerate(body)),"Window callback census")
            need(rows[-1]["frames"]==len(body) and rows[-1]["dropped"]==0,"Window footer census")
            windows.append((header["pid"],header["window_id"]));stop_rows.append(rows[-1])
        except Exception as error:problems.append(str(error))
    for path in sorted((root/"windows/reader-draw").glob("*.jsonl")):
        try:
            rows=jsonl(path);header=rows[0];body=rows[1:-1];footer=rows[-1]
            reader_header(header)
            need((header["pid"],header["window_id"]) in windows,"mixed reader Window")
            need(all(r["kind"] in ("page_set","accept","bitmap_draw","no_bitmap","stop_request") and
                r["pid"]==header["pid"] and r["window_id"]==header["window_id"] and
                r["window_identity"]==header["window_identity"] and r["sequence"]==i+1 for i,r in enumerate(body)),"reader event census")
            need(footer["events"]==footer["attempted"]==len(body) and footer["rejected"]==footer["pending"]==0
                and footer["failed"] is False,"reader footer census")
            events.extend(body);stop_rows.append(footer)
        except Exception as error:problems.append(str(error))
    need(frames and events,"missing reader/Window traces")
    stop=load(root/"stop-request.json")
    requests=[event for event in events if event["kind"]=="stop_request"]
    need(stop["sent"] and len(requests)==1 and requests[0]["status"]=="accepted" and
         requests[0]["expected_pid"]==requests[0]["pid"]==stop["pid"] and
         requests[0]["expected_window_id"]==requests[0]["window_id"]==stop["window_id"],"owned explicit capture stop")
    need(len(stop_rows)==2 and all(r["stop_reason"]=="owned_reader_stop" and
         r["scope_end_requested_elapsed_ns"]==requests[0]["requested_elapsed_ns"] for r in stop_rows),"same explicit stop boundary")
    ready=load(root/"pre-stop-ready.json")
    need(ready["binding_complete"] and (ready["pid"],ready["window_id"])==(stop["pid"],stop["window_id"]),"required actions completed before stop")
    for name in ready["prefix_files"]:
        need((root/"windows"/name).read_bytes().startswith((root/ready["snapshot"] /name).read_bytes()),"captured pre-stop prefix lost: "+name)
    need(load(root/"trace-close-barrier.json")["complete"],"explicit close barrier missing")
    binding=associate(events,frames);problems.extend(binding["problems"])
    ui=load(root/"ui/validation.json");cases=ui["cases"]
    need(ui==load(root/"pre-stop-ui.json"),"helper evidence changed after completed UI test")
    validate_owned_stop_handshake(root,ui,identity,stop)
    cleanup=load(root/"owned-cleanup-before-final-pull.json")
    need(cleanup["after_confirmed_stream_close"] and cleanup["measured_pid"]==stop["pid"] and
         all(not r.get("pid_after") and not r.get("error") and not r.get("identity_error") for r in cleanup["packages"]),
         "final evidence was not collected after owned process cleanup")
    closed_files=list((root/"windows").glob("*-closed.json"))
    need(len(closed_files)==1,"collector closed receipt missing")
    closed=load(closed_files[0])
    need(closed["kind"]=="capture_closed" and closed["failed"] is False and closed["reader_closed_clean"] is True
         and closed["stop_reason"]=="owned_reader_stop" and (closed["pid"],closed["window_id"])==(stop["pid"],stop["window_id"]),"collector did not finish cleanly")
    need(ui["identity"]==identity,"reader UI identity")
    validate_case_clocks(cases)
    need(ui["complete"] and ui["plan"]==[{"id":c,"kind":c,"iteration":0} for c in CASES],"reader declared plan")
    need([c["id"] for c in cases]==list(CASES) and [c["kind"] for c in cases]==list(CASES)
         and all(c["iteration"]==0 for c in cases),"fixed reader case census")
    need(ui["fixture"]["sha256"]==fixture["sha256"] and ui["fixture"]["bytes"]==fixture["size"] and ui["fixture"]["public_title"]=="Sample.epub"
         and ui["fixture"]["query"]=="Chapter three" and ui["fixture"]["distinct_from_seed"],"reader fixture bytes/identity")
    need(all(float(v)==1 for v in ui["animation"].values()) and len(ui["animation"])==3,"animation profile")
    from PIL import Image
    screenshots=[];action_accepts={};action_generations={};images={}
    for case in cases:
        need(all(case.get(k)==v for k,v in identity.items()),"reader case identity")
        need(load(root/"ui/cases"/(case["id"]+".json"))==case,"reader per-case raw")
        path=root/"ui/shots"/(case["id"]+".png")
        with Image.open(path) as image:
            nonuniform=any(a!=b for a,b in image.convert("RGB").getextrema())
        screenshots.append({"case":case["id"],"nonuniform":nonuniform})
        if not nonuniform:problems.append("uniform reader screenshot: "+case["id"])
        expected="n/a" if case["id"]=="body_applicability" else "pass"
        if case["status"]!=expected:problems.append("reader UI "+case["id"]+": "+str(case.get("error",case["status"])))
        need(case["started_elapsed_ns"]<case["finished_elapsed_ns"],"reader case clock")
        detail=case["detail"]
        images[case["id"]]={phase:verified_image(root,detail[phase],
            not (case["id"]=="open" and phase=="before" or case["id"]=="return_shelf" and phase=="after")) for phase in ("before","after")}
        inputs=detail["inputs"]
        need(all(i["started_elapsed_ns"]<=i["finished_elapsed_ns"] for i in inputs),"actual public input clocks")
        if case["id"] in RENDER_CASES:
            need(inputs,"reader action has no recorded public input")
            first_input=min(i["started_elapsed_ns"] for i in inputs)
            need(case["started_elapsed_ns"]<=first_input<case["finished_elapsed_ns"],"public input outside case")
            selected=sorted([e for e in events if e["kind"]=="accept" and
                 first_input<=e["elapsed_ns"]<=case["finished_elapsed_ns"]],key=lambda e:(e["elapsed_ns"],e["sequence"]))
            action_generations[case["id"]]=[{k:e[k] for k in ("pid","window_id","accept_id","request_generation","elapsed_ns")} for e in selected]
            if not selected:problems.append("no accepted generation after actual public input: "+case["id"])
            else:
                value=selected[-1];action_accepts[case["id"]]=value;after=detail["after"]
                if any(e["pid"]!=case["pid"] or e["source_key"]!="epub:"+fixture["sha256"] for e in selected):
                    problems.append("wrong reader PID/book source: "+case["id"])
                page=re.match(r"^p\.([0-9]+)(?: |$)",after["page_label"])
                font=re.fullmatch(r"Size ([0-9]+)",after["font_label"])
                if not page or not font or int(page[1])!=value["page_index"]+1 or int(font[1])!=int(value["font"]) or after["book_title"]!="Sample.epub":
                    problems.append("last accepted generation differs from actual public target state: "+case["id"])
                target_draws=[e for e in events if e["kind"]=="bitmap_draw" and
                    (e["pid"],e["window_id"],e["accept_id"])==(value["pid"],value["window_id"],value["accept_id"])]
                capture_end=images[case["id"]]["after"]["capture_finished_elapsed_ns"]
                if not any(e["elapsed_ns"]<=capture_end for e in target_draws):
                    problems.append("target generation has no real paint by reader screenshot completion: "+case["id"])
    effects=image_effects(images)
    if any(not item["passed"] for item in effects):problems.append("reader visible page/font/locate effect or recovery missing")
    opened_ui=next(c for c in cases if c["id"]=="open")["detail"]
    need(opened_ui["import_status"]=="Imported Sample.epub","actual new independent EPUB import")
    found=next(c for c in cases if c["id"]=="search_found_select")["detail"]
    need(found["query"]=="Chapter three" and found["explicit_result_click"] and
         "Chapter three" in found["selected_result"] and re.match(r"[1-9][0-9]* 个结果",found["search_status_before_click"]),
         "real FOUND search result selection")
    if all(case in action_accepts for case in RENDER_CASES):
        a=action_accepts;opened=a["open"];forward=a["page_forward"];back=a["page_backward"]
        if (forward["part"],forward["page_index"],forward["start"])==(opened["part"],opened["page_index"],opened["start"]):problems.append("forward did not change source page")
        if any(back[k]!=opened[k] for k in ("part","page_index","start","font")):problems.append("back did not restore source page")
        if not a["font_increase"]["font"]>back["font"] or a["font_decrease"]["font"]!=opened["font"]:problems.append("font generations did not increase/restore")
        if (a["search_found_select"]["part"],a["search_found_select"]["start"])==(a["font_decrease"]["part"],a["font_decrease"]["start"]):problems.append("FOUND selection did not relocate source point")
    paints=[e for e in events if e["kind"]=="bitmap_draw"]
    body_na=bool(paints) and all(not e["fixed"] and e["pan_limit_x"]==e["pan_limit_y"]==0 for e in paints)
    if not body_na:problems.append("paged bitmap no-scroll N/A lacks actual pan-limit evidence")
    seed=load(root/"seed/seed.json")
    need(all(seed.get(k)==v for k,v in identity.items()) and seed["books"]==2202 and seed["production_mapping_complete"]
         and len(set(seed["source_keys"]))==2202,"independent original 2202 seed")
    pss=load(root/"pss-sampling.json");valid=[];problems.extend(pss["errors"])
    for sample in pss["samples"]:
        if sample.get("total_pss_kib") is None:continue
        need(not sample.get("process_changed_during_sample") and sample["pid"]==stop["pid"],"reader PSS changed process")
        raw=(root/"pss"/(str(sample["slot"])+".txt")).read_text()
        need(pss_total(raw,sample["pid"])==sample["total_pss_kib"],"reader PSS raw differs")
        valid.append(sample["total_pss_kib"])
    if not valid:problems.append("missing reader memory samples")
    all_frames=summary([f["total_ns"]/1e6 for f in frames]);ordinary=summary([f["total_ns"]/1e6 for f in frames if f["first_draw"]==0])
    matched=summary([b["total_ns"]/1e6 for b in binding["bindings"] if b["status"]=="complete" and b["first_draw"]==0])
    scenarios={}
    for name,kinds in {"reader_open":("open",),"reader_page":("page_forward","page_backward"),
                       "reader_font":("font_increase","font_decrease"),"reader_locate":("search_found_select",)}.items():
        keys={(a["pid"],a["window_id"],a["accept_id"]) for kind,a in action_accepts.items() if kind in kinds}
        rows=[b for b in binding["bindings"] if b["status"]=="complete" and (b["pid"],b["window_id"],b["accept_id"]) in keys]
        scenarios[name]={"all_frames_ms":summary([b["total_ns"]/1e6 for b in rows]),
                         "ordinary_frames_ms":summary([b["total_ns"]/1e6 for b in rows if b["first_draw"]==0]),
                         "first_draw_frames_ms":summary([b["total_ns"]/1e6 for b in rows if b["first_draw"]==1])}
    def within(value):return bool(value["count"] and value["p95"]<=16.67 and value["p99"]<=33.34)
    budget=bool(within(ordinary) and within(matched) and valid and max(valid)<=524288 and
                all(within(scenarios[name]["ordinary_frames_ms"]) for name in ("reader_page","reader_font","reader_locate")))
    return {"identity":identity,"problems":problems,"binding":binding,"all_window_frames_ms":all_frames,
            "ordinary_window_frames_ms":ordinary,"matched_reader_frames_ms":matched,"scenarios":scenarios,"screenshots":screenshots,
            "visible_reader_effects":effects,"action_generations":action_generations,
            "body":{"status":"n/a" if body_na else "missing","reason":"reflow paged bitmap has zero real pan limits"},
            "corpus":{"original_seed_books":2202,"supplemental_imports":1,"expected_total":2203,
                      "independently_observed_total":None,"fixture":fixture},
            "sampled_peak_pss_kib":max(valid,default=None),"valid_pss_samples":len(valid),
            "budget_passed":not problems and budget,"budget_values_within_limits":budget,"accepted":not problems,
            "tti_scope":"unchanged original Shelf case0; supplemental launch is not TTI", "f08_accepted":False}


def ready_prefix(snapshot,ui):
    """Validate a complete prefix without a footer; performance outliers never delay stop."""
    events=[];frames=[];owners=[];names=[]
    for folder,is_reader in ((snapshot,False),(snapshot/"reader-draw",True)):
        paths=sorted(folder.glob("*.jsonl"));need(len(paths)==1,"one current collector Window")
        for path in paths:
            raw=path.read_bytes();need(raw.endswith(b"\n"),"partial pre-stop snapshot")
            rows=[json.loads(line) for line in raw.splitlines()];header=rows[0]
            need(header["kind"]=="start" and not any(r["kind"]=="stop" for r in rows[1:]),"collector closed before explicit stop")
            owner=(header["pid"],header["window_id"]);owners.append(owner);names.append(path.relative_to(snapshot).as_posix())
            body=rows[1:]
            need(all(r["pid"]==owner[0] and r["window_id"]==owner[1] and r["sequence"]==i+1 for i,r in enumerate(body)),"pre-stop trace identity/sequence")
            if is_reader:
                reader_header(header)
                need(all(r["kind"] in ("page_set","accept","bitmap_draw","no_bitmap") for r in body),"reader failure before stop")
                events.extend(body)
            else:
                need(all(r["kind"]=="frame" and r["drop_count"]==0 for r in body),"Window callback failure before stop")
                frames.extend(body)
    need(len(set(owners))==1,"mixed pre-stop Window")
    report=associate(events,frames);need(report["binding_complete"],"required generation/frame association incomplete: "+repr(report["problems"]))
    validate_case_clocks(ui["cases"])
    for case in ui["cases"]:
        need(case["status"]==("n/a" if case["id"]=="body_applicability" else "pass"),"reader action failed before stop")
        if case["id"] not in RENDER_CASES:continue
        need(case["detail"]["inputs"],"reader action has no actual public input before stop")
        start=min(i["started_elapsed_ns"] for i in case["detail"]["inputs"])
        need(any(e["kind"]=="accept" and start<=e["elapsed_ns"]<=case["finished_elapsed_ns"] for e in events),"reader action has no accepted generation")
    return {"pid":owners[0][0],"window_id":owners[0][1],"binding_complete":True,
            "accepted_generations":report["accepted_generations"],"callbacks":len(frames),"prefix_files":[path.relative_to(snapshot).as_posix() for path in sorted(snapshot.rglob("*")) if path.is_file()]}


def stop_capture(plan,root,command,ui=None):
    import native_android as N
    ui=load(root/"pre-stop-ui.json") if ui is None else ui
    need(ui["identity"]==plan["identity"],"pre-stop UI identity")
    deadline=time.monotonic()+10;attempts=[];ready=None
    for index in range(20):
        if time.monotonic()>=deadline:break
        target=root/"pre-stop"/("attempt-%02d"%index);target.mkdir(parents=True)
        item={"snapshot":target.relative_to(root).as_posix(),"host_mono_ns":time.monotonic_ns()}
        try:
            command("pre-stop-pull-%02d"%index,"pull","/sdcard/Android/data/"+N.APP+"/files/shelf-window-metrics",
                    target/"windows",timeout=max(.1,min(3,deadline-time.monotonic())))
            ready=ready_prefix(target/"windows",ui);ready["snapshot"]=(target/"windows").relative_to(root).as_posix()
            item["ready"]=True
        except Exception as error:item["error"]=repr(error)
        attempts.append(item);save(root/"pre-stop-attempts.json",attempts)
        if ready:break
        time.sleep(min(.25,max(0,deadline-time.monotonic())))
    need(ready is not None,"reader required action callbacks did not complete before explicit stop")
    save(root/"pre-stop-ready.json",ready)
    actual=N.adb(plan,"shell","pidof",N.APP,timeout=3).strip()
    need(actual==str(ready["pid"]),"owned capture PID changed before stop")
    request={"pid":ready["pid"],"window_id":ready["window_id"],"sent":False,"host_mono_ns":time.monotonic_ns()}
    save(root/"stop-request.json",request)
    command("request-owned-stop","shell","am","start","-n",N.APP+"/.MainActivity","--activity-single-top",
            "--ez","f08_capture_stop","true","--ei","f08_expected_pid",str(ready["pid"]),
            "--el","f08_expected_window",str(ready["window_id"]),timeout=5)
    request["sent"]=True;request["host_finished_mono_ns"]=time.monotonic_ns();save(root/"stop-request.json",request)
    close_barrier(plan,root)
    target=root/"close-confirm/windows"
    command("pull-close-confirm","pull","/sdcard/Android/data/"+N.APP+"/files/shelf-window-metrics",target,timeout=10)
    for name in ready["prefix_files"]:
        need((target/name).read_bytes().startswith((root/ready["snapshot"]/name).read_bytes()),"pre-stop prefix missing at close: "+name)
    need(not list(target.glob("*-capture-error.json")),"collector failure before owned cleanup")
    for path in target.glob("*.jsonl"):
        need(jsonl(path)[-1]["stop_reason"]=="owned_reader_stop","native explicit footer before cleanup")
    for path in (target/"reader-draw").glob("*.jsonl"):
        need(jsonl(path)[-1]["stop_reason"]=="owned_reader_stop","reader explicit footer before cleanup")
    save(root/"close-confirm.json",{"confirmed":True,"pid":ready["pid"],"window_id":ready["window_id"],
         "host_mono_ns":time.monotonic_ns()})


def close_barrier(plan,root):
    """Read actual owned-signal stop records; never redraw or force-stop to manufacture one."""
    import native_android as N
    deadline=time.monotonic()+10;attempts=[]
    remote="/sdcard/Android/data/"+N.APP+"/files/shelf-window-metrics"
    while time.monotonic()<deadline:
        item={"host_mono_ns":time.monotonic_ns(),"tails":[]};complete=False
        try:
            names=N.adb(plan,"shell","ls",remote+"/reader-draw",timeout=min(2,deadline-time.monotonic())).splitlines()
            need(len(names)==1 and re.fullmatch(r"window-[0-9]+-[0-9]+\.jsonl",names[0]),"one actual reader Window")
            for folder in ("","/reader-draw"):
                remaining=deadline-time.monotonic();need(remaining>0,"reader close deadline")
                raw=N.adb(plan,"shell","tail","-n","1",remote+folder+"/"+names[0],timeout=min(2,remaining))
                item["tails"].append({"folder":folder,"raw":raw})
            remaining=deadline-time.monotonic();need(remaining>0,"reader close receipt deadline")
            receipt=N.adb(plan,"shell","cat",remote+"/"+names[0].replace(".jsonl","-closed.json"),timeout=min(2,remaining))
            item["closed_receipt_raw"]=receipt;closed=json.loads(receipt);owner=load(root/"stop-request.json")
            complete=all(json.loads(t["raw"])["kind"]=="stop" and json.loads(t["raw"])["stop_reason"]=="owned_reader_stop" for t in item["tails"]) and (
                closed["kind"]=="capture_closed" and closed["failed"] is False and closed["reader_closed_clean"] is True
                and closed["stop_reason"]=="owned_reader_stop" and (closed["pid"],closed["window_id"])==(owner["pid"],owner["window_id"]))
        except Exception as error:item["error"]=repr(error)
        attempts.append(item)
        if complete:save(root/"trace-close-barrier.json",{"complete":True,"attempts":attempts});return
        time.sleep(min(.25,max(0,deadline-time.monotonic())))
    save(root/"trace-close-barrier.json",{"complete":False,"attempts":attempts})
    raise ValueError("native reader streams did not close after the owned signal")




def owned_closed_elapsed(root,pid,window_id):
    times=[]
    for folder,field in ((root/"close-confirm/windows","footer_elapsed_ns"),
                         (root/"close-confirm/windows/reader-draw","elapsed_ns")):
        paths=list(folder.glob("*.jsonl"));need(len(paths)==1,"one authenticated closed stream")
        rows=jsonl(paths[0]);header,footer=rows[0],rows[-1]
        need(header["kind"]=="start" and header["pid"]==pid and header["window_id"]==window_id and
             footer["kind"]=="stop" and footer["stop_reason"]=="owned_reader_stop","explicit close stream owner")
        value=footer[field];need(type(value) is int and value>0,"native close clock")
        times.append(value)
    return max(times)


def validate_owned_stop_handshake(root,ui,identity,stop):
    raw=(root/"actions-ready.json").read_bytes();ready=json.loads(raw)
    ack=load(root/"stop-ack.json");trace=load(root/"reader-ui-lifecycle.json")
    need(ready["schema"]=="reader-owned-stop-ready-v1" and ack["schema"]=="reader-owned-stop-ack-v1",
         "owned stop handshake schemas")
    need(re.fullmatch(r"[0-9a-f]{64}",ready["nonce"]) and ready["nonce"]==ack["nonce"]==trace["nonce"],
         "owned stop challenge binding")
    need(ready["identity"]==ack["identity"]==ui["identity"]==identity,"owned stop handshake identities")
    need(ack["confirmed"] is True and ack["product_pid"]==ready["product_pid"]==stop["pid"] and
         ack["helper_pid"]==ready["helper_pid"] and ack["window_id"]==stop["window_id"],"owned stop handshake process/window")
    need(ack["ready_sha256"]==trace["ready_sha256"]==hashlib.sha256(raw).hexdigest(),"owned stop readiness content binding")
    need(trace["instrumentation_thread_alive"] is False and trace["instrumentation_error"] is None,
         "instrumentation not completed after close")
    need(ui["native_stop_handshake"]==ack and all(ui.get(k)==v for k,v in ready["validation"].items()),
         "helper actions changed during stop/cleanup handshake")
    native_end=owned_closed_elapsed(root,stop["pid"],stop["window_id"])
    need(ack["native_closed_elapsed_ns"]==native_end and
         ready["validation"]["cases"][-1]["finished_elapsed_ns"]<=ready["ready_elapsed_ns"]<=native_end<=
         ui["cleanup"]["started_elapsed_ns"]<=ui["finished_elapsed_ns"]<=ready["deadline_elapsed_ns"],
         "native close must precede helper cleanup within original cohort")
    need(ready["deadline_elapsed_ns"]-ready["validation"]["started_elapsed_ns"]==180_000_000_000 and
         ready["ready_elapsed_ns"]<ready["deadline_elapsed_ns"]-10_000_000_000,
         "original cohort deadline and cleanup reserve")


def run_ui_with_owned_stop(plan,root,command,*instrument_args,timeout=210):
    """Keep the original UI cohort alive until its native collectors close explicitly."""
    import native_android as N
    nonce=secrets.token_hex(32)
    deadline=min(time.monotonic()+timeout,plan["operation_deadline_mono"])
    args=(*instrument_args[:-1],"-e","exr_stop_nonce",nonce,instrument_args[-1])
    outcome={};trace={"nonce":nonce,"instrument_deadline_mono":deadline,"polls":0}
    def remaining(cap):
        left=deadline-time.monotonic()
        need(left>0,"reader instrumentation absolute deadline exhausted")
        return min(cap,left)
    def bounded_command(name,*values,timeout=45,check=True):
        return command(name,*values,timeout=remaining(timeout),check=check)
    def invoke():
        try:outcome["stdout"]=command("reader-ui",*args,timeout=remaining(timeout))
        except Exception as error:outcome["error"]=repr(error)
    task=threading.Thread(target=invoke,name="f08-owned-reader-instrumentation")
    task.start()
    remote="/sdcard/Android/data/"+N.HELPER+"/files/reader-evidence/"
    try:
        ready=None;raw=None
        while time.monotonic()<deadline:
            response=N.adb(plan,"shell","cat",remote+"actions-ready.json",raw=True,check=False,
                           timeout=remaining(3))
            trace["polls"]+=1
            if response.returncode==0:
                raw=response.stdout;ready=json.loads(raw);break
            if not task.is_alive():raise ValueError("reader instrumentation ended before authenticated readiness: "+repr(outcome.get("error")))
            time.sleep(min(.5,max(0,deadline-time.monotonic())))
        need(ready is not None,"reader readiness deadline")
        need(ready["schema"]=="reader-owned-stop-ready-v1" and ready["nonce"]==nonce and
             ready["identity"]==plan["identity"],"fresh reader readiness identity")
        need(type(ready["helper_pid"]) is int and ready["helper_pid"]>0 and
             type(ready["product_pid"]) is int and ready["product_pid"]>0,"readiness PID types")
        ui=ready["validation"]
        need(ui["identity"]==plan["identity"] and [c["id"] for c in ui["cases"]]==list(CASES),
             "exact original actions before close")
        need(ready["deadline_elapsed_ns"]-ui["started_elapsed_ns"]==180_000_000_000 and
             ui["cases"][-1]["finished_elapsed_ns"]<=ready["ready_elapsed_ns"]<
             ready["deadline_elapsed_ns"]-10_000_000_000,"original cohort and cleanup reserve")
        need(N.adb(plan,"shell","pidof",N.HELPER,timeout=remaining(3)).strip()==str(ready["helper_pid"]) and
             N.adb(plan,"shell","pidof",N.APP,timeout=remaining(3)).strip()==str(ready["product_pid"]),
             "readiness belongs to current owned processes")
        (root/"actions-ready.json").write_bytes(raw)
        trace["ready_sha256"]=hashlib.sha256(raw).hexdigest()
        remaining(1)
        stop_plan={**plan,"operation_deadline_mono":min(plan["operation_deadline_mono"],deadline)}
        stop_capture(stop_plan,root,bounded_command,ui=ui)
        closed=load(root/"close-confirm.json")
        need(closed["confirmed"] is True and closed["pid"]==ready["product_pid"] and
             type(closed["window_id"]) is int and closed["window_id"]>0,"close binds readiness owner")
        ack={"schema":"reader-owned-stop-ack-v1","nonce":nonce,"identity":plan["identity"],
             "helper_pid":ready["helper_pid"],"product_pid":ready["product_pid"],"window_id":closed["window_id"],
             "confirmed":True,"ready_sha256":trace["ready_sha256"],
             "native_closed_elapsed_ns":owned_closed_elapsed(root,closed["pid"],closed["window_id"])}
        remaining(1)
        save(root/"stop-ack.json",ack)
        command("push-stop-ack","push",root/"stop-ack.json",remote+"stop-ack.json.tmp",
                timeout=remaining(5))
        command("publish-stop-ack","shell","mv",remote+"stop-ack.json.tmp",remote+"stop-ack.json",
                timeout=remaining(3))
        task.join(max(0,deadline-time.monotonic()))
        need(not task.is_alive() and "error" not in outcome,"reader UI completion after native close: "+repr(outcome.get("error")))
        return outcome["stdout"]
    finally:
        first_error=sys.exc_info()[1]
        if task.is_alive():
            # Never start another operation after this instrumentation deadline.
            # The existing outer owned cleanup remains responsible on a timed-out path.
            if time.monotonic()<deadline:
                try:bounded_command("abort-owned-reader-instrumentation","shell","am","force-stop",N.HELPER,timeout=5)
                except Exception as error:trace["abort_error"]=repr(error)
            else:trace["cleanup_deferred_to_owned_outer_finally"]=True
            task.join(max(0,min(10,plan["operation_deadline_mono"]-time.monotonic())))
        trace["instrumentation_thread_alive"]=task.is_alive()
        trace["instrumentation_error"]=outcome.get("error")
        try:save(root/"reader-ui-lifecycle.json",trace)
        except Exception as diagnostic_error:
            if first_error is None:raise
            print("reader lifecycle diagnostic write failed (original error preserved): "+repr(diagnostic_error),file=sys.stderr)


def run(plan,root,proof,namespace):
    """Invoked inside the existing native worker's unchanged 1100-second parent cap."""
    import native_android as N
    root=Path(root);root.mkdir(exist_ok=False);(root/"pss").mkdir()
    identity=plan["identity"];fixture=proof["final_build"]["reader_fixture"]
    result={"problems":[],"accepted":False};samples={"samples":[],"errors":[]};stop=threading.Event();thread=None
    def command(name,*args,timeout=45,check=True):
        call=N.adb(plan,*args,raw=True,check=False,timeout=timeout)
        (root/(name+".stdout.txt")).write_bytes(call.stdout);(root/(name+".stderr.txt")).write_bytes(call.stderr)
        need(not check or call.returncode==0,"reader adb command: "+name)
        return call.stdout.decode(errors="replace")
    def sample():
        try:
            while not stop.is_set():
                slot=len(samples["samples"]);start=time.monotonic_ns()
                text=N.adb(plan,"shell","pidof",N.APP,check=False,timeout=10).strip()
                item={"slot":slot,"pid":int(text) if re.fullmatch(r"[0-9]+",text) else None}
                if item["pid"] is not None:
                    raw=N.adb(plan,"shell","dumpsys","meminfo",str(item["pid"]),timeout=15)
                    (root/"pss"/(str(slot)+".txt")).write_text(raw,encoding="utf-8")
                    after=N.adb(plan,"shell","pidof",N.APP,check=False,timeout=10).strip()
                    if after!=str(item["pid"]):item["process_changed_during_sample"]=True
                    else:item["total_pss_kib"]=namespace["pss_total"](raw,item["pid"])
                item["collection_elapsed_ms"]=(time.monotonic_ns()-start)/1e6;samples["samples"].append(item)
                stop.wait(max(0,1-(time.monotonic_ns()-start)/1e9))
        except Exception as error:samples["errors"].append(repr(error))
    try:
        # The original ten-case raw tree was pulled and inventoried by the native worker before this clear.
        command("install-reader-helper","install","-r","-t",N.ROOT/"build/android-host/artifacts/reader-uitest-debug-androidTest.apk")
        paths=[line.removeprefix("package:") for line in N.adb(plan,"shell","pm","path",N.HELPER+".test").splitlines() if line.startswith("package:")]
        need(len(paths)==1,"installed reader helper path")
        command("pull-installed-reader-helper","pull",paths[0],root/"installed-test.apk")
        digest=N.sha(root/"installed-test.apk");expected=proof["final_build"]["reader_test_apk"]["sha256"]
        save(root/"installed-test-identity.json",{"sha256":digest,"producer_sha256":expected,"matches_producer":digest==expected})
        need(digest==expected,"installed reader helper differs from producer")
        command("clear-independent-cohort","shell","pm","clear",N.APP)
        seed=command("seed","shell","am","instrument","-w","-r","-e","phase","seed-ui","-e","source_sha",identity["source_sha"],
                     "-e","run_id",identity["run_id"],"-e","attempt",identity["attempt"],
                     N.APP+".test/org.exreader.host.ShelfCatalogTest",timeout=900)
        need("EXR_SHELF_SEEDED 2202" in seed and "INSTRUMENTATION_CODE: -1" in seed,"reader real SDK seed")
        command("pull-seed","pull","/sdcard/Android/data/"+N.APP+"/files/shelf-tests",root/"seed",timeout=120)
        command("stop-unmeasured-seeder","shell","am","force-stop",N.APP)
        command("push-reader-fixture","push",N.ROOT/"build/android-host/fixtures/Sample.epub","/sdcard/Download/Sample.epub")
        thread=threading.Thread(target=sample);thread.start()
        command("launch-reader-shelf","shell","am","start","-n",N.APP+"/.MainActivity","--ez","shelf_metrics","true")
        ui=run_ui_with_owned_stop(plan,root,command,"shell","am","instrument","-w","-r","-e","disableAnalytics","true",
                   "-e","class","org.exreader.host.uitest.ReaderF08UiTest#reader",
                   "-e","source_sha",identity["source_sha"],"-e","run_id",identity["run_id"],"-e","attempt",identity["attempt"],
                   "-e","exr_fixture_name","Sample.epub","-e","exr_fixture_path","/sdcard/Download/Sample.epub",
                   "-e","exr_fixture_sha256",fixture["sha256"],"-e","exr_fixture_bytes",str(fixture["size"]),
                   "-e","exr_query","'Chapter three'",proof["final_build"]["reader_test_apk"]["runner"],timeout=210)
        ui_report=command("reader-ui-validation","shell","cat","/sdcard/Android/data/"+N.HELPER+"/files/reader-evidence/validation.json",timeout=10)
        save(root/"pre-stop-ui.json",json.loads(ui_report))
        validate_owned_stop_handshake(root,load(root/"pre-stop-ui.json"),identity,load(root/"stop-request.json"))
        need("INSTRUMENTATION_CODE: -1" in ui and "FAILURES!!!" not in ui,"reader UI instrumentation failed")
    except Exception as error:result["problems"].append(repr(error))
    finally:
        stop.set()
        if thread:thread.join(max(0,min(20,plan["operation_deadline_mono"]-time.monotonic())))
        if thread and thread.is_alive():samples["errors"].append("reader PSS sampler did not stop")
        save(root/"pss-sampling.json",samples)
        # A successful footer/receipt is authenticated before cleanup. On failure this
        # remains incomplete; force-stop never supplies the missing collector footer.
        cleanup_deadline=min(time.monotonic()+40,plan["operation_deadline_mono"])
        measured_pid=load(root/"stop-request.json")["pid"] if (root/"stop-request.json").exists() else None
        cleanup={"measured_pid":measured_pid,"after_confirmed_stream_close":(root/"close-confirm.json").exists(),"packages":[],"host_started_mono_ns":time.monotonic_ns()}
        for package in (N.HELPER,N.APP):
            record={"package":package}
            try:
                remaining=cleanup_deadline-time.monotonic();need(remaining>0,"reader owned cleanup deadline")
                record["pid_before"]=N.adb(plan,"shell","pidof",package,check=False,timeout=min(10,remaining)).strip()
                if package==N.APP and record["pid_before"] and measured_pid is not None and record["pid_before"]!=str(measured_pid):
                    record["identity_error"]="owned app PID changed after capture close"
                    result["problems"].append(record["identity_error"])
                remaining=cleanup_deadline-time.monotonic();need(remaining>0,"reader owned cleanup deadline")
                command("cleanup-"+package,"shell","am","force-stop",package,timeout=min(10,remaining))
                remaining=cleanup_deadline-time.monotonic();need(remaining>0,"reader owned cleanup deadline")
                record["pid_after"]=N.adb(plan,"shell","pidof",package,check=False,timeout=min(10,remaining)).strip()
                need(not record["pid_after"],"owned package remains after reader cleanup")
            except Exception as error:record["error"]=repr(error);result["problems"].append("cleanup: "+repr(error))
            cleanup["packages"].append(record)
        cleanup["host_finished_mono_ns"]=time.monotonic_ns();save(root/"owned-cleanup-before-final-pull.json",cleanup)
        for remote,target in (("/sdcard/Android/data/"+N.HELPER+"/files/reader-evidence","ui"),
                              ("/sdcard/Android/data/"+N.APP+"/files/shelf-window-metrics","windows")):
            try:
                if not (root/target).exists():command("pull-"+target,"pull",remote,root/target,timeout=120)
            except Exception as error:result["problems"].append("collection: "+repr(error))
        try:command("logcat","logcat","-d","-v","threadtime")
        except Exception as error:result["problems"].append("logcat: "+repr(error))
        try:
            replay=analyze(root,identity,fixture,namespace["pss_total"])
            result={**replay,"collection_problems":result["problems"],"accepted":replay["accepted"] and not result["problems"]}
        except Exception:result["problems"].append(traceback.format_exc())
        save(root/"result.json",result)
    return result
