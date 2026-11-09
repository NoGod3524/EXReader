"""On an Apple Silicon Mac, run the downloaded simulator dylib in a real app."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
IDENTIFIER = 'org.exreader.platformruntime'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True, help='downloaded iphonesimulator SDK directory')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        parser.error('this archived simulator dylib requires an Apple Silicon Mac with Xcode')
    sdk, out = args.sdk.resolve(strict=True), args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('choose a fresh output directory')
    app = out / 'PlatformProbe.app'
    frameworks = app / 'Frameworks'
    frameworks.mkdir(parents=True)
    commands = []

    def run(*command):
        command = [str(x) for x in command]
        commands.append(command)
        print('ARGV:', command, flush=True)
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(result.stdout, end='', flush=True)
        if result.stderr:
            print(result.stderr, end='', file=sys.stderr, flush=True)
        return result.stdout.strip()

    run(sys.executable, '-B', ROOT / 'tools/abi/prepare_smoke.py', out / 'smoke')
    for name in ('smoke.epub', 'font.otf'):
        shutil.copyfile(out / 'smoke' / name, app / name)
    original = sdk / 'lib/libexreader.dylib'
    # Preserve the dylib bytes and its @rpath/libexreader.1.dylib install name.
    for name in ('libexreader.dylib', 'libexreader.1.dylib'):
        shutil.copyfile(original, frameworks / name)
    apple_sdk = run('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
    flags = ['-target', 'arm64-apple-ios14.0-simulator', '-isysroot', apple_sdk, '-O2', '-I' + str(ROOT / 'include')]
    run('xcrun', '--sdk', 'iphonesimulator', 'clang', *flags, '-std=c11', '-DPLATFORM_PROBE_EMBEDDED',
        '-c', ROOT / 'tools/platforms/probe.c', '-o', out / 'probe.o')
    run('xcrun', '--sdk', 'iphonesimulator', 'clang', *flags, '-fobjc-arc', ROOT / 'tools/platforms/ios_main.m',
        out / 'probe.o', frameworks / 'libexreader.dylib', '-framework', 'UIKit', '-framework', 'Foundation',
        '-Wl,-rpath,@executable_path/Frameworks', '-o', app / 'PlatformProbe')
    info = {'CFBundleIdentifier': IDENTIFIER, 'CFBundleExecutable': 'PlatformProbe', 'CFBundleName': 'PlatformProbe',
            'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0',
            'MinimumOSVersion': '14.0', 'UIDeviceFamily': [1, 2], 'LSRequiresIPhoneOS': True}
    (app / 'Info.plist').write_bytes(plistlib.dumps(info))
    run('codesign', '--force', '--sign', '-', app)
    devices = json.loads(run('xcrun', 'simctl', 'list', '--json'))
    runtimes = [x for x in devices['runtimes'] if x.get('isAvailable') and '.iOS-' in x['identifier']]
    runtime = max(runtimes, key=lambda x: tuple(map(int, x['version'].split('.'))))
    device_type = next(x['identifier'] for x in reversed(devices['devicetypes']) if x['name'].startswith('iPhone'))
    udid = run('xcrun', 'simctl', 'create', 'EXReader platform runtime', device_type, runtime['identifier'])
    (out / 'simulator-udid.txt').write_text(udid + '\n')
    run('xcrun', 'simctl', 'boot', udid)
    run('xcrun', 'simctl', 'bootstatus', udid, '-b')
    run('xcrun', 'simctl', 'install', udid, app)
    pids = []
    for mode in ('create', 'reopen'):
        run('xcrun', 'simctl', 'launch', udid, IDENTIFIER, mode)
        container = Path(run('xcrun', 'simctl', 'get_app_container', udid, IDENTIFIER, 'data')) / 'Documents'
        deadline = time.monotonic() + 60
        while not (container / (mode + '.exit')).exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('probe did not finish; simulator retained for inspection')
            time.sleep(0.25)
        state = (container / (mode + '.exit')).read_text()
        if not state.startswith('exit=0 '):
            raise RuntimeError(state + (container / (mode + '.log')).read_text())
        pids.append(re.search(r'pid=(\d+)', state).group(1))
        run('xcrun', 'simctl', 'terminate', udid, IDENTIFIER)
    if pids[0] == pids[1]:
        raise RuntimeError('expected distinct process IDs')
    for path in container.iterdir():
        if path.is_file():
            shutil.copyfile(path, out / path.name)
    log = (out / 'reopen.log').read_text()
    checks = {name: bool(re.search(r'^PASS ' + name + r'\b', log, re.M)) for name in ('load', 'open', 'render', 'search', 'annotation')}
    if not all(checks.values()):
        raise RuntimeError('incomplete five-check evidence')
    result = {'checks': checks, 'passed': 5, 'pids': pids, 'runtime': runtime, 'udid': udid,
              'library_sha256': hashlib.sha256(original.read_bytes()).hexdigest(), 'commands': commands}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(log)
    run('xcrun', 'simctl', 'shutdown', udid)
    # Keep the dedicated simulator and its evidence; no existing devices are changed.


if __name__ == '__main__':
    main()
