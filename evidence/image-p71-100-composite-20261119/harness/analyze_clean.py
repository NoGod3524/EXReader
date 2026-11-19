# SPDX-License-Identifier: MIT
"""Summarize clean ablation runs with per-round % saving, CPU distribution, and cohort split."""
import json, statistics as st
from pathlib import Path
import sys

clean_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('evidence/image-p71-100-composite-20261119/clean')
names = sys.argv[2:] if len(sys.argv) > 2 else [
    'control-null', 'v3-s4-opaque', 'v3-s4-full',
    'v3-s3-opaque', 'v3-s3-full', 'v3-all-no-s3b', 'v3-all'
]

opaque_bg_pages = {72, 74, 77, 79, 82, 84, 87, 89, 92, 94, 97, 99}
masked_bg_pages = set(range(71, 101)) - opaque_bg_pages

for name in names:
    p = clean_dir / f'{name}.json'
    if not p.exists():
        continue
    d = json.loads(p.read_text())
    rds = d['rounds']
    pcts = [100.0 * r['saving_ms'] / r['A_ms'] for r in rds]
    cpus = [r['cpu_busy_pre_percent'] for r in rds]
    pp = d['per_page_ms']
    op_sav, mk_sav, op_pct, mk_pct = [], [], [], []
    for idx in range(len(rds)):
        a_op = sum(pp[str(pg)]['A'][idx] for pg in opaque_bg_pages)
        b_op = sum(pp[str(pg)]['B'][idx] for pg in opaque_bg_pages)
        a_mk = sum(pp[str(pg)]['A'][idx] for pg in masked_bg_pages)
        b_mk = sum(pp[str(pg)]['B'][idx] for pg in masked_bg_pages)
        op_sav.append(a_op - b_op)
        op_pct.append(100.0 * (a_op - b_op) / a_op)
        mk_sav.append(a_mk - b_mk)
        mk_pct.append(100.0 * (a_mk - b_mk) / a_mk)
    s = d['summary']
    print(
        f"{name:14s} | A={s['A_median_ms']:7.1f} B={s['B_median_ms']:7.1f} "
        f"sav={s['saving_median_ms']:+7.2f}ms ({st.median(pcts):+5.2f}%, range {min(pcts):+5.2f}..{max(pcts):+5.2f}%) "
        f"fast={s['rounds_b_faster']:2d}/{s['rounds']} | "
        f"op12={st.median(op_pct):+5.2f}% ({st.median(op_sav):+6.1f}ms) "
        f"mk18={st.median(mk_pct):+5.2f}% ({st.median(mk_sav):+6.1f}ms) | "
        f"cpu={min(cpus):.1f}/{st.median(cpus):.1f}/{max(cpus):.1f}%"
    )
