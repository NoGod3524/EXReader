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
result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
print(result.stdout, end="", flush=True)
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
invalid_report = (a.kind == 'g13' and not accepted and result.returncode == 1
                  and any(line.startswith('INVALID REPORT: unevaluated checks ')
                          and 'cannot coexist with audit_completed' in line
                          for line in result.stdout.splitlines()))
expected_exit = (0 if accepted or '--require-accepted' not in command else 2) if a.kind == 'g13' else (0 if accepted else 1)
assert invalid_report or result.returncode == expected_exit, ('unexpected historical process outcome', result.returncode, expected_exit)
# This is a preserved historical validator rejection, never a valid audit.
# Current audit/gate are executed separately and must satisfy every check.

evidence = dict(source_sha=r['source_sha'], run_id=r['run_id'], attempt=r['attempt'],
                kind=a.kind, historical_accepted=accepted, historical_report_valid=not invalid_report,
                validator_output=result.stdout, exit_code=result.returncode,
                command=command, report_sha256=hashlib.sha256(a.report.read_bytes()).hexdigest(),
                interpretation='historical evidence only; not current acceptance')
(a.report.parent / ('execution-self-test.json' if '--self-test' in command else 'execution.json')).write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps(evidence), flush=True)
