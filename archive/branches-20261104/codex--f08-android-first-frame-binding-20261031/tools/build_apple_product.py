# SPDX-License-Identifier: MIT
"""Install product packages beside an already installed frozen Apple SDK."""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
from apple_swift import WAVE3_MODULES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--target', choices=('macos', 'iphonesimulator', 'iphoneos'), required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--product-prefix', type=Path)
    parser.add_argument('--wave3', action='store_true', help='Install the explicit raw five-feature host profile')
    parser.add_argument('--organization', action='store_true', help='Install the revision-aware organization metadata owner')
    parser.add_argument('--selector-bytes-candidate', action='store_true',
                        default=os.environ.get('EXR_APPLE_RAW3', 'OFF') == 'ON')
    parser.add_argument('--sdk-version', choices=('3.40.0', '3.41.0', '3.42.0'),
                        default=os.environ.get('EXR_APPLE_SDK_VERSION', '3.40.0'))
    args = parser.parse_args()
    if args.sdk_version not in ('3.40.0', '3.41.0', '3.42.0'):
        parser.error('Unsupported explicit Apple SDK version')
    root = Path(__file__).absolute().parents[1]
    sdk = args.sdk.absolute()
    stage = args.product_prefix.absolute() if args.product_prefix else sdk
    hash_prefix = (stage / 'opds-hash').resolve()
    if os.environ.get('EXR_APPLE_RAW3', 'OFF') not in ('OFF', 'ON'):
        parser.error('EXR_APPLE_RAW3 must be explicitly OFF or ON')
    if args.selector_bytes_candidate and (args.sdk_version not in ('3.41.0', '3.42.0') or stage.resolve() == sdk.resolve()):
        parser.error('Raw selector candidate requires explicit SDK3.41 or SDK3.42 and an independent product prefix')
    if args.wave3 and not args.selector_bytes_candidate:
        parser.error('--wave3 requires --selector-bytes-candidate')
    version = re.search(r'#define EXR_VERSION "([^"]+)"', (sdk / 'include/exr/base.h').read_text())
    if version is None or version[1] != args.sdk_version:
        parser.error('Installed SDK version differs from the explicitly selected version')
    native = 'macosx' if args.target == 'macos' else args.target
    sysroot = subprocess.check_output(['xcrun', '--sdk', native, '--show-sdk-path'], text=True).strip()
    common = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + str(stage),
              '-DCMAKE_PREFIX_PATH=' + (';'.join(map(str, (stage, sdk))) if stage != sdk else str(stage)), '-DEXR_SDK=' + str(sdk),
              '-DEXR_SDK_VERSION=' + args.sdk_version,
              '-DREADER_PRODUCT_PREFIX=' + str(stage),
              '-DREADER_ORIGINAL_HASH_PREFIX=' + str(hash_prefix),
              '-DLIBXML2_INCLUDE_DIR=' + sysroot + '/usr/include/libxml2',
              '-DLIBXML2_LIBRARY=' + sysroot + '/usr/lib/libxml2.tbd']
    if args.target == 'macos':
        common += ['-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0']
    else:
        common += ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=' + args.target,
                   '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0',
                   '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    # Cross compilation roots package searches in the Apple SDK. Explicit
    # installed config paths keep product dependencies in this target's stage.
    packages = ('EXReader', 'EXReaderProductCatalog', 'EXReaderRevisions', 'EXReaderCommands',
                'EXReaderWebDAV', 'EXReaderSync', 'EXReaderSession', 'EXReaderCredentials', 'EXReaderReadingState',
                'EXReaderSearch', 'EXReaderNavigation', 'EXReaderReadingCommands', 'EXReaderAnnotationView')
    common += ['-D' + name + '_DIR=' + str((sdk if name == 'EXReader' else stage) / 'lib/cmake' / name) for name in packages]
    common += ['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if args.selector_bytes_candidate else 'OFF')]
    modules = [('opds-hash', 'extras/opds'),
               ('catalog', 'apps/reader/store/native'), ('revisions', 'apps/reader/revisions'),
               ('commands', 'apps/reader/commands'), ('webdav', 'extras/webdav'),
               ('sync', 'apps/reader/sync'), ('session', 'apps/reader/session'),
               ('credentials', 'extras/credentials'), ('reading-state', 'apps/reader/reading-state'),
               ('search', 'apps/reader/search'), ('navigation', 'apps/reader/navigation'),
               ('reading-commands', 'apps/reader/reading-commands'), ('annotation-view', 'apps/reader/annotation-view')]
    modules.append(('desktop-metadata', 'apps/reader/desktop-metadata'))
    if args.wave3:
        modules += [(name, 'apps/reader/' + name) for name, _, _ in WAVE3_MODULES]
    wave3_options = {name: list(options) for name, _, options in WAVE3_MODULES}
    for name, relative in modules:
        build = args.build.absolute() / name
        options = ['-DEXR_WEBDAV_APPLE_URLSESSION=ON'] if name == 'webdav' else []
        if name == 'opds-hash':
            options += ['-DEXREADER_OPDS_HASH_ONLY=ON', '-DCMAKE_INSTALL_PREFIX=' + str(hash_prefix)]
        if args.wave3:
            options += wave3_options.get(name, [])
        for command in (['cmake', '-S', str(root / relative), '-B', str(build), *common, *options],
                        ['cmake', '--build', str(build), '--parallel', '4'],
                        ['cmake', '--install', str(build)]):
            subprocess.run(command, check=True)
    if args.wave3:
        for _, target, _ in WAVE3_MODULES:
            for path in (stage / 'lib' / ('lib' + target + '.a'), stage / 'include' / (target + '.h')):
                if not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError('Required installed wave3 product missing: ' + str(path))
    family = {'EXReaderRevisions': '0.4.0', 'EXReaderReadingState': '0.2.0',
              'EXReaderReadingCommands': '0.2.0', 'EXReaderAnnotationView': '0.2.0',
              'EXReaderCommands': '0.2.0', 'EXReaderSync': '0.2.0', 'EXReaderSession': '0.2.0'}
    if args.selector_bytes_candidate:
        proof = args.build.absolute() / 'exact-family-source'
        proof.mkdir(parents=True, exist_ok=True)
        body = 'cmake_minimum_required(VERSION 3.24)\nproject(AppleRawFamily LANGUAGES C CXX)\n'
        body += 'find_package(EXReader ' + args.sdk_version + ' EXACT CONFIG REQUIRED COMPONENTS core library)\n'
        body += ''.join('find_package(' + name + ' ' + version + ' EXACT CONFIG REQUIRED)\n'
                        for name, version in family.items())
        (proof / 'CMakeLists.txt').write_text(body)
        subprocess.run(['cmake', '-S', str(proof), '-B', str(args.build.absolute() / 'exact-family'), *common], check=True)
    source = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    manifest = {'source_sha': source, 'target': args.target, 'sdk_version': args.sdk_version,
                'installed_modules': [x[0] for x in modules],
                'sqlite_provider': 'libreader_catalog_sqlite.a', 'system_sqlite_fallback': False,
                'reading_resolver_linked': False, 'webdav_transport': 'Foundation URLSession',
                'wave3_enabled': args.wave3, 'organization_enabled': True}
    manifest.update(selector_bytes_candidate=args.selector_bytes_candidate,
                    product_prefix=str(stage), sdk_prefix=str(sdk),
                    original_hash_prefix=str(hash_prefix), original_hash_package='EXReaderOPDSHash 0.1.0',
                    exact_candidate_family=family if args.selector_bytes_candidate else {})
    (stage / 'share/exreader-apple').mkdir(parents=True, exist_ok=True)
    (stage / 'share/exreader-apple/product.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
