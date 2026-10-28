#!/usr/bin/env python3
"""Actions-only exact 3.42 Apple installation and native bundle proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = '8357eafa28423a7ab93ba08b823af80f01ad1505'
PATHS = ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings')

def run(*argv):
    subprocess.run(list(map(str, argv)), cwd=ROOT, check=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=('macos', 'iphonesimulator'), required=True)
    target = parser.parse_args().target
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert source == os.environ['GITHUB_SHA']
    if subprocess.run(['git', 'cat-file', '-e', CANDIDATE + '^{commit}'], cwd=ROOT).returncode:
        run('git', 'fetch', '--no-tags', 'origin', CANDIDATE)
    run('git', 'diff', '--exit-code', CANDIDATE, source, '--', *PATHS)
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', *PATHS], cwd=ROOT, text=True)
    out = ROOT / 'build/apple-sdk342' / target
    sdk, products = out / 'sdk', out / 'products'
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_TOOLS=OFF', '-DEXR_ENABLE_AAC=OFF']
    if target == 'iphonesimulator':
        options += ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator', '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0', '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    run('cmake', '-S', ROOT, '-B', out / 'sdk-build', *options)
    run('cmake', '--build', out / 'sdk-build', '--parallel', '4')
    run('cmake', '--install', out / 'sdk-build', '--prefix', sdk)
    run(sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', '3.42.0', '--target', target, '--product-prefix', products, '--selector-bytes-candidate', '--wave3', '--build', out / 'products-build')
    platform = 'macos' if target == 'macos' else 'simulator'
    run(sys.executable, 'tools/build_apple_host.py', '--sdk', sdk, '--sdk-version', '3.42.0', '--platform', platform, '--product-prefix', products, '--selector-bytes-candidate', '--wave3', '--page-theme', '--output', out / 'host')
    app = out / 'host/EXReader.app'
    executable = app / ('Contents/MacOS/EXReader' if target == 'macos' else 'EXReader')
    plist = app / ('Contents/Info.plist' if target == 'macos' else 'Info.plist')
    info = plistlib.loads(plist.read_bytes())
    assert info['EXRSourceSHA'] == source and info['CFBundleShortVersionString'] == '3.42.0'
    assert info['EXRWave3Enabled'] and info['EXRRawSelectorEnabled']
    assert json.loads((out / 'host/build.json').read_text())['page_theme_enabled'] is True
    run('codesign', '--verify', '--deep', '--strict', app)
    archive = out / 'EXReader.zip'
    run('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, archive)
    extracted = out / 'unpacked'
    run('ditto', '-x', '-k', archive, extracted)
    copied = extracted / 'EXReader.app' / executable.relative_to(app)
    assert copied.is_file() and sha(copied) == sha(executable)
    run('codesign', '--verify', '--deep', '--strict', extracted / 'EXReader.app')
    product = json.loads((products / 'share/exreader-apple/product.json').read_text())
    assert product['source_sha'] == source and product['sdk_version'] == '3.42.0' and product['wave3_enabled']
    identity = {'source_sha': source, 'sdk_content_candidate': CANDIDATE, 'sdk_content_paths': PATHS,
                'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'target': target,
                'product': product, 'archive_sha256': sha(archive), 'executable_sha256': sha(executable),
                'page_theme_enabled': True, 'physical_device': False, 'signed_distribution': False}
    (out / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    print(json.dumps(identity), flush=True)

if __name__ == '__main__':
    main()
