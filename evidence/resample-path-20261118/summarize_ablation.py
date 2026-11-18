"""Summarize compare.py --mode runs: per cohort, full (A, mode 0) vs ablated (B) warm medians and probe counters."""
import json, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = {1: 'skip all images', 2: 'skip soft masks', 3: 'skip clips', 4: 'skip the two tiles', 5: 'skip tiles and soft masks'}
def cohort(page):
    if page <= 10: return 'p1-10 slides'
    if page <= 70: return 'p11-70'
    return 'p71-100 masked bg' if (page - 71) % 5 in (0, 2, 4) else 'p71-100 unmasked bg'
rows = []
for mode in NAMES:
    path = HERE/'raw'/f'ablate-mode{mode}.json'
    if not path.exists(): continue
    report = json.loads(path.read_text())
    sweeps = report['sweeps'][1:]  # sweep 0 fills the decode cache
    groups = {}
    for sweep in sweeps:
        for row in sweep['pages']:
            g = groups.setdefault(cohort(row['page']), {'A': {}, 'B': {}, 'trace': {}})
            g['A'].setdefault(row['page'], []).append(row['A']['ms'])
            g['B'].setdefault(row['page'], []).append(row['B']['ms'])
            g['trace'].setdefault(row['page'], []).append(row['A']['trace'])
    for name, g in groups.items():
        a = sum(statistics.median(v) for v in g['A'].values()) / len(g['A'])
        b = sum(statistics.median(v) for v in g['B'].values()) / len(g['B'])
        t = [statistics.median(x[k] for x in v) for v in g['trace'].values() for k in range(11)]
        n = len(g['trace']); tr = [sum(t[i*11+k] for i in range(n)) / n for k in range(11)]
        rows.append((mode, name, a, b, tr))
print('mode | ablation | cohort | full ms/page | ablated ms/page | removed ms/page | blend ms (bg/tile) | clip ms | mask clips | decodes (bg/tile)')
for mode, name, a, b, tr in rows:
    print(f'{mode} | {NAMES[mode]} | {name} | {a:.2f} | {b:.2f} | {a-b:.2f} | {tr[0]:.2f}/{tr[1]:.2f} | {tr[2]:.2f} | {tr[3]:.1f} | {tr[8]:.2f}/{tr[9]:.2f}')
