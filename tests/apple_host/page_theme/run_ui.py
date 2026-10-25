# SPDX-License-Identifier: MIT
"""Drive the real OS appearance while the XCTest waits for actual theme pixels."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'Actions macOS only'
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute(); out.mkdir(parents=True, exist_ok=True)
    commands, served = [], []

    def save_commands():
        report = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': args.platform, 'served': served,
                  'commands': commands, 'physical_device_execution': False}
        (out / 'system-commands.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    save_commands()

    def command(argv, timeout=45, check=True):
        try:
            proc = subprocess.run([str(v) for v in argv], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            commands.append({'argv': [str(v) for v in argv], 'exit_code': None, 'timed_out_seconds': timeout})
            save_commands()
            raise
        commands.append({'argv': [str(v) for v in argv], 'exit_code': proc.returncode,
                         'stdout': proc.stdout, 'stderr': proc.stderr})
        save_commands()
        if check and proc.returncode:
            raise RuntimeError('Native OS command failed: ' + ' '.join(map(str, argv)))
        return proc

    original_style = None
    if args.platform == 'macos':
        scheme, destination, udid = 'EXReaderHost-macOS', 'platform=macOS', None
        original_style = command(['osascript', '-e', 'tell application "System Events" to tell appearance preferences to get dark mode']).stdout.strip()
        assert original_style in ('true', 'false')
        device, runtime = 'macOS host', command(['sw_vers', '-productVersion']).stdout.strip()
    else:
        payload = json.loads(command(['xcrun', 'simctl', 'list', 'devices', 'available', '--json'], timeout=180).stdout)
        prefix = 'iPhone' if args.platform == 'iphone' else 'iPad'
        runtime, device, udid = max((runtime, row['name'], row['udid']) for runtime, rows in payload['devices'].items()
                                   for row in rows if row.get('isAvailable') and row['name'].startswith(prefix))
        command(['xcrun', 'simctl', 'shutdown', udid], check=False)
        command(['xcrun', 'simctl', 'erase', udid])
        command(['xcrun', 'simctl', 'boot', udid])
        command(['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=180)
        destination, scheme = 'platform=iOS Simulator,id=' + udid, 'EXReaderHost-iOS'
    (out / 'destination.txt').write_text('\n'.join((destination, udid or 'macos', device, runtime)) + '\n')

    def appearance(style):
        if udid:
            command(['xcrun', 'simctl', 'ui', udid, 'appearance', style])
        else:
            command(['osascript', '-e', 'tell application "System Events" to tell appearance preferences to set dark mode to ' + ('true' if style == 'dark' else 'false')])

    appearance('light')
    arguments = ['xcodebuild', 'test', '-project', args.project.absolute(), '-scheme', scheme,
                 '-destination', destination, '-derivedDataPath', 'build/ThemeDerivedData', '-resultBundlePath', out / 'theme.xcresult',
                 '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES',
                 '-default-test-execution-time-allowance', '180', '-maximum-test-execution-time-allowance', '300',
                 'EXR_SDK_DIR=' + str(args.sdk.absolute()), 'CODE_SIGNING_ALLOWED=' + ('NO' if udid else 'YES')]
    started = time.monotonic(); process = None
    next_container_probe = started
    built_info = Path('build/ThemeDerivedData/Build/Products/Debug-iphonesimulator/EXReaderHost.app/Info.plist')
    try:
        with (out / 'xcodebuild.log').open('wb') as log:
            process = subprocess.Popen([str(v) for v in arguments], stdout=log, stderr=subprocess.STDOUT)
            marker = None
            while process.poll() is None:
                if time.monotonic() - started > 1500:
                    raise RuntimeError('Theme UI exceeded 25 minutes')
                if udid:
                    # CoreSimulator can block lookup before Xcode has built and
                    # installed the app. A read timeout must not kill that build.
                    if (marker is None or not marker.parent.exists()) and built_info.is_file() and time.monotonic() >= next_container_probe:
                        argv = ['xcrun', 'simctl', 'get_app_container', udid, 'org.exreader.host', 'data']
                        try:
                            probe = subprocess.run(argv, capture_output=True, text=True, timeout=15)
                            commands.append({'argv': argv, 'exit_code': probe.returncode, 'stdout': probe.stdout, 'stderr': probe.stderr})
                            if probe.returncode == 0:
                                container = Path(probe.stdout.strip())
                                assert container.is_absolute() and container.is_dir(), 'invalid actual app container'
                                marker = container / 'Documents/page-theme-system-request.json'
                        except subprocess.TimeoutExpired:
                            commands.append({'argv': argv, 'exit_code': None, 'diagnostic': 'read-only container lookup timed out before a successful resolution'})
                        save_commands()
                        next_container_probe = time.monotonic() + 10
                else:
                    marker = Path.home() / 'Library/Application Support/EXReader/page-theme-system-request.json'
                if marker is not None and marker.is_file():
                    request = json.loads(marker.read_text())
                    assert request['source_sha'] == os.environ['GITHUB_SHA'] and request['choice'] == 'system', 'foreign system request'
                    style = request['requested_appearance']
                    assert style in ('dark', 'light')
                    if style not in served:
                        assert style == ('dark' if not served else 'light'), 'system request order differs'
                        appearance(style); served.append(style)
                time.sleep(1)
            code = process.returncode
        if code:
            print('\n'.join((out / 'xcodebuild.log').read_text(errors='replace').splitlines()[-240:]), flush=True)
            raise RuntimeError('XCTest failed; inspect preserved xcodebuild.log')
        assert served == ['dark', 'light'], 'real OS dark/light commands were not both exercised'
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=30)
        if args.platform == 'macos' and original_style is not None:
            command(['osascript', '-e', 'tell application "System Events" to tell appearance preferences to set dark mode to ' + original_style], check=False)
        elif udid:
            appearance('light')
        save_commands()


if __name__ == '__main__':
    main()
