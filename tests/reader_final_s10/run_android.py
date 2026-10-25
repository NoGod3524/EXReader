#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S10 Android: deliver a real file to the existing import owner on an emulator.

The delivered bytes come from the CI fixture, are copied into the emulator with
adb (the CI stand-in for a USB/MTP copy; no cable is involved), and reach the
existing import entry only through a granted content: URI served by this
package's real DocumentsProvider.  The owner then stages, commits into the
installed SDK library and reads the original back.  Only that library is
inspected here, with an independent SQLite reader.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = 'org.exreader.importprobe'
SENDER = 'org.exreader.s10docs'
PROBE_APK = ROOT / 'tests/reader_android_import_entry/android/app/build/outputs/apk/debug/app-debug.apk'
SENDER_APK = ROOT / 'tests/reader_final_s10/android/sender/build/outputs/apk/debug/sender-debug.apk'


def run(command, check=True, binary=False, timeout=600):
    result = subprocess.run([str(item) for item in command], capture_output=True, timeout=timeout)
    if check and result.returncode:
        sys.stderr.write(result.stdout.decode('utf-8', 'replace'))
        sys.stderr.write(result.stderr.decode('utf-8', 'replace'))
        raise SystemExit('command failed: ' + ' '.join(str(item) for item in command))
    return result.stdout if binary else result.stdout.decode('utf-8', 'replace')


def adb(*arguments, **kwargs):
    return run(['adb', *arguments], **kwargs)


def wait_booted():
    adb('wait-for-device')
    deadline = time.time() + 300
    while time.time() < deadline:
        if adb('shell', 'getprop', 'sys.boot_completed').strip() == '1':
            return
        time.sleep(3)
    raise SystemExit('emulator did not finish booting')


def property(name):
    return adb('shell', 'getprop', name).strip()


def device_bytes(package, path):
    return adb('exec-out', 'run-as', package, 'cat', path, binary=True, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--name', default='S10-Transfer.epub')
    args = parser.parse_args()
    fixtures, output = args.fixtures.absolute(), args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fixtures / 'manifest.json').read_text())
    name = args.name
    source = fixtures / name
    expected = manifest[name]
    data = source.read_bytes()
    checks = []

    def check(check_id, ok, detail=''):
        checks.append({'id': check_id, 'passed': bool(ok), 'detail': detail})

    check('fixture.manifest-matches-file', hashlib.sha256(data).hexdigest() == expected['sha256']
          and len(data) == expected['bytes'], 'local fixture bytes')
    wait_booted()
    adb('install', '-r', '-t', str(PROBE_APK))
    adb('install', '-r', '-t', str(SENDER_APK))
    adb('shell', 'run-as', PROBE, 'rm', '-rf', 'files')
    adb('shell', 'run-as', SENDER, 'rm', '-rf', 'files')
    adb('push', str(source), '/data/local/tmp/s10-transfer.bin')
    adb('shell', 'run-as', SENDER, 'mkdir', '-p', 'files/inbox')
    adb('shell', 'run-as', SENDER, 'cp', '/data/local/tmp/s10-transfer.bin', 'files/inbox/' + name)
    delivered = adb('shell', 'run-as', SENDER, 'sha256sum', 'files/inbox/' + name).split()
    delivered_sha = delivered[0] if delivered else ''
    check('delivery.emulator-file-matches-fixture', delivered_sha == expected['sha256'],
          'emulator file sha256 ' + delivered_sha)

    adb('shell', 'am', 'start', '-W', '-n', SENDER + '/.S10Sender',
        '--es', 'name', name, '--es', 'type', 'application/epub+zip', check=False)
    deadline = time.time() + 300
    events = []
    while time.time() < deadline:
        raw = device_bytes(PROBE, 'files/evidence.jsonl').decode('utf-8', 'replace')
        events = [json.loads(line) for line in raw.splitlines() if line.strip().startswith('{')]
        if any(row.get('ev') in ('readback', 'failed') for row in events):
            break
        time.sleep(3)
    while time.time() < deadline + 60:
        raw = device_bytes(PROBE, 'files/evidence.jsonl').decode('utf-8', 'replace')
        events = [json.loads(line) for line in raw.splitlines() if line.strip().startswith('{')]
        if any(row.get('ev') == 'released' for row in events):
            break
        time.sleep(2)

    (output / 'owner-events.jsonl').write_text(
        '\n'.join(json.dumps(row, sort_keys=True) for row in events) + ('\n' if events else ''))

    submitted = [row for row in events if row.get('ev') == 'submitted']
    ready = [row for row in events if row.get('ev') == 'ready']
    failed = [row for row in events if row.get('ev') == 'failed']
    commits = [row for row in events if row.get('ev') == 'commit']
    readbacks = [row for row in events if row.get('ev') == 'readback']
    releases = [row for row in events if row.get('ev') == 'released']

    check('entry.granted-content-uri-submitted', bool(submitted), 'submitted events ' + str(len(submitted)))
    check('owner.received-original-bytes',
          bool(ready) and ready[-1].get('id') == expected['sha256'] + '.epub'
          and int(ready[-1].get('size', -1)) == expected['bytes']
          and ready[-1].get('format') == 'EPUB',
          json.dumps(ready[-1], sort_keys=True) if ready else 'no ready event')
    check('owner.no-import-failure', not failed,
          json.dumps(failed[-1], sort_keys=True) if failed else '')
    check('owner.committed-into-sdk-library',
          bool(commits) and commits[-1].get('status') == 0 and commits[-1].get('created') == 1
          and int(commits[-1].get('bookId') or 0) > 0,
          json.dumps(commits[-1], sort_keys=True) if commits else 'no commit event')
    check('owner.stored-original-equals-staged', bool(readbacks) and readbacks[-1].get('equal') is True,
          json.dumps(readbacks[-1], sort_keys=True) if readbacks else 'no readback event')
    check('owner.staging-lease-released', bool(releases) and releases[-1].get('fileExists') is False,
          json.dumps(releases[-1], sort_keys=True) if releases else 'no released event')

    adb('shell', 'am', 'force-stop', PROBE, check=False)
    time.sleep(2)
    stored = {'sha256': '', 'bytes': 0, 'books': 0}
    library = device_bytes(PROBE, 'files/probe.exrlib')
    if library:
        (output / 'probe.exrlib').write_bytes(library)
    for suffix in ('-wal', '-shm'):
        extra = device_bytes(PROBE, 'files/probe.exrlib' + suffix)
        if extra:
            (output / ('probe.exrlib' + suffix)).write_bytes(extra)
    if library:
        try:
            connection = sqlite3.connect(str(output / 'probe.exrlib'))
            rows = connection.execute('SELECT id, length(source) FROM books').fetchall()
            stored['books'] = len(rows)
            match = [row for row in rows if row[1] == expected['bytes']]
            if match:
                blob = connection.execute('SELECT source FROM books WHERE id=?', (match[0][0],)).fetchone()[0]
                stored['sha256'] = hashlib.sha256(blob).hexdigest()
                stored['bytes'] = len(blob)
                stored['book_id'] = match[0][0]
            connection.close()
        except sqlite3.Error as error:
            stored['error'] = str(error)
    check('sdk.stored-source-matches-fixture', stored['sha256'] == expected['sha256'],
          json.dumps(stored, sort_keys=True))

    problems = [row['id'] + ': ' + row['detail'] for row in checks if not row['passed']]
    report = {
        'schema': 1,
        'package': 'S10',
        'role': 'android',
        'platform': 'android-emulator',
        'source_sha': os.environ.get('GITHUB_SHA', ''),
        'run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
        'emulator': {
            'android_release': property('ro.build.version.release'),
            'sdk': property('ro.build.version.sdk'),
            'abi': property('ro.product.cpu.abi'),
            'model': property('ro.product.model'),
        },
        'fixture': {'name': name, 'sha256': expected['sha256'], 'bytes': expected['bytes']},
        'delivery': {
            'method': 'adb push of the real fixture plus run-as copy into the sender app inbox',
            'physical_cable_or_mtp': False,
            'emulator_file_sha256': delivered_sha,
        },
        'entry': {
            'intent': 'android.intent.action.VIEW',
            'scheme': 'content',
            'authority': SENDER + '.docs',
            'uri': 'content://' + SENDER + '.docs/document/' + name,
            'grant': 'Intent.FLAG_GRANT_READ_URI_PERMISSION from the provider owner',
            'import_owner': 'extras/android-import-entry (unchanged) hosted by ' + PROBE,
        },
        'owner_events': events,
        'stored_source': stored,
        'checks': checks,
        'problems': problems,
        'accepted': not problems,
        'physical_device_execution': False,
        'usb_cable_execution': False,
        'mtp_execution': False,
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'checks': len(checks), 'problems': problems}, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
