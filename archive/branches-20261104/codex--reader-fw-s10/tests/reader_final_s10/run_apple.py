#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S10 Apple: deliver a real file to the existing Apple import owner on a simulator.

The driver bundle links the UNCHANGED examples/apple owner sources and only
calls the shipped import entry.  CI places the fixture in the app's Documents
container - the same directory the Files app and Finder expose when
UIFileSharingEnabled is set - and then verifies the stored original with an
independent SHA-256 of the owner's own fingerprint report.
"""
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ID = 'org.exreader.s10'
OWNER_SOURCES = [
    'bindings/swift/EXReader.swift',
    'examples/apple/HostSDK.swift',
    'examples/apple/HostModel.swift',
    'examples/apple/HostCatalog.swift',
    'examples/apple/HostAccount.swift',
    'examples/apple/HostSearch.swift',
    'examples/apple/HostNavigation.swift',
    'examples/apple/HostReadingRecords.swift',
    'examples/apple/SelectableText.swift',
    'tests/reader_final_s10/apple/main.swift',
]


def run(command, timeout=1800, check=True):
    result = subprocess.run([str(item) for item in command], capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        sys.stderr.write(result.stdout[-8000:])
        sys.stderr.write(result.stderr[-8000:])
        raise SystemExit('command failed: ' + ' '.join(str(item) for item in command))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True, help='installed iphonesimulator SDK prefix')
    parser.add_argument('--resources', type=Path, required=True, help='prepare_fixtures.py output')
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--name', default='S10-Transfer.epub')
    parser.add_argument('--family', default='iPhone', choices=['iPhone', 'iPad'])
    args = parser.parse_args()
    platform = 'ios-simulator' if args.family == 'iPhone' else 'ipados-simulator'
    sdk = args.sdk.absolute()
    fixtures, resources = args.fixtures.absolute(), args.resources.absolute()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fixtures / 'manifest.json').read_text())
    name = args.name
    expected = manifest[name]
    data = (fixtures / name).read_bytes()
    checks = []

    def check(check_id, ok, detail=''):
        checks.append({'id': check_id, 'passed': bool(ok), 'detail': detail})

    check('fixture.manifest-matches-file',
          hashlib.sha256(data).hexdigest() == expected['sha256'] and len(data) == expected['bytes'],
          'local fixture bytes')

    sys.path.insert(0, str(ROOT / 'tools'))
    from apple_swift import flags  # noqa: E402  (installed product archives and includes)

    sdk_path = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'],
                                       text=True).strip()
    app = output / 'S10Driver.app'
    if app.exists():
        shutil.rmtree(app)
    (app / 'Frameworks').mkdir(parents=True)
    driver = app / 'S10Driver'
    command = ['xcrun', 'swiftc', '-swift-version', '5', '-O', '-sdk', sdk_path,
               '-target', 'arm64-apple-ios15.0-simulator', '-L', str(sdk / 'lib'), '-lexreader',
               *flags(sdk), '-Xlinker', '-rpath', '-Xlinker', '@executable_path/Frameworks',
               '-o', str(driver)]
    command += [str(ROOT / rel) for rel in OWNER_SOURCES]
    build = run(command)
    (output / 'swiftc.log').write_text(build.stdout + build.stderr)

    info = {
        'CFBundleExecutable': 'S10Driver',
        'CFBundleIdentifier': BUNDLE_ID,
        'CFBundleName': 'S10Driver',
        'CFBundleDisplayName': 'EXReader S10 transfer',
        'CFBundlePackageType': 'APPL',
        'CFBundleVersion': '1',
        'CFBundleShortVersionString': '1.0',
        'MinimumOSVersion': '15.0',
        'LSRequiresIPhoneOS': True,
        'UILaunchScreen': {},
        'UIDeviceFamily': [1, 2],
        'CFBundleSupportedPlatforms': ['iPhoneSimulator'],
        'UIFileSharingEnabled': True,
        'LSSupportsOpeningDocumentsInPlace': True,
        'EXRSourceSHA': os.environ.get('GITHUB_SHA', ''),
    }
    (app / 'Info.plist').write_bytes(plistlib.dumps(info))
    for resource in ('Reader.otf', 'reader-catalog-v1.sql'):
        shutil.copyfile(resources / resource, app / resource)
    runtimes = sorted(sdk.glob('lib/libexreader*.dylib'))
    check('build.sdk-runtime-present', bool(runtimes), ','.join(path.name for path in runtimes))
    for runtime in runtimes:
        shutil.copyfile(runtime, app / 'Frameworks' / runtime.name)
    installed = plistlib.loads((app / 'Info.plist').read_bytes())
    check('bundle.files-sharing-declared',
          installed.get('UIFileSharingEnabled') is True
          and installed.get('LSSupportsOpeningDocumentsInPlace') is True,
          json.dumps({'UIFileSharingEnabled': installed.get('UIFileSharingEnabled'),
                      'LSSupportsOpeningDocumentsInPlace': installed.get('LSSupportsOpeningDocumentsInPlace')}))

    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json'],
                                                 text=True))
    choices = [(runtime, device['name'], device['udid']) for runtime, rows in devices['devices'].items()
               for device in rows if device.get('isAvailable') and device['name'].startswith(args.family)]
    if not choices:
        raise SystemExit('no available ' + args.family + ' simulator runtime')
    runtime, device_name, udid = max(choices)
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
    run(['xcrun', 'simctl', 'erase', udid])
    run(['xcrun', 'simctl', 'boot', udid])
    run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=900)
    run(['xcrun', 'simctl', 'install', udid, str(app)])
    container = subprocess.check_output(['xcrun', 'simctl', 'get_app_container', udid, BUNDLE_ID, 'data'],
                                         text=True).strip()
    documents = Path(container) / 'Documents'
    inbox = documents / 'Inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixtures / name, inbox / name)
    check('delivery.copy-into-documents-container',
          (inbox / name).is_file()
          and hashlib.sha256((inbox / name).read_bytes()).hexdigest() == expected['sha256'],
          str(inbox / name))

    launch = run(['xcrun', 'simctl', 'launch', udid, BUNDLE_ID, '-S10Inbox', name], check=False)
    (output / 'launch.log').write_text(launch.stdout + launch.stderr)
    report_path = documents / 's10-report.json'
    deadline = time.time() + 420
    while time.time() < deadline and not report_path.is_file():
        time.sleep(3)
    driver_report = {}
    if report_path.is_file():
        driver_report = json.loads(report_path.read_text())
        (output / 'driver-report.json').write_text(json.dumps(driver_report, indent=2, sort_keys=True) + '\n')
        shutil.copyfile(report_path, output / 'driver-report.original.json')
    else:
        run(['xcrun', 'simctl', 'terminate', udid, BUNDLE_ID], check=False)
        logs = subprocess.run(['xcrun', 'simctl', 'spawn', udid, 'log', 'show', '--last', '5m',
                               '--predicate', 'process == "S10Driver"'], capture_output=True, text=True)
        (output / 'simulator.log').write_text(logs.stdout + logs.stderr)

    problems = []
    check('driver.report-written', bool(driver_report), str(report_path))
    check('driver.accepted-flag', driver_report.get('accepted') is True,
          json.dumps(driver_report.get('problems', [])))
    delivery = driver_report.get('delivery', {})
    check('driver.delivered-original', delivery.get('sha256') == expected['sha256']
          and delivery.get('bytes') == expected['bytes'],
          json.dumps(delivery, sort_keys=True))
    check('driver.files-sharing-visible', delivery.get('info_plist_file_sharing') is True
          and delivery.get('info_plist_open_in_place') is True,
          json.dumps({'file_sharing': delivery.get('info_plist_file_sharing'),
                      'open_in_place': delivery.get('info_plist_open_in_place')}))
    stored = driver_report.get('stored_source', {})
    check('sdk.stored-source-matches-fixture', stored.get('sha256') == expected['sha256'],
          json.dumps(stored, sort_keys=True))
    for row in driver_report.get('checks', []):
        check('owner.' + str(row.get('id')), row.get('passed') is True, str(row.get('detail')))

    problems = [row['id'] + ': ' + row['detail'] for row in checks if not row['passed']]
    report = {
        'schema': 1,
        'package': 'S10',
        'role': 'apple',
        'platform': platform,
        'source_sha': os.environ.get('GITHUB_SHA', ''),
        'run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
        'simulator': {'runtime': runtime, 'name': device_name, 'udid': udid},
        'fixture': {'name': name, 'sha256': expected['sha256'], 'bytes': expected['bytes']},
        'delivery': {
            'method': 'copy into the app Documents container (Files app sharing location)',
            'physical_cable_or_files_transfer': False,
            'container': container,
        },
        'entry': {
            'owner': 'examples/apple HostReaderModel.importFile(url:) (unchanged)',
            'security_scoped': True,
            'document_picker_ui_driven': False,
        },
        'driver_report': driver_report,
        'checks': checks,
        'problems': problems,
        'accepted': not problems,
        'physical_device_execution': False,
        'usb_cable_execution': False,
        'finder_or_itunes_transfer': False,
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
    print(json.dumps({'checks': len(checks), 'problems': problems}, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
