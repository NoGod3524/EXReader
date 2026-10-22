#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record installed bytes and run the two independent Android suites in cloud CI."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from android_host_evidence import PACKAGES, SUITES, check_identity, cloud_identity, load, require, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    require(sys.platform == 'linux', 'Android device execution requires the Linux CI runner')
    output = args.evidence
    output.mkdir(parents=True, exist_ok=True)
    build = load(args.build)
    identity = cloud_identity()
    report = {**identity, 'schema': 1, 'completed': False, 'commands': [], 'installed': {},
              'fixtures': {}, 'suites': {}, 'errors': [], 'files_sha256': {}}

    def command(argv, destination=None, timeout=60):
        record = {'argv': argv, 'timeout_seconds': timeout}
        report['commands'].append(record)
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=timeout)
            record['exit_code'] = proc.returncode
            if destination:
                destination.write_bytes(proc.stdout + proc.stderr)
            else:
                record.update({'stdout': proc.stdout.decode(errors='replace'), 'stderr': proc.stderr.decode(errors='replace')})
            return proc.returncode, proc.stdout.decode(errors='replace').strip()
        except subprocess.TimeoutExpired as error:
            record.update({'exit_code': -1, 'timed_out': True})
            if destination:
                destination.write_bytes((error.stdout or b'') + (error.stderr or b''))
            return -1, ''

    def checked(argv, **kwargs):
        code, text = command(argv, **kwargs)
        require(code == 0, 'device command failed: ' + ' '.join(argv[:4]))
        return text

    try:
        check_identity(build, identity)
        installed = output/'installed'
        installed.mkdir()
        for name, package in PACKAGES.items():
            paths = checked(['adb', 'shell', 'pm', 'path', package]).splitlines()
            require(len(paths) == 1 and paths[0].startswith('package:'), 'installed APK package path missing: ' + package)
            checked(['adb', 'pull', paths[0][len('package:'):], str(installed/name)])
            report['installed'][name] = sha256(installed/name)
            require(report['installed'][name] == build['artifacts'][name]['sha256'], 'device installed a different APK: ' + name)
        for name, value in build['fixtures'].items():
            text = checked(['adb', 'shell', 'sha256sum', '/sdcard/Download/' + name])
            actual = text.split()[0]
            require(actual == value['sha256'], 'device fixture hash mismatch: ' + name)
            report['fixtures'][name] = actual
        for suite, (class_name, method, folder, required_ids) in SUITES.items():
            checked(['adb', 'logcat', '-c'])
            class_path = 'org.exreader.host.uitest.' + class_name
            # Raw mode is mandatory: the checker reads INSTRUMENTATION_STATUS class/test/code
            # records, which am only prints with -r. Pretty mode hides them entirely.
            argv = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'disableAnalytics', 'true',
                '-e', 'class', class_path + '#' + method, '-e', 'exr_suite', suite,
                '-e', 'exr_source_sha', identity['source_sha'], '-e', 'exr_run_id', identity['run_id'],
                '-e', 'exr_attempt', identity['attempt'],
                '-e', 'apk_sha256', build['artifacts']['app-debug.apk']['sha256'],
                '-e', 'test_apk_sha256', build['artifacts']['uitest-debug-androidTest.apk']['sha256'],
                'org.exreader.host.uitest.test/androidx.test.runner.AndroidJUnitRunner']
            code, unused = command(argv, output/(suite + '-instrumentation.txt'), timeout=900)
            log_code, unused = command(['adb', 'logcat', '-d'], output/(suite + '-logcat.txt'))
            remote = {'walkthrough':'evidence', 'review':'review-evidence', 'bounded':'bounded-evidence'}[suite]
            require(not (output/folder).exists(), 'earlier suite evidence must not be reused')
            pull_code, unused = command(['adb', 'pull',
                '/sdcard/Android/data/org.exreader.host.uitest/files/' + remote, str(output/folder)])
            report['suites'][suite] = {'class': class_path, 'method': method, 'exit_code': code,
                'log_exit_code': log_code, 'pull_exit_code': pull_code}
            if code or log_code or pull_code:
                report['errors'].append(suite + ': execution, log or evidence collection failed')
            for suffix in ('instrumentation.txt', 'logcat.txt'):
                name = suite + '-' + suffix
                if (output/name).is_file():
                    report['files_sha256'][name] = sha256(output/name)
        checked(['adb', 'shell', 'dumpsys', 'package', 'org.exreader.host'], destination=output/'package.txt')
        # Preserve the original artifact entry points while retaining suite isolation.
        shutil.copyfile(output/'walkthrough-instrumentation.txt', output/'instrumentation.txt')
        shutil.copyfile(output/'walkthrough-logcat.txt', output/'logcat.txt')
        report['completed'] = not report['errors']
    except Exception as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error)[:500])
    finally:
        (output/'execution.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'completed': report['completed'], 'suites': report['suites'], 'errors': report['errors']}))
    return 0 if report['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
