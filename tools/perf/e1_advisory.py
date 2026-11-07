#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check numeric reachability of existing R3 budgets locally; no cross-OS acceptance.

Recover the eight exact inputs from the existing digest-pinned artifact, without
launching a workflow. Reuse its pure archive verifier, not its Actions-only runner.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from e1_capture import ROOT, encoded, load_snapshot, output, percentile, run, sha, stats, utc, write
sys.path.insert(0, str(ROOT / 'tools/reading_corpus'))
from frozen import restore_archive, verify_origin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--env', type=Path, required=True, help='E1 env.json from this binary/source')
    parser.add_argument('--archive', type=Path, required=True, help='Ignored build directory for downloaded ZIP')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output directory must not exist')
    args.output.mkdir(parents=True)
    (args.output / 'raw').mkdir()
    fingerprint = json.loads(args.env.read_bytes())
    if fingerprint['identities'][str(args.binary.resolve())] != sha(args.binary) or fingerprint['source_sha'] != output(['git', 'rev-parse', 'HEAD']):
        raise ValueError('Environment belongs to another binary/source')
    write(args.output / 'env.json', fingerprint)
    registry_path = ROOT / 'tools/reading_corpus/frozen-inputs.json'
    registry = json.loads(registry_path.read_bytes())
    api = 'repos/' + registry['repository'] + '/'
    origin = json.loads(output(['gh', 'api', api + 'actions/runs/' + str(registry['run_id'])]))
    metadata = json.loads(output(['gh', 'api', api + 'actions/artifacts/' + str(registry['artifact_id'])]))
    verify_origin(registry, origin, [metadata])
    write(args.output / 'artifact-metadata.json', metadata)
    write(args.output / 'origin-run.json', origin)
    if not args.archive.exists():
        fetched = run(['gh', 'api', api + 'actions/artifacts/' + str(registry['artifact_id']) + '/zip'], timeout=180)
        if fetched.returncode:
            raise RuntimeError(fetched.stderr.decode(errors='replace'))
        args.archive.write_bytes(fetched.stdout)
    manifest_path = ROOT / 'tools/reading_corpus/real-v1.json'
    inputs, origins = restore_archive(args.archive.read_bytes(), manifest_path.read_bytes(), registry)
    input_dir = args.archive.parent / 'real-inputs'
    for name, data in inputs.items():
        path = input_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    env = dict(os.environ, E1_WIDTH='800', E1_HEIGHT='1000', E1_MARGIN='32',
               E1_CPU=str(fingerprint['affinity']['logical_cpu']),
               E1_PRIORITY=fingerprint['affinity'].get('priority', 'normal'), OMP_NUM_THREADS='1')
    budget_paths = [ROOT / 'tests/reading_real/budgets.json',
                    *sorted((ROOT / 'tests/reading_real/environments').glob('*/budgets.json'))]
    budgets = {p.parent.name if p.parent.name != 'reading_real' else 'amd-epyc-7763': json.loads(p.read_bytes()) for p in budget_paths}
    report = {'schema': 1, 'advisory': True, 'accepted': False, 'started_at': utc(),
        'source_sha': output(['git', 'rev-parse', 'HEAD']), 'binary_sha256': sha(args.binary), 'font_sha256': sha(args.font),
        'environment_sha256': sha(args.output / 'env.json'), 'comparison_key': fingerprint['comparison_key'],
        'registry_sha256': sha(registry_path), 'manifest_sha256': sha(manifest_path),
        'budget_sha256': {str(p.relative_to(ROOT)): sha(p) for p in budget_paths}, 'origins': origins,
        'scope': 'Numeric diagnostic only: exact frozen eight inputs/font, R3 timed 32 sequential/16 random at 800x1000 margin32. Five fresh pinned Windows processes. Final reference PPM phase omitted; RSS is for timed plan plus hashes. No Poppler/review/signature baseline enforcement. Linux budgets are ineligible on this Windows CPU/compiler.',
        'cases': {}, 'measurement_valid': True}
    for entry in json.loads(manifest_path.read_bytes())['files']:
        case = {'processes': []}
        report['cases'][entry['id']] = case
        for index in range(1, 6):
            time.sleep(3)
            book = input_dir / entry['path']
            book.read_bytes(); args.font.read_bytes()
            command = [args.binary.resolve(), entry['format'].lower(), book.resolve(), args.font.resolve(), '-', '-']
            prefix = entry['id'] + '-' + str(index)
            trial = {'command': list(map(str, command)), 'started_at': utc(), 'load_before': load_snapshot()}
            result = run(command, env=env, timeout=300)
            stdout, stderr = args.output / 'raw' / (prefix + '.json'), args.output / 'raw' / (prefix + '.stderr.txt')
            stdout.write_bytes(result.stdout); stderr.write_bytes(result.stderr)
            trial.update(exit_code=result.returncode, stdout=str(stdout.relative_to(args.output)), stdout_sha256=sha(stdout),
                         stderr=str(stderr.relative_to(args.output)), stderr_sha256=sha(stderr), load_after=load_snapshot())
            try:
                raw = json.loads(result.stdout)
                if result.returncode or not raw['success'] or len(raw['samples']) != 49:
                    raise ValueError('Incomplete native operation plan')
                measured = {key: raw[key] for key in ('font_open_ms', 'open_ms', 'first_visible_ms', 'peak_rss_bytes')}
                for phase in ('sequential', 'random'):
                    for field in ('layout_ms', 'render_ms', 'total_ms'):
                        values = [s[field] for s in raw['samples'] if s['phase'] == phase]
                        if len(values) != (32 if phase == 'sequential' else 16):
                            raise ValueError('Incomplete phase')
                        measured[phase + '_' + field] = percentile(values, 95)
                trial['metrics'] = measured
            except (KeyError, ValueError, TypeError) as error:
                trial['error'] = str(error)
                report['measurement_valid'] = False
            case['processes'].append(trial)
            print(prefix, trial.get('metrics', trial.get('error')), flush=True)
        good = [p['metrics'] for p in case['processes'] if 'metrics' in p]
        if len(good) == 5:
            case['stats'] = {key: stats([g[key] for g in good]) for key in good[0]}
            case['numeric_comparison'] = {name: {key: {'observed_p95': case['stats'][key]['p95'], 'limit': budget['cases'][entry['id']][key],
                'within': case['stats'][key]['p95'] <= budget['cases'][entry['id']][key]} for key in good[0]}
                for name, budget in budgets.items()}
        write(args.output / 'samples.json', report)
    report['finished_at'] = utc()
    write(args.output / 'samples.json', report)
    lines = ['# Existing R3 numeric reachability', '', report['scope'], '',
             'advisory: true; accepted: false.', '', '| Input | First visible p95 ms | Sequential p95 ms | Random p95 ms | Peak bytes p95 |', '|---|---:|---:|---:|---:|']
    for name, case in report['cases'].items():
        s = case.get('stats')
        if s:
            lines.append(f"| {name} | {s['first_visible_ms']['p95']:.3f} | {s['sequential_total_ms']['p95']:.3f} | {s['random_total_ms']['p95']:.3f} | {s['peak_rss_bytes']['p95']:.0f} |")
    lines += ['', '| Budget environment | Above numeric limits (metric/case) |', '|---|---|']
    for env_name in budgets:
        failures = [f"{name}/{key}" for name, case in report['cases'].items() for key, result in case.get('numeric_comparison', {}).get(env_name, {}).items() if not result['within']]
        lines.append(f"| {env_name} | {', '.join(failures) or 'none'} |")
    (args.output / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    write(args.output / 'manifest.json', {str(p.relative_to(args.output)): sha(p) for p in sorted(args.output.rglob('*')) if p.is_file() and p.name != 'manifest.json'})
    return 0 if report['measurement_valid'] else 1


if __name__ == '__main__':
    sys.exit(main())
