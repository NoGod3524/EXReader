"""Execute and retain historical outcomes, never call their failures acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--kind', choices=('g13', 'tools'), required=True)
p.add_argument('--report', type=Path, required=True)
p.add_argument('command', nargs=argparse.REMAINDER)
a = p.parse_args()
command = a.command[1:] if a.command[:1] == ['--'] else a.command
assert command
result = subprocess.run(command, check=False)
# An absent/malformed/unbound report is an infrastructure failure, not a
# historical incompatibility; it must still stop the evidence job.
r = json.loads(a.report.read_text())
assert r['source_sha'] == os.environ['GITHUB_SHA']
assert str(r['run_id']) == os.environ['GITHUB_RUN_ID']
assert str(r['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
assert isinstance(r['checks'], list) and r['checks']
if a.kind == 'g13':
    assert r['audit_completed'] is True and len(r['checks']) == 32
    accepted = r['accessibility_accepted']
else:
    accepted = r['accepted']
    assert accepted or r.get('failure'), 'historical failure must retain its original error'
expected_exit = 0 if accepted else (2 if a.kind == 'g13' else 1)
assert result.returncode == expected_exit, ('unexpected historical process outcome', result.returncode, expected_exit)
evidence = dict(source_sha=r['source_sha'], run_id=r['run_id'], attempt=r['attempt'],
                kind=a.kind, historical_accepted=accepted, exit_code=result.returncode,
                command=command, report_sha256=hashlib.sha256(a.report.read_bytes()).hexdigest(),
                interpretation='historical evidence only; not current acceptance')
(a.report.parent / 'execution.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps(evidence), flush=True)
