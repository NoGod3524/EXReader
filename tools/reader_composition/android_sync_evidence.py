# SPDX-License-Identifier: MIT
"""Actions-only verification of the original Android sync account evidence."""
import hashlib, io, json, os, zipfile
from check_parallel_integration import fetch, pages, download_artifact_zip

RUN = 40630302205
SOURCE = 'c33455a957b02c4e64bf1d5a466b633f51b71ba7'
ARTIFACT = 12792577560
SIZE = 137243021
SHA = '4361cd2866edc0a4faf970c761842d987d4acba4d23bc71e605741b62db95e47'
REQUIRED = {
    'account-status/first-report.json': {
        'initial_read_only_status', 'authentication_failure_visible',
        'correct_credentials_cancel_and_retry', 'forget_keeps_binding'},
    'wave3/first-report.json': {'sync_status_view_without_session_and_real_failed_session'},
}
def verify():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    run = fetch('actions/runs/%d/attempts/1' % RUN)
    assert run['id'] == RUN and run['run_attempt'] == 1 and run['head_sha'] == SOURCE
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    jobs = pages('actions/runs/%d/attempts/1/jobs' % RUN, 'jobs')
    android, = [job for job in jobs if job['name'] == 'android']
    assert android['status'] == 'completed' and android['conclusion'] == 'success'
    steps = {step['name']: step for step in android['steps']}
    for name in ('Exercise account failure cancellation retry and status on API 34',
                 'Execute original C11 navigation and reading suites',
                 'Execute unchanged original sync UI and session regression',
                 'Execute strict 3.41 sync UI adapter'):
        assert steps[name]['status'] == 'completed' and steps[name]['conclusion'] == 'success'
    meta = fetch('actions/artifacts/%d' % ARTIFACT)
    assert meta['id'] == ARTIFACT and meta['expired'] is False
    assert meta['name'] == 'android-organization-sync-build-40630302205-1'
    assert meta['workflow_run']['id'] == RUN and meta['workflow_run']['head_sha'] == SOURCE
    assert meta['size_in_bytes'] == SIZE and meta['digest'] == 'sha256:' + SHA
    raw = download_artifact_zip(ARTIFACT)
    assert len(raw) == SIZE and hashlib.sha256(raw).hexdigest() == SHA
    checked = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        for suffix, required in REQUIRED.items():
            matches = [name for name in names if name.endswith(suffix)]
            assert len(matches) == 1, (suffix, matches)
            report = json.loads(archive.read(matches[0]))
            assert report['source_sha'] == SOURCE and str(report['run_id']) == str(RUN)
            assert str(report['attempt']) == '1' and report['phase'] == 'first' and report['passed'] is True
            rows = report['checks']
            passed = {row['name'] for row in rows if row.get('pass') is True}
            assert required <= passed, (suffix, sorted(required - passed))
            assert report['count'] == len(rows)
            checked[suffix] = sorted(required)
    return {'source': SOURCE, 'run': RUN, 'attempt': 1, 'artifact': ARTIFACT,
            'zip_sha256': SHA, 'verified_cases': checked,
            'scope_basis': 'API 34 emulator UI reports and retained suites in the same pinned run'}
