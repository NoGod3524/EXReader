"""Cohort sums of per-page warm p50 (EXReader vs PDF.js) using #248's page-content.json.

usage: python -X utf8 cohorts.py results.json [out.json]
Cohorts match #250: gradient+smask (any axial shading), image (no gradient), other.
Also reports the synthetic hotspot ranges named in #250.
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
content = json.loads((ROOT / 'evidence/real-doc-throughput-20261118/page-content.json').read_text(encoding='utf-8'))
HOT = {'vector-heavy-100': ('dense vector p66-100', 66, 100), 'image-heavy-100': ('multi-image p71-100', 71, 100)}


def cohort(p):
    if p['axial_shadings'] or p['soft_mask_axial_shadings']:
        return 'gradient+smask'
    return 'image (no gradient)' if p['image_draws'] else 'other'


results = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
out = {}
for key, case in results['cases'].items():
    fixture = key.split('@')[0]
    kinds = {p['page']: cohort(p) for p in content[fixture]['pages']}
    sides = {s: {p['page']: p['p50_ms'] for p in case[s]['per_page']} for s in ('exreader', 'pdfjs')}
    groups = {}
    for page, kind in kinds.items():
        names = [kind]
        if fixture in HOT and HOT[fixture][1] <= page <= HOT[fixture][2]:
            names.append(HOT[fixture][0])
        for n in names:
            g = groups.setdefault(n, {'pages': 0, 'exreader_ms': 0.0, 'pdfjs_ms': 0.0})
            g['pages'] += 1; g['exreader_ms'] += sides['exreader'][page]; g['pdfjs_ms'] += sides['pdfjs'][page]
    for n, g in groups.items():
        g['exreader_ms'] = round(g['exreader_ms'], 1); g['pdfjs_ms'] = round(g['pdfjs_ms'], 1)
        g['ratio'] = round(g['exreader_ms'] / g['pdfjs_ms'], 2)
        print(f'{key:22s} {n:22s} {g["pages"]:4d} {g["exreader_ms"]:9.1f} {g["pdfjs_ms"]:9.1f} {g["ratio"]:6.2f}x')
    out[key] = groups
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding='utf-8')
