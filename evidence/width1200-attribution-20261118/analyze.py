# SPDX-License-Identifier: MIT
"""Validate every accepted capture and derive report tables from saved samples."""
import json
import gzip
from pathlib import Path
import statistics as st

HERE = Path(__file__).resolve().parent
CASES = {'real-mixed-120': 120, 'image-heavy-100': 100, 'vector-heavy-100': 100}
MODES = ('full', 'path', 'glyph', 'image', 'shading', 'group')
MIB = 1024**2


def load(path):
    if path.suffix == '.gz':
        return json.loads(gzip.decompress(path.read_bytes()))
    return json.loads(path.read_text(encoding='utf-8'))


def index(phase, expected):
    data = load(HERE / phase / 'index.json')
    rows = data['samples']
    assert len(rows) == expected, (phase, len(rows), expected)
    assert all(0 <= r['pre_cpu_percent'] <= 15 for r in rows)
    keys = {(r['case'], r['mode'], r['rep']) for r in rows}
    for label, mode, rep in keys:
        pair = [r['width'] for r in rows if (r['case'], r['mode'], r['rep']) == (label, mode, rep)]
        assert pair == ([600, 1200] if rep % 2 == 0 else [1200, 600]), (phase, label, mode, rep, pair)
    return rows


def select(rows, case, width, mode='full'):
    return sorted((r for r in rows if r['case'] == case and r['width'] == width and r['mode'] == mode),
                  key=lambda r: r['rep'])


def hashes(row):
    return [p['rgba_sha256'] for p in load(HERE / row['file'])['pages']]


def aggregate_telemetry(row):
    data = load(HERE / row['file'])
    assert data['page_count'] == CASES[row['case']]
    rounds = []
    for pages in data['rounds']:
        assert max(p['page_trace']['mask_builds'] for p in pages) <= 1
        totals = {'ms': sum(p['ms'] for p in pages),
                  'mask_ms': sum(p['page_trace']['mask_ms'] for p in pages),
                  'mask_builds': sum(p['page_trace']['mask_builds'] for p in pages)}
        for k in pages[0]['metrics']:
            totals[k] = (max if k.endswith('pool_bytes') else sum)(p['metrics'][k] for p in pages)
        for k in ('hits', 'misses', 'evictions', 'decode_ms'):
            totals[k] = sum(p['cache_delta'][k] for p in pages)
        totals['image_cache_bytes'] = max(p['images']['bytes'] for p in pages)
        totals['image_cache_entries'] = max(p['images']['entries'] for p in pages)
        totals['other_ms'] = totals['ms'] - sum(totals[k] for k in ('mask_ms', 'canvas_image_ms', 'canvas_paint_ms', 'canvas_create_ms'))
        rounds.append(totals)
    return {'cold': rounds[0], 'warm': {k: st.mean(r[k] for r in rounds[1:]) for k in rounds[0]}}


def main():
    baseline = index('baseline', 18)
    parity = index('parity', 6)
    ablation = index('ablation', 108)
    telemetry = index('telemetry', 18)
    first = index('firstscreen', 18)
    cached = index('baseline-256mib', 6)
    cachetrace = index('telemetry-256mib', 6)
    controls = [dict(r, file=r['control64_file']) for r in cached]
    for row in baseline + parity + ablation + cached + controls:
        data = load(HERE / row['file'])
        count = CASES[row['case']]
        assert [p['page'] for p in data['pages']] == list(range(1, count + 1))
        assert all(p['dimensions'][0] == row['width'] and len(p['render_ms']) == data['runs'] for p in data['pages'])
        reconstructed = [sum(p['render_ms'][i] for p in data['pages']) for i in range(data['runs'])]
        assert abs(st.median(reconstructed) - data['round_wall_ms_p50']) <= .001
        assert abs(count * 1000 / st.median(reconstructed) - data['throughput_pages_per_s']) <= .011
        assert sum(p['pixels'] for p in data['pages']) == data['active_pixels_per_round']
    archived = load(HERE.parent / 'p95-then-throughput-20261118/results.json')
    for label, count in CASES.items():
        for width in (600, 1200):
            for side in ('exreader', 'pdfjs'):
                side_data = archived['cases'][f'{label}@{width}'][side]
                assert side_data['page_count'] == len(side_data['per_page']) == count
    output = {'baseline': {}, 'ablation': {}, 'telemetry': {}, 'cache256': {}, 'firstscreen': {}, 'cohorts': {}}
    inventory = load(HERE.parent / 'real-doc-throughput-20261118/page-content.json')
    checks = 0
    for label, count in CASES.items():
        output['baseline'][label] = {}
        output['ablation'][label] = {}
        output['telemetry'][label] = {}
        output['firstscreen'][label] = {}
        output['cohorts'][label] = {}
        for w in (600, 1200):
            b = select(baseline, label, w)
            expected = hashes(b[0])
            native_pages = [load(HERE / row['file'])['pages'] for row in b]
            cohorts = {}
            for pg, info in enumerate(inventory[label]['pages']):
                if label == 'image-heavy-100' and pg + 1 >= 71:
                    cohort = 'synthetic multi-image'
                elif label == 'vector-heavy-100' and pg + 1 >= 66:
                    cohort = 'synthetic dense vector'
                elif info['soft_mask_axial_shadings'] and info['axial_shadings']:
                    cohort = 'gradient + soft mask'
                else:
                    cohort = 'other'
                totals = cohorts.setdefault(cohort, {'pages': 0, 'sum_page_medians_ms': 0})
                totals['pages'] += 1
                totals['sum_page_medians_ms'] += st.median(pages[pg]['p50_ms'] for pages in native_pages)
            output['cohorts'][label][w] = cohorts
            assert len(expected) == count
            for row in b + select(parity, label, w) + select(ablation, label, w):
                assert row['page_count'] == count
                assert hashes(row) == expected, row['file']
                checks += count
            for row in select(telemetry, label, w):
                data = load(HERE / row['file'])
                assert [p['sha256'] for p in data['rounds'][0]] == expected
                checks += count
            for row in select(first, label, w):
                assert row['rgba_sha256'] == expected[0]
                checks += 1
            rss = []
            for row in b:
                data = load(HERE / row['file'])
                cold_peak = max(p['peak_rss_after_first_render_bytes'] for p in data['pages'])
                rss.append({'start': data['rss_start_bytes'] / MIB,
                            'open_growth': (data['rss_after_open_bytes'] - data['rss_start_bytes']) / MIB,
                            'cold_peak_growth': (cold_peak - data['rss_after_open_bytes']) / MIB,
                            'warm_peak_growth': (data['peak_rss_bytes'] - cold_peak) / MIB,
                            'peak': data['peak_rss_bytes'] / MIB})
            output['baseline'][label][w] = {
                'pages': count, 'pixels': b[0]['active_pixels_per_round'],
                'ms': st.median(r['round_wall_ms_p50'] for r in b),
                'samples_ms': [r['round_wall_ms_p50'] for r in b],
                'pages_s': st.median(r['throughput_pages_per_s'] for r in b),
                'rss_mean_mib': {k: st.mean(r[k] for r in rss) for k in rss[0]},
            }
            full = select(ablation, label, w)
            output['ablation'][label][w] = {}
            for mode in MODES:
                rows = select(ablation, label, w, mode)
                changed = [sum(a != z for a, z in zip(expected, hashes(r), strict=True)) for r in rows]
                deltas = [f['round_wall_ms_p50'] - r['round_wall_ms_p50'] for f, r in zip(full, rows, strict=True)]
                output['ablation'][label][w][mode] = {
                    'ms': st.median(r['round_wall_ms_p50'] for r in rows),
                    'samples_ms': [r['round_wall_ms_p50'] for r in rows],
                    'saving_ms': st.median(deltas), 'saving_samples_ms': deltas,
                    'changed_pages': changed,
                }
            totals = [aggregate_telemetry(r) for r in select(telemetry, label, w)]
            output['telemetry'][label][w] = {
                kind: {k: st.mean(t[kind][k] for t in totals) for k in totals[0][kind]}
                for kind in ('cold', 'warm')}
            output['telemetry'][label][w]['repeat_warm'] = [t['warm'] for t in totals]
            output['firstscreen'][label][w] = {
                'open_ms': st.median(r['open_ms'] for r in select(first, label, w)),
                'render_ms': st.median(r['first_render_ms'] for r in select(first, label, w)),
            }
    for w in (600, 1200):
        rows = select(cached, 'image-heavy-100', w)
        expected = hashes(select(baseline, 'image-heavy-100', w)[0])
        for row in rows:
            assert hashes(row) == expected
            assert row['cache_order'] == ('64/256' if row['rep'] % 2 == 0 else '256/64')
            assert 0 <= row['control64']['pre_cpu_percent'] <= 15
            assert hashes({'file': row['control64_file']}) == expected
            checks += 200
        traces = [aggregate_telemetry(r) for r in select(cachetrace, 'image-heavy-100', w)]
        for row in select(cachetrace, 'image-heavy-100', w):
            assert [p['sha256'] for p in load(HERE / row['file'])['rounds'][0]] == expected
            checks += 100
        output['cache256'][w] = {
            'ms': st.median(r['round_wall_ms_p50'] for r in rows),
            'samples_ms': [r['round_wall_ms_p50'] for r in rows],
            'pages_s': st.median(r['throughput_pages_per_s'] for r in rows),
            'peak_rss_mean_mib': st.mean(r['peak_rss_bytes'] / MIB for r in rows),
            'paired64_ms': st.median(r['control64']['round_wall_ms_p50'] for r in rows),
            'paired_saving_ms': st.median(r['control64']['round_wall_ms_p50'] - r['round_wall_ms_p50'] for r in rows),
            'paired_saving_samples_ms': [r['control64']['round_wall_ms_p50'] - r['round_wall_ms_p50'] for r in rows],
            'warm_trace': {k: st.mean(t['warm'][k] for t in traces) for k in traces[0]['warm']},
        }
    gates = [r['pre_cpu_percent'] for rows in (baseline, parity, ablation, telemetry, first, cached, cachetrace) for r in rows]
    gates += [r['control64']['pre_cpu_percent'] for r in cached]
    output['validation'] = {'accepted_children': len(gates), 'min_cpu': min(gates), 'max_cpu': max(gates),
                            'matching_page_hash_checks': checks, 'all_width_orders_alternate': True}
    (HERE / 'summary.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output['validation'], indent=2))


if __name__ == '__main__':
    main()
