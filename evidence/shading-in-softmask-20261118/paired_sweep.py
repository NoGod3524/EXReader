"""Per-page alternating A/B, exhaustive active-RGBA hashes, fail-closed sweep gates."""
import ctypes as c
import json, math, statistics as st, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from bench_real_doc import Bitmap,Error,Page,digest_file,hash_active_rgba,wait_idle

def gate():
    while True:
        busy=wait_idle(15,45)
        if busy is not None: return busy
        print('Idle gate failed; retrying the same sweep.',flush=True)

def main():
    a,b,pdf,width,runs,out=sys.argv[1:7]
    a,b,pdf,out=map(lambda p:Path(p).resolve(),(a,b,pdf,out));width,runs=int(width),int(runs)
    arms={}
    for tag,path in [('A',a),('B',b)]:
        e=c.CDLL(str(path));d=c.c_void_p();err=Error()
        for name,args in {
            'exr_fixed_open':[c.c_char_p,c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(Error)],
            'exr_fixed_pages':[c.c_void_p,c.POINTER(c.c_size_t)],
            'exr_fixed_render':[c.c_void_p,c.c_size_t,c.c_double,c.c_void_p,c.POINTER(Bitmap),c.POINTER(Error)],
            'exr_bitmap_free':[c.POINTER(Bitmap)],'exr_fixed_free':[c.c_void_p]}.items():
            getattr(e,name).argtypes=args
        e.exr_fixed_pages.restype=c.POINTER(Page)
        assert e.exr_fixed_open(str(pdf).encode(),None,c.byref(d),c.byref(err))==0,err.message
        n=c.c_size_t();pages=e.exr_fixed_pages(d,c.byref(n));scales=[]
        for i in range(n.value):
            g=pages[i].geometry;w=g.bounds[3]-g.bounds[1] if g.rotation%180 else g.bounds[2]-g.bounds[0]
            scales.append(width/(w*g.unit_scale))
        arms[tag]=(e,d,err,scales)
    assert len(arms['A'][3])==len(arms['B'][3]);count=len(arms['A'][3])
    rows=[{'page':i+1,'A':[],'B':[],'hashes':{}} for i in range(count)]
    gates=[];round_sums={k:[] for k in arms};pixels=0;different=[]
    for r in range(runs+1):
        if r in (0,1) or count>20 or (r-1)%5==0:
            gates.append({'round':r,'cpu_percent':gate()})
        totals={k:0 for k in arms}
        for i,row in enumerate(rows):
            order='AB' if (r+i)%2==0 else 'BA'
            for tag in order:
                e,d,err,scales=arms[tag];bitmap=Bitmap();t=time.perf_counter_ns()
                status=e.exr_fixed_render(d,i,scales[i],None,c.byref(bitmap),c.byref(err));ms=(time.perf_counter_ns()-t)/1e6
                assert status==0,err.message
                try:
                    assert bitmap.width==width and bitmap.channels==4
                    if r==0:
                        h,px=hash_active_rgba(bitmap);row['hashes'][tag]=h
                        if tag=='A': pixels+=px
                    else: row[tag].append(ms);totals[tag]+=ms
                finally: e.exr_bitmap_free(c.byref(bitmap))
            if r==0 and row['hashes']['A']!=row['hashes']['B']: different.append(i+1)
        if r:
            for tag in arms: round_sums[tag].append(totals[tag])
    summary={}
    for tag in arms:
        samples=[v for row in rows for v in row[tag]]
        summary[tag]={'p50_ms':st.median(samples),'p95_ms':sorted(samples)[math.ceil(.95*len(samples))-1],
                      'throughput_pages_s':count*1000/st.median(round_sums[tag]),'round_sum_ms':round_sums[tag]}
        for row in rows: row[tag+'_p50_ms']=st.median(row[tag])
        e,d,_,_=arms[tag];e.exr_fixed_free(d)
    result={'pdf':str(pdf),'pdf_sha256':digest_file(pdf),'a_sha256':digest_file(a),'b_sha256':digest_file(b),
            'width':width,'runs':runs,'order':'AB if (round+zero_based_page)%2==0 else BA; round 0 is pixel warmup',
            'idle_gates':gates,'idle_gate_every_small_sweeps':5,'compared_pixels':pixels,'mismatched_pages':different,'summary':summary,'pages':rows}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=1)+'\n')
    print(pdf.stem,width,json.dumps({k:{f:v for f,v in row.items() if f!='round_sum_ms'} for k,row in summary.items()}), 'pixels',pixels,'mismatches',different,flush=True)
if __name__=='__main__': main()
