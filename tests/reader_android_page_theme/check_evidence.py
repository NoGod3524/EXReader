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
artifact, = [row for row in artifacts if row['name'] == 'reader-android-page-theme-' + run + '-' + attempt]
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
    for path, count in [('host-session-android', 16), ('android-search', 15), ('android-navigation', 18), ('android-reading', 16), ('android-preferences', 17), ('android-cbz-reading', 10), ('android-fixed-pan', 8), ('android-host-import', 20), ('android-page-theme', 10)]:
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
        if path in ('android-preferences','android-page-theme'):
            assert report['page_colors_accepted'] is True
            for phase in report['phases']:
                if path == 'android-page-theme':
                    assert phase['sdk'] == '3.41.0'
                    assert json.loads(read(path+'/ui/'+phase['phase']+'-raw-report.json')) == phase
                for frame in phase['theme_frames']:
                    rgba = read(path+'/ui/theme-frames/'+frame['name']+'.rgba',32*1024**2)
                    png = read(path+'/ui/theme-frames/'+frame['name']+'.png',32*1024**2)
                    assert len(rgba)==frame['width']*frame['height']*4
                    assert hashlib.sha256(rgba).hexdigest()==frame['rgba_sha256']
                    assert hashlib.sha256(png).hexdigest()==frame['png_sha256']
                    from PIL import Image
                    actual_image=Image.open(io.BytesIO(png))
                    assert actual_image.mode=='RGBA' and actual_image.size==(frame['width'],frame['height']) and actual_image.tobytes()==rgba
                    assert rgba[:4].hex()==frame['background_rgba']
                    color=bytes.fromhex(frame['foreground_rgba'])
                    ink=sum(rgba[at:at+4]==color for at in range(0,len(rgba),4))
                    assert ink==frame['solid_ink_pixels'] and ink>10
                    assert frame['frame']['page_theme']['sdk']=='3.41.0' and frame['frame']['page_theme']['enabled'] is True
                    for point in frame.get('preserved_samples',[]):
                        at=(point['y']*frame['width']+point['x'])*4
                        assert rgba[at:at+4].hex()==point['rgba']
                        boxes=frame['frame']['theme_boxes'];base=point['layout_box']*10
                        x,y,width,height=[boxes[base+k]/1000 for k in (4,5,6,7)]
                        assert width>=8 and height>=8 and point['x']==int(x+width/2) and point['y']==int(y+height/2)
                        if point['kind']=='png':
                            assert point['rgba']=='1478dcff' and boxes[base]==2 and boxes[base+8]==0x1478dcff
                        else:
                            assert point['kind']=='author-background' and point['rgba']=='e0b070ff' and boxes[base+2]==0xe0b070ff
            if path=='android-page-theme':
                samples=[point for phase in report['phases'] for frame in phase['theme_frames'] for point in frame.get('preserved_samples',[])]
                assert {'png','author-background'}=={row['kind'] for row in samples}
                anchors=[anchor for phase in report['phases'] for anchor in phase['anchors']]
                assert anchors and all(row['parser']=='exreader-sdk-3.41.0' and row['bookmark_found'] is True and row['highlight_found'] is True for row in anchors)
        reports.append({'suite': path, 'checks': count, 'report_sha256': hashlib.sha256(raw).hexdigest()})
    apk = read('examples/android/app/build/outputs/apk/debug/app-debug.apk', 128 * 1024**2)
    native=json.loads(read('android-page-theme/native/result.json'))
    assert all(native.get(key)==value for key,value in identity.items()) and native['accepted'] is True and native['installed_sdk']=='3.41.0'
    assert native['single_shared_sdk_needed'] is True and native['actual_background_import'] is True and native['sdk340_public_header_rejected'] is True
    providers=json.loads(read('host-session-android/native/result.json'))
    assert all(providers.get(key)==value for key,value in identity.items()) and providers['accepted'] is True
    assert providers['no_static_sdk_or_sqlite_in_host'] is True and providers['product_provider_isolated'] is True
result = {**identity, 'accepted': True, 'scope': 'API34 default x86_64 Android SDK3.41 actual page theme plus 120 inherited business checks', 'checks': 130, 'producer_job': producer['id'], 'artifact': {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}, 'apk_sha256': hashlib.sha256(apk).hexdigest(), 'reports': reports, 'physical_device': False, 'third_party_cloud_provider': False, 'complete_product': False, 'performance_accepted': False}
output = Path('build/android-page-theme-summary/summary.json')
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
