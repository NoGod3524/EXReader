# SPDX-License-Identifier: MIT
"""Absolute cost of one drawing class: one DLL, original PDF (A) vs omission PDF (B).

Both documents are open in one process on the same loaded DLL. Page i of round r
renders AB when (r+i) is even and BA otherwise, so the order alternates per page
and the start order flips each round. Round 0 is a warm-up that also compares the
active RGBA bytes (it counts the pages the omission changed). CPU busy is sampled
for one second before each round and recorded, not gated. The caller holds the
bench lock; every round heartbeats it. A - B is the class's absolute cost.
Usage: omit.py <dll> <class> <out.json> [--rounds N] [--holder NAME]
"""
import argparse, json, os, statistics as st, subprocess, sys
from pathlib import Path
import psutil
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import NativeDocument, digest_file
LOCK = r'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1'
assert os.environ.get('EXR_IDLE_GATE') == 'off', 'set EXR_IDLE_GATE=off'

ap = argparse.ArgumentParser()
ap.add_argument('dll', type=Path); ap.add_argument('name'); ap.add_argument('out', type=Path)
ap.add_argument('--rounds', type=int, default=11); ap.add_argument('--min-clean', type=int, default=11)
ap.add_argument('--max-rounds', type=int, default=25); ap.add_argument('--cpu-limit', type=float, default=25.0)
ap.add_argument('--holder', default='agy-B')
args = ap.parse_args()
pdf = (ROOT/'tests/fixtures/pdf-large/vector-heavy-100.pdf').resolve()
edit = (ROOT/'evidence/dense-vector-path-residual-20261119/_work'/f'vector-heavy-100-{args.name}.pdf').resolve()
docs = {'A': NativeDocument(args.dll.resolve(), pdf, 1200), 'B': NativeDocument(args.dll.resolve(), edit, 1200)}
pages = list(range(65, 100))
rows = {p+1: {t: [] for t in 'AB'} for p in pages}
rounds, changed, compared, clean_count = [], [], 0, 0
r = 0
while r == 0 or (r < args.rounds or (clean_count < args.min_clean and r < args.max_rounds)):
    subprocess.run(['pwsh', '-NoProfile', '-File', LOCK, '-Holder', args.holder, '-Heartbeat'], check=True, capture_output=True)
    cpu = psutil.cpu_percent(interval=1.0)
    tot = dict.fromkeys('AB', 0.0)
    for i, p in enumerate(pages):
        got = {}
        for t in ('AB' if (r+i) % 2 == 0 else 'BA'):
            ms, px = docs[t].render(p, r == 0, None)
            got[t] = px
            if r:
                rows[p+1][t].append(ms); tot[t] += ms
        if r == 0:
            compared += len(got['A'])*1200
            if got['A'] != got['B']:
                changed.append(p+1)
    if r:
        polluted = cpu > args.cpu_limit
        if not polluted:
            clean_count += 1
        rounds.append({'round': r, 'start': 'AB' if r % 2 == 0 else 'BA', 'cpu_busy_pre_percent': cpu,
                       'polluted': polluted, 'A_ms': tot['A'], 'B_ms': tot['B'], 'cost_ms': tot['A']-tot['B']})
        flag = ' [POLLUTED]' if polluted else ''
        print(f"{args.name} r{r} cpu={cpu:.1f}%{flag} full={tot['A']:.2f} omit={tot['B']:.2f} cost={tot['A']-tot['B']:+.2f} (clean={clean_count}/{args.min_clean})", flush=True)
    else:
        print(f'{args.name} warm-up cpu={cpu:.1f}% changed={len(changed)}/35', flush=True)
    r += 1
clean_rounds = [x for x in rounds if not x['polluted']]
polluted_rounds = [x['round'] for x in rounds if x['polluted']]
use = clean_rounds if clean_rounds else rounds
s = [x['cost_ms'] for x in use]
res = {'class': args.name, 'pdf': str(pdf), 'pdf_sha256': digest_file(pdf), 'edit': str(edit), 'edit_sha256': digest_file(edit),
       'dll': str(args.dll), 'dll_sha256': digest_file(args.dll), 'pages': [66, 100], 'width': 1200,
       'order': 'A=original, B=omission; AB if (round+page index) even else BA; round 0 warm-up and pixel compare',
       'compared_pixels': compared, 'changed_pages': changed,
       'summary': {'full_median_ms': st.median(x['A_ms'] for x in use), 'omit_median_ms': st.median(x['B_ms'] for x in use),
                   'cost_median_ms': st.median(s), 'cost_min_ms': min(s), 'cost_max_ms': max(s),
                   'rounds_omit_faster': sum(v > 0 for v in s), 'rounds_total': len(rounds),
                   'clean_rounds': len(clean_rounds), 'polluted_rounds': polluted_rounds,
                   'cpu_limit_percent': args.cpu_limit,
                   'clean_cpu_range': [min(x['cpu_busy_pre_percent'] for x in clean_rounds), max(x['cpu_busy_pre_percent'] for x in clean_rounds)] if clean_rounds else None,
                   'cpu_busy_pre_percent_range': [min(x['cpu_busy_pre_percent'] for x in rounds), max(x['cpu_busy_pre_percent'] for x in rounds)]},
       'rounds': rounds, 'per_page_ms': rows}
for d in docs.values():
    d.close()
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(res, indent=1) + '\n')
print(json.dumps(res['summary']), flush=True)
