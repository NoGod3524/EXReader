"""Rerun the full 19-book plan and freeze an immutable environment-specific baseline.

Default requires genuine GitHub Actions ubuntu-latest provenance. --local writes
local qualification evidence only; it can never produce a CI-qualified baseline.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from sample import arguments, audit, collect, sha, write

TIERS = {'warning': 1.10, 'gate': 1.20, 'hard': 1.35}
WALL_HARD = 3.0


def freeze(folder, output, local=False):
    if output.exists():
        raise ValueError('refusing to overwrite baseline; use a new path and review the diff')
    data, books, signatures = audit(folder)
    host, gh = data['environment']['host'], data['github']
    ci = (gh['GITHUB_ACTIONS'] == 'true' and gh['GITHUB_RUN_ID'] and gh['GITHUB_RUN_ATTEMPT']
          and gh['GITHUB_SHA'] == data['source_revision'] and gh['GITHUB_REPOSITORY'] == 'NoGod3524/EXReader'
          and host['runner_label'] == 'ubuntu-latest' and host['system'] == 'Linux'
          and host['image_os'] and host['image_version'])
    if not local and not ci:
        raise ValueError('CI baseline requires actual GitHub ubuntu-latest capture; local data rejected')
    if data['fault_book'] or any(b['injected_fraction'] for b in books.values()):
        raise ValueError('injected workload cannot freeze a baseline')
    baseline = {'schema': 1, 'status': 'frozen', 'scope': 'local' if local else 'github-ubuntu-latest',
                'frozen_utc': datetime.now(timezone.utc).isoformat(),
                'capture': str(Path(folder).as_posix()), 'capture_sha256': sha(Path(folder) / 'capture.json'),
                'environment': data['environment'], 'compatibility': data['compatibility'],
                'source_revision': data['source_revision'], 'source_trees': data['source_trees'],
                'sdk_sha256': data['sdk_sha256'], 'probe_sha256': data['probe_sha256'],
                'github': gh, 'input_sha256': data['input_sha256'], 'plan': data['plan'],
                'tiers': TIERS, 'wall_hard_multiplier': WALL_HARD, 'books': books, 'signatures': signatures}
    write(output, baseline)
    return baseline


def main():
    p = argparse.ArgumentParser(description=__doc__)
    arguments(p)
    p.add_argument('--baseline', type=Path, default=Path('docs/validation/perf-baseline-ci.json'))
    p.add_argument('--local', action='store_true')
    args = p.parse_args()
    if args.baseline.exists() or args.fault_book:
        p.error('new baseline path and uninjected workload required')
    collect(args)
    freeze(args.output, args.baseline, args.local)
    print(f'frozen: {args.baseline}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
