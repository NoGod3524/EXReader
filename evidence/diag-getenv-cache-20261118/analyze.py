"""Summarize measured independent process pairs and the lookup census."""
import csv
import json
from pathlib import Path
import random
import statistics as s

OUT = Path(__file__).resolve().parent

if __name__ == '__main__':
    rows = json.loads((OUT / 'count-A.json').read_text())
    with (OUT / 'page-counts.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['fixture', 'page', 'cold_lookups', 'warm_lookups', 'cold_estimated_ms_at_1.08us', 'warm_estimated_ms_at_1.08us'])
        for cold in [r for r in rows if r['sweep'] == 'cold']:
            warm = next(r for r in rows if r['fixture'] == cold['fixture'] and r['page'] == cold['page'] and r['sweep'] == 'warm')
            writer.writerow([cold['fixture'], cold['page'], cold['getenv_calls'], warm['getenv_calls'],
                             cold['estimated_lookup_ms_at_1_08_us'], warm['estimated_lookup_ms_at_1_08_us']])
    result = {}
    for name in ['deck', 'word', 'pptx', 'heavy']:
        report = json.loads((OUT / f'{name}-ab.json').read_text())
        for tag in 'AB':
            expected = json.loads((OUT / f'build-{tag}.json').read_text())['dll_sha256']
            assert report[f'library_{tag.lower()}_sha256'] == expected
        d = report['widths']['1200']
        pairs = [100*(b['p50_ms']/a['p50_ms']-1) for a,b in zip(d['A']['repeats'], d['B']['repeats'])]
        rng = random.Random(261118)
        boot = sorted(s.mean(rng.choices(pairs, k=len(pairs))) for _ in range(20000))
        result[name] = {'median_p50_delta_percent': d['p50_ms_delta_pct'],
                        'paired_percent': pairs, 'paired_mean_percent': s.mean(pairs),
                        'paired_mean_bootstrap_95_percent': [boot[499], boot[19499]],
                        'faster_pairs': sum(v<0 for v in pairs), 'orders': d['pair_orders'],
                        'sides': {tag: {
                            'p50_ms': d[tag]['p50_ms_median'], 'p95_ms': d[tag]['p95_ms_median'],
                            'throughput_pages_per_s': d[tag]['throughput_pages_per_s_median'],
                            'spread_percent': d[tag]['spread_percent'],
                            'max_peak_rss_bytes': max(r['peak_rss_bytes'] for r in d[tag]['repeats']),
                            'pre_cpu_percent': [min(r['pre_cpu_percent'] for r in d[tag]['repeats']), max(r['pre_cpu_percent'] for r in d[tag]['repeats'])],
                            'capture_cpu_percent': [min(r['capture_cpu_percent'] for r in d[tag]['repeats']), max(r['capture_cpu_percent'] for r in d[tag]['repeats'])],
                        } for tag in 'AB'}}
        if name == 'heavy':
            result[name]['image_cohort_p71_100_ms'] = {
                tag: s.mean(p['p50_ms'] for p in d[tag]['per_page'][70:100]) for tag in 'AB'}
            cohort_pairs = []
            for i in range(report['repeat']):
                means = {}
                for tag in 'AB':
                    raw = json.loads((OUT / f'.realdoc-heavy-ab/pair-{tag}-w1200-r{i}.json').read_text())
                    means[tag] = s.mean(p['p50_ms'] for p in raw['pages'][70:100])
                cohort_pairs.append(100*(means['B']/means['A']-1))
            rng = random.Random(261118)
            boot = sorted(s.mean(rng.choices(cohort_pairs, k=len(cohort_pairs))) for _ in range(20000))
            result[name]['image_cohort_paired_percent'] = cohort_pairs
            result[name]['image_cohort_paired_mean_percent'] = s.mean(cohort_pairs)
            result[name]['image_cohort_paired_mean_bootstrap_95_percent'] = [boot[499], boot[19499]]
        print(name, json.dumps(result[name]))
    (OUT / 'analysis.json').write_text(json.dumps(result, indent=2)+'\n')
