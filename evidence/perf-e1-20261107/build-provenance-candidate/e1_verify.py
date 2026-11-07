#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strictly audit retained independent samples against an earlier frozen proposal.

Allows inspecting an ineligible baseline, but always rejects it. No recollection
or budget widening occurs. Run after check_e1.py has audited both captures.
"""
import argparse
import json
from pathlib import Path
import sys
from e1_capture import derive_budget, metrics, sha, signatures, summarize, utc, write


def read(path):
    return json.loads(Path(path).read_bytes())


def verify(baseline_dir, candidate_dir):
    baseline, candidate = (read(p / 'samples.json') for p in (baseline_dir, candidate_dir))
    base_env, cand_env = (read(p / 'env.json') for p in (baseline_dir, candidate_dir))
    frozen = read(baseline_dir / 'proposed-budgets.json')
    problems, violations = [], []
    if sha(baseline_dir / 'samples.json') != frozen['samples_sha256']:
        problems.append('baseline samples hash mismatch')
    if derive_budget(base_env, baseline, sha(baseline_dir / 'samples.json')) != frozen:
        problems.append('budget is not derived from retained baseline')
    if not frozen['eligible']:
        problems.append('baseline proposal is ineligible: dispersion or measurement failure')
    if candidate['started_at'] <= baseline['finished_at']:
        problems.append('candidate did not start after baseline completion')
    for key in ('comparison_key', 'source_sha'):
        if base_env[key] != cand_env[key] or frozen[key] != cand_env[key]:
            problems.append('environment/source mismatch: ' + key)
    for key in ('font_sha256', 'input_sha256'):
        if candidate[key] != frozen[key]:
            problems.append('workload mismatch: ' + key)
    if cand_env['identities'][str(Path(candidate['binary']).resolve())] != frozen['binary_sha256']:
        problems.append('binary mismatch')
    if not baseline['measurement_valid'] or not candidate['measurement_valid']:
        problems.append('capture reported a measurement/identity failure')
    if set(candidate['groups']) != set(frozen['limits']):
        problems.append('missing or extra configuration')
    checked = 0
    for name, group in candidate['groups'].items():
        baseline_trial = baseline['groups'][name]['batches'][0]['trials'][0]
        base_raw = baseline_dir / baseline_trial['stdout']
        if sha(base_raw) != baseline_trial['stdout_sha256']:
            problems.append('baseline raw signature source changed: ' + name)
        expected = signatures(read(base_raw))
        if group['final'] != summarize(group['batches'][-1]['trials']) or not group['final']['stable']:
            problems.append('candidate final batch dispersion >=10%: ' + name)
        for batch in group['batches']:
            if batch['summary'] != summarize(batch['trials']):
                problems.append('derived batch statistics changed: ' + name)
            for trial in batch['trials']:
                checked += 1
                if trial.get('exit_code') != 0 or 'metrics' not in trial:
                    problems.append('failed native trial: ' + trial['stdout'])
                    continue
                for field in ('stdout', 'stderr'):
                    if sha(candidate_dir / trial[field]) != trial[field + '_sha256']:
                        problems.append('raw hash mismatch: ' + trial[field])
                raw = read(candidate_dir / trial['stdout'])
                if signatures(raw) != expected:
                    problems.append('RGBA/text/position signature mismatch: ' + trial['stdout'])
                observed = metrics(raw)
                if observed != trial['metrics']:
                    problems.append('derived metrics changed: ' + trial['stdout'])
                for key, value in observed.items():
                    if value > frozen['limits'][name][key]:
                        violations.append({'configuration': name, 'stdout': trial['stdout'], 'metric': key,
                                           'observed': value, 'limit': frozen['limits'][name][key]})
    return {'schema': 1, 'advisory': True, 'accepted': False, 'verified_at': utc(),
        'scope': 'strict local numeric, provenance, deterministic signature and stability audit; not E3 restoration',
        'baseline_samples_sha256': sha(baseline_dir / 'samples.json'),
        'candidate_samples_sha256': sha(candidate_dir / 'samples.json'),
        'frozen_budget_sha256': sha(baseline_dir / 'proposed-budgets.json'), 'verifier_sha256': sha(__file__),
        'independent_processes_checked': checked, 'problems': problems, 'numeric_violations': violations,
        'numeric_within_limits': not violations, 'strict_local_pass': not problems and not violations,
        'e3_restoration_granted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output file must not exist')
    report = verify(args.baseline, args.candidate)
    write(args.output, report)
    print(json.dumps(report, indent=2))
    return 0 if report['strict_local_pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
