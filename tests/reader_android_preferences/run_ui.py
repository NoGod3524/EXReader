"""Actions-only actual F3 settings UI, process reopen and retained palette failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--fixtures', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
identity = {key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
package = 'org.exreader.host'
expected = {
    'first': ['installed_f3_defaults_and_explicit_legacy_import', 'txt_real_relayout_preserves_public_found_point',
              'invalid_fields_keep_previous_file_model_and_pixels', 'sdk_composed_geometry_failure_keeps_last_settings',
              'cancel_prepublication_discards_candidate_and_file', 'real_atomic_save_io_failure_keeps_accepted_page',
              'bounded_and_legacy_epub_keep_projection_and_part', 'fixed_pdf_and_cbz_zoom_real_pixels_same_page',
              'rtl_and_vertical_taps_follow_saved_preferences', 'swipe_only_ignores_taps_and_turns_on_vertical_swipe',
              'hardware_input_ignores_touch_and_uses_actual_key_event', 'dark_page_gap_is_recorded_and_not_saved_as_success',
              'system_resolver_and_saved_light_system_preference', 'unknown_version_truncation_and_oversize_load_preserve_bytes',
              'actual_rotation_cancels_unpublished_settings'],
    'reopen': ['fresh_process_loads_saved_f3_and_actual_layout'],
    'night': ['actual_system_dark_resolves_but_does_not_fake_page_palette'],
}


def adb(*args, input=None, timeout=90):
    return subprocess.check_output(['adb', *map(str, args)], input=input, stderr=subprocess.STDOUT, timeout=timeout)


def private(name):
    return adb('exec-out', 'run-as', package, 'cat', 'files/' + name)


def save(name, data):
    path = a.output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
reports, captures, sources, stops = [], [], [], []
accepted = False
try:
    adb('shell', 'cmd', 'uimode', 'night', 'no')
    assert adb('shell', 'pm', 'clear', package).strip() == b'Success'
    adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
    adb('shell', 'am', 'force-stop', package)
    adb('exec-out', 'run-as', package, 'mkdir', '-p', 'files/preferences-fixtures')
    adb('logcat', '-c')
    for row in manifest['books']:
        data = (a.fixtures / row['file']).read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
        temporary = '/data/local/tmp/reader-preferences-' + row['file']
        adb('push', a.fixtures / row['file'], temporary)
        adb('exec-out', 'run-as', package, 'cp', temporary, 'files/preferences-fixtures/' + row['file'])
    adb('shell', f"run-as {package} sh -c 'cat > files/preferences-input.json'", input=json.dumps(manifest, ensure_ascii=False).encode())
    saved_identity = None
    for phase, names in expected.items():
        adb('shell', 'am', 'force-stop', package)
        if phase == 'night':
            adb('shell', 'cmd', 'uimode', 'night', 'yes')
        command = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'phase', phase]
        for key, value in identity.items():
            command.extend(('-e', key, value))
        command.append(package + '.test/' + package + '.PreferencesUiTest')
        try:
            process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1500, check=False)
            raw = process.stdout
        except subprocess.TimeoutExpired as error:
            save(phase + '-instrumentation.txt', error.stdout or b'')
            raise
        save(phase + '-instrumentation.txt', raw)
        report = json.loads(private('preferences-ui-' + phase + '.json'))
        save(phase + '-report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
        print(json.dumps(report, ensure_ascii=False), flush=True)
        logcat = adb('logcat', '-d', '-v', 'threadtime', '-t', '3000')
        save(phase + '-logcat.txt', logcat)
        if report['passed'] is not True:
            print('\n'.join(line for line in logcat.decode(errors='replace').splitlines() if 'EXRHost' in line or 'AndroidRuntime' in line), flush=True)
        for observation in report['observations']:
            data = private('preferences-captures/' + observation['name'] + '.png')
            assert data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) > 1000
            save('captures/' + phase + '-' + observation['name'] + '.png', data)
            captures.append({'phase': phase, 'name': observation['name'], 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'nodes': observation['nodes']})
        assert process.returncode == 0 and all(report.get(key) == value for key, value in identity.items())
        assert report['phase'] == phase and report['passed'] is True and report['page_colors_accepted'] is False
        assert [check['name'] for check in report['checks']] == names and all(check['pass'] is True for check in report['checks']) and report['count'] == len(names)
        assert ('PREFERENCES_UI_PASS ' + phase).encode() in raw and b'INSTRUMENTATION_CODE: -1' in raw
        if phase in ('first', 'night'):
            gap = report['retained_color_failure']
            assert gap['accepted'] is False and gap['actual_corner_rgba'] != gap['requested_background_rgba'] and gap['user_css_attempted'] and gap['public_api_gap']
        reports.append(report)
        preferences = private('reading-settings/preferences.json')
        declared = json.loads(preferences)
        assert declared['theme'] == 'system'
        actual = {'bytes': len(preferences), 'sha256': hashlib.sha256(preferences).hexdigest()}
        if saved_identity is None:
            saved_identity = actual
        else:
            assert saved_identity == actual
        save(phase + '-preferences.json', preferences)
        for row in manifest['books']:
            original = private('preferences-fixtures/' + row['file'])
            assert len(original) == row['bytes'] and hashlib.sha256(original).hexdigest() == row['sha256']
            sources.append({'phase': phase, 'file': row['file'], 'bytes': len(original), 'sha256': row['sha256']})
        pid = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
        assert not pid or str(report['pid']) in pid.split()
        adb('shell', 'am', 'force-stop', package)
        after = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
        assert not after
        stops.append({'phase': phase, 'instrumentation_pid': report['pid'], 'pid_before_stop': pid, 'pid_after_stop': after})
    assert len({report['pid'] for report in reports}) == 3 and sum(report['count'] for report in reports) == 17
    accepted = True
finally:
    adb('shell', 'cmd', 'uimode', 'night', 'no')
    result = {**identity, 'accepted': accepted, 'scope': 'declared Android local settings and controls only',
              'checks': sum(report['count'] for report in reports), 'phases': reports, 'captures': captures,
              'sources': sources, 'process_stops': stops, 'api': 34, 'abi': 'x86_64', 'physical_device': False,
              'page_colors_accepted': False, 'performance_accepted': False, 'complete_product': False,
              'talkback_speech_accepted': False}
    save('result.json', (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({**identity, 'accepted': accepted, 'checks': result['checks'], 'phases': len(reports), 'page_colors_accepted': False}), flush=True)
