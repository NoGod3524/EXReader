#!/usr/bin/env python3
"""Independent auditor for the C01 admission lease. Never grants acceptance.
  --paths BASE   : changed paths since BASE are exactly inside the owned set.
  --receipt DIR  : receipt.json from the Actions-produced evidence is honest."""
import argparse, json, os, pathlib, subprocess, sys
BASE = '2743f32a4eccd5823657da19cb4f77f2411424af'
PREFIXES = ('extras/migration/windows_admission_lease_20261030/', 'tests/migration/windows_admission_lease_20261030/')
EXACT = {'.github/workflows/claude_dot_lease_20261030.yml', 'scripts/audit/claude_dot_lease_20261030.py',
         'docs/reader-total-progress/CLAUDE_DOT_C01_20261030.md'}
CASES = ['shared_cross_process_then_hard_kill_release', 'exclusive_blocks_all_then_graceful_release',
         'prefix32_matching_tail16_distinct_custody', 'generation_gate_stale_after_bump',
         'same_process_second_handle_conflicts', 'non_full49_identity_rejected_without_side_effect',
         'foreign_header_size_hardlink_junction_refused', 'reparse_lease_directory_refused',
         'held_lease_file_delete_and_rename_refused']
def fail(m): print('AUDIT FAIL:', m); sys.exit(1)
ap = argparse.ArgumentParser(); ap.add_argument('--paths'); ap.add_argument('--receipt'); a = ap.parse_args()
if a.paths:
    anc = subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'])
    if anc.returncode: fail('exact base is not an ancestor of HEAD')
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], text=True).splitlines()
    bad = [p for p in changed if not (p.startswith(PREFIXES) or p in EXACT)]
    if not changed or bad: fail(f'paths outside owned set: {bad}')
    print('paths ok', len(changed))
if a.receipt:
    r = json.loads((pathlib.Path(a.receipt) / 'receipt.json').read_text())
    if r['source'] != os.environ['GITHUB_SHA'] or r['run'] != os.environ['GITHUB_RUN_ID']: fail('source/run mismatch')
    if r['passed'] is not True or [c['case'] for c in r['cases']] != CASES or r['case_count'] != len(CASES): fail('case set')
    if not all(c['passed'] is True for c in r['cases']): fail('case failed')
    for k in ('recovery_admission', 'commit_acknowledged', 'full_p0_acceptance', 'physical_power_loss'):
        if r[k] is not False: fail(f'{k} must be false')
    if r['sdk_open_attempts'] != 0 or len(r['probe_sha256']) != 64 or len(r['library_sha256']) != 64: fail('identity')
    print('receipt ok; cases', len(CASES), '; not P0 acceptance')
