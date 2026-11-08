#!/usr/bin/env python3
"""Derive three latency tiers from retained E1 raw data, then audit a later capture.

python tools/perf/gate_policy.py derive BASELINE OUTPUT.json
python tools/perf/gate_policy.py check POLICY.json CANDIDATE OUTPUT.json
Exit 1 means ineligible/noisy/incompatible/over gate; advisory evidence grants no E3 acceptance.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import e1_capture as e1
from gate_capture import summarize

TIERS = {'warning': 1.10, 'gate': 1.25, 'hard': 1.50}


def read(path):
    return json.loads(Path(path).read_bytes())


def audit(folder):
    env, report = read(folder / 'env.json'), read(folder / 'samples.json')
    problems, summaries, signatures = [], {}, {}
    if not report['measurement_valid']:
        problems.append('capture identity/measurement invalid')
    if set(report['groups']) != set(e1.CONFIGS):
        problems.append('configuration coverage differs')
    for name, group in report['groups'].items():
        if len(group['batches']) != 1:
            problems.append(name + ': exactly one complete batch required')
        trials = [t for b in group['batches'] for t in b['trials']]
        summaries[name] = summarize(trials)
        if not summaries[name]['stable']:
            problems.append(name + ': >=5 processes, idle target and all metrics <5% required')
        for t in trials:
            for load in ('load_before', 'load_after'):
                if t[load].get('ac_line_status') != 1 or t[load].get('battery_saver') != 0:
                    problems.append(name + ': AC/saver precondition failed or unknown')
            for field in ('stdout', 'stderr'):
                path = folder / t[field].replace('\\', '/')
                if not path.resolve().is_relative_to(folder.resolve()):
                    raise ValueError('raw path escapes evidence folder')
                if e1.sha(path) != t[field + '_sha256']:
                    raise ValueError('raw sample digest mismatch')
            raw = read(folder / t['stdout'].replace('\\', '/'))
            if t.get('exit_code') != 0 or e1.metrics(raw) != t.get('metrics'):
                raise ValueError('native status or derived metrics mismatch')
            width, height, _ = e1.CONFIGS[name]
            if any(s['width'] != width or s['height'] != height for s in raw['samples']):
                raise ValueError('viewport mismatch')
            sig = e1.signatures(raw)
            if name in signatures and signatures[name] != sig:
                raise ValueError('RGBA/text/position mismatch')
            signatures[name] = sig
    return env, report, summaries, signatures, problems


def derive(folder):
    env, report, summaries, signatures, problems = audit(folder)
    latency = {}
    memory = {}
    for name, summary in summaries.items():
        latency[name] = {metric: {'baseline_p95': s['p95'], **{
            tier: math.ceil(s['p95'] * multiplier * 1000) / 1000
            for tier, multiplier in TIERS.items()}}
            for metric, s in summary['metrics'].items() if metric.endswith('_ms')}
        memory[name] = math.ceil(summary['metrics']['peak_rss_bytes']['p95'] * 1.05) + 1048576
    return {'schema': 1, 'advisory': True, 'accepted': False, 'eligible': not problems,
            'baseline_directory': folder.as_posix(), 'samples_sha256': e1.sha(folder / 'samples.json'),
            'environment_sha256': e1.sha(folder / 'env.json'), 'exporter_sha256': e1.sha(__file__),
            'comparison_key': env['comparison_key'], 'source_sha': env['source_sha'],
            'protected_trees': env['protected_trees'], 'font_sha256': report['font_sha256'],
            'input_sha256': report['input_sha256'], 'binary_sha256': env['identities'][report['binary']],
            'tiers': TIERS, 'latency_ms': latency, 'memory_gate_bytes': memory,
            'summaries': summaries, 'problems': problems,
            'method': 'nearest-rank process p95; ceil(p95*multiplier*1000)/1000 ms; memory ceil(p95*1.05)+1MiB'}


def check(policy_path, candidate):
    policy = read(policy_path)
    baseline = Path(policy['baseline_directory'])
    frozen_at = policy.pop('frozen_at')
    if derive(baseline) != policy:
        raise ValueError('policy does not match raw derivation or exporter digest')
    env, report, summaries, sigs, problems = audit(candidate)
    if not policy['eligible']:
        problems.append('baseline ineligible: diagnostic thresholds only')
    if report['started_at'] <= frozen_at:
        problems.append('candidate must start after budget derivation')
    if env['comparison_key'] != policy['comparison_key']:
        problems.append('different environment: requires its own baseline')
    for key in ('font_sha256', 'input_sha256'):
        if report[key] != policy[key]:
            problems.append('workload identity differs: ' + key)
    if env['protected_trees'] == policy['protected_trees'] and env['identities'][report['binary']] != policy['binary_sha256']:
        problems.append('unchanged SDK source requires identical binary for this local repeat')
    _, _, _, baseline_sigs, _ = audit(baseline)
    if sigs != baseline_sigs:
        problems.append('baseline RGBA/text/position signatures differ')
    comparisons = []
    for name, summary in summaries.items():
        for metric, s in summary['metrics'].items():
            if metric.endswith('_ms'):
                limits = policy['latency_ms'][name][metric]
                comparisons.append({'configuration': name, 'metric': metric, 'measured_p95': s['p95'],
                    'ratio': s['p95'] / limits['baseline_p95'],
                    'exceeded': [tier for tier in TIERS if s['p95'] > limits[tier]]})
            elif s['p95'] > policy['memory_gate_bytes'][name]:
                problems.append(name + ': memory exceeds independent E1 cap')
    blocked = any('gate' in row['exceeded'] for row in comparisons)
    return {'advisory': True, 'accepted': False, 'e3_restoration_granted': False,
            'policy_sha256': e1.sha(policy_path), 'candidate_samples_sha256': e1.sha(candidate / 'samples.json'),
            'problems': problems, 'comparisons': comparisons,
            'worst_latency_ratio': max(row['ratio'] for row in comparisons),
            'local_numeric_pass': not problems and not blocked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('derive', 'check'))
    parser.add_argument('input', type=Path)
    parser.add_argument('candidate_or_output', type=Path)
    parser.add_argument('output', type=Path, nargs='?')
    args = parser.parse_args()
    target = args.output if args.command == 'check' else args.candidate_or_output
    if target is None or target.exists():
        parser.error('require a new output file')
    result = derive(args.input) if args.command == 'derive' else check(args.input, args.candidate_or_output)
    if args.command == 'derive':
        result['frozen_at'] = e1.utc()
    e1.write(target, result)
    ok = result.get('eligible', result.get('local_numeric_pass', False))
    print(json.dumps({'output': str(target), 'local_pass': ok, 'problems': result['problems']}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
