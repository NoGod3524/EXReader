# SPDX-License-Identifier: MIT
"""Approach B: per-pixel cost of one interpolated image versus working-set size."""
import ctypes as c,json,os,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'tools'))
from capture import DLL,competition,save
from bench_real_doc import digest_file,wait_idle
DIMS=(256,512,1024,2048,2896)      # destination 0.25 MiB ... 32 MiB
RATIOS=(50,100)                    # source side as % of destination side
def main():
    out=HERE/'synthetic.json'
    if out.exists():raise RuntimeError(f'Refusing to overwrite {out}')
    os.add_dll_directory(str(DLL.parent));e=c.CDLL(str(DLL))
    e.split_synthetic.argtypes=[c.c_uint,c.c_uint,c.c_uint,c.c_int,c.c_int,c.POINTER(c.c_double),c.POINTER(c.c_double)]
    rows=[];idle=[]
    for rnd in range(3):
        assert not competition(),'Competing workload before synthetic round'
        busy=wait_idle(15,45)
        if busy is None:raise RuntimeError('Idle gate closed; no sample accepted')
        idle.append(busy)
        cells=[(d,r,w,f) for d in DIMS for r in RATIOS for w in (0,1,2) for f in (0,1)]
        if rnd%2:cells.reverse()  # alternate order between rounds
        for d,r,w,f in cells:
            reps=max(3,int(64e6/(d*d)));best=c.c_double();total=c.c_double()
            s=e.split_synthetic(d,r,reps,w,f,c.byref(best),c.byref(total));assert s==0,(d,r,w,f,s)
            rows.append({'round':rnd,'dim':d,'ratio_percent':r,'which':['production','replica0','replica_all'][w],'flushed':f,'reps':reps,
                         'best_ns_per_pixel':best.value*1e6/(d*d),'mean_ns_per_pixel':total.value*1e6/(reps*d*d),
                         'dest_bytes':4*d*d,'source_bytes':4*(d*r//100)**2})
        assert not competition(),'Competing workload after synthetic round'
        print('round',rnd,flush=True)
    save(out,{'dll_sha256':digest_file(DLL),'idle_cpu_percent':idle,'rows':rows,'time':time.strftime('%Y-%m-%dT%H:%M:%S')})
if __name__=='__main__':main()
