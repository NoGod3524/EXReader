#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify same-run Android shelf observation and installed program identity in Actions."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path('tools').resolve()))
from android_host_evidence import apk_native, inventory, native_record, ownership, sha256, source_files
from run_reader_shelf_ui import analyze

ROOT = Path('build/perf-android')
BUILD = Path('build/android-host')
STAGE = Path('stage/android-x86_64')
PACKAGES = {
    'app-debug.apk': 'org.exreader.host',
    'uitest-debug.apk': 'org.exreader.host.uitest',
    'uitest-debug-androidTest.apk': 'org.exreader.host.uitest.test',
    'app-debug-androidTest.apk': 'org.exreader.host.test',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    identity = {key: os.environ[name] for key, name in (
        ('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'))}
    result = {**identity, 'observation_complete': False, 'performance_accepted': False,
              'physical_device_execution': False, 'problems': []}
    try:
        require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions execution required')
        require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == identity['source_sha'], 'checkout differs')
        build = json.loads((BUILD / 'build.json').read_text())
        require(all(build.get(key) == value for key, value in identity.items()), 'build identity differs')
        require(build.get('sdk_built') is True and build.get('apk_built') is True, 'actual build required')
        require(build.get('ownership') == ownership() and build['ownership']['candidate_only'] is True, 'candidate identity differs')
        require(build.get('sdk_files_sha256') == inventory(STAGE), 'SDK inventory differs')
        require(build.get('source_files_sha256') == source_files(), 'source inventory differs')
        require(build.get('abi') == 'x86_64' and build.get('sdk_version') == '3.41.0', 'SDK target differs')
        fixtures = json.loads((BUILD / 'fixtures/fixtures.json').read_text())
        require(fixtures == build.get('fixtures'), 'fixture manifest differs')
        for name, item in fixtures.items():
            path = BUILD / 'fixtures' / name
            require(Path(name).name == name and path.stat().st_size == item['size'] and sha256(path) == item['sha256'], 'fixture differs: ' + name)
        native = apk_native(BUILD / 'artifacts/app-debug.apk')
        require(native == build.get('native'), 'APK native identity differs')
        for name in ('libexreader.so', 'libexreader_jni.so'):
            require(native['lib/x86_64/' + name]['build_id'] == native_record((STAGE / 'lib' / name).read_bytes())['build_id'], 'SDK runtime build ID differs: ' + name)
        with zipfile.ZipFile(BUILD / 'artifacts/app-debug.apk') as apk:
            require(hashlib.sha256(apk.read('assets/Reader.otf')).hexdigest() == build['font']['sha256'], 'font differs')
        installed = ROOT / 'installed'
        installed.mkdir(exist_ok=True)
        records = {}
        for filename, package in PACKAGES.items():
            source = BUILD / 'artifacts' / filename if filename != 'app-debug-androidTest.apk' else Path('examples/android/app/build/outputs/apk/androidTest/debug') / filename
            paths = subprocess.check_output(['adb', 'shell', 'pm', 'path', package], text=True).splitlines()
            require(len(paths) == 1 and paths[0].startswith('package:'), 'installed package path missing: ' + package)
            with (installed / filename).open('wb') as out:
                subprocess.run(['adb', 'exec-out', 'cat', paths[0][8:]], stdout=out, check=True)
            digest = sha256(source)
            require(sha256(installed / filename) == digest and source.stat().st_size == (installed / filename).stat().st_size, 'installed bytes differ: ' + filename)
            if filename in build['artifacts']:
                require(digest == build['artifacts'][filename]['sha256'] and source.stat().st_size == build['artifacts'][filename]['size'], 'built APK differs: ' + filename)
            records[filename] = {'package': package, 'device_path': paths[0][8:], 'sha256': digest, 'bytes': source.stat().st_size}
        device = {name: subprocess.check_output(['adb', 'shell', 'getprop', prop], text=True).strip() for name, prop in (
            ('api', 'ro.build.version.sdk'), ('abi', 'ro.product.cpu.abi'), ('model', 'ro.product.model'),
            ('build_fingerprint', 'ro.build.fingerprint'))}
        require(device['api'] == '34' and device['abi'] == 'x86_64', 'emulator target differs')
        ui_root = ROOT / 'ui-execution'
        ui = json.loads((ui_root / 'result.json').read_text())
        actual = analyze(ui_root, identity)
        require(ui.get('accepted') is True and ui.get('problems') == [] and
                all(ui.get(key) == value for key, value in identity.items()) and
                all(ui.get(key) == value for key, value in actual.items()), 'raw UI observation differs')
        result.update(observation_complete=True, device=device, installed_apks=records,
                      sdk_version=build['sdk_version'], sdk_files_sha256=build['sdk_files_sha256'],
                      native=native, font=build['font'], fixtures=fixtures, observations=actual)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    (ROOT / 'observation-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    if not result['observation_complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
