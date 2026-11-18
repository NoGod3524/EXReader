# SPDX-License-Identifier: MIT
"""Per-page class ablation on the six named gradient + soft-mask slides at 1200 px.

One process, one open document, the unchanged production DLL. The production
EXR_ATTRIBUTION_SKIP switch is read by getenv on every event, so it is toggled
in-process between renders. Each round passes the fail-closed 15% idle gate,
then renders every (page, mode) pair; mode order rotates and reverses by round
so each mode occupies every position. Savings are medians of within-round
paired differences full - disabled.

  python -X utf8 evidence/gradient-tail-20261118/ablate.py --library build/perf/libexreader.dll \
      --out evidence/gradient-tail-20261118/ablation.json
"""
import argparse
import ctypes as c
import json
import os
import statistics as st
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_real_doc import Bitmap, Error, Page, digest_file, hash_active_rgba, wait_idle  # noqa: E402

PAGES = (2, 11, 12, 14, 16, 17)
MODES = ('full', 'shading', 'softmask', 'path', 'glyph', 'image', 'group')
WIDTH = 1200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--library', type=Path, required=True)
    ap.add_argument('--pdf', type=Path, default=ROOT / 'tests/fixtures/pdf-large/real-mixed-120.pdf')
    ap.add_argument('--pages', type=int, nargs='+', default=list(PAGES))
    ap.add_argument('--modes', nargs='+', default=list(MODES))
    ap.add_argument('--rounds', type=int, default=15)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    os.environ.pop('EXR_ATTRIBUTION_SKIP', None)
    os.add_dll_directory(str(args.library.resolve().parent))
    e = c.CDLL(str(args.library.resolve()))
    e.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    e.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    e.exr_fixed_pages.restype = c.POINTER(Page)
    e.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
    e.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    e.exr_fixed_free.argtypes = [c.c_void_p]
    err, doc = Error(), c.c_void_p()

    def check(status):
        if status:
            raise RuntimeError(f'{status}: {err.message.decode("utf-8", "replace")}')

    check(e.exr_fixed_open(str(args.pdf).encode(), None, c.byref(doc), c.byref(err)))
    n = c.c_size_t()
    pages = e.exr_fixed_pages(doc, c.byref(n))
    scales = []
    for i in range(n.value):
        g = pages[i].geometry
        b = g.bounds
        w = b[3] - b[1] if g.rotation % 180 else b[2] - b[0]
        scales.append(WIDTH / (w * g.unit_scale))

    def render(page, mode, digest=False):
        if mode == 'full':
            os.environ.pop('EXR_ATTRIBUTION_SKIP', None)
        else:
            os.environ['EXR_ATTRIBUTION_SKIP'] = mode
        bm = Bitmap()
        t = time.perf_counter_ns()
        status = e.exr_fixed_render(doc, page - 1, scales[page - 1], None, c.byref(bm), c.byref(err))
        ms = (time.perf_counter_ns() - t) / 1e6
        try:
            check(status)
            assert bm.width == WIDTH and bm.channels == 4
            return ms, (hash_active_rgba(bm)[0] if digest else None)
        finally:
            e.exr_bitmap_free(c.byref(bm))

    # Warm every page once (decoded-image and font caches reach steady state), then hash each mode.
    for p in range(1, n.value + 1):
        render(p, 'full')
    hashes = {m: {p: render(p, m, True)[1] for p in args.pages} for m in args.modes}
    os.environ.pop('EXR_ATTRIBUTION_SKIP', None)
    samples = {m: {p: [] for p in args.pages} for m in args.modes}
    gates = []
    for r in range(args.rounds):
        busy = wait_idle(15, 900)
        if busy is None:
            raise SystemExit('CPU idle gate timed out at 15% (fail closed); rerun.')
        gates.append(round(busy, 2))
        k = r % len(args.modes)
        order = args.modes[k:] + args.modes[:k]
        if r % 2:
            order = order[::-1]
        for p in args.pages:
            for m in order:
                samples[m][p].append(render(p, m)[0])
        print(f'round {r + 1}/{args.rounds} gate {busy:.2f}%', flush=True)
    os.environ.pop('EXR_ATTRIBUTION_SKIP', None)
    e.exr_fixed_free(doc)

    result = {'library': str(args.library.resolve()), 'library_sha256': digest_file(args.library),
              'pdf_sha256': digest_file(args.pdf), 'width': WIDTH, 'rounds': args.rounds,
              'gates_percent': gates, 'pages': {}}
    for p in args.pages:
        full = samples['full'][p]
        row = {}
        for m in args.modes:
            s = samples[m][p]
            row[m] = {'p50_ms': round(st.median(s), 3),
                      'saving_ms': round(st.median(f - x for f, x in zip(full, s)), 3),
                      'changed_pixels': hashes[m][p] != hashes['full'][p],
                      'rgba_sha256': hashes[m][p], 'samples_ms': [round(x, 4) for x in s]}
        result['pages'][str(p)] = row
    args.out.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(f'{"page":>5}' + ''.join(f'{m:>18}' for m in args.modes))
    for p in args.pages:
        row = result['pages'][str(p)]
        print(f'{p:>5}' + ''.join(f'{row[m]["p50_ms"]:>9.2f}/{row[m]["saving_ms"]:>+7.2f}{"*" if row[m]["changed_pixels"] else " "}'
                                  for m in args.modes))


if __name__ == '__main__':
    main()
