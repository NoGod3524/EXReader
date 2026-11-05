"""Actions-only source admission and honest provider readiness; not a product test."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OWN = 'tests/migration/windows_p0_fault_acceptance_20261030/'
EXACT = {
    'tools/reader_composition/windows_p0_fault_independent_20261030.py',
    '.github/workflows/windows-p0-fault-20261030.yml',
    'docs/WINDOWS-P0-FAULT-20261030.md',
}
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    contract = json.loads((HERE / 'contract.json').read_text())
    source = git('rev-parse', 'HEAD')
    assert source == os.environ['GITHUB_SHA']
    subprocess.run(['git', 'merge-base', '--is-ancestor', contract['base'], source], cwd=ROOT, check=True)
    changed = git('diff', '--name-only', contract['base'], source).splitlines()
    assert changed and all(p.startswith(OWN) or p in EXACT for p in changed), changed
    frozen = {}
    for path in contract['frozen']:
        original = git('rev-parse', contract['base'] + ':' + path)
        current = git('rev-parse', source + ':' + path)
        assert current == original, ('frozen source changed', path)
        frozen[path] = current
    # No dynamic executable or untrusted provider command can be supplied by a report.
    # Provider binding requires reviewed source code, interface pins and a new commit.
    assert contract['providers'] == dict(migration=None, publication=None, host=None)
    cases = [dict(id=case, status='pending', passed=False,
                  reason='actual installed provider and phase-observable runner not bound')
             for case in contract['case_ids']]
    assert len(cases) == 10 and len({x['id'] for x in cases}) == 10
    report = dict(schema=1, kind='windows-p0-fault-readiness',
        source_sha=source, run_id=os.environ['GITHUB_RUN_ID'],
        attempt=os.environ['GITHUB_RUN_ATTEMPT'], source_admitted=True,
        product_tests_executed=False, accepted=False, cases=cases,
        frozen_objects=frozen, changed_paths=changed,
        contract_sha256=hashlib.sha256((HERE / 'contract.json').read_bytes()).hexdigest(),
        full_p0_acceptance=False, physical_power_loss_qualified=False,
        directory_fsync_equivalent=False)
    out = ROOT / 'build/windows-p0-fault-readiness'
    out.mkdir(parents=True, exist_ok=False)
    (out / 'readiness.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(source_admitted=True, pending=10, accepted=False)))
if __name__ == '__main__':
    main()
