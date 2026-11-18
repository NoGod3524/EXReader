import ctypes as c, os, sys, time, statistics
sys.path.insert(0, sys.argv[4])
import benchmark_pdf_rect as b
lib, pdf, width = sys.argv[1], sys.argv[2], float(sys.argv[3])
os.add_dll_directory(os.path.dirname(os.path.abspath(lib)))
e = c.CDLL(os.path.abspath(lib))
e.exr_fixed_open.argtypes=[c.c_char_p,c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(b.Error)]
e.exr_fixed_pages.argtypes=[c.c_void_p,c.POINTER(c.c_size_t)]; e.exr_fixed_pages.restype=c.POINTER(b.Page)
e.exr_fixed_render.argtypes=[c.c_void_p,c.c_size_t,c.c_double,c.c_void_p,c.POINTER(b.Bitmap),c.POINTER(b.Error)]
e.exr_bitmap_free.argtypes=[c.POINTER(b.Bitmap)]
err=b.Error(); d=c.c_void_p(); assert e.exr_fixed_open(pdf.encode(),None,c.byref(d),c.byref(err))==0
n=c.c_size_t(); pg=e.exr_fixed_pages(d,c.byref(n)); scales=[]
for i in range(n.value):
    g=pg[i].geometry; bd=g.bounds; nw=bd[3]-bd[1] if g.rotation%180 else bd[2]-bd[0]; scales.append(width/(nw*g.unit_scale))
ts=[]
for it in range(int(os.environ.get('ROUNDS','21'))):
    for i,s in enumerate(scales):
        bm=b.Bitmap(); t=time.perf_counter_ns(); st=e.exr_fixed_render(d,i,s,None,c.byref(bm),c.byref(err)); el=(time.perf_counter_ns()-t)/1e6
        assert st==0, err.message
        e.exr_bitmap_free(c.byref(bm))
        if it: ts.append(el)
print('%s p50 %.3f ms' % (os.environ.get('ZZ_SKIP','full'), statistics.median(ts)))
