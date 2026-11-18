# SPDX-License-Identifier: MIT
"""Validate raw/ captures and write summary.json + TABLES.md. Read-only on raw data."""
import json
from pathlib import Path
import statistics as st
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from bench_real_doc import summarize_repeats  # noqa: E402

CASES = {'real-mixed-120': 120, 'image-heavy-100': 100, 'vector-heavy-100': 100}
SKIPS = ('image', 'image-paint', 'path', 'glyph', 'shading', 'softmask', 'group')
med = st.median


def load(name):
    return json.loads((HERE / 'raw' / name).read_text(encoding='utf-8'))


def cohort(label, pg, info):
    if label == 'image-heavy-100' and pg >= 71:
        return 'synthetic multi-image'
    if label == 'vector-heavy-100' and pg >= 66:
        return 'synthetic dense vector'
    if info['soft_mask_axial_shadings'] and info['axial_shadings']:
        return 'gradient + soft mask'
    return 'other'


def sweep(child):
    """Median warm-round sum of timed page renders, reconstructed from samples."""
    runs = child['runs']
    sums = [sum(p['render_ms'][i] for p in child['pages']) for i in range(runs)]
    return med(sums)


def main():
    index = json.loads((HERE / 'raw/index.json').read_text(encoding='utf-8'))
    old = json.loads((HERE.parent / 'p95-then-throughput-20261118/results.json').read_text(encoding='utf-8'))
    inventory = json.loads((HERE.parent / 'real-doc-throughput-20261118/page-content.json').read_text(encoding='utf-8'))
    reps = index['repeat']
    out = {'library_sha256': index['library_sha256'], 'runs': index['runs'], 'repeat': reps, 'cases': {}}
    checks = {'children': 0, 'hash_comparisons': 0, 'denominators_checked': 0}
    gates = []
    for label, n in CASES.items():
        rows = {(s['arm'], s['rep']): s for s in index['samples'] if s['case'] == label}
        assert len(rows) == reps * len(index['arms']), (label, len(rows))
        kids = {k: load(v['file']) for k, v in rows.items()}
        for (arm, rep), child in kids.items():
            checks['children'] += 1
            gates.append(rows[(arm, rep)]['pre_cpu_percent'])
            assert rows[(arm, rep)]['pre_cpu_percent'] <= 15.0
            assert child['page_count'] == n and len(child['pages']) == n and child['width'] == 1200
            assert [p['page'] for p in child['pages']] == list(range(1, n + 1))
            assert all(len(p['render_ms']) == child['runs'] for p in child['pages'])
            assert abs(round(n * 1000.0 / sweep(child), 2) - child['throughput_pages_per_s']) <= 0.011, (label, arm, rep)
            checks['denominators_checked'] += 1
        # order: alternate full/pdfjs on adjacent positions, reversed on odd repeats
        orders = {rep: [a for a, _ in sorted(((a, rows[(a, rep)]['position']) for a in index['arms']), key=lambda t: t[1])]
                  for rep in range(reps)}
        # deterministic output per arm
        ref = {}
        for (arm, rep), child in kids.items():
            if arm == 'pdfjs':
                continue
            h = [p['rgba_sha256'] for p in child['pages']]
            if arm in ref:
                checks['hash_comparisons'] += n
                assert ref[arm] == h, (label, arm, rep)
            else:
                ref[arm] = h
        old_raw = HERE.parent / 'p95-then-throughput-20261118/.raw-results' / f'{label}-w1200-r0-exreader.json'
        old_hash = [p['rgba_sha256'] for p in json.loads(old_raw.read_text(encoding='utf-8'))['pages']]
        same_as_257 = sum(a == b for a, b in zip(old_hash, ref['full']))
        checks['hash_comparisons'] += n
        changed = {arm: sum(a != b for a, b in zip(ref[arm], ref['full'])) for arm in SKIPS}

        full = [kids[('full', r)] for r in range(reps)]
        pdfjs = [kids[('pdfjs', r)] for r in range(reps)]
        se, sp = summarize_repeats(full), summarize_repeats(pdfjs)
        te, tp = se['throughput_pages_per_s_median'], sp['throughput_pages_per_s_median']
        o = old['cases'][f'{label}@1200']
        oe, op = o['exreader']['throughput_pages_per_s_median'], o['pdfjs']['throughput_pages_per_s_median']
        paired = [kids[('pdfjs', r)]['throughput_pages_per_s'] / kids[('full', r)]['throughput_pages_per_s'] for r in range(reps)]
        case = {
            'orders': orders,
            'exreader': {k: se[k] for k in ('throughput_pages_per_s_median', 'throughput_pages_per_s_repeats', 'p50_ms_median',
                                             'p95_ms_median', 'worst_page', 'worst_page_p50_ms_median', 'peak_rss_mib_median')},
            'pdfjs': {k: sp[k] for k in ('throughput_pages_per_s_median', 'throughput_pages_per_s_repeats', 'p50_ms_median',
                                          'p95_ms_median', 'worst_page', 'worst_page_p50_ms_median', 'peak_rss_mib_median')},
            'pdfjs_gc_warm_share_pct_median': round(med(r['gc_warm_share_pct'] for r in pdfjs), 2),
            'ratio': round(tp / te, 3),
            'paired_ratio_median': round(med(paired), 3), 'paired_ratio_range': [round(min(paired), 3), round(max(paired), 3)],
            'old_257': {'exreader': oe, 'pdfjs': op, 'ratio': round(op / oe, 3), 'p95_exreader': o['exreader']['p95_ms_median'],
                        'p50_exreader': o['exreader']['p50_ms_median']},
            'pages_identical_to_257': same_as_257, 'changed_pages_by_skip': changed,
        }
        # ---- tail vs broad: per-page cross-repeat medians of page p50
        E = [p['p50_ms'] for p in se['per_page']]
        P = [p['p50_ms'] for p in sp['per_page']]
        d = [e - p for e, p in zip(E, P)]
        G = sum(d)
        order_excess = sorted(range(n), key=lambda i: -d[i])

        def pages_for(share):
            acc = 0.0
            for k, i in enumerate(order_excess, 1):
                acc += d[i]
                if acc >= share * G:
                    return k
            return None

        def counterfactual(frac):
            k = round(frac * n)
            top = set(order_excess[:k])
            return round(sum(P[i] if i in top else E[i] for i in range(n)) / sum(P), 3)

        page_ratio = [e / p for e, p in zip(E, P)]
        case['shape'] = {
            'sum_page_p50_exreader_ms': round(sum(E), 2), 'sum_page_p50_pdfjs_ms': round(sum(P), 2),
            'sum_ratio': round(sum(E) / sum(P), 3), 'gap_ms': round(G, 2),
            'pooled_p50_ratio': round(se['p50_ms_median'] / sp['p50_ms_median'], 3),
            'median_page_ratio': round(med(page_ratio), 3),
            'p50_over_total_ratio': round((se['p50_ms_median'] / sp['p50_ms_median']) / (sum(E) / sum(P)), 3),
            'pages_slower': sum(x > 0 for x in d), 'pages_slower_by_10pct': sum(r > 1.1 for r in page_ratio),
            'pages_faster': sum(x < 0 for x in d),
            'excess_on_slower_pages_ms': round(sum(x for x in d if x > 0), 2),
            'lead_on_faster_pages_ms': round(-sum(x for x in d if x < 0), 2),
            'pages_for_50pct_gap': pages_for(0.5), 'pages_for_80pct_gap': pages_for(0.8), 'pages_for_100pct_gap': pages_for(1.0),
            'top10pct_share_of_gap': round(sum(d[i] for i in order_excess[:n // 10]) / G, 3) if G > 0 else None,
            'ratio_if_top10pct_matched': counterfactual(0.1), 'ratio_if_top20pct_matched': counterfactual(0.2),
            'ratio_if_top30pct_matched': counterfactual(0.3),
            'top_excess_pages': [{'page': i + 1, 'exreader_ms': round(E[i], 3), 'pdfjs_ms': round(P[i], 3),
                                  'excess_ms': round(d[i], 3), 'cohort': cohort(label, i + 1, inventory[label]['pages'][i])}
                                 for i in order_excess[:10]],
        }
        # cohorts
        cohorts = {}
        for i in range(n):
            c = cohort(label, i + 1, inventory[label]['pages'][i])
            t = cohorts.setdefault(c, {'pages': 0, 'exreader_ms': 0.0, 'pdfjs_ms': 0.0, 'ratios': []})
            t['pages'] += 1
            t['exreader_ms'] += E[i]
            t['pdfjs_ms'] += P[i]
            t['ratios'].append(page_ratio[i])
        for c, t in cohorts.items():
            t['excess_ms'] = round(t['exreader_ms'] - t['pdfjs_ms'], 2)
            t['share_of_gap'] = round((t['exreader_ms'] - t['pdfjs_ms']) / G, 3) if G > 0 else None
            t['sum_ratio'] = round(t['exreader_ms'] / t['pdfjs_ms'], 3)
            t['median_page_ratio'] = round(med(t['ratios']), 3)
            t['min_page_ratio'] = round(min(t['ratios']), 3)
            t['max_page_ratio'] = round(max(t['ratios']), 3)
            t['exreader_ms'] = round(t['exreader_ms'], 2)
            t['pdfjs_ms'] = round(t['pdfjs_ms'], 2)
            del t['ratios']
        case['cohorts'] = cohorts
        # ---- whole-document ablations
        abl = {}
        full_sweep = [sweep(kids[('full', r)]) for r in range(reps)]
        pdf_sweep = [sweep(kids[('pdfjs', r)]) for r in range(reps)]
        for arm in SKIPS:
            arm_kids = [kids[(arm, r)] for r in range(reps)]
            arm_sweep = [sweep(k) for k in arm_kids]
            saving = [f - a for f, a in zip(full_sweep, arm_sweep)]
            tput = med(k['throughput_pages_per_s'] for k in arm_kids)
            # per-page saving by cohort (median across repeats of within-repeat page-p50 difference)
            per_page = [med(kids[('full', r)]['pages'][i]['p50_ms'] - kids[(arm, r)]['pages'][i]['p50_ms'] for r in range(reps))
                        for i in range(n)]
            by_c = {}
            for i in range(n):
                c = cohort(label, i + 1, inventory[label]['pages'][i])
                by_c[c] = by_c.get(c, 0.0) + per_page[i]
            abl[arm] = {
                'throughput_median': round(tput, 2),
                'throughput_repeats': sorted(round(k['throughput_pages_per_s'], 2) for k in arm_kids),
                'ratio_vs_pdfjs': round(tp / tput, 3),
                'saving_ms_median': round(med(saving), 2), 'saving_ms_repeats': [round(s, 2) for s in saving],
                'saving_share_of_gap': round(med(saving) / (med(full_sweep) - med(pdf_sweep)), 3),
                'reps_at_or_above_pdfjs': sum(arm_kids[r]['throughput_pages_per_s'] >= kids[('pdfjs', r)]['throughput_pages_per_s']
                                              for r in range(reps)),
                'paired_ratio_vs_pdfjs': [round(arm_sweep[r] / pdf_sweep[r], 3) for r in range(reps)],
                'saving_by_cohort_ms': {c: round(v, 2) for c, v in by_c.items()},
                'changed_pages': changed[arm],
            }
        case['sweep_ms'] = {'full_median': round(med(full_sweep), 2), 'pdfjs_median': round(med(pdf_sweep), 2),
                            'gap_median': round(med(full_sweep) - med(pdf_sweep), 2),
                            'paired_gap': [round(f - p, 2) for f, p in zip(full_sweep, pdf_sweep)]}
        case['ablation'] = abl
        # per-page fixed floor: cheapest pages on each side
        cheap = sorted(range(n), key=lambda i: E[i])[: n // 10]
        case['cheapest_decile'] = {'pages': [i + 1 for i in cheap], 'exreader_ms': round(sum(E[i] for i in cheap), 3),
                                   'pdfjs_ms': round(sum(P[i] for i in cheap), 3),
                                   'exreader_min_page_ms': round(min(E), 3), 'pdfjs_min_page_ms': round(min(P), 3)}
        out['cases'][label] = case
    out['validation'] = {**checks, 'gate_min': min(gates), 'gate_max': max(gates)}
    comp = HERE / 'competition.jsonl'
    out['validation']['excluded_children'] = sum('excluded' in json.loads(l) for l in comp.read_text().splitlines()) if comp.exists() else 0
    (HERE / 'summary.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(out['validation']))


if __name__ == '__main__':
    main()
