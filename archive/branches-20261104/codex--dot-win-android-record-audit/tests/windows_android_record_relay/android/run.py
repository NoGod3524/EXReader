#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only Android middle stage. Restore authenticated service state, never app DB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import relay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    args = parser.parse_args()
    identity = relay.identity()
    previous, previous_hash = relay.load(args.previous, 'windows-first')
    args.output.mkdir(parents=True, exist_ok=True)
    dav, user, password = relay.start(args.output, args.previous,
        args.fixture / 'public/server.crt', args.fixture / 'private/server.key')
    sensitive = [user.encode(), password.encode()]
    package = 'org.exreader.host'
    def adb(*parts, data=None, timeout=90):
        return subprocess.check_output(['adb', *map(str, parts)], input=data,
            stderr=subprocess.STDOUT, timeout=timeout)
    def save(name, data):
        # Username is intentionally non-secret and may appear in class names; only password matters.
        assert sensitive[1] not in data, 'generated fixture credential leaked'
        (args.output / name).write_bytes(data)
    report = None
    succeeded = False
    try:
        assert adb('shell', 'pm', 'clear', package).strip() == b'Success'
        adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
        port = urlparse(dav.base).port
        adb('reverse', f'tcp:{port}', f'tcp:{port}')
        payload = {key: previous['data'][key] for key in
            ('original_sha256', 'original_bytes', 'book_identity', 'remote_title', 'windows_program_sha256')}
        payload.update(root=dav.base + '/dav/', user=user, password=password)
        adb('shell', f"run-as {package} sh -c 'cat > files/relay-input.json'",
            data=json.dumps(payload, ensure_ascii=False).encode())
        command = ['shell', 'am', 'instrument', '-w', '-r']
        for key, value in identity.items():
            command += ['-e', key, value]
        raw = adb(*command, package + '.test/' + package + '.RelayAndroidTest', timeout=600)
        save('instrumentation.txt', raw)
        report_raw = adb('exec-out', 'run-as', package, 'cat', 'files/relay-android-report.json')
        save('report.json', report_raw)
        report = json.loads(report_raw)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        assert all(report.get(key) == value for key, value in identity.items())
        assert report['api'] == 34 and report['abi'] == 'x86_64'
        package_paths = adb('shell', 'pm', 'path', package).decode().strip().splitlines()
        assert len(package_paths) == 1 and package_paths[0].startswith('package:/data/app/')
        installed_apk = adb('exec-out', 'cat', package_paths[0][len('package:'):])
        built_apk = Path('build/wave3/artifacts/app-debug.apk').read_bytes()
        assert installed_apk == built_apk, 'installed application is not the same-run APK'
        report['program'] = {'sha256': hashlib.sha256(installed_apk).hexdigest(),
                             'bytes': len(installed_apk), 'source_sha': identity['source_sha'],
                             'package': package, 'installed_equals_same_run_apk': True}
        assert report['passed'] is True, report
        assert b'RELAY_ANDROID_PASS' in raw and b'INSTRUMENTATION_CODE: -1' in raw
        expected = ['empty_library_real_account_and_sync', 'explicit_application_receive_original',
            'windows_records_real_public_resolution', 'ambiguous_record_is_explicit_and_does_not_move_page', 'android_edits_received_note_and_adds_bookmark',
            'application_sync_and_duplicate_idempotence']
        assert [row['name'] for row in report['checks']] == expected
        assert all(row['pass'] is True for row in report['checks'])
        assert len(dav.entries) > len(dav.prior_entries), 'no real outgoing application revision'
        original_path = '/dav/exreader-sync-v1/objects/' + payload['original_sha256'][:2] + '/' + payload['original_sha256'] + '.epub'
        assert dav.entries[original_path] == dav.prior_entries[original_path]
        assert hashlib.sha256(dav.entries[original_path]).hexdigest() == payload['original_sha256']
        report['checks'] = expected
        report['previous_sha256'] = previous_hash
        report['transport'] = 'authenticated staged HTTPS; not simultaneous online hosts'
        relay.save(dav, args.output, 'android', report)
        succeeded = True
    finally:
        for name, command in [('logcat.txt', ('logcat', '-d', '-v', 'threadtime', '-t', '3000')),
                              ('screen.png', ('exec-out', 'screencap', '-p'))]:
            try:
                captured = adb(*command)
                save(name, captured)
                if not succeeded and name == 'logcat.txt':
                    selected = [line for line in captured.decode(errors='replace').splitlines()
                        if any(key in line.lower() for key in ('exreader', 'exception', 'fatal', 'could not', 'sqlite', 'abort'))]
                    print('FAILED APP LOGCAT\n' + '\n'.join(selected[-160:]), flush=True)
            except Exception as error: print('Evidence capture failed:', name, type(error).__name__, flush=True)
        if not succeeded:
            (args.output / 'requests.json').write_text(json.dumps(dav.requests, indent=2))
            dav.server.shutdown()
            dav.server.server_close()
            (args.output / 'key.pem').unlink(missing_ok=True)
        # The fixture private key and session account input are never handoff artifacts.

if __name__ == '__main__':
    main()
