# SPDX-License-Identifier: MIT
"""Compile the native Apple host with its installed product dependencies."""
import argparse
from pathlib import Path
import subprocess
from check_apple_product import inspect
import json
import os
import re


LIBRARIES = ('reader_desktop_metadata', 'reader_reading_commands', 'reader_annotation_view', 'reader_navigation', 'reader_search', 'reader_session', 'reader_sync', 'exr_webdav', 'reader_commands',
             'reader_reading_state_codec', 'reader_revisions', 'reader_revision_hash',
             'reader_catalog', 'reader_catalog_sqlite', 'exr_credentials')

WAVE3_MODULES = (
    ('annotation-export', 'reader_annotation_export', ()),
    ('annotation-import', 'reader_annotation_import', ('-DREADER_ANNOTATION_IMPORT_BUILD=ON',)),
    ('font-library', 'reader_font_library', ('-DREADER_FONT_LIBRARY_BUILD=ON',)),
    ('original-export', 'reader_original_export', ()),
    ('jump-history', 'reader_jump_history', ()),
    ('sync-status-view', 'reader_sync_view', ()),
)


def flags(sdk, product_prefix=None, selector_bytes_candidate=False, wave3=False):
    sdk = Path(sdk).absolute()
    product = Path(product_prefix).absolute() if product_prefix else sdk
    if wave3 and not selector_bytes_candidate:
        raise RuntimeError('Wave3 requires the explicit raw selector product family')
    if selector_bytes_candidate:
        if product.resolve() == sdk.resolve():
            raise RuntimeError('Raw selector products must use an independent prefix')
        manifest = json.loads((product / 'share/exreader-apple/product.json').read_text())
        expected = {'EXReaderRevisions': '0.4.0', 'EXReaderReadingState': '0.2.0',
                    'EXReaderReadingCommands': '0.2.0', 'EXReaderAnnotationView': '0.2.0',
                    'EXReaderCommands': '0.2.0', 'EXReaderSync': '0.2.0', 'EXReaderSession': '0.2.0'}
        if manifest.get('selector_bytes_candidate') is not True or manifest.get('exact_candidate_family') != expected:
            raise RuntimeError('Actual installed raw package family differs')
        if wave3 and manifest.get('wave3_enabled') is not True:
            raise RuntimeError('Installed products do not declare the wave3 profile')
        version = re.search(r'#define EXR_VERSION "([^"]+)"', (sdk / 'include/exr/base.h').read_text())
        if version is None or version[1] not in ('3.41.0', '3.42.0') or manifest.get('sdk_version') != version[1] or Path(manifest['sdk_prefix']).resolve() != sdk.resolve():
            raise RuntimeError('Raw products are bound to another actual SDK')
        for name, version in expected.items():
            text = (product / 'lib/cmake' / name / (name + 'ConfigVersion.cmake')).read_text()
            if re.search(r'set\(PACKAGE_VERSION\s+"' + re.escape(version) + r'"\)', text) is None:
                raise RuntimeError('Actual installed package version differs: ' + name)
    module = Path(__file__).absolute().parents[1] / 'examples/apple/product'
    includes = (sdk / 'include', product / 'include/exreader-product', module)
    if product != sdk:
        includes = (product / 'include', sdk / 'include', product / 'include/exreader-product', module)
    libraries = tuple(target for _, target, _ in WAVE3_MODULES) + LIBRARIES if wave3 else LIBRARIES
    archives = [product / 'lib' / ('lib' + name + '.a') for name in libraries]
    if wave3:
        bridge = Path(__file__).absolute().parents[1] / 'apps/reader/apple-feature-integration/include'
        includes = (*includes, bridge)
        for _, target, _ in WAVE3_MODULES:
            if not (product / 'include' / (target + '.h')).is_file():
                raise RuntimeError('Missing installed wave3 header: ' + target)
        for header in ('reader_annotation_import_raw3.h', 'reader_annotation_export_raw3.h'):
            if not (product / 'include' / header).is_file():
                raise RuntimeError('Missing installed raw wave3 header: ' + header)
        if not (bridge / 'reader_apple_features.h').is_file():
            raise RuntimeError('Missing Apple wave3 product bridge')
    for path in [*includes, *archives]:
        if not path.exists():
            raise RuntimeError('Missing installed Apple product dependency: ' + str(path))
    result = [item for path in includes for item in ('-I', str(path))]
    result += [str(path) for path in archives]
    result += ['-lc++', '-lxml2', '-framework', 'Foundation', '-framework', 'CoreFoundation',
               '-framework', 'Security']
    if selector_bytes_candidate:
        result += ['-Xcc', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=1', '-Xcc', '-DEXR_READER_METADATA_RAW3=1', '-D', 'EXR_APPLE_RAW3']
    if wave3:
        result += ['-Xcc', '-DEXR_APPLE_WAVE3=1', '-D', 'EXR_APPLE_WAVE3']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--product-prefix', type=Path)
    parser.add_argument('--selector-bytes-candidate', action='store_true',
                        default=os.environ.get('EXR_APPLE_RAW3', 'OFF') == 'ON')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.environ.get('EXR_APPLE_RAW3', 'OFF') not in ('OFF', 'ON'):
        parser.error('EXR_APPLE_RAW3 must be explicitly OFF or ON')
    arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    if any(Path(value).name == 'HostModel.swift' for value in arguments):
        for filename in ('HostAccount.swift', 'HostSearch.swift', 'HostNavigation.swift', 'HostReadingRecords.swift', 'HostOrganization.swift'):
            source = Path(__file__).absolute().parents[1] / 'examples/apple' / filename
            if not any(Path(value).name == source.name for value in arguments):
                arguments.append(str(source))
    output = Path(arguments[arguments.index('-o') + 1])
    mapping = Path(str(output) + '.link.map')
    raw_include = ['-I', str(args.product_prefix.absolute() / 'include')] if args.selector_bytes_candidate and args.product_prefix else []
    subprocess.run(['xcrun', 'swiftc', *raw_include, *arguments, *flags(args.sdk, args.product_prefix, args.selector_bytes_candidate), '-Xlinker', '-map',
                    '-Xlinker', str(mapping)], check=True)
    Path(str(output) + '.product.json').write_text(json.dumps(inspect(output, mapping, args.selector_bytes_candidate), indent=2) + '\n')


if __name__ == '__main__':
    main()
