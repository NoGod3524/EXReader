# SPDX-License-Identifier: MIT
"""Build and launch actual production-profile Apple archives in Actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    subprocess.run([str(value) for value in args], cwd=ROOT, check=True)


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.platform != 'darwin':
        raise SystemExit('Apple production builds and launch checks are Actions macOS only')
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=('macos', 'iphonesimulator'), required=True)
    args = parser.parse_args()
    out = ROOT / 'build/composition-apple' / args.target
    if out.exists():
        raise SystemExit('Choose a fresh run; preserve existing build evidence')
    out.mkdir(parents=True)
    sdk, products = out / 'sdk', out / 'products'
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_TOOLS=OFF',
               '-DEXR_ENABLE_AAC=OFF', '-DCMAKE_INSTALL_PREFIX=' + str(sdk)]
    if args.target == 'iphonesimulator':
        options += ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator',
                    '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0',
                    '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    run('cmake', '-S', '.', '-B', out / 'sdk-build', *options)
    run('cmake', '--build', out / 'sdk-build', '--parallel', '4', '--target', 'install')
    run(sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', '3.41.0',
        '--target', args.target, '--product-prefix', products, '--selector-bytes-candidate',
        '--wave3', '--build', out / 'product-build')
    payload = out / 'payload'
    run(sys.executable, 'tools/build_apple_host.py', '--sdk', sdk, '--sdk-version', '3.41.0',
        '--product-prefix', products, '--selector-bytes-candidate', '--wave3', '--page-theme',
        '--platform', 'macos' if args.target == 'macos' else 'simulator', '--output', payload)
    source = os.environ['GITHUB_SHA']
    build = json.loads((payload / 'build.json').read_text())
    assert build['source_sha'] == source and build['wave3_enabled'] is True
    devices = ('macos',) if args.target == 'macos' else ('iphone', 'ipad')
    results = []
    for device in devices:
        delivery, fresh = out / ('delivery-' + device), out / ('fresh-' + device)
        run(sys.executable, 'tools/reader_wave3_package/assemble.py', '--target', device,
            '--payload', payload, '--output', delivery, '--source-sha', source,
            '--sdk-version', '3.41.0', '--require-build-identity')
        archive, = delivery.glob('EXReader-' + device + '-*.zip')
        run(sys.executable, 'tools/reader_wave3_package/unpack.py', '--target', device,
            '--archive', archive, '--manifest', delivery / 'manifest.json',
            '--into', fresh, '--report', out / (device + '-unpack.json'))
        app = fresh / 'EXReader.app'
        binary = app / ('Contents/MacOS/EXReader' if device == 'macos' else 'EXReader')
        original = payload / 'EXReader.app' / binary.relative_to(app)
        assert binary.read_bytes() == original.read_bytes(), 'archive changed actual executable'
        run(sys.executable, 'tools/check_apple_host.py', '--bundle', app,
            '--device', device, '--output', out / ('startup-' + device))
        results.append({'device': device, 'executable_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                        'executable_bytes': binary.stat().st_size,
                        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                        'archive_bytes': archive.stat().st_size})
    report = {'scope': 'production-profile-build-archive-and-native-startup',
              'source': source, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'target': args.target,
              'review_macros_enabled': False, 'full_feature_gui_accepted': False,
              'physical_device_accepted': False, 'results': results, 'ok': True}
    (out / 'production-startup.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
