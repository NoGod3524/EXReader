"""Fixed 2202-book native reader-body and explicit FOUND search jumps."""
import configparser,hashlib,io,json,os,shutil,stat,subprocess,sys,tempfile,time,traceback,zipfile
from pathlib import Path,PurePosixPath
import full as F
R=F.R;ROOT=F.ROOT;HERE=F.HERE;OUT=ROOT/"build/f08-linux-body-jump"
PRODUCER_RUN=41238271101;PRODUCER_SHA="82d6d757346b6450d3290a2c8cafb27b43d4a431"
sys.path.insert(0,str(ROOT/"tests/reader_perf_gtk"));sys.path.insert(0,str(ROOT/"tests/reader_a11y_gtk"))
import observe as O
def stamp():return time.monotonic_ns()//1000
def load(p):return json.loads(p.read_text())
def api(path):return subprocess.check_output(["gh","api","repos/NoGod3524/EXReader/"+path])
def producer():
 meta_run=json.loads(api("actions/runs/"+str(PRODUCER_RUN)));R.need(meta_run["head_sha"]==PRODUCER_SHA and meta_run["status"]=="completed","completed fixed producer")
 artifacts=json.loads(api("actions/runs/"+str(PRODUCER_RUN)+"/artifacts"))["artifacts"];matches=[a for a in artifacts if a["name"]=="f08-linux-product-"+str(PRODUCER_RUN)+"-1"]
 R.need(len(matches)==1,"fixed original artifact");meta=matches[0];data=api("actions/artifacts/"+str(meta["id"])+"/zip");digest=hashlib.sha256(data).hexdigest()
 R.need(meta["digest"]=="sha256:"+digest and len(data)==meta["size_in_bytes"] and not meta["expired"],"producer ZIP identity")
 selected={};manifest=None
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  infos=z.infolist();R.need(len(infos)<20000 and sum(i.file_size for i in infos)<4*1024**3,"producer ZIP bounds");names=set()
  for info in infos:
   p=PurePosixPath(info.filename);key=str(p).casefold();R.need(str(p)!="." and not p.is_absolute() and ".." not in p.parts and "\\" not in info.filename and ":" not in info.filename and key not in names,"producer ZIP path");names.add(key)
   R.need(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"producer ZIP kind")
  manifest=json.loads(z.read("manifest.json"));R.need(manifest["source_sha"]==PRODUCER_SHA and manifest["run_id"]==str(PRODUCER_RUN) and manifest["attempt"]=="1","producer manifest")
  actual={i.filename for i in infos if not i.is_dir()};R.need(actual==set(manifest["files"])|{"manifest.json"},"producer complete inventory")
  for name,item in manifest["files"].items():
   payload=z.read(name);R.need(len(payload)==item["bytes"] and hashlib.sha256(payload).hexdigest()==item["sha256"],"producer file: "+name)
   if name.startswith("perf-package/EXReader-Linux/") or name in ("perf-probe/seed_library","build-identity.json"):
    target=OUT/"producer"/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload);selected[name]=item
 built=load(OUT/"producer/build-identity.json")
 for name,tree in built["components"].items():R.need(R.command(["git","rev-parse","HEAD:"+name],text=True).strip()==tree,"same product tree: "+name)
 binary=OUT/"producer/perf-package/EXReader-Linux/bin/exreader-linux";seed=OUT/"producer/perf-probe/seed_library";binary.chmod(0o755);seed.chmod(0o755)
 R.need(R.sha(binary)==built["program_sha256"],"exact full product binary")
 R.save(OUT/"producer-identity.json",{"run_id":PRODUCER_RUN,"source_sha":PRODUCER_SHA,"artifact_id":meta["id"],"artifact_bytes":len(data),"artifact_sha256":digest,"program_sha256":built["program_sha256"],"components":built["components"],"selected_files":selected})
 return binary,seed
def wait(watch,predicate,since=0,timeout=30):
 index,event=watch.wait(predicate,timeout,since);R.need(index is not None,"native state predicate: "+str(event));return event
def settled(s):
 h=s["host"];keys=("busy","saving") if h.get("reader_visible")==1 else ("busy","saving","shelf_loading","shelf_restoring")
 return all(h.get(k,0)==0 for k in keys)
def search_snapshot(host):
 text=host.state_path.read_text();config=configparser.ConfigParser(interpolation=None);config.read_string(text)
 return dict(config["inbook_search"]) if config.has_section("inbook_search") else {},O.parse_state(text)["host"],hashlib.sha256(text.encode()).hexdigest()
def search_wait(host,row,predicate,timeout=30):
 deadline=time.monotonic()+timeout;last=None
 while time.monotonic()<deadline:
  host.require_alive("native search state");value,h,digest=search_snapshot(host)
  if digest!=last:row.setdefault("search_observations",[]).append({"at":stamp(),"state_sha256":digest,"search":value,"host":h});last=digest
  if predicate(value,h):return value,h
  time.sleep(.02)
 raise TimeoutError("native search section: "+repr(value))
def node(app,name,prefix=False):
 end=time.monotonic()+20
 while time.monotonic()<end:
  matches=[n for n in bus.walk(app) if (bus.name(n).startswith(name) if prefix else bus.name(n)==name) and bus.states(n).get("showing")]
  if matches:return matches[0]
  time.sleep(.02)
 raise TimeoutError("native node: "+name)
def click(n):
 box=bus.extents(n);R.need(box and box["width"]>0 and box["height"]>0,"native control bounds")
 O.command("xdotool","mousemove","--sync",box["x"]+box["width"]//2,box["y"]+box["height"]//2);O.command("xdotool","click","1")
 return box
def run():
 global bus
 import atspi_client as bus
 F.guard();OUT.mkdir(parents=True,exist_ok=False);report={**R.identity(),"planned_launches":4,"launches":[],"problems":[],"f08_accepted":False}
 try:
  binary,seed=producer();F.compile_probe();shutil.copyfile(ROOT/"build"/F.PROBE,OUT/"module.so");report["module_sha256"]=R.sha(OUT/"module.so");R.need(bus.init()[0],"native accessibility bus");bus.Atspi.set_timeout(800,0)
  with tempfile.TemporaryDirectory(prefix="f08-body-jump-") as temp:
   temp=Path(temp);seed_profile=temp/"seed";seed_profile.mkdir();subprocess.run([seed,seed_profile/"library.sqlite",OUT/"corpus.json"],check=True,timeout=600,capture_output=True)
   corpus=load(OUT/"corpus.json");R.need(corpus["books"]==2202,"fixed real library");book=corpus["originals"][0]["id"]
   for number,kind in enumerate(("body","jump","body","jump")):
    folder=OUT/("launch-%02d"%number);folder.mkdir();profile=temp/("profile-%02d"%number);shutil.copytree(seed_profile,profile)
    (profile/"reader.ini").write_text("[reader]\nbook=%d\nfont=24\nzoom=100\n[shelf]\nquery=\ntop_key=\nselected_key=\ntop_offset=0\n"%book)
    runtime=temp/("runtime-%02d"%number);runtime.mkdir();env=dict(os.environ,HOME=str(runtime),XDG_CONFIG_HOME=str(runtime/"config"),XDG_CACHE_HOME=str(runtime/"cache"),XDG_RUNTIME_DIR=str(runtime/"xdg"),GDK_BACKEND="x11",LANG="C.UTF-8",LC_ALL="C.UTF-8",GTK_MODULES=str(ROOT/"build"/F.PROBE),LD_PRELOAD=str(ROOT/"build"/F.PROBE),EXR_F08_NATIVE_OUTPUT=str(folder/"native-cost"),EXR_F08_CAUSAL_OUTPUT=str(folder),NO_AT_BRIDGE="0")
    R.need(len(str(Path(env["XDG_RUNTIME_DIR"])/"at-spi/bus_999999999999"))<100,"short native accessibility socket path")
    Path(env["EXR_F08_NATIVE_OUTPUT"]).mkdir()
    for name in ("XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_RUNTIME_DIR"):Path(env[name]).mkdir(mode=0o700)
    watch=O.Watch(runtime);host=O.Host(binary,binary.parent.parent/"Reader.otf",profile,runtime,env);row={"launch":number,"kind":kind,"actions":[],"complete":False};report["launches"].append(row)
    try:
     host.launch();row["pid"]=host.pid;wait(watch,lambda s:s["host"].get("book")==book and s["host"].get("reader_visible")==1 and settled(s),timeout=600)
     host.find_window();host.activate();host.resize(1040,620);time.sleep(.3);apps=[a for a in bus.applications() if bus._safe(lambda:a.get_process_id())==host.pid];R.need(len(apps)==1,"native PID application");app=apps[0]
     if kind=="body":
      image=node(app,"Rendered reading page; selectable text and notes are in More")
      for slot,button in enumerate(("5","4","5","4","5","4")):
       before=bus.extents(image);h=watch.latest()["state"]["host"];O.command("xdotool","mousemove","--window",host.window,int(h["page_x"])+int(h["page_width"])//2,int(h["page_y"])+int(h["page_height"])//2)
       begin=stamp();O.command("xdotool","click",button);time.sleep(.3);host.require_alive("reader body native scroll");after=bus.extents(image)
       row["actions"].append({"slot":slot,"kind":"body_scroll","button":button,"start":begin,"observed":stamp(),"before":before,"after":after})
     else:
      for slot,paragraph in enumerate((200,1000,1900)):
       host.activate();host.press("ctrl+shift+f");search_wait(host,row,lambda v,h:v.get("visible")=="1" and not h.get("busy") and not h.get("saving"))
       dialog=node(app,"Search within book");window=O.command("xdotool","search","--onlyvisible","--name","^Search within book$").splitlines()[-1];O.command("xdotool","windowactivate","--sync",window)
       query="paragraph %04d"%paragraph;entry=node(app,"In-book query");click(entry);host.press("ctrl+a");host.paste(query);previous_actions=int(search_snapshot(host)[0]["actions"]);host.press("alt+s")
       search_wait(host,row,lambda v,h:int(v.get("actions","0"))>previous_actions and v.get("count")=="1" and v.get("running")=="0" and v.get("complete")=="1" and not h.get("busy") and not h.get("saving"))
       selected=node(app,"Search result 1:",True);R.need(selected.get_component_iface().grab_focus(),"native search row focus");time.sleep(.05)
       baseline=watch.latest()["state"]["host"];begin=stamp();box=click(selected)
       search,after=search_wait(host,row,lambda v,h:h.get("frame_generation",0)>baseline.get("frame_generation",0) and h.get("painted_generation")==h.get("frame_generation") and h.get("selected")==len(query) and v.get("visible")=="0" and not h.get("busy") and not h.get("saving"))
       R.need(after["start"]>baseline["start"] and after["book"]==book,"actual FOUND relocation")
       row["actions"].append({"slot":slot,"kind":"locate_jump","query":query,"start":begin,"observed":stamp(),"before":baseline,"after":after,"native_row_bounds":box});time.sleep(.2)
     row["complete"]=True
    finally:
     row["rss_peak_kb"]=host.hwm_kb()
     if host.alive() and search_snapshot(host)[0].get("visible")=="1":
      host.press("Escape");search_wait(host,row,lambda v,h:v.get("visible")=="0",5)
     row["process_exit"]=host.close();host.close_log();watch.close();row["watcher_failure"]=watch.failure
     O.write_events(folder/"watcher-events.json",watch.events) if hasattr(O,"write_events") else R.save(folder/"watcher-events.json",list(watch.events))
     R.save(OUT/"driver.json",report)
  receipt=replay(OUT,report);R.save(OUT/"summary.json",receipt)
 except BaseException as error:
  report["problems"].append(repr(error));report["traceback"]=traceback.format_exc();raise
 finally:
  R.save(OUT/"driver.json",report);R.save(OUT/"manifest.json",{**R.identity(),"files":{p.relative_to(OUT).as_posix():{"bytes":p.stat().st_size,"sha256":R.sha(p)} for p in sorted(OUT.rglob("*")) if p.is_file() and "producer" not in p.relative_to(OUT).parts and p.name!="manifest.json"},"f08_accepted":False})
def replay(raw,driver):
 values={"body_input_to_native_completion_upper_bound":[],"locate_jump_worker_to_native_completion":[]};rows=[];ui_values={}
 R.need(len(driver["launches"])==4 and not driver["problems"],"complete new launch cohort")
 for row in driver["launches"]:
  R.need(row["complete"] and row["process_exit"]==0 and row["watcher_failure"] is None and len(row["actions"])==(6 if row["kind"]=="body" else 3),"all extra native actions")
  path=raw/("launch-%02d"%row["launch"])/"native-cost"/(str(row["pid"])+".json");doc=load(path);R.need(doc["pid"]==row["pid"] and all(doc[k]==R.identity()[v] for k,v in [("source","source_sha"),("run","run_id"),("attempt","attempt")]),"extra raw identity")
  census=F.inspect(doc)
  for name,items in census["values"].items():
   if name.startswith("ui_"):ui_values.setdefault(name,[]).extend(items)
  R.need(not census["missing_required_generations"] and not census["native_errors"],"complete extra generation/native census")
  actions=[]
  for action in row["actions"]:
   if action["kind"]=="locate_jump":
    jobs=[j for j in doc["jobs"] if j["action"]==36 and j["frame_generation"]==action["after"]["frame_generation"] and j["complete"]]
    R.need(len(jobs)==1,"exact FOUND generation/native join");job=jobs[0];cost=job["complete"]-job["start"];values["locate_jump_worker_to_native_completion"].append(cost);actions.append({"slot":action["slot"],"job_id":job["id"],"frame_generation":job["frame_generation"],"cost_us":cost,"input_to_native_us":job["complete"]-doc["inputs"][job["input"]-1]["at"]})
   else:
    native=[e for e in doc["inputs"] if e["type"]==2 and action["start"]<=e["at"]<=action["observed"]];R.need(native,"native reader-body wheel event")
    bound=[];used=[]
    for e in native:
     frames=[f for f in doc["frames"] if f["input"]==e["id"] and f["kind"]&4 and f["body"]["available"] and f["native_error"]==0];R.need(frames,"actual cached body composition/native completion")
     for f in frames:bound.append(f["sync_end"]-e["at"]);used.append({"frame":f["id"],"scroll":f["body"]["scroll"],"cost_us":f["sync_end"]-e["at"]})
    prior=[f for f in doc["frames"] if f["kind"]&4 and f.get("body",{}).get("available") and f["sync_end"]<native[0]["at"]]
    R.need(prior and any(abs(item["scroll"]-prior[-1]["body"]["scroll"])>.01 for item in used),"actual native body scroll changed")
    values["body_input_to_native_completion_upper_bound"].extend(bound);actions.append({"slot":action["slot"],"native_inputs":[e["id"] for e in native],"frames":used})
  rows.append({"launch":row["launch"],"kind":row["kind"],"jobs":census["jobs"],"native_frames":census["native_frames"],"actions":actions,"raw_sha256":R.sha(path)})
 metrics={k:F.stats(v) for k,v in {**values,**ui_values}.items()};return {**R.identity(),"launches":rows,"metrics":metrics,"producer":load(raw/"producer-identity.json"),"complete":True,"native_fence_wait_included":True,"body_metric_is_input_to_completion_upper_bound":True,"budgets":{"p95_ms":16.67,"p99_ms":33.34},"worker_to_native_is_operation_latency":True,"candidate_ui_frame_passed":all(metrics[k]["count"] and metrics[k]["p95_ms"]<=16.67 and metrics[k]["p99_ms"]<=33.34 for k in ("ui_all_frames","ui_body_frames","ui_locate_jump_frames")),"f08_accepted":False}
def audit():
 F.guard();out=ROOT/"build/f08-linux-body-jump-audit";out.mkdir(parents=True,exist_ok=False);aid=int(os.environ["F08_ARTIFACT_ID"]);meta=json.loads(api("actions/artifacts/"+str(aid)));data=api("actions/artifacts/"+str(aid)+"/zip");digest=hashlib.sha256(data).hexdigest()
 R.need(not meta["expired"] and meta["name"]=="f08-linux-body-jump-"+R.identity()["run_id"]+"-"+R.identity()["attempt"] and meta["digest"]=="sha256:"+digest and len(data)==meta["size_in_bytes"] and os.environ["F08_ARTIFACT_DIGEST"].removeprefix("sha256:")==digest and meta["workflow_run"]["head_sha"]==R.identity()["source_sha"] and str(meta["workflow_run"]["id"])==R.identity()["run_id"],"extra artifact identity")
 raw=out/"raw";raw.mkdir()
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  infos=z.infolist();R.need(len(infos)<5000 and sum(i.file_size for i in infos)<200*1024**2,"extra ZIP bounds");seen=set()
  for i in infos:
   p=PurePosixPath(i.filename);R.need(not p.is_absolute() and ".." not in p.parts and "\\" not in i.filename and ":" not in i.filename and str(p).casefold() not in seen,"extra ZIP path");seen.add(str(p).casefold());R.need(not i.flag_bits&1 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFDIR,stat.S_IFREG),"extra ZIP kind")
   if i.is_dir():continue
   target=raw/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(i))
 manifest=load(raw/"manifest.json");R.need(all(manifest[k]==v for k,v in R.identity().items()),"extra manifest identity")
 R.need({p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file()}==set(manifest["files"])|{"manifest.json"},"extra complete inventory")
 for name,item in manifest["files"].items():R.need(R.sha(raw/name)==item["sha256"] and (raw/name).stat().st_size==item["bytes"],"extra file: "+name)
 producer();R.need(load(OUT/"producer-identity.json")==load(raw/"producer-identity.json"),"independent producer authentication");R.need(R.sha(raw/"module.so")==load(raw/"driver.json")["module_sha256"],"measured module identity")
 result=replay(raw,load(raw/"driver.json"));R.need(result==load(raw/"summary.json"),"independent extra replay");R.save(out/"audit.json",{"artifact_id":aid,"artifact_bytes":len(data),"artifact_sha256":digest,"authenticated":True,"result":result})
if __name__=="__main__":
 if sys.argv[1:]==["audit"]:audit()
 else:
  sys.path.insert(0,str(ROOT/"tests/reader_f08_compact_resume_20261031"));import adapter;adapter.install();run()
