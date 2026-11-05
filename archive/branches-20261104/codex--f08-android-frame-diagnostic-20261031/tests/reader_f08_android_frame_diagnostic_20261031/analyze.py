"""Replay every callback and raw gfxinfo/token join. No F08 acceptance."""
import csv,collections,hashlib,io,json,math,subprocess,sys
from pathlib import Path
FIELDS=("unknown_ns","input_ns","animation_ns","layout_measure_ns","draw_ns","sync_ns","command_issue_ns","swap_buffers_ns","total_ns","gpu_ns","deadline_ns")
def need(value,message):
    if not value:raise ValueError(message)
def load(path):return json.loads(Path(path).read_text())
def stats(values):
    ordered=sorted(values)
    return {"count":len(ordered),"p50":ordered[math.ceil(len(ordered)*.50)-1] if ordered else None,
        "p95":ordered[math.ceil(len(ordered)*.95)-1] if ordered else None,
        "p99":ordered[math.ceil(len(ordered)*.99)-1] if ordered else None,"max":ordered[-1] if ordered else None}
def frame_stats(rows):
    return {field.removesuffix("_ns")+"_ms":stats([r[field]/1e6 for r in rows if type(r.get(field)) is int and r[field]>=0]) for field in FIELDS}
def gfx_rows(directory):
    rows={};invalid=[];snapshots={}
    ordering=lambda p:0 if p.stem=="gfxinfo-initial" else 9 if p.stem=="gfxinfo-final" else 1+int(p.stem.rsplit("-",1)[1])
    for path in sorted(Path(directory).glob("gfxinfo-*.txt"),key=ordering):
        header=None;count=0
        for line in path.read_text(errors="replace").splitlines():
            values=next(csv.reader([line]))
            while values and values[-1]=="":values.pop()
            if values and values[0]=="Flags" and "IntendedVsync" in values:header=values;continue
            if header is None or not values or len(values)!=len(header):continue
            try:row={k:int(v) for k,v in zip(header,values)}
            except ValueError:continue
            count+=1
            token=row.get("FrameTimelineVsyncId")
            key=(row["IntendedVsync"],token)
            if row["IntendedVsync"]<=0:invalid.append({"snapshot":path.name,"row":row});continue
            # Keep all snapshots verbatim. The last snapshot is the final version
            # of the same ring entry; it may acquire completion fields later.
            rows[key]=row
        snapshots[path.name]=count
    return list(rows.values()),invalid,snapshots

def replay(directory,identity):
    root=Path(directory);report=load(root/"report.json");seed=load(root/"seed/seed.json")
    need(all(report.get(k)==v and seed.get(k)==v for k,v in identity.items()),"diagnostic/seed identity")
    need(report.get("f08_accepted") is False and report.get("books")==2202,"diagnostic corpus/F08")
    need(seed.get("books")==2202 and seed.get("txt_books")==2201 and seed.get("pdf_books")==1
        and seed.get("production_mapping_complete") is True and len(set(seed.get("source_keys",[])))==2202,"original seed corpus")
    frames=[json.loads(line) for line in (root/"frames.jsonl").read_text().splitlines()]
    need(report.get("stored_frames")==len(frames) and report.get("callbacks")==len(frames)+report.get("overflow_callbacks",0),"all callback census")
    need([r["sequence"] for r in frames]==list(range(1,len(frames)+1)),"callback sequence")
    need(all(r["pid"]==report["pid"] and r["window_identity"]==report["initial"]["window_identity"] for r in frames),"single Window/PID")
    segments=report.get("segments",[])
    need([s["requested_layer"] for s in segments]==[0,1,1,0] and [s["slot"] for s in segments]==list(range(4)),"ABBA layers")
    expected=report["initial"]
    previous=0
    for segment in segments:
        need(previous<segment["start_mono_ns"]<segment["end_mono_ns"],"monotonic disjoint intervals");previous=segment["end_mono_ns"]
        for phase in ("start","forward","end"):
            value=segment[phase]
            need(all(value[k]==expected[k] for k in ("pid","activity_identity","window_identity","view_identity","resource_name")),"same actual native ListView")
            need(value["layer_type"]==segment["requested_layer"] and value["attached"] and value["shown"] and value["width"]>0 and value["height"]>0,"visible applied layer")
        pose=lambda value:(value["first_position"],value["first_top"])
        need(pose(segment["start"])!=pose(segment["forward"]) and pose(segment["forward"])!=pose(segment["end"]),"actual bidirectional ListView motion")
    need(report["original_layer"]==0 and report["restored"]["layer_type"]==0,"original layer restored")
    need(report["activity_creates"]==1,"one Activity instance")
    groups={str(i):[] for i in range(4)};groups.update(outside=[],unknown=[])
    for row in frames:
        if type(row.get("intended_vsync_ns")) is not int or row["intended_vsync_ns"]<=0:groups["unknown"].append(row);continue
        selected=[s for s in segments if s["start_mono_ns"]<=row["intended_vsync_ns"]<s["end_mono_ns"]]
        need(len(selected)<=1,"overlapping frame segment")
        groups[str(selected[0]["slot"]) if selected else "outside"].append(row)
    need(sum(map(len,groups.values()))==len(frames),"all frame classification")
    unavailable={name:sum(type(r.get(name)) is not int or r[name]<0 for r in frames) for name in FIELDS}
    invalid_total=sum(type(r.get("total_ns")) is not int or r["total_ns"]<=0 for r in frames)
    drops=sum(r["drop_count"] for r in frames)
    need(drops==report["callback_drops"],"callback drop sum")
    complete=report.get("completed") is True and not report.get("problems") and not report["overflow_callbacks"] and not drops and not invalid_total and all(r["same_window"] for r in frames)
    complete=bool(complete and len(frames)>100 and all(len(groups[str(i)])>=10 for i in range(4)))
    details=[]
    for i in range(4):
        rows=groups[str(i)];metrics=frame_stats(rows)
        details.append({"slot":i,"layer":"NONE" if i in (0,3) else "SOFTWARE","all":metrics,
            "ordinary":frame_stats([r for r in rows if r["first_draw"]==0]),"first_draw":frame_stats([r for r in rows if r["first_draw"]==1]),
            "unknown_first_draw":sum(r["first_draw"] not in (0,1) for r in rows),
            "total_budget_checks":{"p95":metrics["total_ms"]["p95"] is not None and metrics["total_ms"]["p95"]<=16.67,
                "p99":metrics["total_ms"]["p99"] is not None and metrics["total_ms"]["p99"]<=33.34}})
    pooled={name:frame_stats(groups[str(a)]+groups[str(b)]) for name,a,b in (("NONE",0,3),("SOFTWARE",1,2))}
    gfx,invalid_gfx,snapshots=gfx_rows(root)
    by_vsync=collections.defaultdict(list)
    for row in gfx:by_vsync[row["IntendedVsync"]].append(row)
    joins=[]
    for frame in frames:
        candidates=by_vsync.get(frame["intended_vsync_ns"],[])
        slot=next((s["slot"] for s in segments if s["start_mono_ns"]<=frame["intended_vsync_ns"]<s["end_mono_ns"]),"outside")
        gfx=candidates[0] if len(candidates)==1 else None
        raw_total=gfx["FrameCompleted"]-gfx["IntendedVsync"] if gfx and 0<gfx.get("FrameCompleted",0)<2**63-1 else None
        joins.append({"sequence":frame["sequence"],"intended_vsync_ns":frame["intended_vsync_ns"],"slot":slot,
            "status":"unique" if len(candidates)==1 else "missing" if not candidates else "ambiguous",
            "java_total_ns":frame["total_ns"],"raw_gfxinfo_total_ns":raw_total,"total_exact_match":raw_total==frame["total_ns"] if raw_total is not None else None,
            "sync_queue_wait_ns":gfx["SyncStart"]-gfx["SyncQueued"] if gfx and gfx.get("SyncStart",0)>0 and gfx.get("SyncQueued",0)>0 else None,
            "dequeue_ns":gfx.get("DequeueBufferDuration") if gfx else None,"queue_ns":gfx.get("QueueBufferDuration") if gfx else None,
            "gfxinfo":gfx if gfx is not None else candidates})
    return {**identity,"f08_accepted":False,"diagnostic_complete":complete,"pid":report["pid"],"callbacks":len(frames),
        "callback_drops":drops,"overflow_callbacks":report["overflow_callbacks"],"invalid_total":invalid_total,"unavailable":unavailable,
        "all_frames":frame_stats(frames),"first_draw_frames":frame_stats([r for r in frames if r["first_draw"]==1]),
        "ordinary_frames":frame_stats([r for r in frames if r["first_draw"]==0]),"outside":frame_stats(groups["outside"]),"unknown":frame_stats(groups["unknown"]),
        "abba":details,"pooled":pooled,"gfxinfo_snapshots":snapshots,"gfxinfo_ring_rows":len(gfx),"gfxinfo_invalid_rows":invalid_gfx,
        "gfxinfo_join_counts":dict(collections.Counter(j["status"] for j in joins)),"gfxinfo_total_exact_matches":sum(j["total_exact_match"] is True for j in joins),
        "gfxinfo_total_mismatches":sum(j["total_exact_match"] is False for j in joins),
        "gfxinfo_breakdown_ms":{name:stats([j[name]/1e6 for j in joins if type(j.get(name)) is int and j[name]>=0]) for name in ("sync_queue_wait_ns","dequeue_ns","queue_ns")},"raw_gfxinfo_joins":joins,
        "budgets_unchanged":{"p95_ms":16.67,"p99_ms":33.34,"tti_ms":2000,"pss_bytes":512*1024**2}}

def trace_queries(pid):
    return {
        "timeline":f"SELECT a.ts,a.dur,a.surface_frame_token,a.display_frame_token,a.layer_name,a.jank_type,a.present_type,a.on_time_finish,a.gpu_composition,p.pid,p.name AS process_name FROM actual_frame_timeline_slice a JOIN process p USING(upid) WHERE p.pid={pid} OR p.name GLOB '*surfaceflinger*' ORDER BY a.ts,a.id",
        "app_slices":f"SELECT s.ts,s.dur,s.name,t.name AS track_name,th.tid,th.name AS thread_name,COALESCE(p.pid,p2.pid) AS pid FROM slice s JOIN track t ON t.id=s.track_id LEFT JOIN thread_track tt ON tt.id=s.track_id LEFT JOIN thread th ON th.utid=tt.utid LEFT JOIN process p ON p.upid=th.upid LEFT JOIN process_track pt ON pt.id=s.track_id LEFT JOIN process p2 ON p2.upid=pt.upid WHERE COALESCE(p.pid,p2.pid)={pid} ORDER BY s.ts,s.id",
        "thread_states":f"SELECT th.tid,th.name,st.state,count(*) AS slices,sum(CASE WHEN st.dur>0 THEN st.dur ELSE 0 END) AS total_ns FROM thread_state st JOIN thread th USING(utid) JOIN process p USING(upid) WHERE p.pid={pid} GROUP BY th.tid,th.name,st.state ORDER BY th.tid,st.state",
        "loss":"SELECT name,idx,severity,source,value FROM stats WHERE value!=0 AND (severity IN ('error','data_loss') OR name GLOB '*lost*' OR name GLOB '*overrun*') ORDER BY name,idx"}

def parse_trace(root,launcher,out):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True);pid=load(root/"report.json")["pid"]
    result={}
    for name,query in trace_queries(pid).items():
        (out/(name+".sql")).write_text(query+";\n")
        run=subprocess.run([sys.executable,str(launcher),"-Q",query,str(root/"trace.perfetto-trace")],capture_output=True,timeout=120)
        (out/(name+".csv")).write_bytes(run.stdout);(out/(name+".stderr.txt")).write_bytes(run.stderr)
        need(run.returncode==0,"Trace Processor query failed: "+name+" "+run.stderr.decode(errors="replace")[-1500:])
        result[name]=list(csv.DictReader(io.StringIO(run.stdout.decode())))
    need(result["timeline"] and {"pid","jank_type","surface_frame_token","display_frame_token"}<=set(result["timeline"][0]),"FrameTimeline schema/data unavailable")
    app=[r for r in result["timeline"] if int(r["pid"])==pid]
    sf=[r for r in result["timeline"] if int(r["pid"])!=pid]
    markers=[r for r in result["app_slices"] if r["name"].startswith("F08_ABBA_")]
    replayed=replay(root,{k:load(root/"report.json")[k] for k in ("source_sha","run_id","attempt")})
    app_by_token=collections.defaultdict(list);sf_by_token=collections.defaultdict(list)
    for row in app:app_by_token[row["surface_frame_token"]].append(row)
    for row in sf:sf_by_token[row["display_frame_token"]].append(row)
    token_joins=[]
    for row in replayed["raw_gfxinfo_joins"]:
        gfx=row["gfxinfo"]
        token=str(gfx.get("FrameTimelineVsyncId")) if row["status"]=="unique" else None
        matches=app_by_token.get(token,[])
        token_joins.append({"sequence":row["sequence"],"intended_vsync_ns":row["intended_vsync_ns"],"slot":row["slot"],"gfxinfo_status":row["status"],
            "surface_frame_token":token,"app_matches":matches,"sf_matches":[sfrow for approw in matches for sfrow in sf_by_token.get(approw["display_frame_token"],[])]})
    return {"trace_complete":bool(app and sf and result["thread_states"] and not result["loss"]),"app_frame_timeline_rows":len(app),
        "sf_frame_timeline_rows":len(sf),"app_jank_types":dict(collections.Counter(r["jank_type"] for r in app)),
        "sf_jank_types":dict(collections.Counter(r["jank_type"] for r in sf)),"markers":markers,"thread_states":result["thread_states"],"loss":result["loss"],
        "callback_to_app_token_joins":sum(bool(r["app_matches"]) for r in token_joins),
        "callback_to_sf_token_joins":sum(bool(r["sf_matches"]) for r in token_joins),
        "per_slot_app_jank_types":{str(slot):dict(collections.Counter(a["jank_type"] for j in token_joins if j["slot"]==slot for a in j["app_matches"])) for slot in range(4)},
        "raw_token_joins":token_joins,"f08_accepted":False}
