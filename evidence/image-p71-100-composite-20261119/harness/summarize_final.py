# SPDX-License-Identifier: MIT
"""Summarize all final timed captures, cohort breakdowns, and RSS."""
import json, statistics as st
from pathlib import Path

F = Path('evidence/image-p71-100-composite-20261119/final')
names = [
    'control-null', 'p71-100', 'image-heavy-100', 'real-mixed-120', 'vector-heavy-100',
    'gate-pptx-20-600', 'gate-pptx-20-1200', 'gate-word-5-600', 'gate-word-5-1200', 'gate-deck-1200'
]

for name in names:
    p = F / f'{name}.json'
    if not p.exists():
        continue
    d = json.loads(p.read_text())
    s = d['summary']
    rds = d['rounds']
    cpus = [r['cpu_busy_pre_percent'] for r in rds]
    pcts = [100.0 * r['saving_ms'] / r['A_ms'] for r in rds]
    p50_ratio = s['B_page_p50_ms'] / s['A_page_p50_ms']
    print(
        f"{name:18s} | n={s['rounds']:2d} | A={s['A_median_ms']:7.2f} B={s['B_median_ms']:7.2f} "
        f"sav={s['saving_median_ms']:+7.2f}ms ({st.median(pcts):+5.2f}%) fast={s['rounds_b_faster']:2d}/{s['rounds']:2d} | "
        f"p50: {s['A_page_p50_ms']:6.3f}->{s['B_page_p50_ms']:6.3f} ({p50_ratio:.4f}x) | "
        f"cpu={min(cpus):.1f}/{st.median(cpus):.1f}/{max(cpus):.1f}% | mis={d['mismatched_pages']}"
    )

# Cohort breakdown for whole-document runs
cohorts = {
    'image-heavy-100': [
        ('Courseware slides (p1-10)', range(1, 11)),
        ('Deck (p11-40)', range(11, 41)),
        ('Word (p41-60)', range(41, 61)),
        ('Image-only (p61-70)', range(61, 71)),
        ('Synthetic multi-image (p71-100)', range(71, 101)),
    ],
    'real-mixed-120': [
        ('Courseware slides (p1-21)', range(1, 22)),
        ('Deck (p22-51)', range(22, 52)),
        ('Word (p52-76)', range(52, 77)),
        ('PPTX (p77-116)', range(77, 117)),
        ('Excel+Chinese (p117-120)', range(117, 121)),
    ],
    'vector-heavy-100': [
        ('Courseware slides (p1-10)', range(1, 11)),
        ('Excel (p11-25)', range(11, 26)),
        ('PPTX (p26-65)', range(26, 66)),
        ('Synthetic dense vector (p66-100)', range(66, 101)),
    ],
}

print("\n=== Whole-document cohort breakdown ===")
for doc, groups in cohorts.items():
    p = F / f'{doc}.json'
    if not p.exists():
        continue
    d = json.loads(p.read_text())
    pp = d['per_page_ms']
    n = len(d['rounds'])
    print(f"\n[{doc}]")
    for label, prange in groups:
        a_s = [sum(pp[str(pg)]['A'][i] for pg in prange) for i in range(n)]
        b_s = [sum(pp[str(pg)]['B'][i] for pg in prange) for i in range(n)]
        sav = [a - b for a, b in zip(a_s, b_s)]
        pct = [100.0 * (a - b) / a for a, b in zip(a_s, b_s)]
        faster = sum(v > 0 for v in sav)
        print(
            f"  {label:34s} | A={st.median(a_s):7.2f} B={st.median(b_s):7.2f} "
            f"sav={st.median(sav):+7.2f}ms ({st.median(pct):+5.2f}%, {min(sav):+.1f}..{max(sav):+.1f}) fast={faster:2d}/{n}"
        )

# RSS summary
rss_p = F / 'rss.json'
if rss_p.exists():
    print("\n=== Peak RSS ===")
    r = json.loads(rss_p.read_text())
    for name, rows in r['working_sets'].items():
        a_max = max(x['A'] for x in rows)
        b_max = max(x['B'] for x in rows)
        pair_max = max((x['B'] - x['A']) / x['A'] for x in rows)
        print(f"  {name:18s} | A_max={a_max:,} B_max={b_max:,} change={100*(b_max-a_max)/a_max:+.2f}% worst_pair={100*pair_max:+.2f}%")
