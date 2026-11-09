"""Fail-closed CPU cost gate: 0 pass, 1 measured regression, 2 invalid evidence.

Warnings do not fail. >=20% CPU fails, >=35% is hard failure; wall >=3x
is a catastrophic watchdog. Neither means exclusive-runner user latency passed.
"""
import argparse
import json
from pathlib import Path
import sys
from sample import audit, p95, read, sha, write, PLAN, ROOT
from refresh_baseline import TIERS, WALL_HARD


def check(baseline, folder, local=False):
    if baseline.get('status') != 'frozen' or baseline.get('schema') != 1:
        raise ValueError('no frozen baseline')
    if not local and baseline['scope'] != 'github-ubuntu-latest':
        raise ValueError('local baseline cannot authorize CI')
    if baseline['tiers'] != TIERS or baseline['wall_hard_multiplier'] != WALL_HARD or baseline['plan'] != PLAN:
        raise ValueError('unreviewed threshold or plan change')
    expected = {b['id']: b['sha256'] for b in read(ROOT / 'tools/regress/corpus.json')['books']}
    if baseline['input_sha256'] != expected or set(baseline['books']) != set(expected):
        raise ValueError('baseline must cover the frozen 19-book corpus')
    data, books, signatures = audit(folder)
    if data['compatibility'] != baseline['compatibility'] or data['input_sha256'] != expected:
        raise ValueError('environment/toolchain/workload mismatch: independent requalification required')
    if data['created_utc'] <= baseline['frozen_utc']:
        raise ValueError('candidate must be sampled after baseline freeze')
    if signatures != baseline['signatures']:
        raise ValueError('pixel/text/position signatures changed')
    if not local:
        gh = data['github']
        if gh['GITHUB_ACTIONS'] != 'true' or not gh['GITHUB_RUN_ID'] or gh['GITHUB_SHA'] != data['source_revision']:
            raise ValueError('candidate lacks GitHub source/run provenance')
        if data['fault_book'] or any(b['injected_fraction'] for b in books.values()):
            raise ValueError('fault injection is qualification-only')
    rows = []
    for book, observed in books.items():
        base = baseline['books'][book]
        if base['samples'] != 48 or observed['samples'] != 48:
            raise ValueError('wrong sample count')
        p95([base['thread_cycles_p95'], base['wall_ms_p95']])  # validate positive finite budgets
        ratio = observed['thread_cycles_p95'] / base['thread_cycles_p95']
        wall = observed['wall_ms_p95'] / base['wall_ms_p95']
        exceeded = [tier for tier, limit in TIERS.items() if ratio >= limit]
        if wall >= WALL_HARD:
            exceeded.append('wall_hard')
        rows.append({'id': book, 'baseline_cycles_p95': base['thread_cycles_p95'],
                     **observed, 'cycle_ratio': ratio, 'wall_ratio': wall, 'exceeded': exceeded})
    failed = [r['id'] for r in rows if any(t in r['exceeded'] for t in ('gate', 'hard', 'wall_hard'))]
    return {'status': 'fail' if failed else 'pass', 'exit_code': int(bool(failed)),
            'scope': 'local' if local else 'github-ubuntu-latest', 'failed_books': failed,
            'candidate_capture_sha256': sha(Path(folder) / 'capture.json'),
            'worst_cycle_ratio': max(r['cycle_ratio'] for r in rows),
            'worst_wall_ratio': max(r['wall_ratio'] for r in rows),
            'exceeded': [r for r in rows if r['exceeded']], 'books': rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path)
    p.add_argument('capture', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--local', action='store_true')
    args = p.parse_args()
    try:
        result = check(read(args.baseline), args.capture, args.local)
        result['baseline_sha256'] = sha(args.baseline)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        result = {'status': 'fail', 'exit_code': 2, 'invalid_evidence': str(exc)}
    write(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'books'}))
    return result['exit_code']


if __name__ == '__main__':
    sys.exit(main())
