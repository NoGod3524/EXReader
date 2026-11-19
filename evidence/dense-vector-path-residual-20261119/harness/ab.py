# SPDX-License-Identifier: MIT
"""Paired A/B over a page range (default vector-heavy-100 pages 66-100 at 1200 px).

Both DLLs live in one process. Page i of round r renders AB when (r+i) is even
and BA otherwise, so the order alternates per page and the start order flips
each round. Round 0 is a warm-up that also compares the active RGBA bytes.
CPU busy is sampled for one second before each round and recorded, not gated.
Rounds with pre-CPU > cpu_limit are marked polluted and excluded from clean medians.
"""
import argparse, json, os, statistics as st, subprocess, sys
from pathlib import Path
import psutil
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import NativeDocument, digest_file, response, close_worker
LOCK = r'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1'
assert os.environ.get('EXR_IDLE_GATE') == 'off', 'set EXR_IDLE_GATE=off'

ap = argparse.ArgumentParser()
ap.add_argument('a', type=Path); ap.add_argument('b', type=Path); ap.add_argument('out', type=Path)
ap.add_argument('--rounds', type=int, default=11); ap.add_argument('--min-clean', type=int, default=11)
ap.add_argument('--max-rounds', type=int, default=25); ap.add_argument('--cpu-limit', type=float, default=25.0)
ap.add_argument('--first', type=int, default=66); ap.add_argument('--last', type=int, default=100)
ap.add_argument('--holder', default='agy-B'); ap.add_argument('--pdfjs-root', type=Path)
ap.add_argument('--pdf', type=Path); ap.add_argument('--width', type=int, default=1200)
args = ap.parse_args()
pdf = (args.pdf or ROOT/'tests/fixtures/pdf-large/vector-heavy-100.pdf').resolve()
docs = {t: NativeDocument(p.resolve(), pdf, args.width) for t, p in zip('AB', (args.a, args.b))}
pages = list(range(args.first-1, args.last))
worker = None
if args.pdfjs_root:
    worker = subprocess.Popen(['node', str(ROOT/'evidence/slides-gradient-20261118/pdfjs_worker.cjs'), str(args.pdfjs_root.resolve()), str(pdf)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    assert response(worker) == 'ready'
tags = 'ABC' if worker else 'AB'
rows = {p+1: {t: [] for t in tags} for p in pages}
rounds, mismatched, compared, clean_count = [], [], 0, 0
r = 0
while r == 0 or (r < args.rounds or (clean_count < args.min_clean and r < args.max_rounds)):
    subprocess.run(['pwsh', '-NoProfile', '-File', LOCK, '-Holder', args.holder, '-Heartbeat'], check=True, capture_output=True)
    cpu = psutil.cpu_percent(interval=1.0)
    tot = dict.fromkeys(tags, 0.0)
    for i, p in enumerate(pages):
        order = 'AB' if (r+i) % 2 == 0 else 'BA'
        if worker:
            order = order+'C' if (r+i) % 2 == 0 else 'C'+order
        got = {}
        for t in order:
            if t == 'C':
                worker.stdin.write(f'{p} 0\n'); worker.stdin.flush()
                ns, _ = json.loads(response(worker)); ms = ns/1e6
            else:
                ms, px = docs[t].render(p, r == 0, None)
                got[t] = px
            if r:
                rows[p+1][t].append(ms); tot[t] += ms
        if r == 0:
            compared += len(got['A'])*args.width
        if r == 0 and got['A'] != got['B']:
            mismatched.append(p+1)
    if r:
        polluted = cpu > args.cpu_limit
        if not polluted:
            clean_count += 1
        rounds.append({'round': r, 'start': 'AB' if r % 2 == 0 else 'BA', 'cpu_busy_pre_percent': cpu,
                       'polluted': polluted, 'A_ms': tot['A'], 'B_ms': tot['B'], 'saving_ms': tot['A']-tot['B']})
        if worker:
            rounds[-1].update({'C_ms': tot['C'], 'gap_A_ms': tot['A']-tot['C'], 'gap_B_ms': tot['B']-tot['C']})
        flag = ' [POLLUTED]' if polluted else ''
        print(f"round {r} cpu={cpu:.1f}%{flag} A={tot['A']:.2f} B={tot['B']:.2f} A-B={tot['A']-tot['B']:+.2f} (clean={clean_count}/{args.min_clean})", flush=True)
    else:
        print(f'warm-up cpu={cpu:.1f}% mismatched={mismatched}', flush=True)
    r += 1
clean_rounds = [x for x in rounds if not x['polluted']]
polluted_rounds = [x['round'] for x in rounds if x['polluted']]
use = clean_rounds if clean_rounds else rounds
clean_idx = [i for i, x in enumerate(rounds) if not x['polluted']] or list(range(len(rounds)))
s = [x['saving_ms'] for x in use]
res = {'pdf': str(pdf), 'pdf_sha256': digest_file(pdf), 'pages': [args.first, args.last], 'width': args.width,
       'a': str(args.a), 'b': str(args.b), 'a_sha256': digest_file(args.a), 'b_sha256': digest_file(args.b),
       'order': 'AB if (round+page index) even else BA; round 0 warm-up and pixel check',
       'compared_pixels': compared, 'mismatched_pages': mismatched,
       'summary': {'A_median_ms': st.median(x['A_ms'] for x in use), 'B_median_ms': st.median(x['B_ms'] for x in use),
                   'saving_median_ms': st.median(s), 'saving_min_ms': min(s), 'saving_max_ms': max(s),
                   'rounds_b_faster': sum(v > 0 for v in s), 'rounds_total': len(rounds),
                   'clean_rounds': len(clean_rounds), 'polluted_rounds': polluted_rounds,
                   'cpu_limit_percent': args.cpu_limit,
                   'A_page_p50_ms': st.median(rows[p]['A'][i] for p in rows for i in clean_idx),
                   'B_page_p50_ms': st.median(rows[p]['B'][i] for p in rows for i in clean_idx),
                   'clean_cpu_range': [min(x['cpu_busy_pre_percent'] for x in clean_rounds), max(x['cpu_busy_pre_percent'] for x in clean_rounds)] if clean_rounds else None,
                   'cpu_busy_pre_percent_range': [min(x['cpu_busy_pre_percent'] for x in rounds), max(x['cpu_busy_pre_percent'] for x in rounds)]},
       'rounds': rounds, 'per_page_ms': rows}
if worker:
    close_worker(worker)
    res['pdfjs_root'] = str(args.pdfjs_root)
    res['order'] += '; with PDF.js as C: ABC on even, CBA on odd'
    res['summary'].update({'C_median_ms': st.median(x['C_ms'] for x in use),
        'gap_A_median_ms': st.median(x['gap_A_ms'] for x in use), 'gap_B_median_ms': st.median(x['gap_B_ms'] for x in use),
        'gap_reduction_median_ms': st.median(x['gap_A_ms'] for x in use)-st.median(x['gap_B_ms'] for x in use)})
for d in docs.values():
    d.close()
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(res, indent=1)+'\n'); print(json.dumps(res['summary'], indent=1), flush=True)
