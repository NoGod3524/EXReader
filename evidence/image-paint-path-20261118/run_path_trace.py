import sys,os,json,subprocess,statistics
from pathlib import Path
sys.path.insert(0,'tools')
from bench_firstscreen import gate,sha256
out={'libraries':{tag:sha256('out/continue/trace-'+tag+'/libexreader.dll') for tag in 'AB'},'cases':{}}
for label,pdf,page in [('mixed','tests/fixtures/pdf-large/real-mixed-120.pdf',1),('bitmap','build/bitmap-first-120.pdf',1),('heavy80','tests/fixtures/pdf-large/image-heavy-100.pdf',80),('deck','tests/fixtures/pdf-ppt/deck.pdf',1)]:
 rows=[]
 for rep in range(5):
  for tag in ('AB' if rep%2==0 else 'BA'):
   while True:
    try:
     idle=gate(15,60)
     break
    except SystemExit:
     print('Idle gate closed; retrying without a sample',flush=True)
   p=subprocess.run([sys.executable,'-X','utf8','tools/bench_firstscreen.py','child','--library','out/continue/trace-'+tag+'/libexreader.dll','--input',pdf,'--width','1200','--page',str(page),'--warm','1'],capture_output=True,text=True,env=dict(os.environ,EXR_IMAGE_TRACE='1'))
   assert p.returncode==0,p.stderr
   result=json.loads(next(l[7:] for l in p.stdout.splitlines() if l.startswith('RESULT ')))
   traces=[dict(v.split('=',1) for v in l.split()[1:]) for l in p.stderr.splitlines() if l.startswith('IMGPATH ')]
   rows.append({'tag':tag,'rep':rep,'idle':idle,'result':result,'images':traces})
   out['cases'][label]=rows
   Path('evidence/image-paint-path-20261118/continue-path-trace.json').write_text(json.dumps(out,indent=2)+'\n')
 out['cases'][label]=rows
 for tag in 'AB':
  rr=[r for r in rows if r['tag']==tag];n=len(rr[0]['images'])//2
  print(label,tag,'first',round(statistics.median(r['result']['first_render_ms'] for r in rr),3),'images',[(rr[0]['images'][i]['path'],statistics.median(float(r['images'][i]['ms']) for r in rr)) for i in range(n)],flush=True)
Path('evidence/image-paint-path-20261118/continue-path-trace.json').write_text(json.dumps(out,indent=2)+'\n')
