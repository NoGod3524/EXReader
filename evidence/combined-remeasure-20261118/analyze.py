# SPDX-License-Identifier: MIT
"""Reduce raw/<cell>-r<n>.json.gz into results.json.

Whole-document value per arm: median of each round's five warm sums, then the median of
the three round medians (the twocells rule). Page-type values for the headline table use
the page times of the selected sweep, so groups sum to the whole-document value.
Effects and interactions are paired within each warm sweep (all arms rendered each page
back to back), averaged over 15 sweeps, with the three round means as the range.
"""
import gzip
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / 'raw'
GROUPS = {
    'image-heavy-100': [('Courseware slides', 1, 10), ('Deck', 11, 40), ('Word', 41, 60),
                        ('Image-only', 61, 70), ('Synthetic multi-image', 71, 100)],
    'real-mixed-120': [('Courseware slides', 1, 21), ('Deck', 22, 51), ('Word', 52, 76),
                       ('PPTX', 77, 116), ('Excel', 117, 119), ('Chinese', 118, 120)],
    'vector-heavy-100': [('Courseware vector/table slides', 1, 10), ('Excel', 11, 25),
                         ('PPTX', 26, 65), ('Synthetic dense vector', 66, 100)],
}
# Excel and Chinese interleave on pages 117-120.
PAGESETS = {('real-mixed-120', 'Excel'): [117, 119], ('real-mixed-120', 'Chinese'): [118, 120]}
FACTORS = {'G': '#264', 'I': '#263', 'V': 'densevec'}


def pages_of(cell, name, a, b):
    return PAGESETS.get((cell, name), list(range(a, b + 1)))


def load(cell):
    runs = [json.loads(gzip.decompress(p.read_bytes())) for p in sorted(RAW.glob(f'{cell}-r*.json.gz'))]
    assert [r['rep'] for r in runs] == [1, 2, 3], cell
    return runs


def ms(ns):
    return ns / 1e6


def group_sum(sweep, pages):
    return ms(sum(sweep[p - 1] for p in pages))


def summarize(cell):
    runs = load(cell)
    arms = runs[0]['arms']
    groups = [(n, pages_of(cell, n, a, b)) for n, a, b in GROUPS[cell]]
    allpages = list(range(1, len(runs[0]['pages']) + 1))
    out = dict(cell=cell, arms=arms, rounds=[], whole={}, selected={}, groups={}, paired={}, hashes={})
    for r in runs:
        out['rounds'].append(dict(rep=r['rep'], idle_before=r['idle_before'], busy=r['busy'],
                                  gate_seconds=r['gate_seconds'], first=r['first_arm_per_sweep']))
    for arm in arms:
        medians, picks = [], []
        for r in runs:
            sums = [ms(sum(s)) for s in r['times_ns'][arm][1:]]
            m = st.median(sums)
            medians.append(m)
            picks.append(r['times_ns'][arm][1 + sums.index(m)])
        sel = st.median(medians)
        k = medians.index(sel)
        out['whole'][arm] = dict(rounds=medians, selected=sel, selected_round=k + 1)
        out['selected'][arm] = {n: group_sum(picks[k], p) for n, p in groups}
    # Paired per-sweep sums for every arm, page group and the whole document.
    sweeps = []  # list of (rep, {arm: {group: ms}})
    for r in runs:
        for s in range(1, r['sweeps']):
            row = {arm: {n: group_sum(r['times_ns'][arm][s], p) for n, p in groups + [('All', allpages)]}
                   for arm in arms}
            sweeps.append((r['rep'], row))

    def stat(f):
        vals = [f(row) for _, row in sweeps]
        by_rep = [st.mean(f(row) for rep, row in sweeps if rep == k) for k in (1, 2, 3)]
        return dict(mean=st.mean(vals), median=st.median(vals), lo=min(by_rep), hi=max(by_rep),
                    positive=sum(v > 0 for v in vals), n=len(vals), sweep_sd=st.stdev(vals))

    out['group_mean'] = {arm: {g: st.mean(row[arm][g] for _, row in sweeps)
                               for g in [n for n, _ in groups] + ['All']} for arm in arms}
    for g in [n for n, _ in groups] + ['All']:
        e = {}
        for arm in arms:
            e[f'gap {arm}'] = stat(lambda row, a=arm: row[a][g] - row['J'][g])
        for arm in arms:
            if arm not in ('J', 'base'):
                e[f'saving {arm}'] = stat(lambda row, a=arm: row['base'][g] - row[a][g])
        # Pairwise and three-way interactions (positive = the changes overlap / eat each other).
        def saving(row, a):
            return row['base'][g] - (row[a][g] if a else row['base'][g])
        for x, y in (('G', 'I'), ('G', 'V'), ('I', 'V')):
            xy = ''.join(sorted(x + y, key='GIV'.index))
            e[f'overlap {xy}'] = stat(lambda row, x=x, y=y, xy=xy: saving(row, x) + saving(row, y) - saving(row, xy))
        e['overlap GIV (sum of singles - combined)'] = stat(
            lambda row: saving(row, 'G') + saving(row, 'I') + saving(row, 'V') - saving(row, 'GIV'))
        e['three-way interaction'] = stat(
            lambda row: (row['GIV'][g] - row['GI'][g] - row['GV'][g] - row['IV'][g]
                         + row['G'][g] + row['I'][g] + row['V'][g] - row['base'][g]))
        # Densevec on top of each background.
        e['V on base (base-V)'] = stat(lambda row: row['base'][g] - row['V'][g])
        e['V on #264 (G-GV)'] = stat(lambda row: row['G'][g] - row['GV'][g])
        e['V on main (GI-GIV)'] = stat(lambda row: row['GI'][g] - row['GIV'][g])
        e['I on base (base-I)'] = stat(lambda row: row['base'][g] - row['I'][g])
        e['I on #264 (G-GI)'] = stat(lambda row: row['G'][g] - row['GI'][g])
        e['G on base (base-G)'] = stat(lambda row: row['base'][g] - row['G'][g])
        e['G on #263 (I-GI)'] = stat(lambda row: row['I'][g] - row['GI'][g])
        e['orig - base'] = stat(lambda row: row['orig'][g] - row['base'][g])
        out['paired'][g] = e
    # Cold pixel hashes: pages whose hash differs from the rebuilt base, and cross-round stability.
    for arm in arms:
        stable = all(r['hashes'][arm] == runs[0]['hashes'][arm] for r in runs)
        ref = 'J' if arm == 'J' else 'base'
        diff = [i + 1 for i, (a, b) in enumerate(zip(runs[0]['hashes'][arm], runs[0]['hashes'][ref])) if a != b]
        out['hashes'][arm] = dict(stable_across_rounds=stable, pages_differing_from_base=diff)
    return out


def main():
    res = {c: summarize(c) for c in GROUPS if list(RAW.glob(f'{c}-r*.json.gz'))}
    (HERE / 'results.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    for c, o in res.items():
        print(f'\n## {c}')
        for arm, w in o['whole'].items():
            j = o['whole']['J']['selected']
            print(f"{arm:5} rounds={[round(x, 2) for x in w['rounds']]} sel={w['selected']:.2f} "
                  f"ratio={w['selected'] / j:.3f} gap={w['selected'] - j:+.2f}")
        for g, e in o['paired'].items():
            v = e['saving GI']
            print(f"  [{g}] base={o['group_mean']['base'][g]:.2f} main saving={v['mean']:+.2f} "
                  f"densevec on main={e['V on main (GI-GIV)']['mean']:+.2f} "
                  f"overlap={e['overlap GIV (sum of singles - combined)']['mean']:+.2f}")
        print('  hashes', {a: (h['stable_across_rounds'], len(h['pages_differing_from_base']))
                           for a, h in o['hashes'].items()})


if __name__ == '__main__':
    main()
