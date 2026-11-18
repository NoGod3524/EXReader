"""Alternate image-call-scoped A/B children; record raw stderr and pixel hashes."""
import json,os,statistics as st,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from bench_real_doc import digest_file,wait_idle
HERE=Path(__file__).resolve().parent
fields='width height interpolate own_mask mask_interpolate matte blend state group_pixels soft_mask m0 m1 m2 m3 m4 m5 ms stable_rows crossing_rows'.split()
def main():
    rows=[];gates=[]
    for r in range(7):
        while True:
            busy=wait_idle(15,45)
            if busy is not None: break
            print('Idle gate failed; retrying same pair.',flush=True)
        gates.append(busy);row={'order':'AB' if r%2==0 else 'BA'}
        for side in row['order']:
            dll=ROOT/f'out/shading-image-{side}/libexreader.dll'
            cmd=[sys.executable,'tools/bench_firstscreen.py','child','--library',str(dll),'--input','tests/fixtures/pdf-large/real-mixed-120.pdf','--width','1200','--page','2','--warm','2']
            p=subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,EXR_IMAGE_TRACE='1'),capture_output=True,text=True)
            assert p.returncode==0,p.stderr
            calls=[dict(zip(fields,map(float,l.split()[1:]))) for l in p.stderr.splitlines() if l.startswith('IMAGE ')]
            row[side]={'result':json.loads(next(l[7:] for l in p.stdout.splitlines() if l.startswith('RESULT '))),'calls':calls,'stderr':p.stderr,'dll_sha256':digest_file(dll)}
        rows.append(row)
    summary={}
    for side in 'AB':
        calls=[call for row in rows for call in row[side]['calls'][3:]]
        summary[side]={str(width):st.median(call['ms'] for call in calls if call['width']==width) for width in sorted({c['width'] for c in calls})}
    (HERE/'image-scopes.json').write_text(json.dumps({'idle_cpu_percent':gates,'summary':summary,'pairs':rows},indent=1)+'\n')
    print(json.dumps(summary))
if __name__=='__main__':main()
