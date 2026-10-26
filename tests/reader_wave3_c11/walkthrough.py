#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the existing uitest suites on the installed C11 host and retain evidence.

The three suites are the unchanged repository drivers (HostWalkthroughTest and
HostReviewTest). This script only installs nothing, records the real installed
bytes, clears logcat per suite, executes the instrumentation and pulls the test
evidence folder back. It runs in Actions only.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
PACKAGE = 'org.exreader.host'
UITEST = 'org.exreader.host.uitest'
SUITES = (
    ('walkthrough', 'org.exreader.host.uitest.HostWalkthroughTest', 'walkthrough', 'evidence', 2400),
    ('review', 'org.exreader.host.uitest.HostReviewTest', 'review', 'review-evidence', 900),
    ('bounded', 'org.exreader.host.uitest.HostReviewTest', 'bounded', 'bounded-evidence', 900),
)
# Picker names stay intact; exact shelf title and format follow ImportEntry.
EXPECTED_TITLES = {name: {'title': Path(name).stem, 'format': Path(name).suffix[1:].upper()}
                   for name in ('Sample.epub', 'Sample.txt', 'Sample.pdf',
                                'BigChapter.epub', 'Ambiguous.epub', 'Second.epub')}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    identity = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT']}
    report = {**identity, 'schema': 1, 'completed': False, 'app_sha256': sha256(args.app),
              'installed_sha256': '', 'fixtures': {}, 'suites': {}, 'errors': [], 'commands': [],
              'expected_titles': EXPECTED_TITLES}

    def command(argv, timeout=120, destination=None):
        record = {'argv': argv, 'timeout_seconds': timeout}
        report['commands'].append(record)
        try:
            process = subprocess.run(argv, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            record['exit_code'] = -1
            record['timed_out'] = True
            if destination:
                destination.write_bytes((error.stdout or b'') + (error.stderr or b''))
            return -1, b''
        record['exit_code'] = process.returncode
        if destination:
            destination.write_bytes(process.stdout + process.stderr)
        return process.returncode, process.stdout

    try:
        candidate = Path('build/wave3/candidate/provenance.json')
        provenance = json.loads(candidate.read_text(encoding='utf-8'))
        if any(provenance['expected_titles'].get(name) != value for name, value in EXPECTED_TITLES.items()):
            raise RuntimeError('candidate does not enforce the independent title and format expectations')
        (output / 'candidate-provenance.json').write_bytes(candidate.read_bytes())
        installed = output / 'installed'
        installed.mkdir()
        code, raw = command(['adb', 'shell', 'pm', 'path', PACKAGE])
        lines = raw.decode(errors='replace').splitlines()
        if code or len(lines) != 1 or not lines[0].startswith('package:'):
            raise RuntimeError('installed application path is missing')
        code, unused = command(['adb', 'pull', lines[0][len('package:'):].strip(), str(installed / 'app-debug.apk')])
        if code:
            raise RuntimeError('cannot pull the installed application')
        report['installed_sha256'] = sha256(installed / 'app-debug.apk')
        if report['installed_sha256'] != report['app_sha256']:
            raise RuntimeError('device installed different application bytes')
        for fixture in sorted(args.fixtures.iterdir()):
            if fixture.suffix not in ('.epub', '.txt', '.pdf'):
                continue
            code, raw = command(['adb', 'shell', 'sha256sum', '/sdcard/Download/' + fixture.name])
            actual = raw.decode(errors='replace').split()[0] if raw.strip() else ''
            expected = sha256(fixture)
            report['fixtures'][fixture.name] = {'expected': expected, 'device': actual}
            if code or actual != expected:
                raise RuntimeError('device fixture differs: ' + fixture.name)
        for suite, class_name, method, remote, timeout in SUITES:
            code, unused = command(['adb', 'logcat', '-c'])
            argv = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'disableAnalytics', 'true',
                    '-e', 'class', class_name + '#' + method, '-e', 'exr_suite', suite,
                    '-e', 'exr_source_sha', identity['source_sha'], '-e', 'exr_run_id', identity['run_id'],
                    '-e', 'exr_attempt', identity['attempt'], '-e', 'apk_sha256', report['app_sha256'],
                    UITEST + '.test/androidx.test.runner.AndroidJUnitRunner']
            code, unused = command(argv, timeout=timeout, destination=output / (suite + '-instrumentation.txt'))
            log_code, unused = command(['adb', 'logcat', '-d'], timeout=180, destination=output / (suite + '-logcat.txt'))
            if re.search(rb'JNI DETECTED ERROR IN APPLICATION|JNI WARNING|JNI call made with exception pending', unused):
                report['errors'].append(suite + ': CheckJNI rejected a JNI call')
            if (output / (suite + '-evidence')).exists():
                raise RuntimeError('earlier evidence folder must not be reused: ' + suite)
            pull_code, unused = command(['adb', 'pull',
                                         '/sdcard/Android/data/' + UITEST + '/files/' + remote,
                                         str(output / (suite + '-evidence'))], timeout=300)
            report['suites'][suite] = {'class': class_name, 'method': method, 'exit_code': code,
                                       'log_exit_code': log_code, 'pull_exit_code': pull_code}
            if code or log_code or pull_code:
                report['errors'].append(suite + ': execution, log or evidence collection failed')
        report['completed'] = not report['errors']
    except Exception as error:  # noqa: BLE001  (record every real failure)
        report['errors'].append(type(error).__name__ + ': ' + str(error)[:500])
    finally:
        (output / 'execution.json').write_text(
            json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'completed': report['completed'], 'suites': report['suites'],
                      'errors': report['errors']}, ensure_ascii=False))
    return 0 if report['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
