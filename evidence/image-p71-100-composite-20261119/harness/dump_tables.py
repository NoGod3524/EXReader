# SPDX-License-Identifier: MIT
"""Dump exact per-round pre-CPU and A-B deltas for REPORT.md."""
import json, statistics as st
from pathlib import Path

E = Path('evidence/image-p71-100-composite-20261119')

def dump_dir(label, subdir, names):
    print(f'### {label}')
    for name in names:
        p = E / subdir / f'{name}.json'
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        s = d['summary']
        rds = d['rounds']
        cpus = [r['cpu_busy_pre_percent'] for r in rds]
        savs = [r['saving_ms'] for r in rds]
        pcts = [100.0 * r['saving_ms'] / r['A_ms'] for r in rds]
        print(f'[{name}] n={len(rds)} A_med={s["A_median_ms"]:.2f} B_med={s["B_median_ms"]:.2f} sav_med={s["saving_median_ms"]:+.2f} ({st.median(pcts):+.2f}%) min={min(savs):+.2f} max={max(savs):+.2f} fast={s["rounds_b_faster"]}/{len(rds)} p50={s["A_page_p50_ms"]:.4f}->{s["B_page_p50_ms"]:.4f}')
        print(f'  cpu min/med/max: {min(cpus):.1f} / {st.median(cpus):.1f} / {max(cpus):.1f}%')
        print('  rounds cpu:', ', '.join(f'{c:.1f}' for c in cpus))
        print('  rounds A-B:', ', '.join(f'{v:+.2f}' for v in savs))
        print(f'  a_sha={d["a_sha256"][:12]} b_sha={d["b_sha256"][:12]}')

dump_dir('FINAL', 'final', [
    'control-null', 'p71-100', 'image-heavy-100', 'real-mixed-120', 'vector-heavy-100',
    'gate-pptx-20-600', 'gate-pptx-20-1200', 'gate-word-5-600', 'gate-word-5-1200', 'gate-deck-1200'
])
dump_dir('CLEAN-ABLATION', 'clean', [
    'control-null', 'v3-s4-opaque', 'v3-s4-full', 'v3-s3-opaque', 'v3-s3-full', 'v3-all-no-s3b', 'v3-all',
    'v4-control-null', 'v4-cand-site3', 'v4-simple', 'v4-uniform', 'v4-uniform-s3'
])
