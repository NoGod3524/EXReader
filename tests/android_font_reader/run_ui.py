"""Actions-only actual reader font UI and accepted-frame/lease preservation evidence.
Framework picker results are stubbed; no real DocumentsUI acceptance is claimed.
"""
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
expected = ["reader_valid_font_import_select_reopen_changes_pixels", "reader_bad_font_preserves_noninitial_page_position_font_and_lease", "reader_exit_releases_font_lease_and_reopen_keeps_position"]


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

try:
    prepare({})
    command = ['adb', 'shell', 'am', 'instrument', '-w', '-r']
    for key, value in identity.items():
        command.extend(('-e', key, value))
    command.append(package + '.test/' + package + '.FontReaderUiTest')
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900, check=False)
    save('instrumentation.txt', process.stdout)
    report = json.loads(private('font-reader-report.json'))
    reports.append(report)
    save('report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(report, ensure_ascii=False), flush=True)
    logcat = adb('logcat', '-d', '-v', 'threadtime')
    save('logcat.txt', logcat)
    for observation in report['observations']:
        if 'name' not in observation:
            continue
        image = private('wave3-captures/' + observation['name'] + '.png')
        assert image.startswith(b'\x89PNG\r\n\x1a\n') and len(image) > 1000
        save('captures/' + observation['name'] + '.png', image)
        captures.append({'name': observation['name'], 'bytes': len(image), 'sha256': hashlib.sha256(image).hexdigest()})
    assert process.returncode == 0 and all(report.get(key) == value for key, value in identity.items())
    assert report['passed'] is True and report['failed_checks'] == 0
    assert [check['name'] for check in report['checks']] == expected and all(check['pass'] is True for check in report['checks'])
    assert report['count'] == len(expected) and report['font_leases'] == 0
    assert b'FONT_READER_PASS' in process.stdout and b'INSTRUMENTATION_CODE: -1' in process.stdout
    assert not re.search(rb'JNI DETECTED ERROR IN APPLICATION|JNI WARNING|JNI call made with exception pending', logcat)
    assert adb('shell', 'getprop', 'ro.build.version.sdk').decode().strip() == '34'
    accepted = True
finally:
    adb('shell', 'am', 'force-stop', package)
    result = {**identity, 'accepted': accepted, 'apk_sha256': app_sha256, 'installed_apk_sha256': installed_sha256,
              'phases': reports, 'captures': captures, 'checkjni': checkjni, 'api': 34, 'abi': 'x86_64',
              'physical_device': False, 'picker_mode': 'framework activity-result stubs returning private-file URIs; DocumentsUI not driven',
              'book_setup': 'existing C11 SDK import fixture seeding; font import and selection through actual app UI',
              'font_sha256': hashlib.sha256(font_bytes).hexdigest(), 'bad_font_sha256': hashlib.sha256(bad).hexdigest(),
              'originals': rows, 'complete_product': False, 'talkback_speech_accepted': False}
    save('result.json', (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({'source_sha': identity['source_sha'], 'accepted': accepted, 'checks': len(expected)}, ensure_ascii=False), flush=True)
