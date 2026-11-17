import ctypes as c
import os, sys
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
from benchmark_pdf_rect import Page
from benchmark_pdf_blend import Bitmap,Error
library,pdf,width=sys.argv[1],sys.argv[2],int(sys.argv[3])
handle=os.add_dll_directory(str(Path(library).resolve().parent))
e=c.CDLL(str(Path(library).resolve()))
e.exr_fixed_open.argtypes=[c.c_char_p,c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(Error)]
e.exr_fixed_pages.argtypes=[c.c_void_p,c.POINTER(c.c_size_t)];e.exr_fixed_pages.restype=c.POINTER(Page)
e.exr_fixed_render.argtypes=[c.c_void_p,c.c_size_t,c.c_double,c.c_void_p,c.POINTER(Bitmap),c.POINTER(Error)]
e.exr_bitmap_free.argtypes=[c.POINTER(Bitmap)];e.exr_fixed_free.argtypes=[c.c_void_p]
doc=c.c_void_p();err=Error();assert not e.exr_fixed_open(str(Path(pdf).resolve()).encode(),None,c.byref(doc),c.byref(err)),err.message
count=c.c_size_t();pages=e.exr_fixed_pages(doc,c.byref(count))
for index in range(count.value):
    print('PAGE',index+1,file=sys.stderr,flush=True)
    g=pages[index].geometry;b=g.bounds
    native=b[3]-b[1] if g.rotation%180 else b[2]-b[0]
    bitmap=Bitmap();assert not e.exr_fixed_render(doc,index,width/(native*g.unit_scale),None,c.byref(bitmap),c.byref(err)),err.message
    e.exr_bitmap_free(c.byref(bitmap))
e.exr_fixed_free(doc)
