"""Measured CPU work plus raw wall latency; Windows thread-cycle sandwich v2.

Reuses v1's input hashes, 19-book plan, signatures and integrity validation.
No fitted coefficients and no trimming. v1 wall ratios remain diagnostics.
"""
import argparse
import math
from pathlib import Path
import sys

from ratio_capture import ROOT, TIERS, capture, read, summarize as wall_summary
from e1_capture import percentile, stats, sha, write


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def metrics(samples, sandwich):
    before, after, target = [], [], []
    for s in samples:
        m = s['load']
        for name in ('target', 'layout', 'render'):
            if any(not isinstance(m[name][k], int) or isinstance(m[name][k], bool) or m[name][k] < 0
                   for k in ('cycles', 'tsc', 'cpu_100ns', 'switches')):
                raise ValueError('invalid native counter')
        if any(m['target'][k] != m['layout'][k] + m['render'][k]
               for k in ('cycles', 'tsc', 'cpu_100ns', 'switches')):
            raise ValueError('target phase accounting mismatch')
        if not math.isclose(m['target']['wall_ms'], s['total_ms'], abs_tol=2e-5):
            raise ValueError('wall and cycle boundaries differ')
        if not math.isclose(s['reference_ms'], m['before']['wall_ms'], abs_tol=2e-6):
            raise ValueError('reference wall mismatch')
        for name in (('before', 'after') if sandwich else ('before',)):
            if not all(positive(v) for v in (m[name]['wall_ms'], m[name]['work']['cycles'], m[name]['work']['tsc'])):
                raise ValueError('invalid reference counters')
        # Coverage check only: invariant elapsed TSC must cover the SAME work as
        # wall total, including EOF probes and chapter transitions. Do not turn
        # QueryThreadCycleTime into milliseconds or label TSC as core frequency.
        rate = m['before']['work']['tsc']/m['before']['wall_ms']
        covered_ms = m['target']['tsc']/rate
        if abs(covered_ms-s['total_ms']) > max(.1, .02*s['total_ms']):
            raise ValueError('TSC/wall coverage mismatch (including chapter transitions)')
        a, b, t = m['before']['work']['cycles'], m['after']['work']['cycles'], m['target']['cycles']
        if not all(positive(v) for v in (a, t)) or (sandwich and not positive(b)):
            raise ValueError('missing/nonpositive/nonfinite cycle observations')
        before.append(a); after.append(b if sandwich else a); target.append(t)
    reference = [math.sqrt(a*b) for a, b in zip(before, after)]
    p95 = lambda xs: percentile(xs, 95)
    return {'target_cycles': p95(target), 'reference_cycles': p95(reference),
            'before_cycles': p95(before), 'after_cycles': p95(after),
            'ratio': p95(target)/p95(reference),
            'one_sided_cycle_ratio': p95(target)/p95(before),
            'wall_ratio': p95([s['total_ms'] for s in samples])/p95([s['reference_ms'] for s in samples]),
            'wall_sandwich_ratio': p95([s['total_ms'] for s in samples])/p95([
                math.sqrt(s['load']['before']['wall_ms'] * s['load']['after']['wall_ms'])
                if sandwich else s['reference_ms'] for s in samples]),
            'target_ms': p95([s['total_ms'] for s in samples]),
            'reference_ms': p95([s['reference_ms'] for s in samples]),
            'target_switches': sum(s['load']['target']['switches'] for s in samples),
            'reference_switches': sum(s['load']['before']['work']['switches'] for s in samples),
            'layout_cycle_fraction': sum(s['load']['layout']['cycles'] for s in samples)/sum(target),
            'target_charged_fraction': sum(target)/sum(s['load']['target']['tsc'] for s in samples),
            'reference_charged_fraction': sum(before)/sum(s['load']['before']['work']['tsc'] for s in samples)}


def summarize(directory):
    directory = Path(directory)
    wall = wall_summary(directory)  # validates every raw hash and page signature
    manifest = read(directory/'capture.json')
    sandwich = manifest['plan']['load_mode'] == 'sandwich'
    runs = []
    if [r['index'] for r in manifest['runs']] != list(range(1, len(manifest['runs'])+1)):
        raise ValueError('duplicate or missing run index')
    for run in manifest['runs']:
        calibration = read(directory/run['reference_file'])
        cycles = [s['reference']['work']['cycles'] for s in calibration['samples']]
        if len(cycles) != 31 or not all(positive(v) for v in cycles):
            raise ValueError('invalid calibration cycles')
        pooled, books = [], {}
        for book in run['books']:
            raw = read(directory/book['file'])
            samples = [s for s in raw['samples'] if s['phase'] == 'sequential']
            books[book['id']] = metrics(samples, sandwich)
            pooled.extend(samples)
        runs.append({'index': run['index'], 'calibration_cycles': percentile(cycles, 95),
                     'calibration_ms': percentile(calibration['reference_ms'], 95),
                     **metrics(pooled, sandwich), 'books': books})
    summary = {k: stats([r[k] for r in runs]) for k in runs[0] if k not in ('books', 'index')}
    return {'schema': 2, 'advisory': True, 'accepted': False,
            'definition': 'p95(target thread cycles) / p95(sqrt(before cycles * after cycles))' if sandwich
                          else 'diagnostic p95(target thread cycles) / p95(before cycles)',
            'eligible': len(runs) >= 5 and summary['calibration_cycles']['range_over_median_pct'] < 3
                        and summary['ratio']['range_over_median_pct'] < 5,
            'runs': runs, 'statistics': summary, 'signatures': wall['signatures'],
            'per_book': {book: {key: stats([r['books'][book][key] for r in runs])
                               for key in runs[0]['books'][book]} for book in wall['signatures']}}


def freeze(directory, output):
    if output.exists():
        raise ValueError('refusing to overwrite frozen policy')
    report = summarize(directory)
    if read(directory/'capture.json')['plan']['load_mode'] != 'sandwich':
        raise ValueError('diagnostic data cannot freeze a policy')
    anchor = report['statistics']['ratio']['p95']
    policy = {'schema': 2, 'advisory': True, 'accepted': False,
              'eligible': report['eligible'], 'capture_sha256': sha(directory/'capture.json'),
              'capture': read(directory/'capture.json'), 'signatures': report['signatures'],
              'anchor_ratio': anchor, 'thresholds': {k: anchor*v for k, v in TIERS.items()},
              'per_book': {b: {k: r['ratio']['p95']*v for k, v in TIERS.items()}
                           for b, r in report['per_book'].items()}}
    write(output, policy)
    return policy


def check(policy, directory):
    report = summarize(directory)
    a, b = policy['capture'], read(directory/'capture.json')
    compatible = all(a[k] == b[k] for k in ('plan', 'input_sha256', 'compatibility'))
    signature_match = report['signatures'] == policy['signatures']
    failed = [book for book, row in report['per_book'].items()
              if row['ratio']['p95'] > policy['per_book'][book]['gate']]
    exceeded = [k for k, v in policy['thresholds'].items() if report['statistics']['ratio']['p95'] > v]
    return {'advisory': True, 'accepted': False, 'compatible': compatible,
            'signatures_match': signature_match, 'failed_books': failed, 'exceeded': exceeded,
            'baseline_eligible': policy['eligible'], 'candidate_eligible': report['eligible'],
            'local_numeric_pass': compatible and signature_match and policy['eligible'] and report['eligible']
                                  and not failed and not any(k in exceeded for k in ('gate', 'hard'))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('capture')
    for k in ('build', 'font', 'output'):
        c.add_argument('--'+k, type=Path, required=True)
    c.add_argument('--manifest', type=Path, default=ROOT/'tools/regress/corpus.json')
    c.add_argument('--cpu', type=int, default=3)
    c.add_argument('--runs', type=int, default=5)
    c.add_argument('--stress-workers', type=int, choices=(0, 1, 3), default=0)
    c.add_argument('--load-mode', choices=('diagnostic', 'sandwich'), default='sandwich')
    for name in ('summarize', 'freeze', 'check'):
        c = sub.add_parser(name)
        if name == 'check':
            c.add_argument('policy', type=Path)
        c.add_argument('directory', type=Path)
        if name != 'summarize':
            c.add_argument('output', type=Path)
    a = p.parse_args()
    if a.command == 'capture':
        if a.runs < 1:
            p.error('positive runs required')
        a.stress = bool(a.stress_workers)
        capture(a)
    elif a.command == 'summarize':
        write(a.directory/'summary.json', summarize(a.directory))
    elif a.command == 'freeze':
        return int(not freeze(a.directory, a.output)['eligible'])
    else:
        result = check(read(a.policy), a.directory)
        write(a.output, result)
        return int(not result['local_numeric_pass'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
