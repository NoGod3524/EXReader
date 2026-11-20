# SPDX-License-Identifier: MIT
"""Stage split of real-mixed p1-21 at 1200 px with the rdtsc probe DLL.

Base and probe DLLs share one process. Page i of round r renders base/probe
when (r+i) is even and probe/base otherwise; round 0 is an unrecorded warm-up
that also compares active RGBA bytes. Probe counters are zeroed after the
warm-up, so they cover exactly the recorded probe renders. CPU busy is
sampled before each round and recorded, never gated. The bench lock is
heartbeated every round.
"""
import argparse, ctypes as c, json, statistics as st, subprocess, sys, time
from pathlib import Path
import psutil
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import NativeDocument, digest_file
LOCK = r'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1'

ap = argparse.ArgumentParser()
ap.add_argument('base', type=Path); ap.add_argument('probe', type=Path); ap.add_argument('out', type=Path)
ap.add_argument('--rounds', type=int, default=11); ap.add_argument('--holder', default='opus-C')
args = ap.parse_args()
pdf = (ROOT/'tests/fixtures/pdf-large/real-mixed-120.pdf').resolve()
docs = {'base': NativeDocument(args.base.resolve(), pdf, 1200), 'probe': NativeDocument(args.probe.resolve(), pdf, 1200)}
lib = docs['probe'].library
cyc = (c.c_ulonglong*96).in_dll(lib, 'exr_probe_cycles'); cnt = (c.c_ulonglong*96).in_dll(lib, 'exr_probe_counts')
lib.exr_probe_rdtsc.restype = c.c_ulonglong
t0, n0 = time.perf_counter(), lib.exr_probe_rdtsc(); time.sleep(1.0); hz = (lib.exr_probe_rdtsc()-n0)/(time.perf_counter()-t0)
pages = list(range(21))
tot_rounds, mismatched = [], []
for r in range(args.rounds+1):
    subprocess.run(['pwsh', '-NoProfile', '-File', LOCK, '-Holder', args.holder, '-Heartbeat'], check=True, capture_output=True)
    cpu = psutil.cpu_percent(interval=1.0)
    tot = {'base': 0.0, 'probe': 0.0}
    for i, p in enumerate(pages):
        order = ('base', 'probe') if (r+i) % 2 == 0 else ('probe', 'base')
        got = {}
        for t in order:
            ms, px = docs[t].render(p, r == 0, None)
            got[t] = px; tot[t] += ms
        if r == 0 and got['base'] != got['probe']:
            mismatched.append(p+1)
    if r == 0:
        for k in range(96): cyc[k] = cnt[k] = 0
        print(f'warm-up cpu={cpu:.1f}% mismatched={mismatched}', flush=True)
        continue
    tot_rounds.append({'round': r, 'cpu_busy_pre_percent': cpu, 'base_ms': tot['base'], 'probe_ms': tot['probe'],
                       'probe_over_base': tot['probe']/tot['base']})
    print(f"round {r} cpu={cpu:.1f}% base={tot['base']:.2f} probe={tot['probe']:.2f}", flush=True)
R = args.rounds
ms = lambda k: cyc[k]/hz*1000/R
n = lambda k: cnt[k]/R
names = {0: 'mask build (inclusive)', 1: 'mask dict parse', 2: 'mask canvas create', 3: 'mask BBox clip',
         4: 'mask sink+begin_group', 5: 'mask paint content', 6: 'mask group commit', 7: 'mask take+free',
         8: 'mask transfer+result take', 9: 'mask luminosity extraction', 10: 'mask RGBA release',
         11: 'page mask install', 12: 'page mask end', 13: 'mask FT init+done', 14: 'begin_group buffer takes',
         15: 'begin_group backdrop copy', 16: 'begin_group clip bounds scan', 17: 'clip_path inside mask'}
sub = {0: 'shading_draw (inclusive)', 1: 'colour table build', 2: 'emit (inclusive)', 3: 'canvas paint (inclusive)',
       4: 'fast span stores', 5: 'row prologue'}
res = {'pdf_sha256': digest_file(pdf), 'base_sha256': digest_file(args.base), 'probe_sha256': digest_file(args.probe),
       'tsc_hz': hz, 'rounds': R, 'mismatched_pages': mismatched,
       'per_sweep': {'base_median_ms': st.median(x['base_ms'] for x in tot_rounds),
                     'probe_median_ms': st.median(x['probe_ms'] for x in tot_rounds),
                     'probe_over_base_median': st.median(x['probe_over_base'] for x in tot_rounds),
                     'cpu_busy_pre_percent_range': [min(x['cpu_busy_pre_percent'] for x in tot_rounds), max(x['cpu_busy_pre_percent'] for x in tot_rounds)]},
       'stage_ms_per_sweep': {v: ms(k) for k, v in names.items()},
       'stage_calls_per_sweep': {v: n(k) for k, v in names.items()},
       'extraction_counts_per_sweep': {'rows_computed': n(20), 'rows_reused': n(21), 'pixels_computed': n(22), 'pixels_reused': n(23)},
       'shading': {}, 'rounds_detail': tot_rounds}
for base, tag in ((32, 'page'), (48, 'mask')):
    res['shading'][tag] = {'ms': {v: ms(base+k) for k, v in sub.items()}, 'calls': {v: n(base+k) for k, v in sub.items()},
                           'rows': n(base+8), 'span_pixels': n(base+9), 'span_pixels_mask_zero': n(base+10),
                           'single_fast_pixels': n(base+11), 'generic_sampled_pixels': n(base+12)}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(res, indent=1)+'\n'); print(json.dumps({k: res[k] for k in ('per_sweep', 'stage_ms_per_sweep', 'extraction_counts_per_sweep', 'shading')}, indent=1))
