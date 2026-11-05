#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""C2 product performance gate: same-source identity, coverage and candidate ceilings.

Reads the evidence written by the existing GTK / Windows samplers (unchanged) after
they ran against the SDK 3.42 hosts built in this run. It adds no measurement, relaxes
no sampler assertion and never grants F08: the candidate ceilings in budgets.json are
unapproved, so `f08_granted` is always false.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDK = '3.42.0'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(source_sha):
    env = {key: os.environ.get(name) for key, name in
           (('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'))}
    return env, bool(env['source_sha']) and source_sha == env['source_sha']


def ceilings(rows):
    """rows: list of (name, observed, maximum, unit, basis)."""
    out = []
    for name, observed, maximum, unit, basis in rows:
        out.append({'metric': name, 'observed': observed, 'max': maximum, 'unit': unit, 'basis': basis,
                    'status': 'passed' if observed is not None and observed <= maximum else 'failed'})
    return out


def gtk(evidence, budgets):
    report, summary = load(evidence / 'report.json'), load(evidence / 'summary.json')
    version = (evidence / 'logs/host-version.txt').read_text().strip()
    env, same = identity(summary['source_sha'])
    checks = [
        {'name': 'sampler-report-accepted', 'status': 'passed' if report['accepted'] else 'failed',
         'detail': report['problems']},
        {'name': 'same-source-run-attempt', 'status': 'passed' if same and report['run_id'] == env['run_id']
         and report['attempt'] == env['attempt'] else 'failed', 'detail': env},
        {'name': 'host-is-sdk-3.42', 'status': 'passed' if version.splitlines()[-1] == SDK + ' 1' else 'failed',
         'detail': version},
    ]
    rows = []
    for metric, spec in budgets['gtk']['latency_p95_ms'].items():
        stat = summary['metrics'].get(metric) or {}
        rows.append((metric + '.p95', stat.get('p95_ms'), spec['max'], 'ms', spec['basis']))
    spec = budgets['gtk']['rss_high_water_max_kb']
    rows.append(('rss.vm_hwm_max', summary['rss'].get('max_kb'), spec['max'], 'KiB', spec['basis']))
    metrics = {name: {'count': value['count'], 'p50_ms': value['p50_ms'], 'p95_ms': value['p95_ms'],
                      'max_ms': value['max_ms']} for name, value in sorted(summary['metrics'].items())}
    payload = summary['environment']['payload']
    return {
        'platform': 'linux-gtk', 'program_sha256': payload.get('binary_sha256'),
        'package_tarball_sha256': (summary['environment'].get('package') or {}).get('tarball_sha256'),
        'launches': summary['launches']['completed'], 'samples': report['samples'],
        'environment': {'os': summary['environment'].get('os'), 'screen': summary['environment'].get('screen')},
        'corpus_books': summary['corpus'].get('books'), 'identity': env, 'checks': checks,
        'candidate_ceilings': ceilings(rows), 'observed_metrics': metrics, 'rss': summary['rss'],
        'frame_time_measured': False,
    }


def windows(evidence, package_build, budgets):
    summary = load(evidence / 'summary.json')
    build = load(package_build)
    env, same = identity(summary['source_sha'])
    checks = [
        {'name': 'sampler-complete', 'status': 'passed' if summary['complete'] else 'failed',
         'detail': {'passed': summary['checks_passed'], 'total': summary['checks_total'],
                    'failed': [k for k, v in summary['checks'].items() if v is not True]}},
        {'name': 'same-source-run-attempt', 'status': 'passed' if same and str(summary['run_id']) == env['run_id']
         and str(summary['attempt']) == env['attempt'] and build.get('source_sha') == env['source_sha']
         else 'failed', 'detail': env},
        {'name': 'package-is-sdk-3.42', 'status': 'passed' if build.get('sdk_version') == SDK else 'failed',
         'detail': build.get('sdk_version')},
    ]
    rows = []
    aggregates = summary['aggregates']
    for key, spec in budgets['windows']['latency_p95_ms'].items():
        cohort, metric = key.split('.')
        stat = (aggregates.get(cohort) or {}).get(metric) or {}
        rows.append((key + '.p95', stat.get('p95'), spec['max'], 'ms', spec['basis']))
    for key, spec in budgets['windows']['peak_working_set_p95_bytes'].items():
        cohort, metric = key.split('.')
        stat = (aggregates.get(cohort) or {}).get(metric) or {}
        rows.append((key + '.p95', stat.get('p95'), spec['max'], 'bytes', spec['basis']))
    cohorts = {c: {m: v for m, v in group.items() if isinstance(v, dict) and 'p95' in v}
               for c, group in aggregates.items()}
    return {
        'platform': 'windows', 'program_sha256': summary['environment']['artifacts'].get('exe_sha256'),
        'launches': summary['measured_process_starts'], 'cohorts': summary['cohorts'],
        'skipped_cohorts': summary.get('skipped_cohorts'), 'txt_path': (summary.get('txt_path') or {}).get('classification'),
        'identity': env, 'checks': checks, 'candidate_ceilings': ceilings(rows),
        'observed_aggregates': cohorts, 'frame_time_measured': False,
    }


def finish(result, budgets, output):
    failed_checks = [c['name'] for c in result['checks'] if c['status'] != 'passed']
    failed_ceilings = [c['metric'] for c in result['candidate_ceilings'] if c['status'] != 'passed']
    result.update({
        'budgets_status': budgets['status'], 'budgets_sha256': sha256(HERE / 'budgets.json'),
        'identity_and_coverage_passed': not failed_checks,
        'candidate_ceilings_passed': not failed_ceilings,
        'failed_checks': failed_checks, 'failed_ceilings': failed_ceilings,
        'not_covered': budgets['not_covered_by_existing_drivers'],
        'f08_granted': False,
        'grant_note': 'Candidate ceilings are unapproved; desktop-only; no frame time; not F01/F07/F08/F12.',
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    for row in result['candidate_ceilings']:
        print('%s %s observed=%s max=%s %s' % (row['status'].upper(), row['metric'], row['observed'],
                                               row['max'], row['unit']))
    print(json.dumps({k: result[k] for k in ('platform', 'identity_and_coverage_passed',
                                              'candidate_ceilings_passed', 'failed_checks', 'failed_ceilings')}))
    return 0 if not failed_checks and not failed_ceilings else 1


def self_test():
    rows = ceilings([('a', 5, 10, 'ms', ''), ('b', 11, 10, 'ms', ''), ('c', None, 10, 'ms', '')])
    assert [r['status'] for r in rows] == ['passed', 'failed', 'failed'], rows
    budgets = load(HERE / 'budgets.json')
    assert budgets['status'] == 'candidate-not-approved'
    assert all(v['max'] > 0 for v in budgets['gtk']['latency_p95_ms'].values())
    print('gate self-test passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('self-test')
    for name in ('gtk', 'windows'):
        p = sub.add_parser(name)
        p.add_argument('--evidence', type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
        if name == 'windows':
            p.add_argument('--package-build', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'self-test':
        return self_test()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('run the gate on GitHub Actions')
    budgets = load(HERE / 'budgets.json')
    result = gtk(args.evidence, budgets) if args.command == 'gtk' else windows(args.evidence, args.package_build, budgets)
    return finish(result, budgets, args.output)


if __name__ == '__main__':
    sys.exit(main())
