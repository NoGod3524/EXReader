#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Same-session PDF render comparator. Operator must own bench-lock throughout.
--pdfjs-root is the installed pdfjs-dist 3.11.174 package; node-canvas required.
Use at least 11 rounds; each six-page block contains all six orderings.
"""
import argparse
import ctypes as c
from contextlib import ExitStack, contextmanager
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

from bench_real_doc import (Bitmap, Error, Page, cpu_busy_percent, cpu_times,
                            digest_file, hash_active_rgba, process_memory_bytes)


def identity(a, a0):
    if a.samefile(a0):
        raise ValueError("A0 must be a distinct byte copy, not an alias")
    digest = digest_file(a)
    if digest_file(a0) != digest:
        raise ValueError("A0 is not byte-identical to A")
    return digest


def schedule(rounds, reverse=False):
    orders = [('A','A0','P'), ('P','A0','A'), ('A0','P','A'),
              ('A','P','A0'), ('P','A','A0'), ('A0','A','P')]
    return [orders[i % 6][::-1] if reverse else orders[i % 6] for i in range(rounds)]


def page_plan(round_index, page_count, reverse_start=False):
    """Offset each round pair; mirror the second round at every page slot."""
    orders = schedule(6)
    mirror = bool(round_index % 2) != reverse_start
    for page in range(1,page_count+1):
        order = orders[(round_index//2 + page-1) % 6]
        yield page, (order[::-1] if mirror else order)


def dispatch_round(round_index, page_count, reverse_start, render, rows):
    for page, order in page_plan(round_index, page_count, reverse_start):
        for arm in order:
            r = render(arm,page)
            rows.append(dict(r, arm=arm,page=page,round=round_index+1))


def summary(rows):
    times = sorted(r['ns'] for r in rows)
    worst = max(rows, key=lambda r: r['ns'])
    return dict(n=len(rows), p50_ns=statistics.median(times),
                p95_ns=times[math.ceil(len(times)*0.95)-1],
                worst_ns=worst['ns'], worst_page=worst['page'], worst_round=worst['round'],
                throughput_pages_s=len(rows)*1e9/sum(times))


class Native:
    def __init__(self, lib):
        self.e = e = c.CDLL(str(lib))
        e.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
        e.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
        e.exr_fixed_pages.restype = c.POINTER(Page)
        e.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p,
                                       c.POINTER(Bitmap), c.POINTER(Error)]
        e.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
        e.exr_fixed_free.argtypes = [c.c_void_p]

    @contextmanager
    def document(self, path, width):
        doc, err, n = c.c_void_p(), Error(), c.c_size_t()
        if self.e.exr_fixed_open(str(path).encode('utf-8'), None, c.byref(doc), c.byref(err)):
            raise RuntimeError(repr(err.message))
        try:
            pages = self.e.exr_fixed_pages(doc, c.byref(n))
            if not pages or not n.value:
                raise ValueError("empty document")
            def render(page):
                g = pages[page-1].geometry
                b = g.bounds
                w = b[3]-b[1] if g.rotation % 180 else b[2]-b[0]
                scale = width/(w*g.unit_scale)
                bm = Bitmap()
                start = time.perf_counter_ns()
                status = self.e.exr_fixed_render(doc, page-1, scale, None, c.byref(bm), c.byref(err))
                ns = time.perf_counter_ns()-start
                try:
                    if status:
                        raise RuntimeError(repr(err.message))
                    if (not bm.pixels or bm.width != width or bm.height < 1 or
                            bm.channels != 4 or bm.stride < width*4):
                        raise ValueError("invalid native bitmap")
                    h, _ = hash_active_rgba(bm)
                    rss, peak = process_memory_bytes()
                    return dict(ns=ns, dimensions=[bm.width,bm.height], sha256=h,
                                rss_bytes=rss, process_peak_bytes=peak)
                finally:
                    self.e.exr_bitmap_free(c.byref(bm))
            yield n.value, render
        finally:
            self.e.exr_fixed_free(doc)


@contextmanager
def worker(root):
    script = Path(__file__).with_name('render_vs_pdfjs_worker.cjs')
    p = subprocess.Popen(['node',str(script),str(root)], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True, encoding='utf-8')
    def request(**msg):
        p.stdin.write(json.dumps(msg)+'\n')
        p.stdin.flush()
        line = p.stdout.readline()
        if not line:
            raise RuntimeError(f"Node worker terminated ({p.poll()}); see stderr")
        res = json.loads(line)
        if 'error' in res:
            raise RuntimeError(res['error'])
        return res
    try:
        yield request
    finally:
        try:
            p.stdin.close()
            p.wait(timeout=10)
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            p.stdout.close()


def capture(args, report):
    with ExitStack() as session:
        if os.name == 'nt':
            for d in {args.library.parent, args.null_library.parent}:
                session.enter_context(os.add_dll_directory(str(d)))
        native = {'A': Native(args.library), 'A0': Native(args.null_library)}
        if native['A'].e._handle == native['A0'].e._handle:
            raise ValueError("DLL loader aliased the control; give the copy a unique basename")
        js = session.enter_context(worker(args.pdfjs_root))
        for name, path in args.cases.items():
            case = report['cases'][name] = dict(path=str(path), sha256=digest_file(path), rounds=[])
            with ExitStack() as docs:
                operands = {k: docs.enter_context(v.document(path,args.width)) for k,v in native.items()}
                meta = case['worker'] = js(op='open',file=str(path))
                n = meta['pages']
                if not n or any(count != n for count,_ in operands.values()):
                    raise ValueError("page count mismatch")
                case['pages'] = n
                def render(arm,page):
                    return (js(op='render',page=page,width=args.width) if arm == 'P'
                            else operands[arm][1](page))
                for i in range(1,args.rounds+1):
                    before = cpu_times()
                    time.sleep(0.2)
                    pre = cpu_busy_percent(before,cpu_times())
                    block = dict(round=i,pre_cpu_percent=pre,rows=[])
                    case['rounds'].append(block)
                    dispatch_round(i-1,n,args.reverse_start,render,block['rows'])
                    signatures = {r['page']: (r['dimensions'],r['sha256'])
                                  for r in block['rows'] if r['arm']=='A'}
                    if any((r['dimensions'],r['sha256']) != signatures[r['page']]
                           for r in block['rows'] if r['arm']=='A0'):
                        raise ValueError(f"null bitmap mismatch: {name} round {i}")
                rows = [r for b in case['rounds'] for r in b['rows']]
                dimensions = {}
                for r in rows:
                    dimensions.setdefault((r['round'],r['page']),set()).add(tuple(r['dimensions']))
                case['matched_dimensions'] = all(len(d)==1 for d in dimensions.values())
                if not case['matched_dimensions']:
                    raise ValueError(f"canvas dimensions differ: {name}; raw rows retained")
                case['summary'] = {arm:summary([r for r in rows if r['arm']==arm])
                                   for arm in ('A','A0','P')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('library','null-library','pdfjs-root','out'):
        p.add_argument('--'+key, type=lambda s:Path(s).resolve(),required=True)
    p.add_argument('--case',action='append',required=True)
    p.add_argument('--width',type=int,required=True)
    p.add_argument('--rounds',type=int,required=True)
    p.add_argument('--reverse-start',action='store_true')
    args = p.parse_args()
    if args.width < 1 or args.rounds < 11:
        p.error('positive width and at least 11 rounds required')
    args.cases = {}
    for item in args.case:
        k, sep, v = item.partition('=')
        if not k or not sep or not v or k in args.cases:
            p.error('each --case needs a unique name=pdf')
        args.cases[k] = Path(v).resolve(strict=True)
    report = dict(schema=1, cases={}, width=args.width, rounds=args.rounds, supervisor_pid=os.getpid(),
                  python=sys.version, platform=sys.platform, library=str(args.library),
                  null_library=str(args.null_library), library_and_copy_sha256=identity(args.library,args.null_library),
                  pdfjs_root=str(args.pdfjs_root), status='incomplete', definitions={
                      'clock':'ns per page: native render call; Node page.render call through render promise',
                      'excluded':'open, page lookup, viewport, Node canvas allocation, IPC, RGBA hashing/readback and cleanup',
                      'state':'one open document per case per arm; all rounds reported including first pass',
                      'summary':'per case/arm across all page-round samples; median, nearest-rank p95, max; pages / summed render seconds',
                      'rss':'process scope, sampled after hashing; native A/A0 share supervisor, P is persistent Node; non-Windows native helper may return peak',
                      'pre_cpu':'system busy percent sampled for 0.2s before each complete round; never filtered',
                      'pixels':'SHA256 active RGBA; null identity enforced; cross-engine hashes are descriptive only',
                      'lock':'operator owns bench-lock externally; tool does not acquire or release it'})
    try:
        capture(args,report)
        report['status']='complete'
    except BaseException as err:
        report['error']=repr(err)
        raise
    finally:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    main()
