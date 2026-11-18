"""Fresh-process paired experiment: output.json A=dll B=dll; resumes matching hashes."""
import sys,os,json,statistics,time
from pathlib import Path
sys.path.insert(0,'tools')
from bench_firstscreen import gate,run_child,sha256
variants=dict(s.split('=',1) for s in sys.argv[2:]);out={'libraries':{tag:sha256(dll) for tag,dll in variants.items()},'cases':{}}
if Path(sys.argv[1]).exists():
 saved=json.loads(Path(sys.argv[1]).read_text())
 assert saved['libraries']==out['libraries']
 out=saved
for label,pdf,page in [('deck','tests/fixtures/pdf-ppt/deck.pdf',1),('bitmap','build/bitmap-first-120.pdf',1),('heavy80','tests/fixtures/pdf-large/image-heavy-100.pdf',80)]:
 rows=out['cases'].setdefault(label,[])
 for rep in range(5):
  for tag in (list(variants) if rep%2==0 else list(variants)[::-1]):
   if any(r['tag']==tag and r['rep']==rep for r in rows):continue
   last=time.monotonic()
   while True:
    try:idle=gate(15,1);break
    except SystemExit:
     if time.monotonic()-last>=60:
      print('Idle gate closed; retrying without a sample',flush=True);last=time.monotonic()
   result=run_child(variants[tag],pdf,1200,page=page,warm=3)
   rows.append({'tag':tag,'rep':rep,'idle':idle,'result':result})
   Path(sys.argv[1]).write_text(json.dumps(out,indent=2)+'\n')
   print(label,rep,tag,round(result['first_render_ms'],3),round(statistics.median(result['warm_render_ms']),3),flush=True)
 for tag in variants:
  rr=[r for r in rows if r['tag']==tag]
  print('SUMMARY',label,tag,'cold',round(statistics.median(r['result']['first_render_ms'] for r in rr),3),'warm',round(statistics.median(statistics.median(r['result']['warm_render_ms']) for r in rr),3),flush=True)
