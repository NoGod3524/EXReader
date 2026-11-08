"""Recompute normal/loaded experiment comparisons; never edits frozen tiers."""
import json
import sys
from pathlib import Path
from ratio_capture import read, summarize
from e1_capture import write


def markdown(data, normal, loaded):
    lines = ['| 状态 / 轮次 | 独立参照 p95 ms | 配对参照 p95 ms | 翻页 p95 ms | ratio |',
             '|---|---:|---:|---:|---:|']
    for name, report in (('正常', normal), ('受压', loaded)):
        for r in report['runs']:
            lines.append(f"| {name} {r['index']} | {r['calibration_ms']:.6f} | {r['reference_ms']:.6f} | {r['target_ms']:.6f} | {r['ratio']:.9f} |")
    lines += ['', '| 五轮离散度 | 正常 | 受压 | 验收 |', '|---|---:|---:|---|']
    for key, label, limit in (('calibration_ms', '独立参照 p95', 3), ('ratio', '翻页 p95 / 参照 p95', 5),
                               ('target_ms', '绝对翻页 p95', None)):
        a, b = [data[k][key]['range_over_median_pct'] for k in ('normal', 'loaded')]
        outcome = f"{'通过' if a < limit else '失败'}（正常要求 <{limit}%）" if limit else '仅诊断'
        lines.append(f'| {label} | {a:.6f}% | {b:.6f}% | {outcome} |')
    a, b, d = data['normal'], data['loaded'], data['drift_pct']
    lines += ['', f"正常→受压：翻页 p95 中位数 **{a['target_ms']['p50']:.6f}→{b['target_ms']['p50']:.6f} ms**，"
              f"**{data['slowdown']['target_ms']:.4f}× / {d['target_ms']:+.4f}%**；配对参照 "
              f"**{data['slowdown']['reference_ms']:.4f}× / {d['reference_ms']:+.4f}%**；"
              f"ratio 中位数 **{a['ratio']['p50']:.9f}→{b['ratio']['p50']:.9f}**，"
              f"漂移 **{d['ratio']:+.4f}%**，"
              f"<10% 验收 **{'通过' if data['acceptance']['loaded_ratio_drift_lt10'] else '失败'}**。", '',
              '| 整体冻结参照 R0 | 受压候选 p95 ratio | 警告 | 门禁 | 硬上限 |',
              '|---:|---:|---:|---:|---:|',
              f"| {data['baseline_anchor_ratio']:.9f} | {b['ratio']['p95']:.9f} | "
              + ' | '.join(f"{data['thresholds'][k]:.9f}" for k in ('warning', 'gate', 'hard')) + ' |', '',
              '19 本各自的冻结阈值与受压候选（每列 p95 均对五轮取 nearest-rank）：', '',
              '| 书籍 ID | 正常 p95 ratio | 受压 p95 ratio | 警告 | 门禁 | 硬上限 | 受压结果 |',
              '|---|---:|---:|---:|---:|---:|---|']
    for r in data['per_book']:
        exceeded = [k for k, v in r['thresholds'].items() if r['loaded_ratio_p95'] > v]
        outcome = '/'.join(exceeded) if exceeded else '三线以下'
        lines.append(f"| {r['id']} | {r['normal_ratio_p95']:.9f} | {r['loaded_ratio_p95']:.9f} | "
                     + ' | '.join(f"{r['thresholds'][k]:.9f}" for k in ('warning', 'gate', 'hard'))
                     + f' | {outcome} |')
    null = data['independent_null_candidate']
    worst = max(data['per_book'], key=lambda r: r['normal_dispersion_pct'])
    drift = max(data['per_book'], key=lambda r: abs(r['ratio_drift_pct']))
    lines += ['', f"单书正常 ratio 离散度最差为 **{worst['normal_dispersion_pct']:.4f}%**"
              f"（{worst['id']}）；受压单书 ratio 中位数漂移最差为 "
              f"**{drift['ratio_drift_pct']:+.4f}%**（{drift['id']}）。"
              '整体统计达标不能代替逐书稳定性。']
    lines += ['', f"独立未变更候选：整体三档超限次数（共 {null['n']} 轮）为 "
              f"**{null['tier_exceedances']}**；任一单书超过门禁的轮次 "
              f"**{null['runs_exceeding_any_book_gate']}/{null['n']}**；"
              f"基线 eligible={data['normal_eligible']}，候选 eligible={data['loaded_eligible']}。", '',
              f"逐页 RGBA/文本/位置签名在所有正常与受压轮之间一致：**{data['signatures_equal']}**。"]
    return '\n'.join(lines)+'\n'


def analyze(directory):
    normal, loaded = [summarize(directory/key) for key in ('normal', 'loaded')]
    policy = read(directory/'ratio-policy.json')
    data = {'schema': 1, 'advisory': True, 'accepted': False,
            'dispersion_definition': '100*(max-min)/nearest-rank-p50; all runs, no trimming',
            'normal': normal['statistics'], 'loaded': loaded['statistics'],
            'normal_eligible': normal['eligible'], 'loaded_eligible': loaded['eligible'],
            'signatures_equal': normal['signatures'] == loaded['signatures'],
            'baseline_anchor_ratio': policy['anchor_ratio'], 'thresholds': policy['thresholds'],
            'drift_pct': {}, 'slowdown': {}, 'per_book': []}
    for key in ('calibration_ms', 'target_ms', 'reference_ms', 'ratio', 'paired_ratio_p95'):
        a, b = [r['statistics'][key]['p50'] for r in (normal, loaded)]
        data['slowdown'][key] = b/a
        data['drift_pct'][key] = 100*(b/a-1)
    for book, row in normal['per_book'].items():
        a, b = row['ratio']['p50'], loaded['per_book'][book]['ratio']['p50']
        data['per_book'].append({'id': book, 'normal_ratio_p50': a,
            'normal_ratio_p95': row['ratio']['p95'], 'loaded_ratio_p50': b,
            'loaded_ratio_p95': loaded['per_book'][book]['ratio']['p95'],
            'ratio_drift_pct': 100*(b/a-1),
            'thresholds': policy['per_book'][book],
            'normal_dispersion_pct': row['ratio']['range_over_median_pct'],
            'loaded_dispersion_pct': loaded['per_book'][book]['ratio']['range_over_median_pct']})
    # Same SDK under stress is an independent null-regression candidate after freeze.
    exceeded = {k: sum(r['ratio'] > threshold for r in loaded['runs'])
                for k, threshold in policy['thresholds'].items()}
    book_gate_exceedances = sum(any(row['ratio'] > policy['per_book'][book]['gate']
                                   for book, row in r['books'].items()) for r in loaded['runs'])
    n = len(loaded['runs'])
    data['independent_null_candidate'] = {'n': n, 'tier_exceedances': exceeded,
        'runs_exceeding_any_book_gate': book_gate_exceedances,
        'gate_exceedance_fraction': exceeded['gate']/n,
        'one_sided_95pct_binomial_upper_if_zero': 1-.05**(1/n) if exceeded['gate'] == 0 else None,
        'qualification_failed': not (policy['eligible'] and loaded['eligible'])}
    data['acceptance'] = {
        'reference_dispersion_lt3': normal['statistics']['calibration_ms']['range_over_median_pct'] < 3,
        'ratio_dispersion_lt5': normal['statistics']['ratio']['range_over_median_pct'] < 5,
        'loaded_ratio_drift_lt10': abs(data['drift_pct']['ratio']) < 10,
        'approximately_2x_target': 1.8 <= data['slowdown']['target_ms'] <= 2.5,
        'signatures_unchanged': data['signatures_equal']}
    data['acceptance']['all_book_dispersion_lt5'] = all(r['normal_dispersion_pct'] < 5 for r in data['per_book'])
    data['acceptance']['all_book_loaded_drift_lt10'] = all(abs(r['ratio_drift_pct']) < 10 for r in data['per_book'])
    write(directory/'experiment.json', data)
    (directory/'measured-results.md').write_text(markdown(data, normal, loaded), encoding='utf-8')
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


if __name__ == '__main__':
    analyze(Path(sys.argv[1]))
