"""Direct wp_presentation capability census; never a product benchmark."""
import hashlib,json,os,shlex,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/"build/f08-linux-presentation";RAW=OUT/"raw"
BASE="0c89ee0bee126c2316b2a6445bde7a5a47bb42f3"
FILES={"tests/reader_f08_linux_presentation_20261031/"+n for n in ("capability.c","run.py","audit.py")}|{".github/workflows/f08-linux-presentation-20261031.yml","docs/reader-total-progress/F08_LINUX_PRESENTATION_20261031.md"}
def need(ok,message):
 if not ok:raise ValueError(message)
def save(path,value):path.write_text(json.dumps(value,indent=2)+"\n")
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identity():return {"source_sha":os.environ["GITHUB_SHA"],"run_id":os.environ["GITHUB_RUN_ID"],"attempt":os.environ["GITHUB_RUN_ATTEMPT"]}
def guard():
 need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform.startswith("linux"),"Linux Actions only")
 need(subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()==identity()["source_sha"],"source identity")
 changed=set(subprocess.check_output(["git","diff","--name-only",BASE,"HEAD"],cwd=ROOT,text=True).splitlines())
 need(changed==FILES,"additive exact scope")
 for p in ("src","include","apps/reader","examples/linux"):
  need(subprocess.check_output(["git","rev-parse","HEAD:"+p],cwd=ROOT)==subprocess.check_output(["git","rev-parse",BASE+":"+p],cwd=ROOT),"unchanged production tree: "+p)
def evaluate(doc):
 need(doc.get("schema")==1 and doc.get("synthetic_only") is True,"synthetic schema")
 need(type(doc.get("clock_id")) is int and type(doc.get("errors")) is int,"clock/errors")
 rows=doc.get("rows");need(type(rows) is list and len(rows)==doc.get("requested") and 0<len(rows)<=120,"complete row inventory")
 statuses={"pending":0,"presented":0,"discarded":0};flags={};nonzero=0;callbacks=0;order_errors=0
 for i,r in enumerate(rows):
  need(type(r) is dict and r.get("index")==i,"row index")
  for k in ("feedback_object","request_ns","callback_ns","status","presentation_ns","refresh_ns","sequence","flags","sync_outputs"):
   need(type(r.get(k)) is int and 0<=r[k]<2**64,"row integer: "+k)
  need(r["feedback_object"]>0 and r["request_ns"]>0 and r["status"] in (0,1,2),"feedback request")
  statuses[("pending","presented","discarded")[r["status"]]]+=1
  if r["status"]:
   callbacks+=1
   if r["callback_ns"]<r["request_ns"]:order_errors+=1
  if r["status"]==1:
   flags[str(r["flags"])]=flags.get(str(r["flags"]),0)+1
   if r["presentation_ns"]>0:nonzero+=1
   if r["presentation_ns"]>r["callback_ns"]:order_errors+=1
   if r["presentation_ns"] and r["presentation_ns"]<r["request_ns"]:order_errors+=1
 need(order_errors==0,"clock ordering")
 return {"requested":len(rows),"statuses":statuses,"callbacks":callbacks,"nonzero_presentation_timestamps":nonzero,"feedback_flags":flags,
  "clock_id":doc["clock_id"],"errors":doc["errors"],
  "native_feedback_observed":callbacks>0,
  "all_requests_resolved":callbacks==len(rows),
  "all_presentations_have_nonzero_timestamps":statuses["presented"]>0 and nonzero==statuses["presented"],
  "hardware_flags_are_observations_not_F08_requirements":True,
  "product_sampled":False,"frame_budget_measured":False,"f08_accepted":False}
def controls():
 row=dict(index=0,feedback_object=2,request_ns=100,callback_ns=200,status=1,presentation_ns=180,refresh_ns=16666667,sequence=1,flags=0,sync_outputs=1)
 good=dict(schema=1,synthetic_only=True,clock_id=1,errors=0,requested=1,rows=[row])
 need(evaluate(good)["native_feedback_observed"],"positive native feedback")
 zero=json.loads(json.dumps(good));zero["rows"][0]["presentation_ns"]=0
 need(not evaluate(zero)["all_presentations_have_nonzero_timestamps"],"zero timestamp retained")
 pending=json.loads(json.dumps(good));pending["rows"][0].update(status=0,callback_ns=0,presentation_ns=0)
 need(not evaluate(pending)["all_requests_resolved"],"pending retained")
 discarded=json.loads(json.dumps(good));discarded["rows"][0].update(status=2,presentation_ns=0)
 need(evaluate(discarded)["statuses"]["discarded"]==1,"discarded retained")
 bad=[]
 for name,edit in [("missing",lambda d:d.update(requested=2)),("index",lambda d:d["rows"][0].update(index=1)),("bool",lambda d:d["rows"][0].update(flags=True)),("future",lambda d:d["rows"][0].update(presentation_ns=201)),("before_request",lambda d:d["rows"][0].update(presentation_ns=99)),("callback_order",lambda d:d["rows"][0].update(callback_ns=99)),("invalid_status",lambda d:d["rows"][0].update(status=3))]:
  d=json.loads(json.dumps(good));edit(d)
  try:evaluate(d)
  except ValueError:bad.append(name)
 need(len(bad)==7,"negative controls")
 return {"positive":4,"negative":7,"rejected":bad}
def command(args,name,check=False,env=None,timeout=60):
 with (RAW/(name+".log")).open("wb") as f:
  result=subprocess.run(list(map(str,args)),cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=timeout)
 if check:need(result.returncode==0,"command: "+name)
 return result.returncode
def inner():
 compositor=None
 with (RAW/"mutter.log").open("wb") as log:
  try:
   compositor=subprocess.Popen(["mutter","--wayland","--nested","--no-x11","--wayland-display=f08-presentation","--sm-disable"],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
   socket=Path(os.environ["XDG_RUNTIME_DIR"])/"f08-presentation"
   for _ in range(200):
    if socket.exists():break
    need(compositor.poll() is None,"compositor exited");time.sleep(.1)
   need(socket.exists(),"Wayland socket")
   env=dict(os.environ,GDK_BACKEND="wayland",WAYLAND_DISPLAY="f08-presentation")
   with (RAW/"feedback.json").open("wb") as out,(RAW/"probe-stderr.log").open("wb") as err:
    result=subprocess.run([OUT/"capability"],cwd=ROOT,stdout=out,stderr=err,env=env,timeout=15)
   save(RAW/"probe-exit.json",{"exit_code":result.returncode})
   need(result.returncode==0,"probe exit")
  finally:
   if compositor is not None and compositor.poll() is None:
    compositor.terminate()
    try:compositor.wait(timeout=10)
    except subprocess.TimeoutExpired:compositor.kill();compositor.wait(timeout=5)
def collect():
 guard();RAW.mkdir(parents=True,exist_ok=False);problems=[];codes={}
 save(RAW/"identity.json",identity());save(RAW/"controls.json",controls())
 save(RAW/"device-inventory.json",{"dri_exists":Path("/dev/dri").exists(),"dri_devices":sorted(p.name for p in Path("/dev/dri").glob("*")),"profile":"CI nested compositor on isolated Xvfb 1440x900x24","physical_display_proven":False})
 for args,name in [(["mutter","--version"],"mutter-version"),(["mutter","--help"],"mutter-help"),(["pkg-config","--modversion","gtk+-3.0","wayland-client"],"toolchain"),(["cc","--version"],"compiler"),(["uname","-a"],"kernel")]:codes[name]=command(args,name)
 xvfb=None
 try:
  xml=Path(subprocess.check_output(["pkg-config","--variable=pkgdatadir","wayland-protocols"],text=True).strip())/"stable/presentation-time/presentation-time.xml"
  need(xml.is_file(),"installed stable protocol")
  (RAW/"presentation-time.xml").write_bytes(xml.read_bytes())
  for mode,out in [("client-header","presentation-time-client-protocol.h"),("private-code","presentation-time-protocol.c")]:
   command(["wayland-scanner",mode,xml,OUT/out],"generate-"+mode,True)
  flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","gtk+-3.0","wayland-client"],text=True))
  command(["cc","-O2","-std=c11","-D_POSIX_C_SOURCE=200809L","-Wall","-Wextra","-Werror","-I"+str(OUT),HERE/"capability.c",OUT/"presentation-time-protocol.c","-o",OUT/"capability",*flags],"compile",True)
  (RAW/"capability").write_bytes((OUT/"capability").read_bytes())
  runtime=OUT/"runtime";runtime.mkdir(mode=0o700)
  env=dict(os.environ,DISPLAY=":98",XDG_RUNTIME_DIR=str(runtime))
  with (RAW/"xvfb.log").open("wb") as log:
   xvfb=subprocess.Popen(["Xvfb",":98","-screen","0","1440x900x24","-nolisten","tcp"],stdout=log,stderr=subprocess.STDOUT)
   time.sleep(2);need(xvfb.poll() is None,"isolated Xvfb")
   codes["xdpyinfo"]=command(["xdpyinfo"],"xdpyinfo",True,env)
   codes["renderer"]=command(["glxinfo","-B"],"renderer",False,env)
   codes["inner"]=command(["dbus-run-session","--",sys.executable,HERE/"run.py","inner"],"session",False,env,60)
   need(codes["inner"]==0,"nested capability session")
  doc=json.loads((RAW/"feedback.json").read_text());result=evaluate(doc);save(RAW/"capability-summary.json",result)
  need(result["native_feedback_observed"] and result["all_requests_resolved"] and result["all_presentations_have_nonzero_timestamps"],"native timestamp capability incomplete")
 except Exception as e:
  problems.append(str(e));(RAW/"exception.log").write_text(traceback.format_exc())
 finally:
  if xvfb is not None and xvfb.poll() is None:xvfb.terminate();xvfb.wait(timeout=10)
  save(RAW/"collection.json",{**identity(),"command_codes":codes,"problems":problems,"synthetic_only":True,"product_sampled":False,"frame_budget_measured":False,"f08_accepted":False})
  save(RAW/"manifest.json",{**identity(),"files":{p.relative_to(RAW).as_posix():{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(RAW.rglob("*")) if p.is_file() and p.name!="manifest.json"},"f08_accepted":False})
 print(json.dumps({"problems":problems,"raw":str(RAW),"f08_accepted":False}),flush=True)
 return 1 if problems else 0
if __name__=="__main__":
 if sys.argv[1:]==["inner"]:guard();inner()
 else:sys.exit(collect())
