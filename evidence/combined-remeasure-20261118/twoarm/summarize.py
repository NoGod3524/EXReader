# SPDX-License-Identifier: MIT
"""Two-arm (twocells driver) controls: whole-document median-of-round-medians per engine and
page-type sums from the selected sweeps, exactly as in twocells-attribution-20261118."""
import gzip
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from analyze import GROUPS, pages_of  # noqa: E402

res = {}
for arm in ('orig', 'GI', 'GIV'):
    for cell in GROUPS:
        runs = [json.loads(gzip.decompress((HERE / arm / 'raw' / f'{cell}-r{r}-baseline.json.gz').read_bytes()))
                for r in (1, 2, 3)]
        o = {}
        for eng, key in (('X', 'X full'), ('J', 'J full')):
            meds, picks = [], []
            for d in runs:
                sums = [sum(s) / 1e6 for s in d['times_ns'][key][1:]]
                m = st.median(sums)
                meds.append(m)
                picks.append(d['times_ns'][key][1 + sums.index(m)])
            sel = st.median(meds)
            k = meds.index(sel)
            o[eng] = dict(rounds=meds, selected=sel, round=k + 1,
                          groups={n: sum(picks[k][p - 1] for p in pages_of(cell, n, a, b)) / 1e6
                                  for n, a, b in GROUPS[cell]})
        o['ratio'] = o['X']['selected'] / o['J']['selected']
        o['gap'] = o['X']['selected'] - o['J']['selected']
        o['idle_before'] = [d['idle_before'] for d in runs]
        o['dll'] = runs[0]['dll']
        res.setdefault(cell, {})[arm] = o
(HERE / 'results.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
for cell, arms in res.items():
    print('\n##', cell)
    for arm, o in arms.items():
        print(f"{arm:4} X={o['X']['selected']:.2f} {[round(v, 2) for v in o['X']['rounds']]} "
              f"J={o['J']['selected']:.2f} {[round(v, 2) for v in o['J']['rounds']]} ratio={o['ratio']:.3f} gap={o['gap']:+.2f}")
        print('     gaps', {n: round(o['X']['groups'][n] - o['J']['groups'][n], 2) for n in o['X']['groups']})
        print('     X   ', {n: round(v, 2) for n, v in o['X']['groups'].items()})
        print('     J   ', {n: round(v, 2) for n, v in o['J']['groups'].items()})
