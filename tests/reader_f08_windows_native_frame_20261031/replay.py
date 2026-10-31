"""Strict replay of native GDI full-frame production candidates; all rows retained."""
import argparse,copy,json,math
from pathlib import Path

def need(value,reason):
 if not value:raise ValueError(reason)
def stats(values):
 if not values:return {"n":0,"p95_ms":None,"p99_ms":None,"max_ms":None,"passed":False}
 ordered=sorted(values);p95=ordered[math.ceil(.95*len(ordered))-1];p99=ordered[math.ceil(.99*len(ordered))-1]
 return {"n":len(values),"p95_ms":p95,"p99_ms":p99,"max_ms":max(values),"passed":p95<=16.67 and p99<=33.34}
def replay(document):
 rows=document["rows"];frequency=document["frequency"]
 need(type(frequency) is int and frequency>0,"QPC frequency")
 need(document["overflow"] is False and document["rows_attempted"]==len(rows),"complete bounded trace")
 need(rows and rows[0]["kind"]=="start" and rows[-1]["kind"]=="normal_exit","normal native lifetime")
 need([r["index"] for r in rows]==list(range(len(rows))),"contiguous raw inventory")
 need(all(type(r["qpc"]) is int and r["qpc"]>0 for r in rows),"native timestamps")
 inputs={r["input_id"]:r for r in rows if r["kind"]=="input"}
 need(len(inputs)==sum(r["kind"]=="input" for r in rows),"unique input identities")
 workers={r["job_id"]:r for r in rows if r["kind"]=="worker_end"}
 need(len(workers)==sum(r["kind"]=="worker_end" for r in rows),"unique worker identities")
 produced=[r for r in workers.values() if r["flags"]==0 and r["v0"] and r["v1"]]
 paints=[r for r in rows if r["kind"]=="reader_gdi_complete"]
 publications=[r for r in rows if r["kind"]=="reader_publish" and r["flags"]]
 reader=[];missing=[];all_ids=set();font=[];page=[]
 for pub in publications:
  identity=(pub["job_id"],pub["generation"],pub["book"])
  need(identity not in all_ids,"duplicate accepted generation");all_ids.add(identity)
  worker=workers.get(pub["job_id"])
  need(worker is not None and (worker["generation"],worker["book"])==identity[1:],"publication worker identity")
  start=worker["worker_start_qpc"];end=worker["worker_end_qpc"]
  need(0<worker["queued_qpc"]<=start<=end<=pub["qpc"],"full worker chronology")
  candidates=[r for r in paints if (r["job_id"],r["generation"],r["book"])==identity]
  if not candidates:missing.append({"identity":identity,"reason":"no same-generation GDI completion"});continue
  paint=min(candidates,key=lambda r:r["qpc"])
  need(end<=paint["start_qpc"]<=paint["qpc"],"native paint chronology")
  need(paint["flags"]==3 and paint["v0"]>0,"visible successful product bitmap and GDI flush")
  value=(paint["qpc"]-start)*1000/frequency;input_row=inputs.get(worker["input_id"])
  sample={"identity":identity,"full_frame_production_ms":value,
   "worker_ms":(end-start)*1000/frequency,"queue_ms":(start-worker["queued_qpc"])*1000/frequency,
   "paint_ms":(paint["qpc"]-paint["start_qpc"])*1000/frequency,"input_to_complete_ms":None,
   "worker_start_qpc":start,"completion_qpc":paint["qpc"],"input_id":worker["input_id"]}
  if input_row:
   need(input_row["qpc"]<=worker["queued_qpc"],"input precedes production")
   sample["input_to_complete_ms"]=(paint["qpc"]-input_row["qpc"])*1000/frequency
   if input_row["control"] in (113,114):font.append(value)
   if input_row["control"] in (105,106):page.append(value)
  else:missing.append({"identity":identity,"reason":"input causality unavailable"})
  reader.append(sample)
 for worker in produced:
  identity=(worker["job_id"],worker["generation"],worker["book"])
  if identity not in all_ids:missing.append({"identity":identity,"reason":"produced frame never accepted/published"})
 shelf=[];shelf_unknown=[];seen=set()
 for row in rows:
  if row["kind"]!="shelf_frame_complete":continue
  key=(row["job_id"],row["generation"])
  if not row["worker_start_qpc"] or not row["job_id"]:
   shelf_unknown.append(row["index"]);continue
  if key in seen:continue
  seen.add(key);need(0<row["worker_start_qpc"]<=row["start_qpc"]<=row["qpc"],"shelf production chronology")
  shelf.append({"identity":key,"full_frame_production_ms":(row["qpc"]-row["worker_start_qpc"])*1000/frequency,
                "input_id":row["input_id"],"message":row["message"],"completion_qpc":row["qpc"]})
 # Native LISTBOX internals can update selection/scrollbars without changing top/count.
 # Keep every dispatch and completion; do not promote this partial census to all frames.
 return {"raw_rows":len(rows),"reader_produced":len(produced),"reader_published":len(publications),
  "reader_paints":len(paints),"reader_samples":reader,"reader_missing":missing,
  "reader_full_frame_production":stats([r["full_frame_production_ms"] for r in reader]),
  "reader_font_full_frame_production":stats(font),"reader_page_full_frame_production":stats(page),
  "shelf_full_frame_production_candidates":stats([r["full_frame_production_ms"] for r in shelf]),
  "shelf_samples":shelf,"shelf_unbound_completions":shelf_unknown,"shelf_full_census_proven":False,
  "reader_coverage_complete":bool(reader) and not missing,
  "all_frame_budget_measured":False,"f08_accepted":False,
  "boundary":"worker-entry/native-scroll-entry to same-generation GDI execution completion",
  "percentile":"nearest rank, every candidate retained; no trimming",
  "physical_scanout_proven":False}

def control():
 def row(kind,t,**extra):
  r=dict(index=0,kind=kind,qpc=t,start_qpc=0,job_id=0,input_id=0,queued_qpc=0,worker_start_qpc=0,
         worker_end_qpc=0,generation=0,book=0,control=0,message=0,flags=0,v0=0,v1=0,thread=1);r.update(extra);return r
 origin=dict(job_id=1,input_id=1,queued_qpc=20,worker_start_qpc=30,worker_end_qpc=40030,generation=1,book=7)
 rows=[row("start",1),row("input",10,input_id=1,control=114),row("worker_end",40030,**origin,v0=1,v1=1),
       row("reader_publish",40040,**origin,flags=1),row("reader_gdi_complete",40060,**origin,start_qpc=40050,flags=3,v0=720),row("normal_exit",40100)]
 for i,r in enumerate(rows):r["index"]=i
 d=dict(frequency=1000000,overflow=False,rows_attempted=len(rows),rows=rows)
 result=replay(d);need(result["reader_full_frame_production"]["p95_ms"]==40.03,"full worker cost, not cheap paint tail")
 need(not result["reader_full_frame_production"]["passed"],"unchanged frame budget")
 checks=["full-worker-boundary"]
 for name,change in [("overflow",lambda x:x.update(overflow=True)),
  ("wrong-generation",lambda x:x["rows"][3].update(generation=2)),
  ("reverse-time",lambda x:x["rows"][4].update(qpc=25)),
  ("failed-gdi",lambda x:x["rows"][4].update(flags=-1)),
  ("invisible-frame",lambda x:x["rows"][4].update(flags=1)),
  ("partial-bitmap",lambda x:x["rows"][4].update(v0=0))]:
  bad=copy.deepcopy(d);change(bad)
  try:replay(bad)
  except (ValueError,KeyError):checks.append(name)
  else:raise AssertionError(name+" accepted")
 missing=copy.deepcopy(d);missing["rows"][4]["kind"]="unknown"
 need(not replay(missing)["reader_coverage_complete"],"missing GDI retained as missing")
 missing=copy.deepcopy(d);missing["rows"][1]["kind"]="unknown"
 need(not replay(missing)["reader_coverage_complete"],"missing input retained as missing")
 checks.extend(["missing-paint","missing-input"])
 return checks
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("trace",nargs="?");p.add_argument("--output");p.add_argument("--self-test",action="store_true");a=p.parse_args()
 result={"controls":control()} if a.self_test else replay(json.loads(Path(a.trace).read_text()))
 text=json.dumps(result,indent=2);print(text)
 if a.output:Path(a.output).write_text(text+"\n")
