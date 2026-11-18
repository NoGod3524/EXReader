import ctypes as c, os, sys, time, statistics, json
sys.path.insert(0, sys.argv[3]); import benchmark_pdf_rect as b
pdf=sys.argv[1]; width=float(sys.argv[2]); rounds=int(sys.argv[4]); out=sys.argv[5]
libs={}
for k in ('base','new'):
    p=os.path.abspath(f'out/prof-{k}.dll'); os.add_dll_directory(os.path.dirname(p)); e=c.CDLL(p)
    e.exr_fixed_open.argtypes=[c.c_char_p,c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(b.Error)]
    e.exr_fixed_pages.argtypes=[c.c_void_p,c.POINTER(c.c_size_t)]; e.exr_fixed_pages.restype=c.POINTER(b.Page)
    e.exr_fixed_render.argtypes=[c.c_void_p,c.c_size_t,c.c_double,c.c_void_p,c.POINTER(b.Bitmap),c.POINTER(b.Error)]
    e.exr_bitmap_free.argtypes=[c.POINTER(b.Bitmap)]
    err=b.Error(); d=c.c_void_p(); assert e.exr_fixed_open(pdf.encode(),None,c.byref(d),c.byref(err))==0
    n=c.c_size_t(); pg=e.exr_fixed_pages(d,c.byref(n)); sc=[]
    for i in range(n.value):
        g=pg[i].geometry; bd=g.bounds; nw=bd[3]-bd[1] if g.rotation%180 else bd[2]-bd[0]; sc.append(width/(nw*g.unit_scale))
    libs[k]=(e,d,sc,err)
cats=['full','image','path','glyph','gfill','group']
res={(k,s):[] for k in libs for s in cats}
for r in range(rounds+1):
    for j,s in enumerate(cats):
        os.environ['ZZ_SKIP']='' if s=='full' else s
        for k in (('base','new') if (r+j)%2==0 else ('new','base')):
            e,d,sc,err=libs[k]
            for i,x in enumerate(sc):
                bm=b.Bitmap(); t=time.perf_counter_ns(); st=e.exr_fixed_render(d,i,x,None,c.byref(bm),c.byref(err)); el=(time.perf_counter_ns()-t)/1e6
                assert st==0; e.exr_bitmap_free(c.byref(bm))
                if r: res[(k,s)].append(el)
table={k:{s:round(statistics.median(res[(k,s)]),4) for s in cats} for k in libs}
json.dump({'pdf':pdf,'width':width,'rounds':rounds,'p50_ms':table},open(out,'w'),indent=2)
for s in cats: print('%-6s base %.3f  new %.3f' % (s,table['base'][s],table['new'][s]))
