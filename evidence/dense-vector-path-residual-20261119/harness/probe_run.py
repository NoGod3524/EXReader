# SPDX-License-Identifier: MIT
"""Run the rdtsc stage probe DLL over vector-heavy-100 pages 66-100 (or custom PDF/pages)."""
import ctypes as c, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import NativeDocument

dll = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
sweeps = int(sys.argv[3]) if len(sys.argv) > 3 else 5
pdf = Path(sys.argv[4]).resolve() if len(sys.argv) > 4 else (ROOT/'tests/fixtures/pdf-large/vector-heavy-100.pdf').resolve()
first = int(sys.argv[5]) if len(sys.argv) > 5 else 66
last = int(sys.argv[6]) if len(sys.argv) > 6 else 100

doc = NativeDocument(dll, pdf, 1200)
lib = doc.library
cyc = (c.c_ulonglong*64).in_dll(lib, 'exr_probe_cycles')
cnt = (c.c_ulonglong*64).in_dll(lib, 'exr_probe_counts')
lib.exr_probe_rdtsc.restype = c.c_ulonglong
t0, n0 = time.perf_counter(), lib.exr_probe_rdtsc()
time.sleep(1.0)
hz = (lib.exr_probe_rdtsc() - n0) / (time.perf_counter() - t0)

pages = list(range(first - 1, last))
for p in pages:
    doc.render(p, False, None)
for i in range(64):
    cyc[i] = cnt[i] = 0
wall = 0.0
for _ in range(sweeps):
    for p in pages:
        wall += doc.render(p, False, None)[0]

vnames = {
    0: 'alloc+bucket', 1: 'active update', 2: 'coverage clear', 3: 'edge tests',
    4: 'crossing sort', 5: 'span collect', 6: 'interior_runs', 7: 'span accumulate',
    8: 'stable check', 9: 'mask/rgba touched', 10: 'rgba runs', 11: 'free'
}
cnames = {
    32: 'flatten fill', 33: 'stroke flatten', 34: 'stroke dash', 35: 'stroke outline',
    36: 'new_mask x2', 37: 'mask_fill fill', 38: 'mask_fill stroke',
    39: 'compound composite', 40: 'unref', 41: 'standalone fill', 42: 'standalone stroke',
    43: 'clip_path'
}
ms = lambda v: v / hz * 1000.0 / sweeps
res = {
    'pdf': str(pdf), 'pages': [first, last], 'tsc_hz': hz, 'sweeps': sweeps,
    'wall_ms_per_sweep': wall / sweeps,
    'mask': {nm: ms(cyc[k]) for k, nm in vnames.items()},
    'rgba': {nm: ms(cyc[k+16]) for k, nm in vnames.items()},
    'canvas': {nm: ms(cyc[k]) for k, nm in cnames.items()},
    'counts': {}
}
for b, tag in ((0, 'mask'), (16, 'rgba')):
    at = cnt[b+3] / sweeps
    cr = cnt[b+4] / sweeps
    tp = cnt[b+5] / sweeps
    nz = cnt[b+6] / sweeps
    res['counts'][tag] = {
        'calls': cnt[b]/sweeps, 'rows': cnt[b+1]/sweeps, 'edges': cnt[b+2]/sweeps,
        'active_tests': at, 'crossings': cr,
        'edge_hit_rate_pct': (cr / at * 100.0) if at else 0.0,
        'touched_pixels': tp, 'nonzero_cov_pixels': nz,
        'touched_nonzero_pct': (nz / tp * 100.0) if tp else 0.0,
        'run_pixels': cnt[b+7]/sweeps, 'full_cov_nonrun_pixels': cnt[b+8]/sweeps,
    }
res['counts']['compounds'] = cnt[32]/sweeps
res['counts']['standalone_strokes'] = cnt[40]/sweeps
res['counts']['compound_pixels'] = {
    'bbox': cnt[48]/sweeps, 'solid': cnt[49]/sweeps,
    'aa_slow': cnt[50]/sweeps, 'empty_skip': cnt[51]/sweeps
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res, indent=1) + '\n')
print(json.dumps(res, indent=1))
doc.close()
