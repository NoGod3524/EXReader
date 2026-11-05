"""Pure protocol/native consumers and generated-source injection; no import-time actions."""
import json,math,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PROFILE=json.loads((HERE/"profile.json").read_text())
CLOCK=PROFILE["clock"]
IDENTITY_KEYS=("nonce","pid","window_number","case_id","source_sha","executable_url","executable_sha256")
def request_name(identity,iteration,phase):
 return "org.exreader.f08.a.{nonce}.{pid}.{window_number}.{case_id}.{iteration}.{phase}".format(**identity,iteration=iteration,phase=phase)
def validate_protocol(test_record,app_record,expected_identity):
 if not all(isinstance(x,dict) for x in (test_record,app_record,expected_identity)):return {"complete":False,"problems":["malformed"],"details":[],"iterations":0,"f08_accepted":False}
 problems=[];details=[]
 def check(value,code,at=""):
  if not value:
   if code not in problems:problems.append(code)
   details.append({"code":code,"at":at})
 def ns(v):return type(v) is int and v>0
 try:
  case=str(expected_identity["case_id"])
  check(case in PROFILE["action_lists"],"expected.identity")
  check(bool(re.fullmatch("[0-9a-f]{32}",expected_identity["nonce"])) and ns(expected_identity["pid"]) and ns(expected_identity["window_number"]),"expected.identity")
  check(bool(re.fullmatch("[0-9a-f]{40}",expected_identity["source_sha"])) and bool(re.fullmatch("[0-9a-f]{64}",expected_identity["executable_sha256"])) and expected_identity["executable_url"].startswith("/"),"expected.identity")
  for label,record in (("test",test_record),("app",app_record)):
   check(type(record.get("schema")) is int and record["schema"]==1,label+".schema")
   check(record.get("clock")==CLOCK,"clock",label)
   check(all(record.get("identity",{}).get(k)==expected_identity.get(k) for k in IDENTITY_KEYS),label+".identity")
   check(record.get("errors")==[],"protocol.errors",label)
  check(app_record.get("complete_log") is True,"app.eof")
  iterations=test_record["iterations"];events=app_record["events"]
  check(len(iterations)==6 and all(type(x.get("index")) is int for x in iterations) and [x.get("index") for x in iterations]==list(range(6)),"test.iterations")
  check(len(events)==12 and all(type(x.get("sequence")) is int for x in events) and [x.get("sequence") for x in events]==list(range(1,13)),"app.events")
  previous_stop=0
  for i,item in enumerate(iterations):
   at=str(i)
   check(item.get("warmup") is (i==0) and ((item.get("native_measurement_index") is None) if i==0 else (type(item.get("native_measurement_index")) is int and item["native_measurement_index"]==i-1)),"iteration.identity",at)
   times=[item.get(k) for k in ("start_before_ns","start_after_ns","stop_before_ns","stop_after_ns")]
   check(all(ns(x) for x in times) and times==sorted(times) and times[0]>=previous_stop,"iteration.clock",at)
   previous_stop=times[-1] if ns(times[-1]) else 0
   check(item.get("errors")==[],"protocol.errors",at)
   actions=item["actions"];screens=item["screenshots"]
   check([x.get("id") for x in actions]==PROFILE["action_lists"][case],"actions",at)
   check([x.get("phase") for x in screens]==PROFILE["screenshot_phases"][case],"screenshots",at)
   last=item["begin"]["ack_received_ns"]
   for action in actions:
    a,b=action.get("started_ns"),action.get("finished_ns")
    check(ns(a) and ns(b) and last<=a<=b<=item["end"]["request_post_before_ns"],"actions.clock",at)
    check(bool(action.get("inputs")) and all(ns(x.get("started_ns")) and ns(x.get("finished_ns")) and a<=x["started_ns"]<=x["finished_ns"]<=b for x in action["inputs"]),"actions.inputs",at)
    last=b
   for shot_index,shot in enumerate(screens):
    a,b=shot.get("started_ns"),shot.get("finished_ns")
    check(ns(a) and ns(b) and item["begin"]["ack_received_ns"]<=a<=b<=item["end"]["request_post_before_ns"],"screenshots.clock",at)
    previous=item["begin"]["ack_received_ns"] if shot_index==0 else actions[shot_index-1]["finished_ns"]
    following=actions[shot_index]["started_ns"] if shot_index<len(actions) else item["end"]["request_post_before_ns"]
    check(previous<=a<=b<=following,"screenshots.order",at)
    check(type(shot.get("actual_pid")) is int and shot["actual_pid"]==expected_identity["pid"] and type(shot.get("actual_window_number")) is int and shot["actual_window_number"]==expected_identity["window_number"] and shot.get("window_visible") is True,"screenshots.window",at)
    check(bool(re.fullmatch("[0-9a-f]{64}",shot.get("png_sha256",""))) and bool(shot.get("attachment_name")) and ns(shot.get("pixel_width")) and ns(shot.get("pixel_height")),"screenshots.payload",at)
   for offset,(phase,key,active) in enumerate((("b","begin",True),("e","end",False))):
    control=item[key];event=events[2*i+offset];name=request_name(expected_identity,i,phase)
    check(control.get("request_name")==event.get("request_name")==name and control.get("ack_name")==event.get("ack_name")==name+".ack" and type(control.get("ack_receipt_count")) is int and control["ack_receipt_count"]==1,"request.identity",at+phase)
    check(all(type(event.get(k)) is int for k in ("case_id","iteration","actual_pid","actual_window_number")) and event.get("phase")==key and event.get("case_id")==expected_identity["case_id"] and event.get("iteration")==i and event.get("actual_pid")==expected_identity["pid"] and event.get("actual_window_number")==expected_identity["window_number"] and event.get("actual_source_sha")==expected_identity["source_sha"],"app.event_identity",at+phase)
    check(event.get("main_thread") is True and event.get("window_visible") is True,"app.main_thread",at+phase)
    check(type(event.get("starts")) is int and type(event.get("ends")) is int and event.get("signpost_type")==("animationBegin" if active else "end") and event.get("starts")==i+1 and event.get("ends")==i+(not active) and event.get("active") is active,"app.counter",at+phase)
    values=[control.get("ack_registered_ns"),control.get("request_post_before_ns"),control.get("request_post_after_ns"),control.get("ack_received_ns")]
    check(all(ns(x) for x in values) and values==sorted(values),"request.clock",at+phase)
    values=[event.get(k) for k in ("request_received_ns","signpost_before_ns","signpost_after_ns","ack_post_before_ns","ack_post_after_ns")]
    check(all(ns(x) for x in values) and values==sorted(values),"app.clock",at+phase)
    check(item["start_after_ns"]<=control["request_post_before_ns"]<=event["request_received_ns"]<=event["signpost_before_ns"]<=event["signpost_after_ns"]<=event["ack_post_before_ns"]<=control["ack_received_ns"]<=item["stop_before_ns"],"bridge.order",at+phase)
   check(item["begin"]["ack_received_ns"]<=item["end"]["request_post_before_ns"],"bridge.order",at)
  flush=test_record["flush"];name=request_name(expected_identity,"all","flush")
  check(flush.get("request_name")==app_record.get("flush_request_name")==name and flush.get("ack_name")==name+".ack" and type(flush.get("ack_receipt_count")) is int and flush["ack_receipt_count"]==1,"flush")
  values=[flush.get(k) for k in ("ack_registered_ns","request_post_before_ns","request_post_after_ns","ack_received_ns")]
  check(all(ns(x) for x in values) and values==sorted(values) and ns(app_record.get("flush_received_ns")) and ns(app_record.get("flush_prepare_ns")),"flush.clock")
  check(previous_stop<=flush["request_post_before_ns"]<=app_record["flush_received_ns"]<=app_record["flush_prepare_ns"]<=flush["ack_received_ns"],"flush.clock")
 except (KeyError,TypeError,IndexError,ValueError,AttributeError) as error:
  check(False,"malformed",repr(error))
 return {"complete":not problems,"problems":problems,"details":details,"iterations":len(test_record["iterations"]) if isinstance(test_record.get("iterations"),list) else 0,"f08_accepted":False}
def native_coverage(performance_cases,configurations):
 def value(x):return x.get("_value") if isinstance(x,dict) else x
 def numbers(metric):
  values=[value(v) for v in metric.get("measurements",{}).get("_values",[])]
  try:parsed=[float(x) if not isinstance(x,bool) else float("nan") for x in values]
  except (TypeError,ValueError,OverflowError):parsed=[]
  return values,parsed
 rows=[]
 for key,name in PROFILE["cases"].items():
  expected=name+"()";cases=[c for c in performance_cases if c.get("identifier")==expected];case=cases[0] if len(cases)==1 else {}
  metrics=case.get("performance_metrics",[]);found={}
  for kind,suffix,unit,integral,positive in (("frames",".animation.frame.count","frames",True,True),("hitches",".animation.hitch.number","hitches",True,False),("hitch_duration",".animation.hitches.total.duration","ms",False,False),("ratio",".animation.hitch.time.ratio","ms per s",False,False)):
   matches=[m for m in metrics if value(m.get("identifier"))=="com.apple.dt.XCTMetric_OSSignpost-"+PROFILE["signpost"]["name"]+suffix]
   metric=matches[0] if len(matches)==1 else {};raw,values=numbers(metric)
   valid=len(matches)==1 and value(metric.get("unitOfMeasurement"))==unit and len(values)==5 and all(math.isfinite(x) and (x>0 if positive else x>=0) and (not integral or x.is_integer()) for x in values)
   found[kind]={"identifier":value(metric.get("identifier")),"unit":value(metric.get("unitOfMeasurement")),"measurements":metric.get("measurements"),"raw_values":raw,"valid":valid}
  configured=any(c.get("case")==expected and "XCTOSSignpostMetric" in c.get("configuration",{}).get("configured_native_metric_types",[]) and c["configuration"].get("signpost")==PROFILE["signpost"] for c in configurations)
  positive=len(cases)==1 and case.get("status")=="Success" and configured and all(v["valid"] for v in found.values())
  zero=positive and all(float(x)==0 for k in ("hitches","hitch_duration") for x in found[k]["raw_values"])
  rows.append({"case":expected,"status":case.get("status","missing"),"configured":configured,"metrics":found,"positive_native_frame_capability":positive,"no_observed_hitches":zero,"expanded_ratio_is_frozen_budget":False,"f08_accepted":False})
 return rows
def injected_reader_app(text):
 old="init() { HostF08Review.beginLaunch() }"
 if text.count(old)!=1:raise ValueError("original App init boundary")
 return text.replace(old,"init() { HostF08Review.beginLaunch(); F08ReaderAnimationBridge.installIfEnabled() }")
def swift_function(text,name):
 start=text.index("    "+name);brace=text.index("{",start);depth=1;end=brace+1
 while depth and end<len(text):
  depth+=(text[end]=="{")-(text[end]=="}");end+=1
 if depth:raise ValueError("Swift function boundary")
 return text[start:end]
def driver_sources(source_sha,expected_executable_url):
 original=(ROOT/"tests/apple_host/shelf/ui/ShelfUITests.swift").read_text()
 metrics=(ROOT/"tests/reader_f08_apple_20261031/Metrics.swift").read_text()
 inside,marker,standalone=metrics.partition("// F08_STANDALONE_CLASSES")
 if not marker:raise ValueError("original metrics boundary")
 at=original.rfind("}")
 baseline=original[:at]+inside+original[at:]+standalone
 # Only setup preparation is generated; original test11/12/nativeMetrics bodies stay exact.
 prefix,mark,reader=baseline.partition("final class F08ReaderUITests")
 old="        app.launch()\n    }"
 if not mark or reader.count(old)!=1:raise ValueError("original reader setup boundary")
 baseline=prefix+mark+reader.replace(old,"        app.launch()\n        XCTAssertTrue(F08PrepareReaderWindow(self, app))\n    }",1)
 names=["private func node(","private func text(","private func wait(","private func tap(","private func readerObservation(","private func reader()","private func openShelf(","private func locate("]
 common="\n".join(swift_function(metrics,name) for name in names)
 new=(HERE/"ReaderAnimationTests.swift").read_text().replace("/*F08_COMMON_HELPERS*/",common)
 for token,value in [("__F08_DIAG_SOURCE__",source_sha),("__F08_APP_EXE__",expected_executable_url)]:
  new=new.replace('"'+token+'"',json.dumps(value,ensure_ascii=False))
 return {"ShelfUITests.swift":baseline,"ReaderAnimationTests.swift":new}

def verify_window_images(attachments,test_record):
 """Decode original PNGs and independently compare an exact Window crop to the reader-element ROI."""
 import hashlib,io
 problems=[];details=[];rows=[]
 def check(value,code,at=""):
  if not value:
   if code not in problems:problems.append(code)
   details.append({"code":code,"at":at})
 def number(v):return type(v) in (int,float) and math.isfinite(v)
 def integer(v):return number(v) and v.is_integer() if type(v) is float else type(v) is int
 def rect(value):
  if not isinstance(value,dict) or set(value)!={"x","y","width","height"}:raise ValueError("rectangle fields")
  if not all(number(x) for x in value.values()) or value["width"]<=0 or value["height"]<=0:raise ValueError("rectangle values")
  return value
 def read(shot,at):
  data=attachments.get(shot["attachment_name"])
  if type(data) is not bytes:raise ValueError("missing PNG bytes "+at)
  check(hashlib.sha256(data).hexdigest()==shot["png_sha256"],"images.sha256",at)
  image=Image.open(io.BytesIO(data));check(image.format=="PNG","images.format",at);image.load();image=image.convert("RGBA")
  check(image.width==shot["pixel_width"] and image.height==shot["pixel_height"],"images.dimensions",at)
  return image
 try:
  from PIL import Image
  identity=test_record["identity"]
  check(len(test_record["iterations"])==6,"images.iterations")
  for item in test_record["iterations"]:
   at=str(item["index"]);shots=item["screenshots"];whole=item["window_screenshot"];located=shots[-1]
   check(all(type(whole.get(k)) is int and whole[k]>0 for k in ("started_ns","finished_ns","pixel_width","pixel_height")),"images.window_clock_type",at)
   check(located["finished_ns"]<=whole["started_ns"]<=whole["finished_ns"]<=item["end"]["request_post_before_ns"],"images.window_clock",at)
   check(type(whole.get("actual_pid")) is int and whole["actual_pid"]==identity["pid"] and type(whole.get("actual_window_number")) is int and whole["actual_window_number"]==identity["window_number"] and whole.get("window_visible") is True,"images.window_identity",at)
   window=rect(whole["window_frame_points"]);axwindow=rect(whole["ax_window_frame_points"]);reader=rect(whole["reader_frame_points"])
   check(window==axwindow,"images.window_geometry",at)
   check(reader==located["reader_frame_points"] and window==located["window_frame_points"] and axwindow==located["ax_window_frame_points"],"images.stable_geometry",at)
   image=read(whole,at+"/window");sx=whole["scale_x"];sy=whole["scale_y"]
   check(number(sx) and number(sy) and sx>0 and sx==sy and sx==image.width/window["width"] and sy==image.height/window["height"],"images.scale",at)
   x=(reader["x"]-window["x"])*sx;y=(reader["y"]-window["y"])*sy;w=reader["width"]*sx;h=reader["height"]*sy;bottom=2*sy
   check(all(integer(v) for v in (x,y,w,h,bottom)) and x>=0 and y>=0 and w>0 and h>bottom and x+w<=image.width and y+h<=image.height,"images.crop_geometry",at)
   if not all(integer(v) for v in (x,y,w,h,bottom)):raise ValueError("non-integral exact crop")
   x,y,w,h,bottom=map(int,(x,y,w,h,bottom));window_roi=image.crop((x,y,x+w,y+h-bottom))
   bodies={};hashes={};visible_hashes={};backdrop=(255,255,255,255)
   for shot in shots:
    phase=shot["phase"];element=read(shot,at+"/"+phase);r=rect(shot["reader_frame_points"])
    check(r==reader and shot.get("window_frame_points")==window and shot.get("ax_window_frame_points")==axwindow,"images.stable_geometry",at+"/"+phase)
    check(type(shot.get("actual_pid")) is int and shot["actual_pid"]==identity["pid"] and type(shot.get("actual_window_number")) is int and shot["actual_window_number"]==identity["window_number"] and shot.get("window_visible") is True,"images.window_identity",at+"/"+phase)
    check(shot.get("crop_bottom_points")==2 and element.width==r["width"]*sx and element.height==r["height"]*sy and element.height>bottom,"images.element_geometry",at+"/"+phase)
    body=element.crop((0,0,element.width,element.height-bottom));bodies[phase]=body
    visible=Image.alpha_composite(Image.new("RGBA",body.size,backdrop),body)
    check(any(lo!=hi for lo,hi in visible.getextrema()[:3]),"images.blank_body",at+"/"+phase)
    hashes[phase]=hashlib.sha256(body.tobytes()).hexdigest()
    visible_hashes[phase]=hashlib.sha256(visible.tobytes()).hexdigest()
   located_body=bodies["located"]
   check(window_roi.size==located_body.size and window_roi.tobytes()==located_body.tobytes(),"images.window_roi_mismatch",at)
   before="next" if str(identity["case_id"])=="12" else "before"
   check(visible_hashes["larger"]!=visible_hashes[before] and visible_hashes["restored"]!=visible_hashes["larger"],"images.font_body_unchanged",at)
   if str(identity["case_id"])=="12":
    check(visible_hashes["next"]!=visible_hashes["before"] and visible_hashes["located"]!=visible_hashes["restored"],"images.page_body_unchanged",at)
   rows.append({"index":item["index"],"body_sha256":hashes,"raw_body_sha256":hashes,"visible_body_sha256":visible_hashes,"visible_comparison":{"method":"Pillow.Image.alpha_composite","backdrop_rgba":list(backdrop),"scope":"Comparison normalization only; opaque pixels unchanged; original PNG and raw ROI equality retained"},"window_reader_visible_body_sha256":hashlib.sha256(Image.alpha_composite(Image.new("RGBA",window_roi.size,backdrop),window_roi).tobytes()).hexdigest(),"window_reader_body_sha256":hashlib.sha256(window_roi.tobytes()).hexdigest(),"pixel_equality":window_roi.size==located_body.size and window_roi.tobytes()==located_body.tobytes(),"crop_bottom_points":2})
 except (ImportError,KeyError,TypeError,ValueError,AttributeError,OSError,IndexError,OverflowError) as error:
  check(False,"images.malformed",repr(error))
 return {"complete":not problems,"problems":problems,"details":details,"iterations":rows,"f08_accepted":False}

def assess(folder,performance,program,run_identity):
 """Recompute the capture from exact per-case native metrics and original attachment bytes."""
 import hashlib
 folder=Path(folder);base=folder/"attachments";problems=[];details=[];rows=[];configs=[];protocols=[];baseline=[]
 def check(value,code,at=""):
  if not value:
   if code not in problems:problems.append(code)
   details.append({"code":code,"at":at})
 def invalid_constant(value):raise ValueError("nonfinite JSON: "+value)
 def unique_object(pairs):
  value={}
  for k,v in pairs:
   if k in value:raise ValueError("duplicate JSON key: "+k)
   value[k]=v
  return value
 def load(raw):return json.loads(raw,parse_constant=invalid_constant,object_pairs_hook=unique_object)
 def contents(attachment):
  name=attachment["exportedFileName"];path=base/name
  if not isinstance(name,str) or not name or Path(name).name!=name or path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):raise ValueError("attachment export path")
  return path.read_bytes()
 def named(attachments,name):return [a for a in attachments if a.get("suggestedHumanReadableName","").startswith(name+"_")]
 def one(attachments,name):
  found=named(attachments,name)
  if len(found)!=1:raise ValueError("unique "+name+" attachment required")
  return found[0],contents(found[0])
 try:
  check(program.get("program_source_sha")==run_identity["source_sha"] and program.get("sdk_input_source_sha")==PROFILE["producer_source_sha"] and program.get("resource_input_source_sha")==PROFILE["producer_source_sha"],"program.source_identity")
  check(bool(re.fullmatch("[0-9a-f]{64}",program.get("program_sha256",""))) and str(program.get("built_executable_url","")).startswith("/"),"program.executable_identity")
  if not isinstance(performance,list):raise ValueError("native case list malformed")
  manifest=load((base/"manifest.json").read_bytes())
  expected_cases=[x+"()" for x in PROFILE["baseline_cases"]]+[x+"()" for x in PROFILE["cases"].values()]
  check(len(manifest)==4 and sorted(x.get("testIdentifier","") for x in manifest)==sorted(expected_cases),"capture.case_set")
  check(len(performance)==4 and sorted(x.get("identifier","") for x in performance)==sorted(expected_cases),"native.case_set")
  nonces=set()
  for name in PROFILE["baseline_cases"]:
   identifier=name+"()";items=[x for x in manifest if x.get("testIdentifier")==identifier];native=[x for x in performance if x.get("identifier")==identifier]
   if len(items)!=1 or len(native)!=1:raise ValueError("baseline case missing/duplicate "+identifier)
   _,raw=one(items[0].get("attachments",[]),"f08-reader-observations");value=load(raw);samples=value.get("samples",[])
   _,preparation_raw=one(items[0].get("attachments",[]),"f08-reader-window-preparation");preparation=load(preparation_raw)
   bindings=[x.get("actual_identity",{}) for x in preparation.get("events",[]) if x.get("phase")=="owned-runtime-bound"]
   binding=bindings[0] if len(bindings)==1 else {}
   bound=len(bindings)==1 and type(binding.get("pid")) is int and binding["pid"]>0 and type(binding.get("window_number")) is int and binding["window_number"]>0 and binding.get("source_sha")==run_identity["source_sha"] and binding.get("executable_url")==program["built_executable_url"] and binding.get("executable_sha256")==program["program_sha256"]
   check(bound,"baseline.runtime_identity",identifier)
   good=native[0].get("status")=="Success" and len(samples)==6
   check(good,"baseline.status_or_samples",identifier)
   baseline.append({"case":identifier,"status":native[0].get("status"),"raw_sample_count":len(samples),"samples":samples,"original_body_preserved":True,"runtime_identity":binding,"f08_accepted":False})
  for case_id,name in PROFILE["cases"].items():
   identifier=name+"()";items=[x for x in manifest if x.get("testIdentifier")==identifier]
   if len(items)!=1:raise ValueError("supplementary case missing/duplicate "+identifier)
   attachments=items[0].get("attachments",[])
   _,raw_test=one(attachments,"f08-reader-animation-protocol");test=load(raw_test)
   _,raw_app=one(attachments,"f08-reader-animation-app-log");app=load(raw_app)
   _,raw_config=one(attachments,"f08-reader-animation-metric-configuration");configuration=load(raw_config)
   if not isinstance(configuration,dict):raise ValueError("native configuration malformed")
   configs.append({"case":identifier,"configuration":configuration})
   expected=dict(test.get("identity",{}));expected.update(case_id=int(case_id),source_sha=run_identity["source_sha"],executable_sha256=program["program_sha256"],executable_url=program["built_executable_url"])
   check(test.get("kind")=="reader-animation-protocol" and app.get("kind")=="reader-animation-app-log","capture.kind",identifier)
   check(expected.get("nonce") not in nonces,"capture.unique_nonce",identifier);nonces.add(expected.get("nonce"))
   ready=test.get("bridge_ready",{});registered=ready.get("registered_names",[])
   names=[request_name(expected,i,p) for i in range(6) for p in ("b","e")]+[request_name(expected,"all","flush")]
   check(ready.get("kind")=="reader-animation-bridge-ready" and ready.get("identity")==expected and ready.get("errors")==[] and sorted(registered)==sorted(names),"capture.ready_binding",identifier)
   check(type(ready.get("registered_ns")) is int and ready["registered_ns"]>0 and test["iterations"][0]["start_before_ns"]>=ready["registered_ns"],"capture.registration_order",identifier)
   root=Path(test.get("temporary_root",""));path=Path(test.get("app_log_path",""))
   check(root.is_absolute() and path==root/("F08ReaderAnimation-"+expected["nonce"])/"app-bridge.json" and app.get("temporary_root")==ready.get("temporary_root")==str(root) and app.get("app_log_path")==ready.get("app_log_path")==str(path),"capture.sidecar_path",identifier)
   check(test.get("app_log_sha256")==hashlib.sha256(raw_app).hexdigest(),"capture.sidecar_sha256",identifier)
   check(app.get("callbacks_closed") is True and type(app.get("callbacks_closed_ns")) is int and app["flush_received_ns"]<=app["callbacks_closed_ns"]<=app["flush_prepare_ns"],"capture.closed_app_log",identifier)
   protocol=validate_protocol(test,app,expected)
   for problem in protocol["problems"]:check(False,"protocol."+problem,identifier)
   images={}
   for iteration in test.get("iterations",[]):
    for shot in iteration.get("screenshots",[])+([iteration["window_screenshot"]] if "window_screenshot" in iteration else []):
     name=shot["attachment_name"];_,data=one(attachments,name)
     if name in images:raise ValueError("duplicate PNG attachment identity")
     images[name]=data
   image_check=verify_window_images(images,test)
   for problem in image_check["problems"]:check(False,problem,identifier)
   check(len(test.get("samples",[]))==6,"capture.samples",identifier)
   row={"case":identifier,"identity":expected,"protocol":protocol,"images":image_check,"raw_sample_count":len(test.get("samples",[])),"app_log_sha256":hashlib.sha256(raw_app).hexdigest(),"f08_accepted":False}
   rows.append(row);protocols.append({"case":identifier,"test_record":test,"app_record":app})
 except (KeyError,TypeError,ValueError,AttributeError,OSError,IndexError) as error:
  check(False,"assessment.malformed",repr(error))
 coverage=native_coverage(performance if isinstance(performance,list) else [],configs)
 for row in coverage:
  check(row["positive_native_frame_capability"],"native.counter_or_configuration_missing",row["case"])
 check(len(rows)==2 and len(baseline)==2,"capture.complete_case_set")
 complete=not problems
 return {"complete":complete,"capture_complete":complete,"problems":problems,"details":details,"baseline":baseline,"cases":rows,"protocol_records":protocols,"native_coverage":coverage,
         "positive_native_frame_capability":len(coverage)==2 and all(x["positive_native_frame_capability"] for x in coverage),
         "zero_hitch_observed":len(coverage)==2 and all(x["no_observed_hitches"] for x in coverage),
         "native_ratio_is_frozen_budget":False,"diagnostic_only":True,"f08_accepted":False}
