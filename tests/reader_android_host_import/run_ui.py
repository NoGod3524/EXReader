"""Actions-only same-APK provider, system picker, rotation and actual process-death orchestration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
package = 'org.exreader.host'
source = 'org.exreader.hostimportsource'
identity = {key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
expected = {
    'first': ['real_VIEW_epub_uses_existing_owner_stable_original_and_product_mapping', 'real_SEND_pdf_retains_original_after_staging_release', 'SEND_MULTIPLE_unknown_length_short_reads_and_untrusted_name', 'duplicate_redelivery_preserves_ids_paths_revisions_and_outbox', 'real_system_DocumentsUI_SAF_selects_granted_provider_document', 'rotation_during_real_provider_copy_keeps_single_process_controller', 'rotation_during_host_SDK_task_acknowledges_old_owner_and_retries_ready', 'user_cancel_before_publication_rolls_back_sdk_and_preserves_product', 'visible_copy_cancel_survives_rotation_and_preserves_sdk_product', 'provider_midstream_error_and_underreported_size_never_publish_prefix', '128MiB_staging_does_not_raise_32MiB_host_reading_limit'],
    'kill-copy': ['prepare_real_process_kill_during_unfinished_provider_copy'],
    'recover-copy': ['fresh_process_cleans_partial_and_requires_real_URI_redelivery'],
    'kill-stable': ['prepare_real_process_kill_with_unfinished_stable_host_copy'],
    'recover-stable': ['fresh_process_removes_stable_copy_partial_and_recovers_private_ready'],
    'kill-ready': ['prepare_real_process_kill_after_staging_before_host_publication'],
    'recover-ready': ['fresh_process_recovers_ready_without_provider_URI_permission', 'replayed_intent_after_recovery_is_exactly_idempotent'],
    'kill-published': ['prepare_real_process_kill_after_stable_path_publication'],
    'recover-published': ['fresh_process_repairs_mapping_then_releases_ready_and_reuses_stable_source'],
}

def adb(*args, input=None, timeout=90):
    return subprocess.check_output(['adb', *map(str, args)], input=input, stderr=subprocess.STDOUT, timeout=timeout)

def save(name, data):
    target = a.output / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

def private(name):
    return adb('exec-out', 'run-as', package, 'cat', 'files/' + name)

def reset():
    assert adb('shell', 'pm', 'clear', package).strip() == b'Success'
    adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
    adb('shell', 'am', 'force-stop', package)
    adb('shell', f"run-as {package} sh -c 'cat > files/host-import-input.json'", input=json.dumps(fixtures).encode())

pattern = b'0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ \n'
fixtures = {}
for role, length in [('short', 300000), ('evil', 1000), ('seekable', 70000), ('slow', 2 * 1024 * 1024), ('rotating', 11000), ('stable', 12000), ('ready', 8000), ('published', 9000)]:
    body = (pattern * ((length + len(pattern) - 1) // len(pattern)))[:length]
    fixtures[role] = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
for role, name in [('epub', 'cover-import.epub'), ('pdf', 'pdf-public.pdf')]:
    body = (Path('tests/fixtures') / name).read_bytes()
    fixtures[role] = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
save('independent-expected-sources.json', (json.dumps(fixtures, indent=2) + '\n').encode())
reports, captures, stops = [], [], []
apk_identities = []
accepted = False
try:
    adb('install', '-r', '-t', 'tests/reader_android_host_import/source/build/outputs/apk/debug/hostimportsource-debug.apk')
    for installed_package, artifact_path in [(package, 'examples/android/app/build/outputs/apk/debug/app-debug.apk'), (package + '.test', 'build/android-host-import/test-apks/host-import-ui.apk'), (source, 'tests/reader_android_host_import/source/build/outputs/apk/debug/hostimportsource-debug.apk')]:
        expected_apk_sha = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
        installed_path, = [line.removeprefix('package:') for line in adb('shell', 'pm', 'path', installed_package).decode().splitlines() if line.startswith('package:') and line.endswith('/base.apk')]
        installed_sha = adb('shell', 'sha256sum', installed_path).decode().split()[0]
        assert installed_sha == expected_apk_sha
        apk_identities.append({'package': installed_package, 'artifact_path': artifact_path, 'sha256': expected_apk_sha, 'installed_path': installed_path, 'installed_sha256': installed_sha})
    # The artifact basename follows the Gradle project name, not its directory name.
    reset()
    for phase, names in expected.items():
        if phase.startswith('kill-'):
            reset()
        adb('shell', 'am', 'force-stop', package)
        adb('logcat', '-c')
        command = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'phase', phase]
        for key, value in identity.items():
            command.extend(('-e', key, value))
        command.append(package + '.test/' + package + '.HostImportUiTest')
        boundary_stop = None
        if phase.startswith('kill-'):
            # Keep instrumentation alive at the observed boundary, then kill its actual PID externally.
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                present = subprocess.run(['adb', 'exec-out', 'run-as', package, 'test', '-f', 'files/host-import-' + phase + '.boundary'], capture_output=True, timeout=10)
                if present.returncode == 0:
                    break
                if process.poll() is not None:
                    break
                time.sleep(.1)
            boundary = json.loads(private('host-import-' + phase + '.json'))
            if boundary['passed'] is not True:
                output, _ = process.communicate(timeout=30)
                save(phase + '-instrumentation.txt', output)
                save(phase + '-failed-report.json', json.dumps(boundary, ensure_ascii=False, indent=2).encode())
                save(phase + '-logcat.txt', adb('logcat', '-d', '-v', 'threadtime', '-t', '4000'))
                print(json.dumps(boundary, ensure_ascii=False), flush=True)
                raise AssertionError('device boundary check failed')
            before = adb('shell', 'pidof', package).decode().strip()
            assert boundary['passed'] is True and str(boundary['pid']) in before.split()
            adb('shell', 'am', 'force-stop', package)
            after = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
            assert not after
            boundary_stop = {'phase': phase, 'instrumentation_pid': boundary['pid'], 'pid_before_stop': before, 'pid_after_stop': after, 'force_stop': True, 'held_boundary': True}
            document = {'kill-copy': 'txt-slow', 'kill-stable': 'txt-stable', 'kill-ready': 'txt-ready', 'kill-published': 'txt-published'}[phase]
            adb('shell', 'am', 'broadcast', '-f', '32', '-n', source + '/.ControlReceiver', '--es', 'cmd', 'revoke', '--es', 'doc', document)
            output, _ = process.communicate(timeout=30)
            process = subprocess.CompletedProcess(command, process.returncode, output)
        else:
            process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900, check=False)
        save(phase + '-instrumentation.txt', process.stdout)
        save(phase + '-logcat.txt', adb('logcat', '-d', '-v', 'threadtime', '-t', '4000'))
        raw = private('host-import-' + phase + '.json')
        save(phase + '-raw-report.json', raw)
        report = json.loads(raw)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        reports.append(report)
        for observation in report['observations']:
            if 'capture' in observation:
                name = observation['capture']
                png = private('host-import-captures/' + name + '.png')
                assert png.startswith(b'\x89PNG\r\n\x1a\n') and len(png) > 1000
                save('captures/' + name + '.png', png)
                captures.append({'name': name, 'bytes': len(png), 'sha256': hashlib.sha256(png).hexdigest(), 'package': observation['package']})
            if 'book' in observation:
                observed = observation['book']
                declared = fixtures[observation['role']]
                assert observed['sha256'] == declared['sha256'] and observed['bytes'] == declared['bytes']
                retained = adb('exec-out', 'run-as', package, 'cat', observed['path'])
                assert len(retained) == declared['bytes'] and hashlib.sha256(retained).hexdigest() == declared['sha256']
        assert all(report.get(key) == value for key, value in identity.items())
        assert report['phase'] == phase and report['passed'] is True and report['count'] == len(names)
        assert [item['name'] for item in report['checks']] == names and all(item['pass'] is True for item in report['checks'])
        if boundary_stop:
            assert ('HOST_IMPORT_BOUNDARY_READY ' + phase).encode() in process.stdout
        else:
            assert process.returncode == 0 and ('HOST_IMPORT_PASS ' + phase).encode() in process.stdout and b'INSTRUMENTATION_CODE: -1' in process.stdout
        before = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
        adb('shell', 'am', 'force-stop', package)
        after = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
        assert not after
        stops.append(boundary_stop or {'phase': phase, 'instrumentation_pid': report['pid'], 'pid_before_stop': before, 'pid_after_stop': after, 'force_stop': True})
    assert len({report['pid'] for report in reports}) == len(reports)
    assert any(item['name'] == 'system-documentsui' and item['package'] == 'com.android.documentsui' for item in captures)
    accepted = True
finally:
    result = {**identity, 'accepted': accepted, 'api': 34, 'abi': 'x86_64', 'checks': sum(report['count'] for report in reports), 'phases': reports, 'captures': captures, 'process_stops': stops, 'apk_identities': apk_identities, 'physical_device': False, 'third_party_cloud_provider': False, 'performance_accepted': False, 'complete_product': False, 'reading_limit_bytes': 32 * 1024 * 1024}
    save('result.json', (json.dumps(result, indent=2, ensure_ascii=False) + '\n').encode())
