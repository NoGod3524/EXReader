"""Actions-only real SDK and separate exact raw product installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]


def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=('macos', 'iphonesimulator'), required=True)
    args = parser.parse_args()
    out = ROOT / 'build/raw3-ios-sdk' / args.target
    sdk, raw = out / 'sdk', out / 'raw-products'
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_TOOLS=OFF', '-DEXR_ENABLE_AAC=OFF']
    if args.target == 'iphonesimulator':
        options += ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator', '-DCMAKE_OSX_ARCHITECTURES=arm64',
                    '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0', '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    run('cmake', '-S', '.', '-B', out / 'sdk-build', *options)
    run('cmake', '--build', out / 'sdk-build', '--parallel', '4')
    run('cmake', '--install', out / 'sdk-build', '--prefix', sdk)
    run(sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', '3.41.0',
        '--target', args.target, '--build', out / 'legacy-build')
    run(sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', '3.41.0',
        '--target', args.target, '--product-prefix', raw, '--selector-bytes-candidate', '--build', out / 'raw-build')
    run(sys.executable, 'tests/apple_host/evidence_contract.py', 'sdk', '--root', sdk, '--platform', args.target,
        '--output', out / 'sdk-identity.json')
    identity = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'target': args.target,
                'raw_files': {path.relative_to(raw).as_posix(): {'bytes': path.stat().st_size,
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in raw.rglob('*') if path.is_file()}}
    (out / 'raw-identity.json').write_text(json.dumps(identity, indent=2) + '\n')


if __name__ == '__main__':
    main()
