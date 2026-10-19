#!/usr/bin/env python3
"""Fresh-process PDF open/repaint measurements through the installed C ABI.

The process high-water mark includes this Python/ctypes host. Compare identical
hosts and inputs; small one-page fixtures are compositor probes, not book tests.
"""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


class Error(c.Structure):
    _fields_=[('code',c.c_int),('message',c.c_char*256)]


class Bitmap(c.Structure):
    _fields_=[('width',c.c_uint32),('height',c.c_uint32),('stride',c.c_uint32),
              ('pixels',c.c_void_p),('channels',c.c_uint32)]


def peak_rss():
    if sys.platform=='win32':
        from ctypes import wintypes as w
        class Counters(c.Structure):
            _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(n,c.c_size_t) for n in
                ('peak','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
        kernel=c.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=w.HANDLE
        kernel.K32GetProcessMemoryInfo.argtypes=[w.HANDLE,c.POINTER(Counters),w.DWORD]
        counters=Counters();counters.cb=c.sizeof(counters)
        if not kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(),c.byref(counters),counters.cb):
            raise c.WinError(c.get_last_error())
        return counters.peak
    import resource
    value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform=='darwin' else value*1024


def measure(library,book,scale,repaints=8):
    directory=os.add_dll_directory(str(library.parent)) if sys.platform=='win32' else None
    engine=c.CDLL(str(library))
    engine.exr_fixed_open.argtypes=[c.c_char_p,c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(Error)]
    engine.exr_fixed_render.argtypes=[c.c_void_p,c.c_size_t,c.c_double,c.c_void_p,c.POINTER(Bitmap),c.POINTER(Error)]
    engine.exr_fixed_free.argtypes=[c.c_void_p];engine.exr_fixed_free.restype=None
    engine.exr_bitmap_free.argtypes=[c.POINTER(Bitmap)];engine.exr_bitmap_free.restype=None
    engine.exr_version.restype=c.c_char_p
    document=c.c_void_p();error=Error();baseline=peak_rss();start=time.perf_counter_ns()
    status=engine.exr_fixed_open(str(book).encode('utf-8'),None,c.byref(document),c.byref(error))
    opened=time.perf_counter_ns()
    if status:raise RuntimeError(f'{status}: {error.message.decode("utf-8")}')
    timings=[];signature=None
    try:
        for _ in range(repaints+1):
            bitmap=Bitmap();before=time.perf_counter_ns()
            status=engine.exr_fixed_render(document,0,scale,None,c.byref(bitmap),c.byref(error))
            elapsed=(time.perf_counter_ns()-before)/1e6
            try:
                if status:raise RuntimeError(f'{status}: {error.message.decode("utf-8")}')
                assert bitmap.pixels and bitmap.width and bitmap.height and bitmap.channels==4
                digest=hashlib.sha256(c.string_at(bitmap.pixels,bitmap.stride*bitmap.height)).hexdigest()
                if signature is not None:assert signature==digest
                signature=digest;timings.append(elapsed);dimensions=[bitmap.width,bitmap.height]
            finally:engine.exr_bitmap_free(c.byref(bitmap))
        peak=peak_rss()
    finally:engine.exr_fixed_free(document)
    if directory:directory.close()
    ordered=sorted(timings[1:])
    return {'engine_version':engine.exr_version().decode(), 'open_ms':(opened-start)/1e6,
        'first_render_ms':timings[0],'repaint_ms_samples':timings[1:],
        'repaint_p50_ms':ordered[math.ceil(len(ordered)*.5)-1],
        'repaint_p95_ms':ordered[math.ceil(len(ordered)*.95)-1],
        'baseline_peak_rss_bytes':baseline,'peak_rss_bytes':peak,
        'incremental_peak_rss_bytes':peak-baseline,'rgba_sha256':signature,'dimensions':dimensions}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library',type=Path);parser.add_argument('fixtures',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--runs',type=int,default=3);parser.add_argument('--scale',type=float,default=4)
    parser.add_argument('--repaints',type=int,default=8)
    parser.add_argument('--case',action='append',choices=('flat','primitives','state','groups','compound','ap-groups','nonisolated','ap-nonisolated'));parser.add_argument('--child',metavar='CASE');args=parser.parse_args()
    if not 1<=args.runs<=20 or not .25<=args.scale<=4:parser.error('runs: 1..20, scale: .25..4')
    if not 8<=args.repaints<=1000:parser.error('repaints: 8..1000')
    args.library=args.library.resolve();args.fixtures=args.fixtures.resolve()
    if args.child:
        print(json.dumps(measure(args.library,args.fixtures/args.child,args.scale,args.repaints)));return
    report={'platform':platform.platform(),'host':sys.version,'library_sha256':hashlib.sha256(args.library.read_bytes()).hexdigest(),
        'library_bytes':args.library.stat().st_size,'scale':args.scale,'runs':args.runs,
        'scope':'One-page original PDF probes; fresh Python/ctypes processes; RSS includes host; disk cache/background load uncontrolled; repeated repaint, not page navigation.', 'cases':{}}
    args.output.mkdir(parents=True,exist_ok=True)
    for name in (args.case or ('flat','primitives','state','groups','compound','ap-groups','nonisolated','ap-nonisolated')):
        records=[]
        for run in range(args.runs):
            result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(args.library),str(args.fixtures),str(args.output),
                '--scale',str(args.scale),'--repaints',str(args.repaints),'--child',name+'.pdf'],capture_output=True,text=True,timeout=120)
            if result.returncode:raise RuntimeError(result.stderr)
            record=json.loads(result.stdout);records.append(record)
            (args.output/f'{name}-{run+1}.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        assert len({r['rgba_sha256'] for r in records})==1
        report['cases'][name]={key:statistics.median(r[key] for r in records) for key in
            ('open_ms','first_render_ms','repaint_p50_ms','repaint_p95_ms','peak_rss_bytes','incremental_peak_rss_bytes')}
        report['cases'][name]['pdf_sha256']=hashlib.sha256((args.fixtures/(name+'.pdf')).read_bytes()).hexdigest()
        print(name,report['cases'][name],flush=True)
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
