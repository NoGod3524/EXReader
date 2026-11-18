"""Alternate DLLs page by page, for diagnostic ablations or direct active-row pixel checks."""
import argparse
import ctypes as c
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from bench_real_doc import Bitmap, Error, Page, digest_file, wait_idle

class Document:
    def __init__(self, library, pdf, width):
        self.dll = e = c.CDLL(str(library.resolve()))
        e.exr_fixed_open.argtypes=[c.c_char_p,c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(Error)]
        e.exr_fixed_pages.argtypes=[c.c_void_p,c.POINTER(c.c_size_t)]
        e.exr_fixed_pages.restype=c.POINTER(Page)
        e.exr_fixed_render.argtypes=[c.c_void_p,c.c_size_t,c.c_double,c.c_void_p,c.POINTER(Bitmap),c.POINTER(Error)]
        e.exr_bitmap_free.argtypes=[c.POINTER(Bitmap)]
        e.exr_fixed_free.argtypes=[c.c_void_p]
        self.doc,self.error=c.c_void_p(),Error()
        self.check(e.exr_fixed_open(os.fsencode(str(pdf.resolve())),None,c.byref(self.doc),c.byref(self.error)))
        count=c.c_size_t()
        pages=e.exr_fixed_pages(self.doc,c.byref(count))
        self.scales=[]
        for i in range(count.value):
            g=pages[i].geometry
            box=g.bounds
            extent=box[3]-box[1] if g.rotation%180 else box[2]-box[0]
            self.scales.append(width/(extent*g.unit_scale))

    def check(self, status):
        if status:
            raise RuntimeError(self.error.message)

    def render(self, i, mode, compare):
        bitmap=Bitmap()
        if mode is not None:
            self.dll.probe_begin(mode)
        start=time.perf_counter_ns()
        self.check(self.dll.exr_fixed_render(self.doc,i,self.scales[i],None,c.byref(bitmap),c.byref(self.error)))
        ms=(time.perf_counter_ns()-start)/1e6
        try:
            result={'ms':ms}
            if mode is not None:
                trace=(c.c_double*16)()
                self.dll.probe_end(trace)
                result['trace']=list(trace)[:11]
            if compare:
                row=bitmap.width*4
                assert bitmap.channels==4
                result['size']=[bitmap.width,bitmap.height]
                data=(c.string_at(bitmap.pixels,row*bitmap.height) if row==bitmap.stride else
                      b''.join(c.string_at(bitmap.pixels+y*bitmap.stride,row) for y in range(bitmap.height)))
            else:
                data=None
            return result,data
        finally:
            self.dll.exr_bitmap_free(c.byref(bitmap))

def idle():
    while True:
        value=wait_idle(15,60)
        if value is not None:
            return value

def main():
    p=argparse.ArgumentParser()
    for option in ('a','b','pdf','out'):
        p.add_argument('--'+option,type=Path,required=True)
    p.add_argument('--width',type=int,default=1200)
    p.add_argument('--mode',type=int)
    p.add_argument('--rounds',type=int,default=2)
    args=p.parse_args()
    libs=[args.a,args.b]
    docs=[Document(lib,args.pdf,args.width) for lib in libs]
    pixels=args.mode is None
    report={'dll_sha256':[digest_file(lib) for lib in libs],'pdf_sha256':digest_file(args.pdf),
            'width':args.width,'mode':args.mode,'sweeps':[]}
    assert docs[0].scales==docs[1].scales
    for sweep in range(1 if pixels else args.rounds+1):
        gate=idle()
        rows=[]
        for i in range(len(docs[0].scales)):
            order=(1,0) if (i+sweep)%2 else (0,1)
            values=[None,None]
            for k in order:
                mode=None if pixels else (0 if k==0 else args.mode)
                values[k]=docs[k].render(i,mode,pixels)
            a,b=values
            result={'page':i+1,'order':''.join('AB'[j] for j in order),'A':a[0],'B':b[0]}
            if pixels:
                assert a[0]['size']==b[0]['size'] and a[0]['size'][0]==args.width
                result['pixels']=len(a[1])//4
                result['different']=0 if a[1]==b[1] else sum(a[1][k:k+4]!=b[1][k:k+4] for k in range(0,len(a[1]),4))
            rows.append(result)
        report['sweeps'].append({'idle_cpu_percent':gate,'pages':rows})
        args.out.write_text(json.dumps(report,separators=(',',':')))
        print(args.out.name,sweep,flush=True)
    for doc in docs:
        doc.dll.exr_fixed_free(doc.doc)

if __name__=='__main__':
    main()
