#!/usr/bin/env python3
"""Paired A/B render and open probe for two EXReader builds in one process.

Both DLLs are loaded side by side. For every page of every round the call order
alternates (A,B then B,A), so CPU frequency and background load hit both builds
equally. Each round waits for the idle gate first. Reports per-build p50/p95 over
all measured page renders, per-round p50 spread, and paired open p50.

  python -X utf8 paired_ab.py --a base.dll --b new.dll --input deck.pdf --pages 15 \
      --width 1200 --rounds 12 --opens 400 --out result.json
"""
import argparse, ctypes as c, hashlib, json, os, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / 'tools'))
from benchmark_pdf_rect import Page  # noqa: E402
from benchmark_pdf_blend import Bitmap, Error  # noqa: E402
sys.path.insert(0, r'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\projects\exreader-handoff\tools')
from bench_engine import cpu_busy_percent  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    os.add_dll_directory(str(Path(path).resolve().parent))
    e = c.CDLL(str(Path(path).resolve()))
    e.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    e.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    e.exr_fixed_pages.restype = c.POINTER(Page)
    e.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
    e.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    e.exr_fixed_free.argtypes = [c.c_void_p]
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', required=True); ap.add_argument('--b', required=True)
    ap.add_argument('--input', required=True); ap.add_argument('--pages', type=int, required=True)
    ap.add_argument('--width', type=float, required=True); ap.add_argument('--rounds', type=int, default=12)
    ap.add_argument('--opens', type=int, default=400); ap.add_argument('--idle', type=float, default=15.0)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    libs = {'a': load(args.a), 'b': load(args.b)}
    err = Error(); docs = {}; scales = None
    for k, e in libs.items():
        d = c.c_void_p(); assert e.exr_fixed_open(args.input.encode(), None, c.byref(d), c.byref(err)) == 0
        n = c.c_size_t(); pg = e.exr_fixed_pages(d, c.byref(n)); assert n.value == args.pages, n.value
        s = []
        for i in range(n.value):
            g = pg[i].geometry; bd = g.bounds
            nw = bd[3] - bd[1] if g.rotation % 180 else bd[2] - bd[0]
            s.append(args.width / (nw * g.unit_scale))
        scales = s; docs[k] = d

    def render(k, i):
        bm = Bitmap(); t = time.perf_counter_ns()
        st = libs[k].exr_fixed_render(docs[k], i, scales[i], None, c.byref(bm), c.byref(err))
        el = (time.perf_counter_ns() - t) / 1e6
        assert st == 0, err.message
        libs[k].exr_bitmap_free(c.byref(bm)); return el

    for i in range(len(scales)):  # warmup round
        render('a', i); render('b', i)
    samples = {'a': [], 'b': []}; rounds = {'a': [], 'b': []}; idle = []
    for r in range(args.rounds):
        busy = cpu_busy_percent(); waited = 0
        while busy > args.idle and waited < 60:
            time.sleep(1.0); waited += 1; busy = cpu_busy_percent()
        idle.append(round(busy, 2)); row = {'a': [], 'b': []}
        for i in range(len(scales)):
            order = ('a', 'b') if (i + r) % 2 == 0 else ('b', 'a')
            for k in order:
                row[k].append(render(k, i))
        for k in row:
            samples[k] += row[k]; rounds[k].append(statistics.median(row[k]))
    opens = {'a': [], 'b': []}
    for j in range(args.opens):
        for k in (('a', 'b') if j % 2 == 0 else ('b', 'a')):
            d = c.c_void_p(); t = time.perf_counter_ns()
            assert libs[k].exr_fixed_open(args.input.encode(), None, c.byref(d), c.byref(err)) == 0
            el = (time.perf_counter_ns() - t) / 1e6; libs[k].exr_fixed_free(d)
            if j >= 20: opens[k].append(el)

    def summary(k):
        s = sorted(samples[k]); rp = sorted(rounds[k])
        return {'path': str(Path(getattr(args, k)).resolve()), 'sha256': sha(getattr(args, k)),
                'p50_ms': round(statistics.median(s), 4), 'p95_ms': round(s[int(0.95 * len(s)) - 1], 4),
                'round_p50_min_ms': round(rp[0], 4), 'round_p50_max_ms': round(rp[-1], 4),
                'round_spread_percent': round(100 * (rp[-1] - rp[0]) / rp[0], 1),
                'open_p50_ms': round(statistics.median(opens[k]), 4), 'samples': len(s)}
    res = {'input': args.input, 'input_sha256': sha(args.input), 'width': args.width, 'rounds': args.rounds,
           'pages': args.pages, 'idle_cpu_percent_per_round': idle, 'a': summary('a'), 'b': summary('b')}
    res['render_change_percent'] = round(100 * (res['b']['p50_ms'] - res['a']['p50_ms']) / res['a']['p50_ms'], 2)
    res['open_change_percent'] = round(100 * (res['b']['open_p50_ms'] - res['a']['open_p50_ms']) / res['a']['open_p50_ms'], 2)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2) + '\n', encoding='utf-8')
    print('%s @%d: A %.3f  B %.3f ms (%+.2f%%)  spread %.1f%%/%.1f%%  open %.4f/%.4f (%+.2f%%)  idle %s..%s' % (
        Path(args.input).name, args.width, res['a']['p50_ms'], res['b']['p50_ms'], res['render_change_percent'],
        res['a']['round_spread_percent'], res['b']['round_spread_percent'], res['a']['open_p50_ms'],
        res['b']['open_p50_ms'], res['open_change_percent'], min(idle), max(idle)))


if __name__ == '__main__':
    main()
