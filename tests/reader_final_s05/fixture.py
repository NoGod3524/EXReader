#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the CI-only simulator fixture app and prove the verifier with mutants.

The fixture bundle is compiled inside the Actions job from fixture/AppDelegate.m
and fixture/Kit.m. It is an ad-hoc signed iPhone/iPad simulator app with a
nested framework-style dylib, a resource, a license file and the source binding
key. Every mutant is a single deliberate change to that generated bundle; the
verifier must reject each one with a named check. The fixture is never a product
build and never stands in for a producer run.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app_bundle


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(argv, timeout=900):
    proc = subprocess.run([str(value) for value in argv], capture_output=True, text=True, timeout=timeout)
    require(proc.returncode == 0, 'command failed: %s\n%s\n%s'
            % (' '.join(str(value) for value in argv), (proc.stdout or '')[-3000:], (proc.stderr or '')[-3000:]))
    return proc.stdout.strip()


def sdk():
    return command(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'])


def runtime_version():
    value = json.loads(command(['xcrun', 'simctl', 'list', 'runtimes', '--json']))
    versions = []
    for runtime in value.get('runtimes') or []:
        if not runtime.get('isAvailable') or 'iOS' not in str(runtime.get('identifier', '')):
            continue
        version = runtime.get('version')
        if version:
            versions.append(version)
    require(versions, 'no available iOS simulator runtime on this runner')
    versions.sort(key=lambda item: app_bundle.version_tuple(item) or ())
    return versions[-1]


def build(output, source_sha):
    output = Path(output).absolute()
    require(not output.exists(), 'choose a new fixture directory: ' + str(output))
    output.mkdir(parents=True)
    app = output / 'EXReaderS05Fixture.app'
    frameworks = app / 'Frameworks'
    frameworks.mkdir(parents=True)
    sysroot = sdk()
    target = 'arm64-apple-ios15.0-simulator'
    command(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-dynamiclib', '-fobjc-arc',
             '-target', target, '-isysroot', sysroot, '-install_name', '@rpath/libS05Kit.dylib',
             '-framework', 'Foundation', str(HERE / 'fixture' / 'Kit.m'),
             '-o', str(frameworks / 'libS05Kit.dylib')])
    command(['xcrun', '--sdk', 'iphonesimulator', 'clang', '-fobjc-arc', '-target', target,
             '-isysroot', sysroot, '-framework', 'UIKit', '-framework', 'Foundation',
             '-L', str(frameworks), '-lS05Kit', '-Wl,-rpath,@executable_path/Frameworks',
             str(HERE / 'fixture' / 'AppDelegate.m'), '-o', str(app / 'EXReaderS05Fixture')])
    info = {
        'CFBundleExecutable': 'EXReaderS05Fixture',
        'CFBundleIdentifier': 'org.exreader.s05fixture',
        'CFBundleName': 'EXReaderS05Fixture',
        'CFBundleDisplayName': 'EXReader S05 fixture',
        'CFBundlePackageType': 'APPL',
        'CFBundleVersion': '1',
        'CFBundleShortVersionString': '1.0',
        'CFBundleSupportedPlatforms': ['iPhoneSimulator'],
        'UIDeviceFamily': [1, 2],
        'MinimumOSVersion': '15.0',
        'LSRequiresIPhoneOS': True,
        'UILaunchScreen': {},
        'UIFileSharingEnabled': True,
        'LSSupportsOpeningDocumentsInPlace': True,
        'UISupportedInterfaceOrientations': ['UIInterfaceOrientationPortrait'],
        'EXRSourceSHA': source_sha,
        'S05Fixture': True,
    }
    with (app / 'Info.plist').open('wb') as stream:
        plistlib.dump(info, stream)
    (app / 'Sample.txt').write_text('EXReader S05 fixture resource\n')
    licenses = app / 'Licenses'
    licenses.mkdir()
    (licenses / 'Notice.txt').write_text('Fixture only. Not a product distribution.\n')
    command(['codesign', '--force', '--sign', '-', str(frameworks / 'libS05Kit.dylib')])
    command(['codesign', '--force', '--deep', '--sign', '-', str(app)])
    files, _symlinks, _special = app_bundle.walk(app)
    record = {'schema': 1, 'source_sha': source_sha, 'app': str(app), 'sdk': sysroot, 'target': target,
              'identifier': info['CFBundleIdentifier'], 'executable': info['CFBundleExecutable'],
              'executable_sha256': app_bundle.sha256(app / info['CFBundleExecutable']),
              'info_plist_sha256': app_bundle.sha256(app / 'Info.plist'),
              'files': len(files), 'bytes': sum(entry['bytes'] for entry in files),
              'signature': app_bundle.signature(app),
              'fixture_only': True}
    (output / 'fixture.json').write_text(json.dumps(record, indent=2) + '\n')
    print('fixture ' + str(app))
    return record


def copy_app(source, destination):
    if shutil.which('ditto'):
        command(['ditto', str(source), str(destination)])
    else:
        shutil.copytree(str(source), str(destination), symlinks=True)


def rewrite_info(app, changes):
    path = Path(app) / 'Info.plist'
    info = plistlib.loads(path.read_bytes())
    for key, value in changes.items():
        if value is None:
            info.pop(key, None)
        else:
            info[key] = value
    with path.open('wb') as stream:
        plistlib.dump(info, stream)


def patch_cputype(path):
    data = bytearray(Path(path).read_bytes())
    require(struct.unpack_from('<I', data, 0)[0] == 0xFEEDFACF, 'fixture executable is not thin 64-bit Mach-O')
    struct.pack_into('<I', data, 4, 0x01000007)
    Path(path).write_bytes(bytes(data))


def patch_platform(path):
    data = bytearray(Path(path).read_bytes())
    parsed = app_bundle.parse_binary(path)
    require(not parsed['fat'], 'fixture executable unexpectedly fat')
    offset = None
    for item in parsed['slices'][0]['commands']:
        if item['cmd'] == app_bundle.LC_BUILD_VERSION:
            offset = item['offset']
            break
    require(offset is not None, 'fixture executable has no LC_BUILD_VERSION')
    struct.pack_into('<I', data, offset + 8, 2)
    Path(path).write_bytes(bytes(data))


def mutants(app, work, implementation_sha, version):
    app = Path(app)

    def platform_device(target):
        rewrite_info(target, {'CFBundleSupportedPlatforms': ['iPhoneOS']})

    def family_ipad(target):
        rewrite_info(target, {'UIDeviceFamily': [2]})

    def executable_missing(target):
        (target / 'EXReaderS05Fixture').unlink()

    def executable_not_executable(target):
        os.chmod(str(target / 'EXReaderS05Fixture'), 0o644)

    def identifier_missing(target):
        rewrite_info(target, {'CFBundleIdentifier': ''})

    def minimum_os_newer(target):
        rewrite_info(target, {'MinimumOSVersion': '99.0'})

    def info_plist_missing(target):
        (target / 'Info.plist').unlink()

    def arch_x86_only(target):
        patch_cputype(target / 'EXReaderS05Fixture')

    def arch_device_platform(target):
        patch_platform(target / 'EXReaderS05Fixture')

    def platform_device_nested(target):
        patch_platform(target / 'Frameworks' / 'libS05Kit.dylib')

    def symlink_escape(target):
        os.symlink('/etc/passwd', str(target / 'escape'))

    def private_entitlement(target):
        rights = work / 'entitlements.plist'
        with rights.open('wb') as stream:
            plistlib.dump({'com.apple.private.security.no-sandbox': True}, stream)
        command(['codesign', '--force', '--sign', '-', str(target / 'Frameworks' / 'libS05Kit.dylib')])
        command(['codesign', '--force', '--sign', '-', '--entitlements', str(rights), str(target)])

    def signature_tampered(target):
        path = target / 'Sample.txt'
        path.write_bytes(path.read_bytes() + b'tampered\n')

    def nested_library_replaced(target):
        (target / 'Frameworks' / 'libS05Kit.dylib').write_text('not a mach-o binary\n')

    cases = [
        ('platform_device', platform_device, 'bundle.platform'),
        ('family_ipad_only', family_ipad, 'bundle.family'),
        ('executable_missing', executable_missing, 'bundle.executable'),
        ('executable_not_executable', executable_not_executable, 'bundle.executable'),
        ('identifier_missing', identifier_missing, 'bundle.identifier'),
        ('minimum_os_newer', minimum_os_newer, 'bundle.minimum_os'),
        ('info_plist_missing', info_plist_missing, 'bundle.info_plist'),
        ('arch_x86_only', arch_x86_only, 'arch.main_arm64'),
        ('arch_device_platform', arch_device_platform, 'arch.simulator_platform'),
        ('arch_device_platform_nested', platform_device_nested, 'arch.simulator_platform'),
        ('resource_symlink_escape', symlink_escape, 'resources.symlink'),
        ('private_entitlement', private_entitlement, 'entitlements.no_private'),
        ('signature_tampered', signature_tampered, 'signature.verify'),
        ('nested_library_replaced', nested_library_replaced, 'arch.nested_code'),
    ]
    records = []
    for name, mutate, expected in cases:
        target = work / ('mutant-' + name) / app.name
        target.parent.mkdir()
        copy_app(app, target)
        mutate(target)
        value = app_bundle.manifest(target)
        checks = app_bundle.check(value, 'iphone', mode='fixture',
                                  runtime_version=version, expected_source=implementation_sha)
        found = next((item for item in checks if item['id'] == expected), None)
        records.append({'mutant': name, 'expected': expected,
                        'status': found['status'] if found else 'missing',
                        'detail': (found or {}).get('detail'),
                        'rejected': bool(found) and found['status'] == 'fail'})
    return records


def self_check(fixture, output, implementation_sha):
    fixture = Path(fixture)
    output = Path(output).absolute()
    require(not output.exists(), 'choose a new self-check directory: ' + str(output))
    output.mkdir(parents=True)
    record = json.loads((fixture / 'fixture.json').read_text())
    app = Path(record['app'])
    version = runtime_version()
    value = app_bundle.manifest(app)
    checks = app_bundle.check(value, 'iphone', mode='fixture', runtime_version=version,
                              expected_source=implementation_sha)
    failing = [item for item in checks if item['status'] == 'fail']
    valid = {'checks': checks, 'failing': [item['id'] for item in failing],
             'accepted': not failing, 'files': value['app']['files'], 'bytes': value['app']['bytes'],
             'runtime_version': version, 'signature': value['signature']['state'],
             'entitlements': value['signature']['entitlements']}
    work = output / 'mutants'
    work.mkdir()
    records = mutants(app, work, implementation_sha, version)
    producer_checks = app_bundle.check(value, 'iphone', mode='producer', runtime_version=version,
                                       expected_source=implementation_sha)
    producer_fixture = next(item for item in producer_checks if item['id'] == 'bundle.not_fixture')
    result = {
        'schema': 1,
        'kind': 'reader-final-s05-fixture-self-check',
        'implementation': {'sha': implementation_sha},
        'fixture': {'app': str(app), 'identifier': record['identifier'],
                    'executable_sha256': record['executable_sha256'],
                    'info_plist_sha256': record['info_plist_sha256']},
        'runtime_version': version,
        'valid': valid,
        'mutants': records,
        'rejected': sum(1 for item in records if item['rejected']),
        'total': len(records),
        'fixture_cannot_be_producer': producer_fixture['status'] == 'fail',
        'passed': bool(valid['accepted']) and all(item['rejected'] for item in records)
                   and producer_fixture['status'] == 'fail',
    }
    (output / 'fixture-checks.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'valid_accepted': valid['accepted'], 'rejected': result['rejected'],
                      'total': result['total'], 'fixture_cannot_be_producer': result['fixture_cannot_be_producer'],
                      'passed': result['passed'], 'runtime_version': version}, indent=2))
    return 0 if result['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--implementation-sha', required=True)
    args = parser.parse_args()
    require(sys.platform == 'darwin', 'the fixture app is compiled on macOS only')
    if args.build:
        build(args.output, args.implementation_sha)
        return 0
    if args.self_check:
        require(args.fixture is not None, '--self-check needs --fixture')
        return self_check(args.fixture, args.output, args.implementation_sha)
    parser.error('choose --build or --self-check')


if __name__ == '__main__':
    sys.exit(main())
