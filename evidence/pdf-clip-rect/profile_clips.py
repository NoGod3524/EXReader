"""One render per page; clip counters only, never performance measurements.
Run from the repository root after building build/perf. Restores canvas.c on exit.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

ap=argparse.ArgumentParser()
ap.add_argument('--baseline',action='store_true')
ap.add_argument('--out',type=Path,required=True)
args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
source=Path('src/canvas.c');original=source.read_bytes()
if args.baseline:
    text=subprocess.check_output(['git','show','baf348d2d:src/canvas.c'],text=True)
    text=text.replace('  if(status==EXR_OK && !group && covers_canvas(c,&flat)) {',
        '  if(status==EXR_OK && !group && covers_canvas(c,&flat)) {\n    fprintf(stderr,"BASE_IDENTITY\\n");')
    text=text.replace('  } else if(status==EXR_OK) {\n    status=new_mask(c,&mask,e);',
        '  } else if(status==EXR_OK) {\n    fprintf(stderr,"BASE_MASK\\n");\n    status=new_mask(c,&mask,e);')
else:
    text='#define EXR_CLIP_PROFILE\n'+original.decode().replace('\r\n','\n')
    text=text.replace('#ifdef EXR_CLIP_PROFILE\n',
        '#ifdef EXR_CLIP_PROFILE\n  if(status==EXR_OK && !group && !c->clip) fprintf(stderr,"IDENTITY\\n");\n')

def build():
    result=subprocess.run(['cmake','--build','build/perf','--target','exreader','--parallel','6'],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)

try:
    source.write_text(text);build();reports={}
    for name,pdf in [('deck','tests/fixtures/pdf-ppt/deck.pdf'),('pptx','tests/fixtures/pdf-hybrid-real/pptx-20.pdf')]:
        proc=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).with_name('profile_render.py')),
                             'build/perf/libexreader.dll',pdf,'1200'],capture_output=True,text=True,check=True)
        (args.out/(name+'.log')).write_text(proc.stderr)
        pages=[];page=None
        for line in proc.stderr.splitlines():
            if line.startswith('PAGE '):
                page=Counter();pages.append(page)
            elif line.startswith(('BASE_','EXR_CLIP','IDENTITY')):
                page[line]+=1
        total=sum(pages,Counter())
        reports[name]={'width':1200,'pages':[dict(p) for p in pages],'totals':dict(total)}
    (args.out/'counts.json').write_text(json.dumps(reports,indent=2)+'\n')
finally:
    source.write_bytes(original);build()
