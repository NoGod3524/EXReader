import ctypes as c
from contextlib import ExitStack
from pathlib import Path
import json, statistics, subprocess, sys, time
ROOT=Path.cwd()
sys.path.insert(0,str(ROOT.parent/'EXReader-openperf/tools'))
import render_vs_pdfjs as b
OUT=ROOT/'evidence/pptx600-fix-20261120/raw-dot'
LIB={tag: ROOT/'build/p600-dlls'/f'{name}.dll' for tag,name in {'A':'base','A0':'base-null','B':'cand'}.items()}
FIX=ROOT/'tests/fixtures'
SMALL=[('pdf-hybrid-real/pptx-20.pdf',w,20) for w in (600,1200,2400)]+[('pdf-ppt/deck.pdf',w,15) for w in (600,1200)]+[('pdf-hybrid-real/word-5.pdf',w,5) for w in (600,1200)]
def save(name,data): (OUT/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def deck():
    from itertools import permutations
    digest=b.identity(LIB['A'],LIB['A0'])
    libs={k:b.Native(v) for k,v in LIB.items()}
    assert len({n.e._handle for n in libs.values()})==3
    orders=list(permutations(libs))
    raw=[]
    with ExitStack() as s:
        ds={k:s.enter_context(n.document(FIX/'pdf-ppt/deck.pdf',600)) for k,n in libs.items()}
        assert all(n==15 for n,_ in ds.values())
        for r in range(12):
            cpu=b.cpu_times(); time.sleep(.2); pre=b.cpu_busy_percent(cpu,b.cpu_times())
            rows=[]
            for p in range(1,16):
                o=orders[(r//2+p-1)%6]; o=o[::-1] if r%2 else o
                samples={k:ds[k][1](p) for k in o}
                assert len({(tuple(v['dimensions']),v['sha256']) for v in samples.values()})==1
                rows.append({'page':p,'order':o,'samples':samples})
            raw.append({'round':r+1,'pre_cpu_percent':pre,'rows':rows})
    pooled={k:statistics.median(v['samples'][k]['ns'] for r in raw for v in r['rows']) for k in libs}
    sums=[{k:sum(v['samples'][k]['ns'] for v in r['rows']) for k in libs} for r in raw]
    result={'sha256':{k:b.digest_file(v) for k,v in LIB.items()},'rounds': raw,'p50_ns':pooled,
            'B/A':pooled['B']/pooled['A'],'null_median_abs':statistics.median(abs(s['A']/s['A0']-1) for s in sums),
            'null_max_abs':max(abs(s['A']/s['A0']-1) for s in sums),'paired_B/A':[s['B']/s['A'] for s in sums]}
    save('deck-600.json',result)
    print({k:v for k,v in result.items() if k!='rounds'},flush=True)
def pixels():
    old=ROOT.parent/'EXReader-vhslides/evidence/slides-gradient-20261118/paired_sweep.py'
    total=diff=0
    for pdf,w,n in SMALL:
        out=OUT/f"pixels-{Path(pdf).stem}-{w}.json"
        subprocess.run([sys.executable,'-B',str(old),str(LIB['A']),str(LIB['B']),str(FIX/pdf),str(w),'0',str(out)],check=True)
        d=json.loads(out.read_text())
        assert len(d['pages'])==n
        total+=d['compared_pixels']; diff+=d['differing_pixels']
    print('small pixels',total,'different',diff,flush=True)
    assert total==111897000 and diff==0
def rss():
    results={}
    for pdf,w,n in [SMALL[i] for i in (0,3,5)]:
        key=f"{Path(pdf).stem}-{w}"; results[key]=pairs=[]
        for i,order in enumerate(('AB','BA','AB'),1):
            pair={}
            for k in order:
                f=OUT/f'rss-{key}-{i}-{k}.json'
                subprocess.run([sys.executable,'-B',str(ROOT/'tools/bench_real_doc.py'),'--library',str(LIB[k]),'--input',str(FIX/pdf),'--expect-pages',str(n),'--child-width',str(w),'--runs','1','--child-out',str(f)],check=True)
                pair[k]=json.loads(f.read_text())['peak_rss_bytes']; assert pair[k]>0
            pairs.append(pair)
        print(key,pairs,flush=True)
    save('rss-summary.json',results)
    for k,pairs in results.items():
        assert max(p['B'] for p in pairs)<=1.10*max(p['A'] for p in pairs), k

def backgrounds():
    class Control(c.Structure):
        _fields_=[('cancelled',c.c_void_p),('progress',c.c_void_p),('context',c.c_void_p)]
    class Options(c.Structure):
        _fields_=[('channels',c.c_uint32),('background',c.c_uint32),('mask_budget',c.c_size_t),('control',Control)]
    results=[]
    for pdf,width,pages in SMALL:
        if Path(pdf).stem not in ('pptx-20','word-5') or width==2400:
            continue
        path=FIX/pdf
        for name,ch,col in [('white',4,0xffffffff),('transparent',4,0),('tinted',4,0x4a6e91ff),('grayscale',1,0x808080ff)]:
            opts=Options(ch,col,0,Control()); rows=[]
            for tag in 'AB':
                dll=b.Native(LIB[tag]).e
                doc,n,err=c.c_void_p(),c.c_size_t(),b.Error()
                assert dll.exr_fixed_open(str(path).encode(),None,c.byref(doc),c.byref(err))==0,err.message
                try:
                    page=dll.exr_fixed_pages(doc,c.byref(n))
                    assert n.value==pages
                    variants=[]
                    for i in range(n.value):
                        g=page[i].geometry; u=int(bool(g.rotation%180)); scale=width/((g.bounds[u+2]-g.bounds[u])*g.unit_scale)
                        bm=b.Bitmap()
                        assert dll.exr_fixed_render(doc,i,scale,c.byref(opts),c.byref(bm),c.byref(err))==0, err.message
                        try:
                            assert bm.width==width and bm.channels==ch
                            rows_data=[c.string_at(bm.pixels+y*bm.stride,width*ch) for y in range(bm.height)]
                            import hashlib
                            variants.append(dict(page=i+1,dimensions=[bm.width,bm.height],image=hashlib.sha256(b''.join(rows_data)).hexdigest(),last_row=hashlib.sha256(rows_data[-1]).hexdigest()))
                        finally:
                            dll.exr_bitmap_free(c.byref(bm))
                    rows.append(variants)
                finally:
                    dll.exr_fixed_free(doc)
            mismatches=[r['page'] for r,s in zip(*rows) if r!=s]
            results.append(dict(fixture=pdf,width=width,background=name,compared=len(rows[0]),mismatches=mismatches,base=rows[0],candidate=rows[1]))
    save('backgrounds.json',results)
    print('page comparisons',sum(r['compared'] for r in results),'mismatches',sum(len(r['mismatches']) for r in results))
    assert all(not r['mismatches'] for r in results)

globals()[sys.argv[1]]()


