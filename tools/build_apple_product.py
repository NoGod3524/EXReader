# SPDX-License-Identifier: MIT
"""Install product packages beside an already installed frozen Apple SDK."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--target', choices=('macos', 'iphonesimulator', 'iphoneos'), required=True)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).absolute().parents[1]
    stage = args.sdk.absolute()
    native = 'macosx' if args.target == 'macos' else args.target
    sysroot = subprocess.check_output(['xcrun', '--sdk', native, '--show-sdk-path'], text=True).strip()
    common = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + str(stage),
              '-DCMAKE_PREFIX_PATH=' + str(stage), '-DEXR_SDK=' + str(stage),
              '-DREADER_PRODUCT_PREFIX=' + str(stage),
              '-DLIBXML2_INCLUDE_DIR=' + sysroot + '/usr/include/libxml2',
              '-DLIBXML2_LIBRARY=' + sysroot + '/usr/lib/libxml2.tbd']
    if args.target != 'macos':
        common += ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=' + args.target,
                   '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0',
                   '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    # Cross compilation roots package searches in the Apple SDK. Explicit
    # installed config paths keep product dependencies in this target's stage.
    packages = ('EXReader', 'EXReaderProductCatalog', 'EXReaderRevisions', 'EXReaderCommands',
                'EXReaderWebDAV', 'EXReaderSync', 'EXReaderSession', 'EXReaderCredentials', 'EXReaderReadingState')
    common += ['-D' + name + '_DIR=' + str(stage / 'lib/cmake' / name) for name in packages]
    modules = [('catalog', 'apps/reader/store/native'), ('revisions', 'apps/reader/revisions'),
               ('commands', 'apps/reader/commands'), ('webdav', 'extras/webdav'),
               ('sync', 'apps/reader/sync'), ('session', 'apps/reader/session'),
               ('credentials', 'extras/credentials'), ('reading-state', 'apps/reader/reading-state')]
    for name, relative in modules:
        build = args.build.absolute() / name
        for command in (['cmake', '-S', str(root / relative), '-B', str(build), *common],
                        ['cmake', '--build', str(build), '--parallel', '4'],
                        ['cmake', '--install', str(build)]):
            subprocess.run(command, check=True)
    source = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    manifest = {'source_sha': source, 'target': args.target, 'installed_modules': [x[0] for x in modules],
                'sqlite_provider': 'libreader_catalog_sqlite.a', 'system_sqlite_fallback': False,
                'reading_resolver_linked': False}
    (stage / 'share/exreader-apple').mkdir(parents=True, exist_ok=True)
    (stage / 'share/exreader-apple/product.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
