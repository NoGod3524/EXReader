#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only bounded anchor diagnostic; preserves every process and failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
import generate_bounded_chapter_corpus as corpus


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', choices=['release', 'gprof'], required=True)
    parser.add_argument('--baseline-binary', type=Path)
    parser.add_argument('--baseline-engine', type=Path)
    args = parser.parse_args()
    if not os.environ.get('GITHUB_ACTIONS'):
        parser.error('Run only in GitHub Actions')
    args.output.mkdir(parents=True, exist_ok=False)
    binary, font, engine = args.binary.resolve(), args.font.resolve(), args.engine.resolve()
    sha = subprocess.check_output(['git', '-C', str(engine), 'rev-parse', 'HEAD'], text=True).strip()
    tree = subprocess.check_output(['git', '-C', str(engine), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    report = {'schema': 1, 'diagnostic_only': not bool(args.baseline_binary), 'optimization_accepted': False,
              'engine_sha': sha, 'engine_tree': tree, 'tool_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'profile': args.profile, 'disk_cache': 'uncontrolled', 'warmup': 0,
              'threads': 1, 'environment': platform.platform(), 'binary_sha256': digest(binary),
              'font_sha256': digest(font), 'probe_sha256': digest(ROOT/'tools/r4_anchor_probe.c'),
              'runner_sha256': digest(__file__), 'generator_sha256': digest(corpus.__file__),
              'records': [], 'cases': {}}
    binaries = {'candidate': binary}
    if bool(args.baseline_binary) != bool(args.baseline_engine):
        parser.error('Both baseline binary and engine are required for comparison')
    if args.baseline_binary:
        binaries['baseline'] = args.baseline_binary.resolve()
        report['baseline_engine_sha'] = subprocess.check_output(
            ['git', '-C', str(args.baseline_engine), 'rev-parse', 'HEAD'], text=True).strip()
    report['binaries'] = {role: {'sha256': digest(path), 'bytes': path.stat().st_size}
                          for role, path in binaries.items()}
    plans = [(1, 16384, 0), (4, 16384, 0), (4, 4194304, 0), (4, 16384, 64)]
    if args.profile == 'gprof':
        plans = [(4, 16384, 0)]
    for mib, window, quote in plans:
        name = f'chapter-{mib}MiB.epub'
        book = args.output/name
        if not book.exists():
            corpus.write_epub(book, mib*1024*1024, 1, corpus.Counter())
        key = f'{mib}MiB-window{window}-quote{quote}'
        records = []
        for repeat in range(1 if args.profile == 'gprof' else 3):
            roles = list(reversed(binaries)) if repeat % 2 == 0 else list(binaries)
            for role in roles:
                stem = f'{key}-{repeat+1}-{role}'
                stdout, stderr = args.output/(stem+'.json'), args.output/(stem+'.stderr')
                command = [str(binaries[role]), str(book.resolve()), str(font), str(window), str(quote)]
                record = {'role': role, 'repeat': repeat+1, 'command': command,
                          'book_sha256': digest(book), 'exit': None,
                          'stdout': stdout.name, 'stderr': stderr.name, 'result': None}
                try:
                    with stdout.open('wb') as out, stderr.open('wb') as err:
                        completed = subprocess.run(command, stdout=out, stderr=err, timeout=120,
                                                   cwd=args.output.resolve())
                    record['exit'] = completed.returncode
                    record['result'] = json.loads(stdout.read_text())
                except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                    record['failure'] = type(error).__name__
                record.update(stdout_sha256=digest(stdout), stderr_sha256=digest(stderr))
                records.append(record)
                report['records'].append(record)
        good = all(r['exit'] == 0 and r['result'] and r['result']['status'] == 0 and
                   r['result']['sdk'] == '3.40.0' and r['result']['abi'] == 1 and
                   r['result']['same_match'] and r['result']['same_pages'] and
                   r['result']['snapshot_bytes'] == 0 for r in records)
        medians = {role: {metric: statistics.median(r['result'][metric] for r in records if r['role'] == role)
                           for metric in ('create_ms', 'resolve_ms', 'snapshot_resolve_ms',
                                          'resolve_windows_loaded', 'bounded_peak_rss_bytes', 'peak_workspace_bytes')}
                   for role in binaries} if good else None
        case = {'passed': good, 'samples': len(records), 'median': medians}
        if good and args.baseline_binary:
            case['same_results'] = all(len({json.dumps(r['result'][name], sort_keys=True) for r in records}) == 1
                                      for name in ('match_state', 'expected_state', 'page_hashes', 'projection_bytes'))
            case['resolve_ratio'] = medians['candidate']['resolve_ms']/medians['baseline']['resolve_ms']
            case['comparison_passed'] = (case['same_results'] and case['resolve_ratio'] < .25 and
                medians['candidate']['peak_workspace_bytes'] <= medians['baseline']['peak_workspace_bytes'] and
                medians['candidate']['bounded_peak_rss_bytes'] <= medians['baseline']['bounded_peak_rss_bytes']*1.05+1048576)
        report['cases'][key] = case
    report['diagnostic_completed'] = all(c['passed'] for c in report['cases'].values())
    report['identity_stable'] = (digest(binary) == report['binary_sha256'] and digest(font) == report['font_sha256'] and
        subprocess.check_output(['git', '-C', str(engine), 'rev-parse', 'HEAD'], text=True).strip() == sha and
        subprocess.run(['git', '-C', str(engine), 'diff', '--quiet', 'HEAD']).returncode == 0 and
        all(digest(path) == report['binaries'][role]['sha256'] for role, path in binaries.items()))
    if args.baseline_binary:
        report['size_passed'] = report['binaries']['candidate']['bytes'] <= report['binaries']['baseline']['bytes']+4096
        report['optimization_accepted'] = (report['diagnostic_completed'] and report['identity_stable'] and
            report['size_passed'] and all(c.get('comparison_passed') for c in report['cases'].values()))
    (args.output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'records'}, indent=2))
    return 0 if (report['optimization_accepted'] if args.baseline_binary else
                 report['diagnostic_completed'] and report['identity_stable']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
