"""Record whether the new shear renderer processes any small-fixture rows."""
import json,os,subprocess,sys
from pathlib import Path
from image_trace import ROOT,HERE,fields
from bench_real_doc import digest_file,wait_idle
cases=[('pdf-hybrid-real/pptx-20.pdf',20),('pdf-ppt/deck.pdf',15),('pdf-hybrid-real/word-5.pdf',5)]
dll=ROOT/'out/shading-image-B/libexreader.dll';result={'dll_sha256':digest_file(dll),'fixtures':{}}
for fixture,pages in cases:
    while True:
        busy=wait_idle(15,45)
        if busy is not None:break
    out=ROOT/'out'/f'shading-path-{Path(fixture).stem}.json'
    p=subprocess.run([sys.executable,'tools/bench_real_doc.py','--library',str(dll),'--input',str(ROOT/'tests/fixtures'/fixture),'--expect-pages',str(pages),'--runs','1','--child-width','1200','--child-out',str(out)],cwd=ROOT,env=dict(os.environ,EXR_IMAGE_TRACE='1'),capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    calls=[dict(zip(fields,map(float,l.split()[1:]))) for l in p.stderr.splitlines() if l.startswith('IMAGE ')]
    result['fixtures'][fixture]={'pre_cpu_percent':busy,'calls':calls,'stderr':p.stderr,'shear_rows':sum(c['stable_rows']+c['crossing_rows'] for c in calls)}
(HERE/'small-paths.json').write_text(json.dumps(result,indent=1)+'\n');print(json.dumps({k:v['shear_rows'] for k,v in result['fixtures'].items()}))
