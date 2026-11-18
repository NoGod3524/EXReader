# SPDX-License-Identifier: MIT
"""Per-call knock-out arms; every restore, flush and copy is outside the timed calls."""
import argparse,ctypes as c,gzip,json,os,platform,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
sys.path.insert(0,str(ROOT/'tools'))
from bench_real_doc import Bitmap,Error,Page,digest_file,hash_active_rgba,wait_idle
DLL=ROOT/'build/rgb-sink-arithmetic/rgb-sink-arithmetic.dll'
def save(p,x):
    data=(json.dumps(x,separators=(',',':'))+'\n').encode()
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix=='.gz' else data)
def competition():
    script="Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|node|gcc|cc1|ninja|cmake)\\.exe$' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    p=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,check=True)
    rows=json.loads(p.stdout or '[]');rows=[rows] if isinstance(rows,dict) else rows
    return [r for r in rows if r['ProcessId']!=os.getpid() and 'rgb-sink-arithmetic-20261118' not in (r['CommandLine'] or '') and any(w in (r['CommandLine'] or '').lower() for w in ('bench','capture.py','pdfjs_ab','cc1','ninja','cmake'))]
class Document:
    def __init__(self,dll,pdf,width):
        self.dll_dir=os.add_dll_directory(str(dll.parent));self.e=c.CDLL(str(dll));self.error=Error();self.ptr=c.c_void_p()
        for n,a in {'exr_fixed_open':[c.c_char_p,c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(Error)],'exr_fixed_pages':[c.c_void_p,c.POINTER(c.c_size_t)],'exr_fixed_render':[c.c_void_p,c.c_size_t,c.c_double,c.c_void_p,c.POINTER(Bitmap),c.POINTER(Error)],'exr_bitmap_free':[c.POINTER(Bitmap)],'exr_fixed_free':[c.c_void_p]}.items():getattr(self.e,n).argtypes=a
        self.e.exr_fixed_pages.restype=c.POINTER(Page)
        self.check(self.e.exr_fixed_open(str(pdf).encode(),None,c.byref(self.ptr),c.byref(self.error)))
        count=c.c_size_t();pages=self.e.exr_fixed_pages(self.ptr,c.byref(count));self.scales=[]
        for i in range(count.value):
            g=pages[i].geometry;b=g.bounds;w=b[3]-b[1] if g.rotation%180 else b[2]-b[0];self.scales.append(width/(w*g.unit_scale))
    def check(self,s):
        if s:raise RuntimeError((s,self.error.message))
    def render(self,i):
        b=Bitmap();self.check(self.e.exr_fixed_render(self.ptr,i,self.scales[i],None,c.byref(b),c.byref(self.error)))
        try:return hash_active_rgba(b)
        finally:self.e.exr_bitmap_free(c.byref(b))
    def close(self):self.e.exr_fixed_free(self.ptr)
def child(args):
    gate=(lambda:[]) if args.pilot else competition
    assert not gate(),'Competing workload before capture'
    pdf=ROOT/f'tests/fixtures/pdf-large/{args.case}.pdf'
    base=Path(args.base).resolve();doc=Document(DLL,pdf,args.width);control=Document(base,pdf,args.width)
    doc.e.split_begin.argtypes=[c.c_int,c.c_int];doc.e.split_read.argtypes=[c.POINTER(c.c_double)];n=doc.e.split_count()
    pages=range(len(doc.scales)) if not args.pages else range(min(args.pages,len(doc.scales)))
    data={'pilot':args.pilot,'case':args.case,'width':args.width,'rep':args.rep,'metric_count':n,'pdf_sha256':digest_file(pdf),'dll_sha256':digest_file(DLL),'base_sha256':digest_file(base),'rounds':[],'idle':[]}
    expected=[]
    try:
        for sweep in range(args.runs+1):
            assert not gate(),'Competing workload before sweep'
            busy=-1 if args.pilot else wait_idle(15,45)
            if busy is None:raise RuntimeError('Idle gate closed; no sample accepted')
            data['idle'].append(busy);rows=[]
            for i in pages:
                if sweep==0:expected.append(control.render(i))
                rotate=7*sweep+3*args.rep+i;doc.e.split_begin(1,rotate)
                h,pixels=doc.render(i);assert (h,pixels)==expected[i],f'Pixel mismatch {i+1}'
                v=(c.c_double*n)();doc.e.split_read(v);rows.append({'page':i+1,'rotate':rotate,'sha256':h,'pixels':pixels,'m':list(v)})
            data['rounds'].append(rows);save(args.out.with_suffix('.partial.json'),data)
            assert not gate(),'Competing workload after sweep; partial file excluded'
            print(args.case,args.width,args.rep,sweep,flush=True)
    finally:doc.close();control.close()
    save(args.out,data);args.out.with_suffix('.partial.json').unlink()
def run(args):
    for key in ('EXR_BUFFER_POOL','EXR_PDF_IMAGE_PROFILE','EXR_ATTRIBUTION_SKIP','EXR_PDF_IMAGE_CACHE_BYTES'):os.environ.pop(key,None)
    raw=HERE/args.raw;raw.mkdir(exist_ok=True)
    meta={'platform':platform.platform(),'cpu':platform.processor(),'power':subprocess.check_output(['powercfg','/getactivescheme'],text=True),'runs':args.runs,'repeat':args.repeat,'pages':args.pages,'base':str(Path(args.base).resolve())}
    save(raw/'environment.json',meta)
    attempts=[]
    for case in args.cases.split(','):
        for rep in range(args.repeat):
            for width in ((600,1200) if rep%2==0 else (1200,600)):
                out=raw/f'{case}-{width}-r{rep}.json.gz'
                if out.exists():raise RuntimeError(f'Refusing to overwrite {out}')
                for attempt in range(1,args.attempts+1):
                    while competition():time.sleep(60)
                    code=subprocess.run([sys.executable,'-X','utf8',str(__file__),'child','--base',args.base,'--case',case,'--width',str(width),'--rep',str(rep),'--runs',str(args.runs),'--pages',str(args.pages),'--out',str(out)]).returncode
                    partial=out.with_suffix('.partial.json')
                    # A rejected child is never analyzed; its partial file is discarded and the child rerun from scratch.
                    attempts.append({'child':out.name,'attempt':attempt,'returncode':code,'accepted':code==0 and out.exists(),'time':time.strftime('%Y-%m-%dT%H:%M:%S')})
                    if partial.exists():partial.unlink()
                    save(raw/'attempts.json',attempts)
                    if code==0:break
                else:raise RuntimeError(f'{out.name}: no accepted attempt')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['run','child']);p.add_argument('--base',default='C:/Users/Oscar/Documents/Codex/EXReader-p95b/build/perf/libexreader.dll')
    p.add_argument('--runs',type=int,default=3);p.add_argument('--repeat',type=int,default=3);p.add_argument('--pages',type=int,default=0);p.add_argument('--raw',default='raw');p.add_argument('--pilot',action='store_true',help='no gates; never used as evidence')
    p.add_argument('--cases',default='real-mixed-120,image-heavy-100');p.add_argument('--attempts',type=int,default=6)
    p.add_argument('--case');p.add_argument('--width',type=int);p.add_argument('--rep',type=int);p.add_argument('--out',type=Path);a=p.parse_args();child(a) if a.mode=='child' else run(a)
