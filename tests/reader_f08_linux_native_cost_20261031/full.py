"""Run the frozen full GTK product with complete job/native completion spans."""
import importlib.util,json,math,os,shlex,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
LEGACY=ROOT/"tests/reader_f08_linux_product_20261031"
sys.path.insert(0,str(LEGACY))
import run as R
BASE="c86f18a088cff42db9ee0c33a5bd9fbd6cbe01bd"
FILES={"tests/reader_f08_linux_native_cost_20261031/"+n for n in ("probe.c","inject.py","control.c","full.py")}|{".github/workflows/f08-linux-native-cost-20261031.yml",".github/workflows/f08-linux-presentation-20261031.yml","docs/reader-total-progress/F08_LINUX_NATIVE_COST_20261031.md","tests/reader_f08_linux_native_cost_20261031/extras.py",".github/workflows/f08-linux-body-jump-20261031.yml","docs/reader-total-progress/F08_LINUX_BODY_JUMP_20261031.md"}
PROBE="f08-native-cost/libexreader_f08_native_cost.so"
def guard():
 R.need(os.environ.get("GITHUB_ACTIONS")=="true" and sys.platform.startswith("linux"),"Linux Actions only")
 R.need(R.command(["git","rev-parse","HEAD"],text=True).strip()==R.identity()["source_sha"],"source")
 R.need(set(R.command(["git","diff","--name-only",BASE,"HEAD"],text=True).splitlines())==FILES,"additive scope")
 for p in ("src","include","apps/reader","examples","tools"):
  R.need(R.command(["git","rev-parse","HEAD:"+p])==R.command(["git","rev-parse",BASE+":"+p]),"unchanged production: "+p)
R.guard=guard
R.PROBES=(*R.PROBES,PROBE);R.TREES=(*R.TREES,"f08-native-cost-result")
R.FROZEN=(*R.FROZEN,R.ADAPTERS[0]);R.ADAPTERS=("tests/reader_f08_linux_native_cost_20261031/inject.py",R.ADAPTERS[1])
def stats(values):
 ordered=sorted(values)
 return {"count":len(ordered),"p50_ms":ordered[math.ceil(.5*len(ordered))-1]/1000,"p95_ms":ordered[math.ceil(.95*len(ordered))-1]/1000,"p99_ms":ordered[math.ceil(.99*len(ordered))-1]/1000,"max_ms":ordered[-1]/1000} if ordered else {"count":0}
def inspect(doc):
 R.need(doc.get("schema")==1 and doc.get("overflow")==0 and doc.get("capacity")==65536 and doc.get("queue_observed") is True,"protocol/queue")
 jobs=doc["jobs"];frames=doc["frames"];inputs=doc["inputs"]
 R.need(0<len(jobs)<=65536 and 0<len(frames)<=65536 and len(inputs)<=65536,"census bounds")
 missing=[];page=[];shelf=[];initial=[];categories={};overhead=[];native_errors=[];reader_repaint=[];shelf_bounds=[]
 for i,e in enumerate(inputs):R.need(e["id"]==i+1 and type(e["at"]) is int and e["at"]>0,"native input")
 for i,f in enumerate(frames):
  R.need(f["id"]==i+1 and all(type(f[k]) is int and f[k]>=0 for k in ("before","sync_start","sync_end","counter","kind","page_job","shelf_job","input")),"native frame")
  R.need(0<f["before"]<=f["sync_start"]<=f["sync_end"] and f["input"]<=len(inputs),"native ordering")
  R.need(f["page_job"]<=len(jobs) and f["shelf_job"]<=len(jobs),"native job binding")
  overhead.append(f["sync_end"]-f["sync_start"])
  if f["native_error"]:native_errors.append(i+1)
  if f["kind"]&1:reader_repaint.append(f["sync_end"]-f["before"])
  if f["kind"]&2 and f["input"]:
   start=inputs[f["input"]-1]["at"];R.need(start<=f["sync_end"],"shelf input clock");shelf_bounds.append(f["sync_end"]-start)
 first=True
 for i,j in enumerate(jobs):
  R.need(j["id"]==i+1 and type(j["action"]) is int and 0<=j["action"]<=62 and j["input"]<=len(inputs),"job inventory")
  R.need(all(type(j[k]) is int and j[k]>=0 for k in ("queued","start","worker_end","apply_start","apply_end","image_at","draw_end","complete")),"job times")
  R.need(j["queued"]>0 and (not j["start"] or j["start"]>=j["queued"]),"queue ordering")
  if not (j["page"] or j["shelf"]):continue
  required=j["page"] or j["shelf_visible"]
  if not j["complete"]:
   if required:missing.append(i+1)
   continue
  R.need(j["queued"]<=j["start"]<=j["worker_end"]<=j["apply_start"]<=j["apply_end"]<=j["draw_end"]<=j["complete"],"full job ordering")
  matches=[f for f in frames if f["sync_end"]==j["complete"] and f["native_error"]==0 and f["clock"]==j["clock"] and f["counter"]==j["counter"] and (f["page_job"]==j["id"] if j["page"] else f["shelf_job"]==j["id"])]
  R.need(len(matches)==1,"exact native completion binding")
  duration=j["complete"]-j["start"]
  if j["page"]:
   R.need(j["frame_generation"]>0,"accepted page generation")
   page.append(duration)
   if first:initial.append(duration);first=False
   name="page_turn" if j["action"] in (3,4) else "font" if j["action"] in (5,58) else "locate_jump" if j["action"] in (8,36,40,47,61) else "reader_other"
   categories.setdefault(name,[]).append(duration)
  elif j["shelf_visible"]:shelf.append(duration)
 return {"jobs":len(jobs),"page_generations":sum(bool(j["page"]) for j in jobs),"shelf_generations":sum(bool(j["shelf"]) for j in jobs),"non_frame_jobs":sum(not(j["page"] or j["shelf"]) for j in jobs),"background_shelf_generations":sum(bool(j["shelf"] and not j["shelf_visible"]) for j in jobs),"native_frames":len(frames),"native_errors":native_errors,"missing_required_generations":missing,"inputs":len(inputs),"probe_static_bytes":doc["probe_static_bytes"],"values":{"all_page_generations":page,"initial_page_generation":initial,"visible_shelf_worker_generations":shelf,"shelf_input_to_native_completion_upper_bound":shelf_bounds,"reader_body_native_full_GDK_phase_only":reader_repaint,"native_fence_wait":overhead,**categories}}
def verify(raw,output=None):
 reports=[];combined={};ident=R.identity();raw=Path(raw)
 for cohort,expected in [("perf-evidence",32),("perf-interactions",12)]:
  launches=R.load(raw/cohort/"launches.json")["launches"];R.need(len(launches)==expected,"all original launches")
  for launch in launches:
   directory=raw/cohort/"raw"/("launch-%02d"%launch["launch"])/"native-cost";paths=list(directory.glob("*.json"));pid=launch["pid"]
   R.need(len(paths)==1 and paths[0].name==str(pid)+".json" and launch["process_exit"]==0,"normal native PID output")
   doc=R.load(paths[0]);R.need(doc["pid"]==pid and all(doc[k]==ident[v] for k,v in [("source","source_sha"),("run","run_id"),("attempt","attempt")]) and doc["executable"].endswith("/bin/exreader-linux"),"native identity")
   result=inspect(doc);values=result.pop("values");result.update(cohort=cohort,launch=launch["launch"],pid=pid,raw_sha256=R.sha(paths[0]))
   for name,rows in values.items():combined.setdefault(name,[]).extend(rows)
   result["metrics"]={k:stats(v) for k,v in values.items()};reports.append(result)
 # The separate six-launch causal census is required and remains independently verified by the original driver.
 causal=[]
 for path in sorted((raw/"f08-causal").rglob("native-cost/*.json")):
  doc=R.load(path);R.need(all(doc[k]==ident[v] for k,v in [("source","source_sha"),("run","run_id"),("attempt","attempt")]),"causal native identity")
  item=inspect(doc);values=item.pop("values");item["metrics"]={k:stats(v) for k,v in values.items()};item["raw_sha256"]=R.sha(path);causal.append(item)
 R.need(len(causal)==6,"six causal native traces")
 complete=not any(r["native_errors"] or r["missing_required_generations"] for r in reports+causal)
 metrics={k:stats(v) for k,v in combined.items()};checks=[]
 for name in ("all_page_generations","visible_shelf_worker_generations","shelf_input_to_native_completion_upper_bound"):
  m=metrics[name];checks.append({"metric":name,"count":m["count"],"p95_max_ms":16.67,"p99_max_ms":33.34,"passed":bool(m["count"]) and m["p95_ms"]<=16.67 and m["p99_ms"]<=33.34})
 receipt={**ident,"launches":reports,"causal_launches":causal,"metrics":metrics,"complete_generation_census":complete,"checks":checks,"candidate_native_cost_budget_passed":complete and all(c["passed"] for c in checks),"physical_presentation_proven":False,"shelf_bound_includes_input_queue_and_animation":True,"native_fence_changes_timing_and_is_included":True,"reader_body_GDK_phase_is_not_substituted_for_full_generation_cost":True,"f08_accepted":False}
 if output:R.save(Path(output)/"summary.json",receipt)
 print("F08_NATIVE_COST",json.dumps({k:v for k,v in receipt.items() if k not in ("launches","causal_launches")}),flush=True)
 return receipt
def compile_probe():
 guard();folder=ROOT/"build/f08-native-cost";folder.mkdir(parents=True,exist_ok=True)
 flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","gtk+-3.0","x11"],text=True))
 subprocess.run(["cc","-O2","-shared","-fPIC","-Wall","-Wextra",str(HERE/"probe.c"),"-o",str(ROOT/"build"/PROBE),*flags,"-ldl","-pthread"],check=True,cwd=ROOT)
 return flags
def control():
 flags=compile_probe();folder=ROOT/"build/f08-native-control";folder.mkdir(parents=True,exist_ok=False)
 subprocess.run(["cc","-O2",str(HERE/"control.c"),"-o",str(folder/"exreader-linux"),*flags],check=True,cwd=ROOT)
 env=dict(os.environ,GTK_MODULES=str(ROOT/"build"/PROBE),LD_PRELOAD=str(ROOT/"build"/PROBE),EXR_F08_NATIVE_OUTPUT=str(folder),F08_CONTROL_STATE=str(folder/"state.ini"))
 subprocess.run([folder/"exreader-linux"],check=True,env=env,timeout=10)
 paths=list(folder.glob("*.json"));R.need(len(paths)==1,"control output")
 doc=R.load(paths[0]);result=inspect(doc);values=result.pop("values");R.need(result["page_generations"]==2 and not result["missing_required_generations"] and not result["native_errors"],"complete synthetic generations")
 jobs=[j for j in doc["jobs"] if j["page"]];R.need([j["action"] for j in jobs]==[3,5] and all(j["complete"]-j["start"]>=delay for j,delay in zip(jobs,[50000,80000])),"worker delay survives end-to-end boundary")
 missing=json.loads(json.dumps(doc));next(j for j in missing["jobs"] if j["page"])["complete"]=0
 R.need(inspect(missing)["missing_required_generations"],"missing generation retained")
 R.save(folder/"control-result.json",{"synthetic_only":True,"generations":2,"full_cost_ms":[(j["complete"]-j["start"])/1000 for j in jobs],"native_fence_wait":stats(values["native_fence_wait"]),"worker_delay_included":True,"missing_retained":True,"f08_accepted":False})
def main():
 mode=sys.argv[1]
 if mode=="control":control()
 elif mode=="build":compile_probe();R.build()
 elif mode=="sample":
  try:R.sample()
  finally:
   output=ROOT/"build/f08-native-cost-result";output.mkdir(parents=True,exist_ok=True);verify(ROOT/"build",output)
 elif mode=="seal":R.seal()
 elif mode=="audit":
  spec=importlib.util.spec_from_file_location("native_legacy_audit",LEGACY/"audit.py");audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit);audit.main()
  raw=ROOT/"build/f08-linux-product-audit/raw";result=verify(raw);R.need(result==R.load(raw/"f08-native-cost-result/summary.json"),"independent native cost replay");R.save(ROOT/"build/f08-linux-product-audit/native-cost-audit.json",result)
 else:raise ValueError(mode)
if __name__=="__main__":main()
