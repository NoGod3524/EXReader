"""Recompute three-level load evidence from every retained native sample."""
import json
from pathlib import Path
import sys
from load_capture import summarize, check, read
from e1_capture import write


def analyze(directory):
    reports = {name: summarize(directory/name) for name in ('none', 'medium', 'high')}
    captures = {name: read(directory/name/'capture.json') for name in reports}
    base = reports['none']
    result = {'schema': 2, 'advisory': True, 'accepted': False,
              'dispersion_definition': '100*(max-min)/nearest-rank-p50; no trimming',
              'reports': reports, 'drift_pct': {}, 'per_book': {}, 'acceptance': {},
              'signatures_equal': all(r['signatures'] == base['signatures'] for r in reports.values()),
              'same_sdk': len({c['sdk_sha256'] for c in captures.values()}) == 1,
              'compatible': all(all(c[k] == captures['none'][k]
                    for k in ('plan', 'compatibility', 'input_sha256')) for c in captures.values())}
    for name, report in reports.items():
        result['drift_pct'][name] = {k: 100*(v['p50']/base['statistics'][k]['p50']-1)
            for k, v in report['statistics'].items() if base['statistics'][k]['p50']}
        result['per_book'][name] = {book: {
            'ratio_p50': r['ratio']['p50'], 'ratio_p95': r['ratio']['p95'],
            'dispersion_pct': r['ratio']['range_over_median_pct'],
            'drift_pct': 100*(r['ratio']['p50']/base['per_book'][book]['ratio']['p50']-1)}
            for book, r in report['per_book'].items()}
        result['acceptance'][name] = {
            'five_runs': len(report['runs']) == 5,
            'ratio_drift_lt10': abs(result['drift_pct'][name]['ratio']) < 10,
            'ratio_dispersion_lt10': report['statistics']['ratio']['range_over_median_pct'] < 10,
            'all_book_drift_lt10': all(abs(r['drift_pct']) < 10 for r in result['per_book'][name].values()),
            'all_book_dispersion_lt10': all(r['dispersion_pct'] < 10 for r in result['per_book'][name].values())}
    if (directory/'policy.json').exists():
        policy = read(directory/'policy.json')
        result['thresholds'] = policy['thresholds']
        result['per_book_thresholds'] = policy['per_book']
        result['checks'] = {name: check(policy, directory/name) for name in ('medium', 'high')}
    lines = ['| 负载 / 轮次 | 参照前 p95 ms | 目标 p95 ms | 参照周期 p95 / M | 目标周期 p95 / M | 校正 ratio | 原墙钟 ratio |',
             '|---|---:|---:|---:|---:|---:|---:|']
    labels = {'none': '无', 'medium': '中', 'high': '高'}
    for name, report in reports.items():
        for r in report['runs']:
            lines.append(f"| {labels[name]} {r['index']} | {r['reference_ms']:.4f} | {r['target_ms']:.4f} | "
                f"{r['reference_cycles']/1e6:.4f} | {r['target_cycles']/1e6:.4f} | {r['ratio']:.9f} | {r['wall_ratio']:.9f} |")
    lines += ['', '| 负载 | ratio 中位数 | 漂移 | ratio 离散度 | 参照校准周期离散度 | 原墙钟漂移 | 墙钟三明治漂移 |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for name, report in reports.items():
        s, d = report['statistics'], result['drift_pct'][name]
        lines.append(f"| {labels[name]} | {s['ratio']['p50']:.9f} | {d['ratio']:+.4f}% | "
            f"{s['ratio']['range_over_median_pct']:.4f}% | {s['calibration_cycles']['range_over_median_pct']:.4f}% | "
            f"{d['wall_ratio']:+.4f}% | {d['wall_sandwich_ratio']:+.4f}% |")
    lines += ['', '| 负载 | 目标计入周期 / TSC | 参照计入周期 / TSC | 目标切换次数 / 304 页 | 参照前切换次数 / 304 次 | 排版占目标周期 |',
              '|---|---:|---:|---:|---:|---:|']
    for name, report in reports.items():
        s = report['statistics']
        lines.append(f"| {labels[name]} | {s['target_charged_fraction']['p50']:.4f} | "
            f"{s['reference_charged_fraction']['p50']:.4f} | {s['target_switches']['p50']} | "
            f"{s['reference_switches']['p50']} | {100*s['layout_cycle_fraction']['p50']:.4f}% |")
    lines += ['', '| 书籍 | 无 ratio p95 / 离散度 | 中漂移 / 离散度 | 高漂移 / 离散度 | warning / gate / hard |',
              '|---|---:|---:|---:|---|']
    for book, row in result['per_book']['none'].items():
        m, h = [result['per_book'][name][book] for name in ('medium', 'high')]
        thresholds = result.get('per_book_thresholds', {}).get(book)
        tiers = ' / '.join(f'{v:.9f}' for v in thresholds.values()) if thresholds else '诊断未定线'
        lines.append(f"| {book} | {row['ratio_p95']:.9f} / {row['dispersion_pct']:.3f}% | {m['drift_pct']:+.3f}% / {m['dispersion_pct']:.3f}% | "
                     f"{h['drift_pct']:+.3f}% / {h['dispersion_pct']:.3f}% | {tiers} |")
    write(directory/'experiment.json', result)
    (directory/'measured-results.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in
        ('reports', 'per_book', 'per_book_thresholds')}, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    analyze(Path(sys.argv[1]))
