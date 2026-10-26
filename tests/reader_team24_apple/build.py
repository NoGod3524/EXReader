#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Team24 Apple Actions-only installation, retaining frozen SDK and separate raw products."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
MODULES = ('annotation-export', 'annotation-import', 'font-library', 'original-export', 'jump-history', 'sync-status-view')
TARGETS = {
    'annotation-export': 'reader_annotation_export',
    'annotation-import': 'reader_annotation_import',
    'font-library': 'reader_font_library',
    'original-export': 'reader_original_export',
    'jump-history': 'reader_jump_history',
    'sync-status-view': 'reader_sync_view',
}
ENABLE = {
    'annotation-import': ['-DREADER_ANNOTATION_IMPORT_BUILD=ON'],
    'font-library': ['-DREADER_FONT_LIBRARY_BUILD=ON'],
}
PACKAGES = ('EXReaderProductCatalog', 'EXReaderRevisions', 'EXReaderReadingState', 'EXReaderAnnotationView',
            'EXReaderCommands', 'EXReaderSync', 'EXReaderSession', 'EXReaderWebDAV', 'EXReaderAnnotationExport')
def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'Actions macOS only'
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=('macos', 'iphonesimulator'), required=True)
    args = parser.parse_args()
    run(sys.executable, 'tests/apple_host/raw3/ios/reading/build_sdk.py', '--target', args.target)
    out = ROOT / 'build/raw3-ios-sdk' / args.target
    sdk, stage = out / 'sdk', out / 'raw-products'
    native = 'macosx' if args.target == 'macos' else args.target
    sysroot = subprocess.check_output(['xcrun', '--sdk', native, '--show-sdk-path'], text=True).strip()
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + str(stage),
        '-DCMAKE_PREFIX_PATH=' + str(stage) + ';' + str(sdk), '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0',
        '-DEXReader_DIR=' + str(sdk / 'lib/cmake/EXReader'), '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON',
        '-DLIBXML2_INCLUDE_DIR=' + sysroot + '/usr/include/libxml2', '-DLIBXML2_LIBRARY=' + sysroot + '/usr/lib/libxml2.tbd']
    options += ['-D' + name + '_DIR=' + str(stage / 'lib/cmake' / name) for name in PACKAGES]
    if args.target != 'macos':
        options += ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator', '-DCMAKE_OSX_ARCHITECTURES=arm64',
            '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0', '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    for module in MODULES:
        build = out / ('wave3-' + module)
        run('cmake', '-S', ROOT / 'apps/reader' / module, '-B', build, *options, *ENABLE.get(module, []))
        run('cmake', '--build', build, '--target', TARGETS[module], '--parallel', '4')
        run('cmake', '--install', build)
    required = [stage / 'lib' / ('lib' + target + '.a') for target in TARGETS.values()]
    required += [stage / 'include' / (target + '.h') for target in TARGETS.values()]
    required += [stage / 'include' / name for name in
                 ('reader_annotation_import_raw3.h', 'reader_annotation_export_raw3.h')]
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError('Required installed Apple module output missing: ' + ', '.join(missing))
    (out / 'wave3-packages.json').write_text(json.dumps({'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'target': args.target,
        'modules': MODULES, 'sdk_frozen_source': 'edddc463c06ed5731195cdb8f06b2df6dff7699e'}, indent=2) + '\n')
if __name__ == '__main__': main()
