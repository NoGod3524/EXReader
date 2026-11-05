"""Actions-only authenticated raw-ZIP readiness audit. Never grants product acceptance."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def read_archive(raw):
    assert len(raw) <= 16 * 1024 * 1024, 'ZIP bound'
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries = z.infolist()
        assert len(entries) <= 100
        names = [i.filename for i in entries]
        assert len(names) == len(set(names)), 'duplicate ZIP names'
        total = 0
        for item in entries:
            p = PurePosixPath(item.filename)
            assert not p.is_absolute() and '..' not in p.parts
            assert '\\' not in item.filename and ':' not in item.filename
            assert ((item.external_attr >> 16) & 0o170000) != 0o120000
            assert item.file_size <= 2 * 1024 * 1024
            total += item.file_size
            assert total <= 8 * 1024 * 1024
        reports = [i for i in entries if i.filename == 'readiness.json']
        assert len(reports) == 1 and len(entries) == 1, names
        return json.loads(z.read(reports[0]))
def verify_readiness(report, source, run, attempt):
    assert report['schema'] == 1 and report['kind'] == 'windows-p0-fault-readiness'
    assert (report['source_sha'], str(report['run_id']), str(report['attempt'])) == (source, str(run), str(attempt))
    assert report['source_admitted'] is True and report['product_tests_executed'] is False
    for flag in ('accepted', 'full_p0_acceptance', 'physical_power_loss_qualified', 'directory_fsync_equivalent'):
        assert report[flag] is False, flag
    cases = report['cases']
    assert len(cases) == 10 and {c['id'] for c in cases} == {'M%02d' % n for n in range(1, 11)}
    assert all(c['status'] == 'pending' and c['passed'] is False and c['reason'] for c in cases)
    assert report['frozen_objects'] and report['changed_paths']
    return dict(readiness_audited=True, product_tests_executed=False, accepted=False, pending=10)
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    p = argparse.ArgumentParser()
    for name in ('run', 'attempt', 'job', 'artifact', 'bytes'):
        p.add_argument('--' + name, required=True, type=int)
    for name in ('source', 'sha256', 'artifact-name'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    assert len(a.source) == 40 and set(a.source) <= set('0123456789abcdef')
    assert len(a.sha256) == 64 and set(a.sha256) <= set('0123456789abcdef')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from check_parallel_integration import fetch, download_artifact_zip
    run = fetch('actions/runs/%s/attempts/%s' % (a.run, a.attempt))
    job = fetch('actions/jobs/%s' % a.job)
    assert run['path'].split('@')[0] == '.github/workflows/windows-p0-fault-20261030.yml'
    assert job['name'] == 'readiness'
    assert a.artifact_name == 'windows-p0-fault-readiness-%s-%s' % (a.run, a.attempt)
    assert (run['head_sha'], run['run_attempt'], run['status'], run['conclusion']) == (a.source, a.attempt, 'completed', 'success')
    assert (job['run_id'], job['head_sha'], job['status'], job['conclusion']) == (a.run, a.source, 'completed', 'success')
    assert job['id'] in {j['id'] for j in fetch('actions/runs/%s/attempts/%s/jobs?per_page=100' % (a.run, a.attempt))['jobs']}
    pin = fetch('actions/artifacts/%s' % a.artifact)
    assert not pin['expired'] and pin['name'] == a.artifact_name
    assert (pin['workflow_run']['id'], pin['workflow_run']['head_sha']) == (a.run, a.source)
    assert pin['size_in_bytes'] == a.bytes and pin['digest'] == 'sha256:' + a.sha256
    raw = download_artifact_zip(a.artifact)
    assert len(raw) == a.bytes and digest(raw) == a.sha256
    report = read_archive(raw)
    result = verify_readiness(report, a.source, a.run, a.attempt)
    # Independently recompute source admission, do not trust producer booleans.
    import subprocess
    root = Path(__file__).resolve().parents[2]
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root).decode().strip()
    base = '2743f32a4eccd5823657da19cb4f77f2411424af'
    for path, identity in report['frozen_objects'].items():
        assert git('rev-parse', base + ':' + path) == git('rev-parse', a.source + ':' + path) == identity
    actual = git('diff', '--name-only', base, a.source).splitlines()
    assert actual == report['changed_paths']
    allowed = {'tools/reader_composition/windows_p0_fault_independent_20261030.py',
               '.github/workflows/windows-p0-fault-20261030.yml', 'docs/WINDOWS-P0-FAULT-20261030.md'}
    assert all(x.startswith('tests/migration/windows_p0_fault_acceptance_20261030/') or x in allowed for x in actual)
    contract = subprocess.check_output(['git', 'show', a.source + ':tests/migration/windows_p0_fault_acceptance_20261030/contract.json'], cwd=root)
    assert digest(contract) == report['contract_sha256']
    assert set(report['frozen_objects']) == set(json.loads(contract)['frozen'])
    result.update(source_sha=a.source, run=a.run, attempt=a.attempt, job=a.job,
                  artifact=a.artifact, bytes=a.bytes, sha256=a.sha256)
    out = root / 'build/windows-p0-fault-independent'
    out.mkdir(parents=True, exist_ok=False)
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
if __name__ == '__main__':
    main()
