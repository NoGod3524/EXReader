"""Actions-only original artifact authentication and real-app evidence audit."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
sys.path.insert(0, str(Path(__file__).parent))
from relay import identity

ID = identity()
out = ROOT / 'build/apple-android/summary.json'
out.parent.mkdir(parents=True, exist_ok=True)
summary = {**ID, 'accepted': False, 'failures': [], 'artifacts': [],
    'same_online_service': False, 'same_apple_sandbox': False,
    'physical_devices': False, 'scope': 'iPhone Simulator -> Android API 34 x86_64 emulator -> fresh iPhone Simulator; staged authenticated HTTPS snapshots',
    'all_platform_F02_F04_accepted': False}

def digest(data): return hashlib.sha256(data).hexdigest()
def check_id(value):
    assert all(str(value[key]) == expected for key, expected in ID.items()), 'source/run/attempt mismatch'

def report_suffix(archive, suffix):
    names = [name for name in archive.namelist() if name == suffix or name.endswith('/' + suffix)]
    assert len(names) == 1, 'report missing or ambiguous: ' + suffix
    value = json.loads(archive.read(names[0])); check_id(value)
    assert value['accepted'] is True, suffix
    return value

def artifact(prefix, rows):
    name = prefix + '-' + ID['run_id'] + '-' + ID['attempt']
    matches = [row for row in rows if row['name'] == name and not row['expired']]
    assert len(matches) == 1, name + ': missing or duplicate'
    row = matches[0]
    assert row['workflow_run']['head_sha'] == ID['source_sha']
    raw = download_artifact_zip(row['id'])
    assert len(raw) == row['size_in_bytes'] and 'sha256:' + digest(raw) == row['digest'], name
    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = archive.namelist()
    assert len(names) == len(set(names))
    assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
    summary['artifacts'].append({key: row[key] for key in ('id', 'name', 'digest', 'size_in_bytes')})
    return archive

try:
    jobs = fetch('actions/runs/' + ID['run_id'] + '/attempts/' + ID['attempt'] + '/jobs?per_page=100')['jobs']
    expected = {'android', 'retained', 'Relay Apple installed macos', 'Relay Apple installed iphonesimulator',
        'Relay retained iPhone native suites', 'Apple imports reads and uploads original and position',
        'Android receives resolves moves and syncs back', 'Apple receives Android position and resolves in public SDK'}
    producers = [row for row in jobs if row['name'] in expected]
    summary['jobs'] = [{key: row[key] for key in ('id', 'name', 'head_sha', 'status', 'conclusion')} for row in producers]
    assert {row['name'] for row in producers} == expected, 'producer job set incomplete'
    assert all(row['head_sha'] == ID['source_sha'] and row['conclusion'] == 'success' for row in producers), 'retained or relay job not successful'
    artifacts = fetch('actions/runs/' + ID['run_id'] + '/artifacts?per_page=100')['artifacts']
    original = artifact('relay-original', artifacts)
    provenance = json.loads(original.read('provenance.json')); check_id(provenance)
    book = original.read('epub-alice.epub')
    sha = '4f81245d31380ac1d6eafb9a321e3691369bc70985736ae4bccf849a4f784036'
    assert digest(book) == sha and len(book) == 189249
    assert provenance['sha256'] == sha and provenance['entry']['kind'] == 'real'
    previous = None; states = []; phase_rows = []
    for phase, prefix in [('apple-first', 'relay-apple-first'), ('android', 'relay-android'), ('apple-return', 'relay-apple-return')]:
        archive = artifact(prefix, artifacts)
        raw = archive.read('state.json'); state = json.loads(raw); check_id(state)
        assert state['phase'] == phase and state['schema'] == 1
        assert state['previous_sha256'] == (digest(previous) if previous is not None else None)
        assert state['server']['base'].startswith('https://127.0.0.1:')
        assert state['server']['certificate_sha256'] == digest(archive.read('cert.pem'))
        assert state['server']['implementation_sha256'] == digest((ROOT / 'tests/apple_android_relay/relay.py').read_bytes())
        assert state['server']['dav_implementation_sha256'] == digest((ROOT / 'tests/reader_d23_relay/relay.py').read_bytes())
        data = state['data']; check_id(data)
        assert data['passed'] is True and data['physical_device'] is False
        assert data['original_sha256'] == sha and data['original_bytes'] == len(book) and data['book_identity'] == 'epub:' + sha
        entries = {path: base64.b64decode(value['body'], validate=True) for path, value in state['entries'].items()}
        assert all(digest(body) == state['entries'][path]['sha256'] for path, body in entries.items())
        objects = [body for path, body in entries.items() if '/objects/' in path]
        assert objects == [book], 'one original is relayed without replacing bytes'
        if states:
            assert all(state['entries'].get(path) == value for path, value in states[-1]['entries'].items()), 'prior app revisions overwritten'
        requests = json.loads(archive.read('requests.json'))
        assert requests and all(row['authenticated'] for row in requests)
        if phase != 'apple-first': assert any(row['method'] == 'GET' and '/objects/' in row['path'] for row in requests)
        if phase != 'apple-return': assert any(row['method'] == 'PUT' and '/revisions/' in row['path'] for row in requests)
        progress = [json.loads(body) for path, body in entries.items() if '/revisions/' in path
                    and json.loads(body).get('entity_kind') == 'progress']
        assert progress and all(r['entity_key'] == 'epub:' + sha for r in progress)
        loc = data['location']
        matching = [r for r in progress if r.get('payload')
            and r['payload']['location'].get('part_path') == loc['path']
            and r['payload']['location'].get('part') == loc['part']
            and all(r['payload']['location']['selector'][key] == loc[key]
                    for key in ('start', 'end', 'exact', 'prefix', 'suffix'))]
        assert len(matching) == 1, 'displayed/captured location lacks exact application-authored remote revision'
        if phase == 'android':
            assert matching[0]['id'] == loc['head']
            assert data['incoming_location']['head'] in matching[0]['parents'], 'Android update did not descend from Apple progress'
        checks = data['checks']; assert len(checks) == len(set(checks))
        if phase == 'android':
            assert checks == ['empty_library_real_account_and_sync', 'explicit_application_receive_original',
                'apple_progress_public_parse_real_jump', 'real_forward_pages_and_application_save', 'application_sync_outgoing_position']
            assert data['api'] == 34 and data['abi'] == 'x86_64'
            boundary = data['independent_boundary_tests']
            assert boundary['passed'] is True and boundary['app_database_seeded'] is False
            assert 0 <= boundary['all_empty_failed_ms'] < 20000
            assert boundary['leases_after_empty_failure'] == boundary['leases_after_image_discard'] == 0
            assert boundary['image_leases_live'] > 0 and boundary['image_boxes'] > 0
            cover = data['initial_frame']
            assert cover['part'] == boundary['image_part'] and cover['start'] == cover['end'] == 0
            assert cover['bounded_visual_boxes'] > 0 and cover['bitmap_width'] > 0 and cover['bitmap_height'] > 0
            assert all(data['incoming_location'][k] == states[0]['data']['location'][k] for k in ('part', 'path', 'start', 'end', 'exact', 'prefix', 'suffix'))
            assert data['location']['head'] != data['incoming_location']['head']
            frame = data['restored_frame']; loc = data['incoming_location']
            assert frame['part'] == loc['part'] and frame['path'] == loc['path']
            assert frame['start'] <= loc['start'] < frame['end'], 'real displayed page must contain original anchor'
        else:
            assert len(checks) == 3 and len(data['cases']) == 1 and data['cases'][0]['result'] == 'Passed'
            assert all(command['exit'] == 0 for command in data['commands'])
            assert data['program']['bundle_source_sha'] == ID['source_sha'] and data['program']['bundle_id'] == 'org.exreader.host'
            with zipfile.ZipFile(io.BytesIO(archive.read('program.zip'))) as program:
                binary = program.read('EXReaderHost.app/EXReaderHost')
                assert digest(binary) == data['program']['sha256'] and len(binary) == data['program']['bytes']
            if phase == 'apple-return':
                assert all(data['location'][k] == states[1]['data']['location'][k] for k in ('part', 'path', 'start', 'end'))
        states.append(state); previous = raw
        phase_rows.append({'phase': phase, 'snapshot_sha256': digest(raw), 'checks': checks, 'location': data['location']})
    retained = artifact('relay-apple-retained', artifacts)
    d21 = report_suffix(retained, 'd21-receive/iphone/result.json')
    assert len(d21['cases']) == 1 and d21['cases'][0]['result'] == 'Passed'
    assert all(row['exit'] == 0 for row in d21['commands'])
    # Upload roots are build/, preserving both original evidence locations.
    apple_reports = [json.loads(retained.read(n)) for n in retained.namelist()
        if n.endswith('/evidence/result.json') or n == 'team24-apple/iphone/evidence/result.json']
    assert len(apple_reports) == 1
    report = apple_reports[0]; check_id(report); assert report['accepted']
    assert {phase['mode']: phase['expected_cases'] for phase in report['phases']} == {'wave3': 5, 'base': 13, 'control': 13, 'search': 4, 'theme': 4}
    assert all(phase['accepted'] and all(case['result'] == 'Passed' for case in phase['cases']) for phase in report['phases'])
    runtime = artifact('d22-runtime', artifacts)
    apk = runtime.read('artifacts/app-debug.apk')
    assert states[1]['data']['program']['sha256'] == digest(apk)
    assert states[1]['data']['program']['bytes'] == len(apk)
    assert states[1]['data']['program']['installed_equals_same_run_apk'] is True
    android_retained = artifact('d22-retained', artifacts)
    for suite in ('original-sync', 'sync-341'):
        retained_report = report_suffix(android_retained, 'evidence/' + suite + '/result.json')
        assert retained_report['api'] == 34 and retained_report['abi'] == 'x86_64'
        assert len(retained_report['phases']) == 4 and all(phase['passed'] for phase in retained_report['phases'])
    android_receive = artifact('d22-android-receive', artifacts)
    receive_report = report_suffix(android_receive, 'evidence/d22-receive/result.json')
    assert receive_report['checks'] == 24 and len(receive_report['phases']) == 4
    assert all(phase['passed'] for phase in receive_report['phases'])
    report_suffix(android_receive, 'evidence/organization-sync/result.json')
    summary.update(accepted=True, original_sha256=sha, original_bytes=len(book), phases=phase_rows)
except Exception as error:
    summary['failures'].append(type(error).__name__ + ': ' + str(error))
finally:
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)
assert summary['accepted'], 'relay or retained evidence not accepted'
