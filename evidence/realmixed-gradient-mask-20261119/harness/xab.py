# SPDX-License-Identifier: MIT
"""Cross-process paired A/B: same schedule as dense-vector-residual ab.py, but each DLL runs in its
own worker process, so neither arm shares a CRT heap, allocator state or caches' process context
with the other. Page i of round r renders AB when (r+i) is even, else BA. Round 0 is warm-up and
compares SHA-256 of the active RGBA rows. CPU busy is sampled for 1 s before each round and
recorded, never gated. Output schema matches ab.py (summary / rounds / per_page_ms).
"""
import argparse, hashlib, json, statistics as st, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
LOCK = r'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1'

if len(sys.argv) > 1 and sys.argv[1] == '--worker':
    sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
    from paired_sweep import NativeDocument
    doc = NativeDocument(Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]))
    print('ready', flush=True)
    for line in sys.stdin:
        p, verify = map(int, line.split())
        ms, rows = doc.render(p, bool(verify), None)
        h = hashlib.sha256(b''.join(rows)).hexdigest() if rows else ''
        print(json.dumps([ms, h, len(rows) if rows else 0]), flush=True)
    sys.exit(0)

import psutil
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import digest_file
ap = argparse.ArgumentParser()
ap.add_argument('a', type=Path); ap.add_argument('b', type=Path); ap.add_argument('out', type=Path)
ap.add_argument('--rounds', type=int, default=15); ap.add_argument('--first', type=int, required=True)
ap.add_argument('--last', type=int, required=True); ap.add_argument('--holder', required=True)
ap.add_argument('--pdf', type=Path, required=True); ap.add_argument('--width', type=int, default=1200)
args = ap.parse_args()
pdf = args.pdf.resolve()
w = {}
for t, p in zip('AB', (args.a, args.b)):
    w[t] = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(p.resolve()), str(pdf), str(args.width)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    assert w[t].stdout.readline().strip() == 'ready'
def render(t, p, verify):
    w[t].stdin.write(f'{p} {int(verify)}\n'); w[t].stdin.flush()
    return json.loads(w[t].stdout.readline())
pages = list(range(args.first-1, args.last))
rows = {p+1: {'A': [], 'B': []} for p in pages}
rounds, mismatched, compared = [], [], 0
for r in range(args.rounds+1):
    subprocess.run(['pwsh', '-NoProfile', '-File', LOCK, '-Holder', args.holder, '-Heartbeat'], check=True, capture_output=True)
    cpu = psutil.cpu_percent(interval=1.0)
    tot = {'A': 0.0, 'B': 0.0}
    for i, p in enumerate(pages):
        got = {}
        for t in ('AB' if (r+i) % 2 == 0 else 'BA'):
            ms, h, n = render(t, p, r == 0); got[t] = (h, n)
            if r:
                rows[p+1][t].append(ms); tot[t] += ms
        if r == 0:
            compared += got['A'][1]*args.width
            if got['A'] != got['B']:
                mismatched.append(p+1)
    if r:
        rounds.append({'round': r, 'start': 'AB' if r % 2 == 0 else 'BA', 'cpu_busy_pre_percent': cpu,
                       'A_ms': tot['A'], 'B_ms': tot['B'], 'saving_ms': tot['A']-tot['B']})
        print(f"round {r} cpu={cpu:.1f}% A={tot['A']:.2f} B={tot['B']:.2f} A-B={tot['A']-tot['B']:+.2f}", flush=True)
    else:
        print(f'warm-up cpu={cpu:.1f}% mismatched={mismatched}', flush=True)
for t in w.values():
    t.stdin.close(); t.wait()
s = [x['saving_ms'] for x in rounds]
A = [v for r in rows.values() for v in r['A']]; B = [v for r in rows.values() for v in r['B']]
res = {'harness': 'xab.py (one worker process per DLL)', 'pdf': str(pdf), 'pdf_sha256': digest_file(pdf), 'pages': [args.first, args.last],
       'width': args.width, 'a': str(args.a), 'b': str(args.b), 'a_sha256': digest_file(args.a), 'b_sha256': digest_file(args.b),
       'order': 'AB if (round+page index) even else BA; round 0 warm-up and pixel check (sha256 of rows)',
       'compared_pixels': compared, 'mismatched_pages': mismatched,
       'summary': {'A_median_ms': st.median(x['A_ms'] for x in rounds), 'B_median_ms': st.median(x['B_ms'] for x in rounds),
                   'saving_median_ms': st.median(s), 'saving_min_ms': min(s), 'saving_max_ms': max(s),
                   'rounds_b_faster': sum(v > 0 for v in s), 'rounds': len(s),
                   'A_page_p50_ms': st.median(A), 'B_page_p50_ms': st.median(B), 'ratio_B_over_A': st.median(B)/st.median(A),
                   'cpu_busy_pre_percent_range': [min(x['cpu_busy_pre_percent'] for x in rounds), max(x['cpu_busy_pre_percent'] for x in rounds)]},
       'rounds': rounds, 'per_page_ms': rows}
args.out.write_text(json.dumps(res, indent=1)+'\n'); print(json.dumps(res['summary'], indent=1))
