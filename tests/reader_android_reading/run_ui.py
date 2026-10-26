"""Actions-only real Android product-reading controls, kill/retry and evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--fixtures', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
identity = {key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
package = 'org.exreader.host'
expected = {
    'first': ['same_sdk_product_sqlite_and_installed_g03_g04', 'read_only_empty_list_preserves_sdk_product_and_pixels',
              'real_txt_progress_and_point_bookmark_do_not_write_sdk', 'real_txt_selection_highlight_and_note_edit_keep_selector',
              'explicit_current_found_navigation_renders_without_sdk_note_copy', 'delete_and_explicit_retained_restore_do_not_auto_navigate',
              'epub_actual_capture_keeps_spine_path_and_current_font', 'pdf_and_cbz_real_page_id_points',
              'missing_legacy_nul_and_fixed_page_id_are_never_guessed', 'unsafe_graphs_display_counts_without_exposing_or_choosing_heads',
              'stale_selected_head_never_overwrites_new_head', 'cancel_real_capture_keeps_stores_and_actual_frame',
              'close_rotation_background_drop_real_pending_reads', 'bounded_record_pagination_and_plain_text_labels',
              'saved_bookmark_survives_cancelled_refresh', 'saved_bookmark_survives_failed_refresh',
              'conflict_remains_reachable_with_saved_bookmarks'],
    'retry': ['real_process_kill_after_commit_replays_identical_request_without_duplicate'],
    'reopen': ['process_reopen_retains_reading_graph_and_releases_old_panels'],
}


def adb(*args, input=None, timeout=90):
    return subprocess.check_output(['adb', *map(str, args)], input=input, stderr=subprocess.STDOUT, timeout=timeout)


def private(name):
    return adb('exec-out', 'run-as', package, 'cat', 'files/' + name)


def save(name, data):
    path = a.output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def command(phase):
    result = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'phase', phase]
    for key, value in identity.items():
        result.extend(('-e', key, value))
    result.append(package + '.test/' + package + '.ReadingUiTest')
    return result


manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
reports, captures, sources, stops = [], [], [], []
accepted = False
kill = None
try:
    assert adb('shell', 'pm', 'clear', package).strip() == b'Success'
    adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
    adb('shell', 'am', 'force-stop', package)
    adb('exec-out', 'run-as', package, 'mkdir', '-p', 'files/reading-fixtures')
    adb('logcat', '-c')
    for row in manifest['books']:
        data = (a.fixtures / row['file']).read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
        temporary = '/data/local/tmp/reader-reading-' + row['file']
        adb('push', a.fixtures / row['file'], temporary)
        adb('exec-out', 'run-as', package, 'cp', temporary, 'files/reading-fixtures/' + row['file'])
    adb('shell', f"run-as {package} sh -c 'cat > files/reading-input.json'", input=json.dumps(manifest, ensure_ascii=False).encode())
    for phase in ('first', 'crash', 'retry', 'reopen'):
        adb('shell', 'am', 'force-stop', package)
        if phase == 'crash':
            process = subprocess.Popen(command(phase), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    present = subprocess.run(['adb', 'exec-out', 'run-as', package, 'cat', 'files/reading-crash-ready'], capture_output=True, timeout=10)
                    if present.returncode == 0 and present.stdout == b'\x01':
                        break
                    assert process.poll() is None, 'crash instrumentation ended before actual commit boundary'
                    time.sleep(.15)
                else:
                    raise AssertionError('actual postcommit boundary not reached')
                pending = private('reading-request.json')
                request = json.loads(pending)
                assert request['body'] == 'lost response exact request' and request['operation'] == 0
                pid = adb('shell', 'pidof', package).decode().strip()
                assert pid
                save('killed-pending-request.json', pending)
                adb('shell', 'am', 'force-stop', package)
                after = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
                assert not after
                kill = {'actual_postcommit_gate': True, 'pid_before_stop': pid, 'pid_after_stop': after,
                        'request_sha256': hashlib.sha256(pending).hexdigest(), 'revision_id': request['revision'],
                        'annotation_id': request['annotation'], 'request_bytes': len(pending)}
            finally:
                try:
                    raw = process.communicate(timeout=60)[0]
                except subprocess.TimeoutExpired:
                    process.kill()
                    raw = process.communicate(timeout=10)[0]
                save('crash-instrumentation.txt', raw)
                save('crash-logcat.txt', adb('logcat', '-d', '-v', 'threadtime', '-t', '3000'))
            continue
        names = expected[phase]
        try:
            process = subprocess.run(command(phase), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1200, check=False)
            raw = process.stdout
        except subprocess.TimeoutExpired as error:
            save(phase + '-instrumentation.txt', error.stdout or b'')
            raise
        save(phase + '-instrumentation.txt', raw)
        report = json.loads(private('reading-ui-' + phase + '.json'))
        save(phase + '-report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
        print(json.dumps({'phase': phase, 'expected': names, 'actual': report['checks'], 'failed_check': report.get('failed_check'),
                          'failure': report.get('failure'), 'failure_trace': report.get('failure_trace'), 'observations': report['observations']}, ensure_ascii=False), flush=True)
        logcat = adb('logcat', '-d', '-v', 'threadtime', '-t', '3000')
        save(phase + '-logcat.txt', logcat)
        if report['passed'] is not True:
            print('\n'.join(line for line in logcat.decode(errors='replace').splitlines() if 'EXRHost' in line or 'AndroidRuntime' in line), flush=True)
        for observation in report['observations']:
            image = private('reading-captures/' + observation['name'] + '.png')
            assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image) > 1000
            save('captures/' + phase + '-' + observation['name'] + '.png', image)
            captures.append({'phase': phase, 'name': observation['name'], 'bytes': len(image), 'sha256': hashlib.sha256(image).hexdigest(), 'nodes': observation['nodes']})
        assert process.returncode == 0 and all(report.get(key) == value for key, value in identity.items())
        assert report['phase'] == phase and report['passed'] is True
        assert [check['name'] for check in report['checks']] == names and all(check['pass'] is True for check in report['checks']) and report['count'] == len(names)
        assert ('READING_UI_PASS ' + phase).encode() in raw and b'INSTRUMENTATION_CODE: -1' in raw
        reports.append(report)
        for row in manifest['books']:
            original = private('reading-fixtures/' + row['file'])
            assert len(original) == row['bytes'] and hashlib.sha256(original).hexdigest() == row['sha256']
            sources.append({'phase': phase, 'file': row['file'], 'bytes': len(original), 'sha256': row['sha256']})
        pid = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
        assert not pid or str(report['pid']) in pid.split()
        adb('shell', 'am', 'force-stop', package)
        after = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
        assert not after
        stops.append({'phase': phase, 'instrumentation_pid': report['pid'], 'pid_before_stop': pid,
                      'ended_with_instrumentation': not bool(pid), 'pid_after_stop': after, 'requested': True})
    assert len({report['pid'] for report in reports}) == 3 and sum(report['count'] for report in reports) == 19 and kill
    accepted = True
finally:
    result = {**identity, 'accepted': accepted, 'checks': sum(report['count'] for report in reports), 'phases': reports,
              'captures': captures, 'sources': sources, 'process_stops': stops, 'real_postcommit_kill': kill,
              'api': 34, 'abi': 'x86_64', 'physical_device': False, 'reading_ui_accepted': accepted,
              'performance_accepted': False, 'complete_product': False, 'talkback_speech_accepted': False}
    save('result.json', (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({**identity, 'accepted': accepted, 'checks': result['checks'], 'phases': len(reports)}, ensure_ascii=False), flush=True)
