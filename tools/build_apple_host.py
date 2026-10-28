#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the native Apple reference host against an installed EXReader SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
from host_font import fetch as host_font
from run_benchmarks import make_epub
from apple_swift import flags as product_flags
from check_apple_product import inspect as inspect_product

ROOT = Path(__file__).absolute().parents[1]


def run(*command):
    subprocess.run([str(x) for x in command], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--platform', choices=['macos', 'simulator', 'iphoneos'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product-prefix', type=Path)
    parser.add_argument('--wave3', action='store_true', help='Enable the installed five-feature product without review entry points')
    parser.add_argument('--selector-bytes-candidate', action='store_true',
                        default=os.environ.get('EXR_APPLE_RAW3', 'OFF') == 'ON')
    parser.add_argument('--sdk-version', choices=('3.40.0', '3.41.0', '3.42.0'),
                        default=os.environ.get('EXR_APPLE_SDK_VERSION', '3.40.0'))
    parser.add_argument('--page-theme', action='store_true', default=os.environ.get('EXR_APPLE_PAGE_THEME', 'OFF') == 'ON',
                        help='Explicit SDK3.41 or SDK3.42 page-theme candidate')
    args = parser.parse_args()
    if args.sdk_version not in ('3.40.0', '3.41.0', '3.42.0'):
        parser.error('Unsupported explicit Apple SDK version')
    if os.environ.get('EXR_APPLE_PAGE_THEME', 'OFF') not in ('OFF', 'ON'):
        parser.error('EXR_APPLE_PAGE_THEME must be explicitly OFF or ON')
    if os.environ.get('EXR_APPLE_RAW3', 'OFF') not in ('OFF', 'ON'):
        parser.error('EXR_APPLE_RAW3 must be explicitly OFF or ON')
    if sys.platform != 'darwin':
        parser.error('The Apple SDK build requires a macOS host')
    sdk, output = args.sdk.absolute(), args.output.absolute()
    if args.page_theme and args.sdk_version not in ('3.41.0', '3.42.0'):
        parser.error('--page-theme requires explicit --sdk-version=3.41.0 or 3.42.0')
    if args.wave3 and not args.selector_bytes_candidate:
        parser.error('--wave3 requires --selector-bytes-candidate')
    if output.exists():
        parser.error('Choose a new output directory to preserve earlier artifacts')
    for path in [sdk/'include/exreader.h', sdk/'lib', ROOT/'examples/apple/ReaderApp.swift',
                 ROOT/'examples/apple/HostSDK.swift']:
        if not path.exists():
            parser.error('Missing SDK or host source: '+str(path))
    version = re.search(r'#define EXR_VERSION "([^"]+)"', (sdk/'include/exr/base.h').read_text())[1]
    if version != args.sdk_version:
        parser.error('Installed SDK version differs from the explicitly selected version')
    output.mkdir(parents=True)
    app = output/'EXReader.app'
    mobile = args.platform != 'macos'
    executable = app/'EXReader' if mobile else app/'Contents/MacOS/EXReader'
    resources = app if mobile else app/'Contents/Resources'
    frameworks = app/'Frameworks' if mobile else app/'Contents/Frameworks'
    for folder in [executable.parent, resources, frameworks]:
        folder.mkdir(parents=True, exist_ok=True)
    native_sdk = {'macos': 'macosx', 'simulator': 'iphonesimulator', 'iphoneos': 'iphoneos'}[args.platform]
    sdk_path = subprocess.check_output(['xcrun', '--sdk', native_sdk, '--show-sdk-path'], text=True).strip()
    architecture = 'arm64' if mobile else subprocess.check_output(['uname', '-m'], text=True).strip()
    target = architecture+('-apple-macosx12.0' if not mobile else '-apple-ios15.0'+('-simulator' if args.platform == 'simulator' else ''))
    rpath = '@executable_path/Frameworks' if mobile else '@executable_path/../Frameworks'
    sources = sorted((ROOT/'examples/apple').glob('*.swift'))
    command = ['xcrun', '--sdk', native_sdk, 'swiftc', '-swift-version', '5', '-O', '-parse-as-library',
               '-sdk', sdk_path, '-target', target, '-I', sdk/'include', '-L', sdk/'lib',
               '-lexreader', *product_flags(sdk, args.product_prefix, args.selector_bytes_candidate, args.wave3), '-Xlinker', '-rpath', '-Xlinker', rpath,
               ROOT/'bindings/swift/EXReader.swift', *sources, '-o', executable,
               '-Xlinker', '-map', '-Xlinker', output/'product-link.map']
    if args.selector_bytes_candidate and args.product_prefix:
        command[4:4] = ['-I', str(args.product_prefix.absolute() / 'include')]
    if args.page_theme:
        command += ['-D', 'EXR_APPLE_PAGE_THEME']
    run(*command)
    (output/'product-link.json').write_text(json.dumps(inspect_product(executable, output/'product-link.map', args.selector_bytes_candidate), indent=2)+'\n')
    source_sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    info = {'CFBundleExecutable': 'EXReader', 'CFBundleIdentifier': 'org.exreader.host',
            'CFBundleName': 'EXReader', 'CFBundleDisplayName': 'EXReader',
            'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1',
            'CFBundleShortVersionString': version, 'EXRSourceSHA': source_sha,
            'EXRRawSelectorEnabled': args.selector_bytes_candidate, 'EXRWave3Enabled': args.wave3}
    if mobile:
        info.update({'MinimumOSVersion': '15.0', 'LSRequiresIPhoneOS': True,
                     'UIApplicationSceneManifest': {'UIApplicationSupportsMultipleScenes': True},
                     'CFBundleSupportedPlatforms': ['iPhoneSimulator' if args.platform == 'simulator' else 'iPhoneOS'],
                     'UIDeviceFamily': [1, 2], 'UILaunchScreen': {}, 'UIFileSharingEnabled': True,
                     'LSSupportsOpeningDocumentsInPlace': True,
                     'UISupportedInterfaceOrientations': ['UIInterfaceOrientationPortrait',
                         'UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight'],
                     'UISupportedInterfaceOrientations~ipad': ['UIInterfaceOrientationPortrait',
                         'UIInterfaceOrientationPortraitUpsideDown', 'UIInterfaceOrientationLandscapeLeft',
                         'UIInterfaceOrientationLandscapeRight']})
    else:
        info.update({'LSMinimumSystemVersion': '12.0', 'NSHighResolutionCapable': True})
    with (app/'Info.plist' if mobile else app/'Contents/Info.plist').open('wb') as stream:
        plistlib.dump(info, stream)
    for name, source in [('Sample.pdf', 'pdf-public.pdf')]:
        shutil.copyfile(ROOT/'tests/fixtures'/source, resources/name)
    shutil.copyfile(ROOT/'apps/reader/store/001_catalog.sql', resources/'reader-catalog-v1.sql')
    make_epub(resources/'Sample.epub', 3, 16384, single_paragraph=True)
    font = host_font(ROOT/'build/host-font-cache')
    shutil.copyfile(font/'Reader.otf', resources/'Reader.otf')
    shutil.copyfile(font/'OFL.txt', resources/'Noto-OFL.txt')
    shutil.copyfile(ROOT/'LICENSE', resources/'EXReader-LICENSE.txt')
    shutil.copyfile(ROOT/'THIRD_PARTY_NOTICES.md', resources/'THIRD_PARTY_NOTICES.md')
    shutil.copytree(sdk/'share/exreader/licenses', resources/'licenses')
    libraries = list((sdk/'lib').glob('libexreader*.dylib'))
    if not libraries:
        parser.error('Installed SDK is missing its shared runtime')
    # Keep versioned runtime names required by the linker's install name.
    for library in libraries:
        shutil.copyfile(library, frameworks/library.name)
        run('codesign', '--force', '--sign', '-', frameworks/library.name)
    run('codesign', '--force', '--deep', '--sign', '-', app)
    manifest = {'schema': 1, 'source_sha': source_sha, 'sdk_version': version,
                'page_theme_enabled': args.page_theme,
                'selector_bytes_candidate': args.selector_bytes_candidate,
                'wave3_enabled': args.wave3,
                'platform': args.platform, 'target': target, 'bundle': str(app),
                'signing': 'ad-hoc; device installation requires the owner signing identity',
                'files': {str(p.relative_to(app)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(app.rglob('*')) if p.is_file()}}
    (output/'build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if args.platform == 'iphoneos':
        payload = output/'Payload'
        payload.mkdir()
        shutil.copytree(app, payload/'EXReader.app')
        archive = shutil.make_archive(str(output/'EXReader-iOS-unsigned'), 'zip', root_dir=output, base_dir='Payload')
        Path(archive).rename(output/'EXReader-iOS-unsigned.ipa')
    print('Built '+str(app))


if __name__ == '__main__':
    main()
