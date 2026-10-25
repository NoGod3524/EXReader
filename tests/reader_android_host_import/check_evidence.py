"""Actions-only authentication of the one producer ZIP before reading same-source host reports."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
identity = {key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
repo = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/'
run, attempt, source = identity['run_id'], identity['attempt'], identity['source_sha']

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', repo + path]))

record = api('actions/runs/' + run)
assert record['head_sha'] == source and record['run_attempt'] == int(attempt)
jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
producer, = [job for job in jobs if job['name'] == 'android']
assert producer['head_sha'] == source and producer['status'] == 'completed' and producer['conclusion'] == 'success'
artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
artifact, = [row for row in artifacts if row['name'] == 'reader-android-host-import-' + run + '-' + attempt]
assert artifact['workflow_run']['id'] == int(run) and artifact['workflow_run']['head_sha'] == source
assert not artifact['expired'] and 0 < artifact['size_in_bytes'] <= 512 * 1024**2
assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
body = subprocess.check_output(['gh', 'api', repo + 'actions/artifacts/' + str(artifact['id']) + '/zip'])
assert len(body) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(body).hexdigest() == artifact['digest']
reports = []
with zipfile.ZipFile(io.BytesIO(body)) as archive:
    names = archive.namelist()
    assert len(names) <= 30000 and len(names) == len(set(names))
    def read(suffix, maximum=16 * 1024**2):
        name, = [name for name in names if name.endswith(suffix)]
        info = archive.getinfo(name)
        assert 0 < info.file_size <= maximum
        return archive.read(name)
    for path, count in [('host-session-android', 16), ('android-search', 15), ('android-navigation', 18), ('android-reading', 16), ('android-preferences', 17), ('android-cbz-reading', 10), ('android-fixed-pan', 8), ('android-host-import', 20)]:
        raw = read(path + '/ui/result.json')
        report = json.loads(raw)
        assert all(report.get(key) == value for key, value in identity.items())
        assert report['accepted'] is True and report['checks'] == count
        assert report['api'] == 34 and report['abi'] == 'x86_64' and report['physical_device'] is False
        assert sum(phase['count'] for phase in report['phases']) == count
        for phase in report['phases']:
            assert phase['passed'] is True and phase['count'] == len(phase['checks'])
            assert all(row['pass'] is True for row in phase['checks'])
        if path == 'android-host-import':
            assert report['reading_limit_bytes'] == 32 * 1024**2
            assert report['marker_protocol']['present_exit_code'] == 0 and report['marker_protocol']['absent_exit_code'] != 0
            assert len(report['phases']) == 9 and len({phase['pid'] for phase in report['phases']}) == 9
            held = [stop for stop in report['process_stops'] if stop.get('held_boundary')]
            assert len(held) == 4 and all(str(stop['instrumentation_pid']) in stop['pid_before_stop'].split() and not stop['pid_after_stop'] for stop in held)
            assert {stop['phase'] for stop in held} == {'kill-copy', 'kill-stable', 'kill-ready', 'kill-published'}
            for stop in held:
                marker_body = read(path + '/ui/' + stop['phase'] + '-boundary-marker.json')
                marker = json.loads(marker_body)
                assert marker == stop['boundary_marker'] and hashlib.sha256(marker_body).hexdigest() == stop['marker_sha256']
                assert all(marker.get(key) == value for key, value in identity.items()) and marker['phase'] == stop['phase'] and marker['pid'] == stop['instrumentation_pid']
                raw_boundary = read(path + '/ui/' + stop['phase'] + '-raw-report.json')
                assert len(raw_boundary) == marker['report_bytes'] and hashlib.sha256(raw_boundary).hexdigest() == marker['report_sha256']
            all_checks = []
            for phase in report['phases']:
                raw_phase = json.loads(read(path + '/ui/' + phase['phase'] + '-raw-report.json'))
                assert raw_phase == phase and all(raw_phase.get(key) == value for key, value in identity.items())
                all_checks.extend(row['name'] for row in raw_phase['checks'])
            assert len(all_checks) == len(set(all_checks)) == 20
            assert len(report['apk_identities']) == 3
            assert {apk['package'] for apk in report['apk_identities']} == {'org.exreader.host', 'org.exreader.host.test', 'org.exreader.hostimportsource'}
            for apk in report['apk_identities']:
                assert apk['sha256'] == apk['installed_sha256'] == hashlib.sha256(read(apk['artifact_path'], 128 * 1024**2)).hexdigest()
            assert any(capture['name'] == 'system-documentsui' and capture['package'] == 'com.android.documentsui' for capture in report['captures'])
        reports.append({'suite': path, 'checks': count, 'report_sha256': hashlib.sha256(raw).hexdigest()})
    apk = read('examples/android/app/build/outputs/apk/debug/app-debug.apk', 128 * 1024**2)
result = {**identity, 'accepted': True, 'scope': 'API34 default x86_64 Android actual host imports and unchanged inherited suites only', 'checks': 120, 'producer_job': producer['id'], 'artifact': {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}, 'apk_sha256': hashlib.sha256(apk).hexdigest(), 'reports': reports, 'physical_device': False, 'third_party_cloud_provider': False, 'complete_product': False, 'performance_accepted': False}
output = Path('build/android-host-import-summary/summary.json')
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
