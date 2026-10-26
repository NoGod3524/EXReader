"""Actions-only actual Android wave3 controls: local fonts, original export, portable annotations,
jump history and the read-only sync status view, with retained evidence."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--fixtures', type=Path, required=True)
p.add_argument('--font', type=Path, required=True)
p.add_argument('--app', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
identity = {key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
package = 'org.exreader.host'
expected = {
    'first': ['stage_cancel_before_and_after_rename_removes_private_files',
              'original_export_cancel_receipt_and_ordinary_exception_under_checkjni',
              'jump_history_back_forward_over_real_search_landing', 'closed_panel_drops_real_pending_jump_peek_on_owner',
              'wave3_surfaces_present_and_no_leases',
              'local_font_saf_import_select_lease_and_release', 'invalid_font_rejected_and_library_unchanged',
              'quick_size_cancel_keeps_accepted_frame_and_stored_appearance',
              'quick_size_settings_failure_keeps_frame_and_stored_appearance',
              'original_export_private_original_receipt_and_saf_save', 'annotation_export_private_files_and_saf_save',
              'annotation_import_wrong_book_rejected_without_write', 'sync_status_view_without_session_and_real_failed_session',
              'rotation_keeps_selected_font_and_releases_leases', 'toc_directory_entry_reaches_real_chapter'],
    'cancel': ['annotation_batch_cancel_retains_committed_receipt_and_stops_remaining_items'],
    'restore': ['annotation_preview_confirm_import_creates_records', 'annotation_reimport_all_duplicates_no_new_rows',
                'tampered_file_rejected_before_any_write', 'imported_bookmark_navigable_by_public_found'],
}


def adb(*args, input=None, timeout=120):
    return subprocess.check_output(['adb', *map(str, args)], input=input, stderr=subprocess.STDOUT, timeout=timeout)


def private(name):
    return adb('exec-out', 'run-as', package, 'cat', 'files/' + name)


def save(name, data):
    path = a.output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def push_private(local, name):
    temporary = '/data/local/tmp/wave3-' + Path(name).name
    adb('push', local, temporary)
    adb('exec-out', 'run-as', package, 'cp', temporary, 'files/' + name)


app_sha256 = hashlib.sha256(a.app.read_bytes()).hexdigest()
checkjni = adb('shell', 'getprop', 'debug.checkjni').decode().strip()
assert checkjni == '1', 'CheckJNI must be enabled before the application starts'
installed_path = adb('shell', 'pm', 'path', package).decode().strip()
assert installed_path.startswith('package:'), installed_path
installed_apk = a.output / 'installed.apk'
subprocess.run(['adb', 'pull', installed_path[len('package:'):].strip(), str(installed_apk)],
               check=True, capture_output=True, timeout=300)
installed_sha256 = hashlib.sha256(installed_apk.read_bytes()).hexdigest()
assert installed_sha256 == app_sha256, 'the device did not install these application bytes'

manifest = json.loads((a.fixtures / 'manifest.json').read_text(encoding='utf-8'))
rows = [row for row in manifest['books'] if row['role'] in ('txt', 'epub')]
assert [row['role'] for row in rows] == ['txt', 'epub'], rows
font_bytes = a.font.read_bytes()
bad = b'This is plain text and not an SDK usable font program.\n'
reports, captures, sources, stops, accepted = [], [], [], [], False


def prepare(extra):
    assert adb('shell', 'pm', 'clear', package).strip() == b'Success'
    adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
    adb('shell', 'am', 'force-stop', package)
    adb('exec-out', 'run-as', package, 'mkdir', '-p', 'files/wave3-fixtures')
    adb('logcat', '-c')
    for row in rows:
        data = (a.fixtures / row['file']).read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
        push_private(a.fixtures / row['file'], 'wave3-fixtures/' + row['file'])
    push_private(a.font, 'wave3-fixtures/' + a.font.name)
    with tempfile.TemporaryDirectory() as folder:
        badfile = Path(folder) / 'not-a-font.txt'
        badfile.write_bytes(bad)
        push_private(badfile, 'wave3-fixtures/not-a-font.txt')
        for name, data in extra.items():
            target = Path(folder) / name
            target.write_bytes(data)
            push_private(target, 'wave3-fixtures/' + name)
    value = {'books': rows, 'font_file': a.font.name, 'font_label': a.font.stem, 'bad_font_file': 'not-a-font.txt',
             'sync_root': 'https://127.0.0.1:9/dav/', 'expected': manifest['expected']}
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'wave3-input.json'
        target.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        push_private(target, 'wave3-input.json')


def instrument(phase):
    adb('shell', 'am', 'force-stop', package)
    command = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'phase', phase]
    for key, value in identity.items():
        command.extend(('-e', key, value))
    command.append(package + '.test/' + package + '.Wave3UiTest')
    try:
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1500, check=False)
    except subprocess.TimeoutExpired as error:
        save(phase + '-instrumentation.txt', error.stdout or b'')
        raise
    raw = process.stdout
    save(phase + '-instrumentation.txt', raw)
    report = json.loads(private('wave3-ui-' + phase + '.json'))
    save(phase + '-report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({'phase': phase, 'expected': expected[phase], 'actual': report['checks'], 'passed': report.get('passed'),
                      'failed_check': report.get('failed_check'), 'failure': report.get('failure'),
                      'failure_trace': report.get('failure_trace')}, ensure_ascii=False), flush=True)
    logcat = adb('logcat', '-d', '-v', 'threadtime')
    save(phase + '-logcat.txt', logcat)
    for observation in report['observations']:
        image = private('wave3-captures/' + observation['name'] + '.png')
        assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image) > 1000
        save('captures/' + phase + '-' + observation['name'] + '.png', image)
        captures.append({'phase': phase, 'name': observation['name'], 'bytes': len(image), 'sha256': hashlib.sha256(image).hexdigest()})
    assert process.returncode == 0 and all(report.get(key) == value for key, value in identity.items())
    assert report['phase'] == phase and report['passed'] is True
    assert [check['name'] for check in report['checks']] == expected[phase] and all(check['pass'] is True for check in report['checks'])
    assert ('WAVE3_UI_PASS ' + phase).encode() in raw and b'INSTRUMENTATION_CODE: -1' in raw
    assert report['font_leases'] == 0, 'a font lease survived the phase'
    assert not re.search(rb'JNI DETECTED ERROR IN APPLICATION|JNI WARNING|JNI call made with exception pending', logcat), 'CheckJNI reported an unsafe JNI call'
    reports.append(report)
    pid = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
    adb('shell', 'am', 'force-stop', package)
    after = subprocess.run(['adb', 'shell', 'pidof', package], capture_output=True, text=True, timeout=10).stdout.strip()
    assert not after
    stops.append({'phase': phase, 'pid_before_stop': pid, 'pid_after_stop': after})
    assert report['passed'] is True, 'phase ' + phase + ' recorded failing checks: ' + json.dumps(
        [check for check in report['checks'] if not check['pass']], ensure_ascii=False)
    return report


try:
    prepare({})
    instrument('first')
    exported = private('wave3-sink/annotations.jsonl')
    assert exported.startswith(b'{') and b'exreader-annotation-export-raw3' in exported and b'wave3 bookmark one' in exported
    save('exported-annotations.jsonl', exported)
    markdown = adb('exec-out', 'run-as', package, 'sh', '-c', 'cat files/annotation-export/*/annotations.md')
    assert markdown, 'private Markdown export retained'
    save('exported-annotations.md', markdown)
    original = private('wave3-sink/original.epub')
    epub = next(row for row in rows if row['role'] == 'epub')
    assert hashlib.sha256(original).hexdigest() == epub['sha256']
    sources.append({'what': 'saf-saved-original', 'bytes': len(original), 'sha256': epub['sha256']})
    needle = b'wave3 bookmark one'
    assert exported.count(needle) >= 1
    tampered = exported.replace(needle, b'wave3 bookmark ONE', 1)
    assert tampered != exported and len(tampered) == len(exported)
    # A fresh data profile receives the same originals: identical global keys, an empty product store.
    prepare({'annotations.jsonl': exported, 'annotations-tampered.jsonl': tampered})
    instrument('cancel')
    prepare({'annotations.jsonl': exported, 'annotations-tampered.jsonl': tampered})
    instrument('restore')
    sources.append({'what': 'portable-annotations', 'bytes': len(exported), 'sha256': hashlib.sha256(exported).hexdigest()})
    accepted = True
finally:
    result = {**identity, 'accepted': accepted, 'apk_sha256': app_sha256, 'installed_apk_sha256': installed_sha256,
              'checks': sum(report['count'] for report in reports), 'phases': reports, 'captures': captures, 'checkjni': checkjni,
              'sources': sources, 'process_stops': stops, 'api': 34, 'abi': 'x86_64', 'physical_device': False, 'wave3_ui_accepted': accepted,
              'picker_mode': 'framework activity-result stubs returning private-file URIs; the system DocumentsUI is not driven for wave3 pickers',
              'share_intent': 'not available: the host manifest declares no content provider',
              'complete_product': False, 'performance_accepted': False, 'talkback_speech_accepted': False}
    save('result.json', (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({**identity, 'accepted': accepted, 'checks': result['checks'], 'phases': len(reports)}, ensure_ascii=False), flush=True)
