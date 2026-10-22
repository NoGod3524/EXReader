#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check a reading preset's installed SDK against the registered license manifest.

This is a materials check: every fetched, linked or installed third-party item
must be registered, and every registered license text must be installed
unchanged from its original source. It is not a legal judgment and never
reports that the project as a whole is compliant.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_reading_profile import digest

READING_PROFILES = ['reading-core', 'reading-library']
LICENSES = 'share/exreader/licenses/'
NOTICE_NAME = re.compile(r'(LICEN[CS]E|COPYING|COPYRIGHT|NOTICE|PATENTS)([._-].*)?$', re.I)
SCOPE = ('Materials check against the registered manifest: sources, pins, enable '
         'conditions, linked archives and installed license texts. Not a legal opinion.')


def upstream(path, installed, sha256=None, when=None):
    return {'origin': 'upstream', 'path': path, 'installed': installed, 'sha256': sha256, 'when': when}


def repo(path, installed, sha256=None, when=None, pinned=True):
    return {'origin': 'repository', 'path': path, 'installed': installed, 'sha256': sha256, 'when': when,
            'pinned': pinned}


# `when` uses CMake cache switches: `&` binds tighter than `|`; empty is always.
# `when` on a file overrides the component's condition for installation only.
COMPONENTS = [
    {'id': 'exreader', 'name': 'EXReader (first party)', 'version': 'repository HEAD',
     'source': 'repository', 'archive_sha256': None, 'license': 'MIT', 'when': '', 'fetch': False,
     'vendor_files': [], 'linkage': 'EXReader component archives',
     'files': [repo('LICENSE', 'LICENSE', pinned=False),
               repo('LICENSE', 'share/exreader/LICENSE', pinned=False),
               repo('THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md', pinned=False),
               repo('THIRD_PARTY_NOTICES.md', 'share/exreader/THIRD_PARTY_NOTICES.md', pinned=False)]},
    {'id': 'freetype', 'name': 'FreeType', 'version': 'VER-2-15-0',
     'source': 'https://codeload.github.com/freetype/freetype/tar.gz/refs/tags/VER-2-15-0',
     'archive_sha256': '87c7f1f8699b91e89f773f7dcfa505b044e1dae67f62a55d4e29c3afdcac4fb8',
     'license': 'FTL OR GPL-2.0-only; FTL selected in THIRD_PARTY_NOTICES.md', 'when': '',
     'fetch': True, 'vendor_files': ['freetype'], 'notice_marker': 'FreeType',
     'linkage': 'private static archive', 'files': [
         upstream('docs/FTL.TXT', LICENSES + 'freetype/FTL.TXT',
                  '5a5ee54c5001bbad1cdc1a57cc3dd4c42199b2da09d39c7ee41fab002d02967f'),
         upstream('LICENSE.TXT', LICENSES + 'freetype/LICENSE.TXT',
                  'bd36c8b474855fa294c2ec5c184544478ef3720aad37d65a6296a4f264fd2d3b')]},
    {'id': 'expat', 'name': 'Expat', 'version': 'R_2_9_0',
     'source': 'https://codeload.github.com/libexpat/libexpat/tar.gz/refs/tags/R_2_9_0',
     'archive_sha256': '6e8ce7b52ebbaa423c59becc7cf1e6875c42e49228c062ac8123c10e700cec27',
     'license': 'MIT', 'when': '', 'fetch': True, 'vendor_files': ['expat'],
     'notice_marker': 'Expat', 'linkage': 'private static archive', 'notice_dirs': ['.', 'expat'],
     'files': [upstream('expat/COPYING', LICENSES + 'expat/COPYING',
                        '31b15de82aa19a845156169a17a5488bf597e561b2c318d159ed583139b25e87')]},
    {'id': 'miniz', 'name': 'miniz', 'version': '3.1.2',
     'source': 'https://codeload.github.com/richgel999/miniz/tar.gz/refs/tags/3.1.2',
     'archive_sha256': '98468f8924934b723276680f85238b6c78bf1f8b49b4459cc9b7214a20e2e9fb',
     'license': 'MIT', 'when': '', 'fetch': True, 'vendor_files': ['miniz'],
     'notice_marker': 'miniz', 'linkage': 'private static archive',
     'files': [upstream('LICENSE', LICENSES + 'miniz/LICENSE',
                        '0115478d567121238cf6cc1c0c361926cf07a49d9e4c9e66da97fac6a01646b3')]},
    {'id': 'stb', 'name': 'stb_image', 'version': 'commit 2c980bb59875b0d32144a71867fbdebb2f77cd20',
     'source': 'https://codeload.github.com/nothings/stb/tar.gz/2c980bb59875b0d32144a71867fbdebb2f77cd20',
     'archive_sha256': '9a955b1b49a4410088a2e0ee2a9c057c3c907d0c1d75454144cb980aca0ba515',
     'license': 'MIT OR public domain; MIT selected in THIRD_PARTY_NOTICES.md', 'when': '',
     'fetch': True, 'vendor_files': [], 'notice_marker': 'stb_image',
     'linkage': 'header compiled into exr_graphics from a patched private copy',
     'build_evidence': ['exr-stb/stb_image.h'],
     'files': [upstream('LICENSE', LICENSES + 'stb/LICENSE',
                        'bebfe904b14301657e4e5d655c811d51fd31b97c455b9cc2d8600d6bac6cff63')]},
    {'id': 'libwebp', 'name': 'libwebp', 'version': 'v1.5.0',
     'source': 'https://codeload.github.com/webmproject/libwebp/tar.gz/refs/tags/v1.5.0',
     'archive_sha256': '668c9aba45565e24c27e17f7aaf7060a399f7f31dba6c97a044e1feacb930f37',
     'license': 'BSD-3-Clause', 'when': 'EXR_ENABLE_IMAGE_WEBP', 'fetch': True,
     'vendor_files': ['webp', 'webpdemux', 'sharpyuv'], 'notice_marker': 'libwebp',
     'linkage': 'private static archives',
     'files': [upstream('COPYING', LICENSES + 'libwebp/COPYING',
                        '5aec868f669e384a22372a4e8a1a6cd7d44c64cd451f960ca69cc170d1e13acf')]},
    {'id': 'zlib', 'name': 'zlib', 'version': 'v1.3.1',
     'source': 'https://codeload.github.com/madler/zlib/tar.gz/refs/tags/v1.3.1',
     'archive_sha256': '17e88863f3600672ab49182f217281b6fc4d3c762bde361935e436a95214d05c',
     'license': 'Zlib', 'when': 'EXR_ENABLE_IMAGE_TIFF', 'fetch': True,
     'vendor_files': ['zlibstatic'], 'notice_marker': 'zlib', 'linkage': 'private static archive',
     'files': [upstream('LICENSE', LICENSES + 'zlib/LICENSE',
                        '845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243'),
               upstream('LICENSE', LICENSES + 'libtiff/LICENSE',
                        '845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243')]},
    {'id': 'libtiff', 'name': 'libtiff', 'version': 'v4.7.0',
     'source': 'https://codeload.github.com/libsdl-org/libtiff/tar.gz/refs/tags/v4.7.0',
     'archive_sha256': '8f568a0dfac2e514074b04d7368c22e8afc1009af29780762a2536fd4d111e16',
     'license': 'libtiff', 'when': 'EXR_ENABLE_IMAGE_TIFF', 'fetch': True,
     'vendor_files': ['tiff'], 'notice_marker': 'libtiff', 'linkage': 'private static archive',
     'files': [upstream('LICENSE.md', LICENSES + 'libtiff/LICENSE.md',
                        '0780558a8bfba0af1160ec1ff11ade4f41c0d7deafd6ecfc796b492a788e380d')]},
    {'id': 'libaom', 'name': 'libaom', 'version': 'commit af3dc9aadc793c1b00edc003e3fc19a44fdeb574',
     'source': 'https://codeload.github.com/arthenica/libaom/tar.gz/af3dc9aadc793c1b00edc003e3fc19a44fdeb574',
     'archive_sha256': 'a606215ed62ee1aaffc1360867c637b0ccafbc1a0c1c8430e2412257b8baa62a',
     'license': 'BSD-2-Clause AND AOM Patent License 1.0', 'when': 'EXR_ENABLE_IMAGE_AVIF',
     'fetch': True, 'vendor_files': ['aom'], 'notice_marker': 'libaom',
     'linkage': 'private static archive (decoder only)', 'version_file': ['CHANGELOG', '3.15.2'],
     'files': [upstream('LICENSE', LICENSES + 'libaom/LICENSE',
                        '4764a286d8b2faeaf42f4418e7d7a28d58fc8fd4d00a3d0a7f44b0a4099de7f2'),
               upstream('PATENTS', LICENSES + 'libaom/PATENTS',
                        '661fb8e504744e95587b556b94a58343448300606a41bea8c7a9b97125696e61')]},
    {'id': 'libavif', 'name': 'libavif', 'version': 'v1.2.0',
     'source': 'https://codeload.github.com/AOMediaCodec/libavif/tar.gz/refs/tags/v1.2.0',
     'archive_sha256': '2182f4900d1a9617cee89746922a58dd825f2a3547f23907b8d78dc3685f7d8c',
     'license': 'BSD-2-Clause', 'when': 'EXR_ENABLE_IMAGE_AVIF', 'fetch': True,
     'vendor_files': ['avif'], 'notice_marker': 'libavif', 'linkage': 'private static archive',
     'files': [upstream('LICENSE', LICENSES + 'libavif/LICENSE',
                        '165abf92cc04b39e80d29cadea7a6a7e8fddf59407d4ad2616507a7ebe8216f9')]},
    {'id': 'mbedtls', 'name': 'Mbed TLS crypto subset', 'version': 'mbedtls-3.6.7',
     'source': 'https://codeload.github.com/Mbed-TLS/mbedtls/tar.gz/refs/tags/mbedtls-3.6.7',
     'archive_sha256': '807f0a1cc7c63b571180e9efeb6236b677e550869eb0442ace33aa9c69055fcc',
     'license': 'Apache-2.0 OR GPL-2.0-or-later; Apache-2.0 selected in THIRD_PARTY_NOTICES.md',
     'when': 'EXR_ENABLE_PDF&EXR_ENABLE_PDF_CRYPTO', 'fetch': True, 'vendor_files': ['exr_crypto'],
     'notice_marker': 'Mbed TLS', 'linkage': 'seven upstream sources in exr_crypto; ARC4 adapted from '
     'mbedtls-2.28.10 into src/pdf_crypto.c',
     'files': [upstream('LICENSE', LICENSES + 'mbedtls/LICENSE',
                        '9b405ef4c89342f5eae1dd828882f931747f71001cfba7d114801039b52ad09b')]},
    {'id': 'lcms', 'name': 'LittleCMS', 'version': 'lcms2.19.1',
     'source': 'https://codeload.github.com/mm2/Little-CMS/tar.gz/refs/tags/lcms2.19.1',
     'archive_sha256': '267705e278e2f7c2fb886c259dadcbaeb2be52748bcbc71c79f08aacacb7a709',
     'license': 'MIT', 'when': 'EXR_ENABLE_ICC', 'fetch': True, 'vendor_files': ['exr_lcms'],
     'notice_marker': 'LittleCMS', 'linkage': 'upstream src/cms*.c in exr_lcms',
     'files': [upstream('LICENSE', LICENSES + 'lcms/LICENSE',
                        '6dbd60437f8ef91d8de1f08ad75882547fd4931bfcc3566a0735f28db1484d31')]},
    {'id': 'sqlite', 'name': 'SQLite amalgamation', 'version': '3.54.0',
     'source': 'https://www.sqlite.org/2026/sqlite-amalgamation-3540000.zip',
     'archive_sha256': '68e913b0fe8ec6b4e5f391c594a28872884e80d6cd042a1e50c957be46b5aa4d',
     'license': 'Public domain', 'when': 'EXR_ENABLE_LIBRARY|EXR_BUILD_TEXT_INDEX', 'fetch': True,
     'vendor_files': ['exr_sqlite'], 'notice_marker': 'SQLite', 'linkage': 'private static archive',
     'evidence': [['sqlite3.c', 'The author disclaims copyright to this source code']],
     'pending': ['upstream ships no license file; the public-domain dedication is only in the '
                 'sqlite3.c header and a THIRD_PARTY_NOTICES.md row, nothing under ' + LICENSES],
     'files': []},
    {'id': 'minimp3', 'name': 'minimp3', 'version': 'commit ea99364f61c14656440e8d77e9c233ccf3124633',
     'source': 'https://codeload.github.com/lieff/minimp3/tar.gz/ea99364f61c14656440e8d77e9c233ccf3124633',
     'archive_sha256': '5628166eb82a9bb581317918a334c317a2c0a30278bb14a20381307976768f34',
     'license': 'CC0-1.0', 'when': 'EXR_ENABLE_AUDIO&EXR_ENABLE_MP3', 'fetch': True,
     'vendor_files': [], 'notice_marker': 'minimp3', 'linkage': 'header compiled into exr_audio',
     'files': [upstream('LICENSE', LICENSES + 'minimp3/LICENSE')]},
    {'id': 'faad2', 'name': 'FAAD2', 'version': 'commit 521d105979795b887ea11e1f36565e97a8fbfc53',
     'source': 'https://codeload.github.com/knik0/faad2/tar.gz/521d105979795b887ea11e1f36565e97a8fbfc53',
     'archive_sha256': '9284bd9c5ef998f636b233055f4d988aadf0d5a97acdb3109bcb9d4e3c7cfdd8',
     'license': 'GPL-2.0-or-later', 'when': 'EXR_ENABLE_AUDIO&EXR_ENABLE_AAC', 'fetch': True,
     'vendor_files': ['faad'], 'notice_marker': 'FAAD2', 'linkage': 'private static archive',
     'files': [upstream('COPYING', LICENSES + 'faad2/COPYING'),
               repo('licenses/faad2-notice.txt', LICENSES + 'faad2/faad2-notice.txt')]},
    {'id': 'unicode', 'name': 'Unicode Character Database derived tables', 'version': '17.0.0 and 3.2',
     'source': 'https://www.unicode.org/Public/ (pinned by tools/generate_*.py)', 'archive_sha256': None,
     'license': 'Unicode-3.0', 'when': '', 'fetch': False, 'vendor_files': [],
     'notice_marker': 'Unicode-3.0', 'linkage': 'generated C tables in core and PDF sources',
     'files': [repo('tests/fixtures/unicode/LICENSE.txt', LICENSES + 'unicode/LICENSE.txt',
                    'e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96')]},
    {'id': 'argyll-cmyk', 'name': 'Argyll fallback CMYK profile', 'version': 'repository data',
     'source': 'src/profiles/default_cmyk.icc.zlib', 'archive_sha256': None,
     'license': 'Public domain', 'when': 'EXR_ENABLE_ICC', 'fetch': False, 'vendor_files': [],
     'notice_marker': 'Argyll', 'linkage': 'embedded generated header in exr_graphics',
     'pinned_data': [['src/profiles/default_cmyk.icc.zlib',
                      '20f63c910decd30bf87d7ce2461f133d0305f552279ccdc388cdcfc8762753b2']],
     'files': [repo('licenses/default-cmyk-profile.txt', LICENSES + 'default-cmyk-profile.txt',
                    '45d3e9b11893bcae1724cd0e6d377c2ed842269de495307ba6153e1b0b80e1da')]},
    {'id': 'adobe-glyph-list', 'name': 'Adobe Glyph List and ITC Zapf Dingbats Glyph List',
     'version': 'agl-aglfn commit 4036a9ca80a62f64f9de4f7321a9a045ad0ecfd6',
     'source': 'https://github.com/adobe-type-tools/agl-aglfn/tree/4036a9ca80a62f64f9de4f7321a9a045ad0ecfd6',
     'archive_sha256': None, 'license': 'BSD-3-Clause', 'when': 'EXR_ENABLE_PDF', 'fetch': False,
     'vendor_files': [], 'notice_marker': 'adobe-glyph-list.txt',
     'linkage': 'facts in src/pdf_font_data.h', 'files': [
         repo('licenses/adobe-glyph-list.txt', LICENSES + 'pdf-font-data/adobe-glyph-list.txt',
              'c85f2b0da9de3e0a96cb42594708d19f7696945bb185cfd98c262f8f2d6f3aa7', when='')]},
    {'id': 'pdfjs-data', 'name': 'PDF.js encoding and metric facts',
     'version': 'pdf.js commit 81525fd446779f0a29003cf06e3ba33751954826',
     'source': 'https://github.com/mozilla/pdf.js/tree/81525fd446779f0a29003cf06e3ba33751954826/src/core',
     'archive_sha256': None, 'license': 'Apache-2.0', 'when': 'EXR_ENABLE_PDF', 'fetch': False,
     'vendor_files': [], 'notice_marker': 'licenses/pdfjs.txt',
     'linkage': 'facts in src/pdf_font_data.h', 'files': [
         repo('licenses/pdfjs.txt', LICENSES + 'pdf-font-data/pdfjs.txt',
              '8d1fb64269e430755e4f12c2eb113d71b4b2a33ad11db0069e09ebb47415ca53', when='')]},
    {'id': 'pdf-calculator-names', 'name': 'PostScript calculator operator names',
     'version': 'PDF 32000-1 table 42', 'source': 'THIRD_PARTY_NOTICES.md', 'archive_sha256': None,
     'license': 'Adobe permission notice', 'when': 'EXR_ENABLE_PDF', 'fetch': False,
     'vendor_files': [], 'notice_marker': 'PDF calculator command names',
     'linkage': 'operator names in src/pdf_calculator.c', 'files': []},
    {'id': 'noto-test-fonts', 'name': 'Noto Sans script test fonts (notice only)',
     'version': 'tests/fixtures/wp7', 'source': 'licenses/noto-sans-test-fonts.txt', 'archive_sha256': None,
     'license': 'OFL-1.1', 'when': '', 'fetch': False, 'vendor_files': [],
     'notice_marker': 'noto-sans-test-fonts.txt', 'linkage': 'none; fonts are not installed',
     'absent_pattern': r'Noto.*\.(?:ttf|otf|ttc)$',
     'files': [repo('licenses/noto-sans-test-fonts.txt', LICENSES + 'wp7-fonts/noto-sans-test-fonts.txt',
                    '754f0e221aa7d5a915489f3bf1f20fe53ddc35ab2834a4d91656d78f9622de70')]},
]


def switch(value):
    if isinstance(value, dict):
        value = value.get('value')
    return 'ON' if str(value).upper() in ('ON', 'TRUE', '1', 'YES', 'Y') else 'OFF'


def enabled(expression, switches):
    return not expression or any(all(switches.get(name) == 'ON' for name in term.split('&'))
                                 for term in expression.split('|'))


def preset_cache(root, profile):
    presets = {preset['name']: preset for preset in
               json.loads((root / 'CMakePresets.json').read_text(encoding='utf-8'))['configurePresets']}

    def resolve(name):
        preset = presets[name]
        parents = preset.get('inherits', [])
        values = {}
        # Earlier parents take precedence, as in CMake presets.
        for parent in reversed([parents] if isinstance(parents, str) else parents):
            values.update(resolve(parent))
        values.update(preset.get('cacheVariables', {}))
        return values
    return resolve(profile)


def preset_switches(root, profile):
    return {key: switch(value) for key, value in preset_cache(root, profile).items()
            if key.startswith('EXR_')}


def read_cache(path):
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if line and not line.startswith(('#', '//')) and '=' in line and ':' in line.split('=', 1)[0]:
            key, value = line.split('=', 1)
            values[key.split(':', 1)[0]] = value
    return values


def inside(base, relative):
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or '..' in path.parts or ':' in relative:
        return None
    return base.joinpath(*path.parts)


def manifest_problems(root, components=COMPONENTS):
    problems = []
    deps = (root / 'cmake/deps.cmake').read_text(encoding='utf-8')
    installs = (root / 'CMakeLists.txt').read_text(encoding='utf-8')
    ids = [component['id'] for component in components]
    problems += [f'duplicate manifest id: {name}' for name in sorted({i for i in ids if ids.count(i) > 1})]
    declared = {name.lower() for name in re.findall(r'FetchContent_Declare\((\w+)', deps)}
    fetched = {component['id'] for component in components if component['fetch']}
    problems += [f'FetchContent declaration not registered: {name}' for name in sorted(declared - fetched)]
    problems += [f'registered dependency not declared in cmake/deps.cmake: {name}'
                 for name in sorted(fetched - declared)]
    profiles = [preset_switches(root, profile) for profile in READING_PROFILES]
    for component in components:
        name = component['id']
        if component['fetch']:
            for value in (component['source'], component['archive_sha256']):
                if not value or value not in deps:
                    problems.append(f'{name}: {value} not pinned in cmake/deps.cmake')
        for item in component['files']:
            when = component['when'] if item['when'] is None else item['when']
            if inside(Path('.'), item['path']) is None or inside(Path('.'), item['installed']) is None:
                problems.append(f'{name}: invalid manifest path {item["path"]} -> {item["installed"]}')
                continue
            source, installed = PurePosixPath(item['path']), PurePosixPath(item['installed'])
            rule = f'${{{name}_SOURCE_DIR}}/{item["path"]}' if item['origin'] == 'upstream' else item['path']
            if rule not in installs or f'DESTINATION {installed.parent.as_posix()}' not in installs:
                problems.append(f'{name}: no install rule from {rule} to {installed.parent.as_posix()}')
            if source.name != installed.name:
                problems.append(f'{name}: installed name {installed.name} differs from {source.name}')
            if item['sha256'] is None and item.get('pinned', True) and \
                    any(enabled(when, switches) for switches in profiles):
                problems.append(f'{name}: {item["installed"]} hash not pinned in manifest')
    return problems


def check(profile, root, build, stage, components=COMPONENTS):
    failures = list(manifest_problems(root, components))
    pending = []
    cache = read_cache(build / 'CMakeCache.txt')
    switches = {key: switch(value) for key, value in cache.items() if key.startswith('EXR_')}
    expected = preset_switches(root, profile)
    failures += [f'cache {key}: preset {value}, observed {switches.get(key)}'
                 for key, value in sorted(expected.items()) if switches.get(key) != value]
    audio = {key: switches.get(key) for key in ('EXR_ENABLE_AUDIO', 'EXR_ENABLE_MP3', 'EXR_ENABLE_AAC')}
    if any(value != 'OFF' for value in audio.values()):
        failures.append(f'audio codecs are not disabled: {audio}')
    modules = build / 'exr-modules.json'
    layers = json.loads(modules.read_text(encoding='utf-8'))['layers'] if modules.is_file() else None
    if layers is None:
        failures.append('exr-modules.json missing from build directory')
    else:
        if 'audio' in layers:
            failures.append('audio layer is built')
        if ('library' in layers) != (switches.get('EXR_ENABLE_LIBRARY') == 'ON'):
            failures.append('library layer does not match EXR_ENABLE_LIBRARY')

    deps = build / '_deps'
    fetched = sorted(path.name[:-4] for path in deps.glob('*-src') if path.is_dir()) if deps.is_dir() else []
    registered = {component['id'] for component in components if component['fetch']}
    failures += [f'unregistered fetched dependency: {name}' for name in fetched if name not in registered]

    config = stage / 'lib/cmake/EXReader/EXReaderDependencies.cmake'
    configured = set()
    if config.is_file():
        configured = set(re.findall(r'add_library\(EXReader::vendor_file_(\w+) STATIC IMPORTED\)',
                                    config.read_text(encoding='utf-8')))
    else:
        failures.append('installed EXReaderDependencies.cmake missing')
    archives = {}
    vendor = stage / 'lib/exreader'
    for path in sorted(vendor.iterdir()) if vendor.is_dir() else []:
        match = re.fullmatch(r'(?:lib)?exr_vendor_(.+)\.(?:a|lib)', path.name)
        if match:
            archives[match.group(1)] = path
        else:
            failures.append(f'unrecognized file in lib/exreader: {path.name}')
    if set(archives) != configured:
        failures.append(f'vendor archives {sorted(archives)} differ from package configuration '
                        f'{sorted(configured)}')
    owners = {name for component in components for name in component['vendor_files']}
    failures += [f'unregistered linked vendor archive: {name}'
                 for name in sorted(set(archives) | configured) if name not in owners]

    notices_path = root / 'THIRD_PARTY_NOTICES.md'
    notices = notices_path.read_text(encoding='utf-8') if notices_path.is_file() else ''
    registered_files = set()
    rows = []
    for component in components:
        name = component['id']
        active = enabled(component['when'], switches)
        source_dir = deps / f'{name}-src' if component['fetch'] else root
        row = {key: component.get(key) for key in
               ['id', 'name', 'version', 'source', 'archive_sha256', 'license', 'when', 'linkage']}
        row.update({'active': active, 'fetched': name in fetched,
                    'linked_archives': sorted(f for f in component['vendor_files'] if f in archives),
                    'files': [], 'upstream_notice_files': []})
        rows.append(row)
        if component['fetch'] and active != (name in fetched):
            failures.append(f'{name}: ' + ('enabled dependency was not fetched' if active
                                           else 'disabled dependency was fetched'))
        for file in component['vendor_files']:
            if (file in archives) != active:
                failures.append(f'{name}: vendor archive {file} ' +
                                ('missing' if active else 'installed although disabled'))
        if active:
            marker = component.get('notice_marker')
            if marker and marker not in notices:
                failures.append(f'{name}: not described in THIRD_PARTY_NOTICES.md ({marker})')
            for path, needle in component.get('evidence', []):
                original = source_dir / path
                if not original.is_file() or needle not in original.read_text(encoding='utf-8', errors='replace'):
                    failures.append(f'{name}: license statement missing from {path}')
            for path in component.get('build_evidence', []):
                if not (build / path).is_file():
                    failures.append(f'{name}: build input {path} missing')
            for path, sha256 in component.get('pinned_data', []):
                if not (root / path).is_file() or digest(root / path) != sha256:
                    failures.append(f'{name}: pinned data {path} missing or altered')
            pending += [f'{name}: {note}' for note in component.get('pending', [])]
            if component.get('version_file') and name in fetched:
                path, claimed = component['version_file']
                lines = (source_dir / path).read_text(encoding='utf-8', errors='replace').splitlines() \
                    if (source_dir / path).is_file() else []
                found = re.search(r'v?(\d+\.\d+\.\d+)', next((line for line in lines if line.strip()), ''))
                row['observed_version'] = found.group(1) if found else None
                if not found:
                    pending.append(f'{name}: cannot confirm declared version {claimed} from {path}')
                elif found.group(1) != claimed:
                    failures.append(f'{name}: declared version {claimed}, upstream {path} reports {found.group(1)}')
            if name in fetched:
                listed = {PurePosixPath(item['path']) for item in component['files'] if item['origin'] == 'upstream'}
                for directory in component.get('notice_dirs', ['.']):
                    base = source_dir / directory
                    for path in sorted(base.iterdir()) if base.is_dir() else []:
                        if path.is_file() and NOTICE_NAME.match(path.name):
                            relative = PurePosixPath(path.relative_to(source_dir).as_posix())
                            row['upstream_notice_files'].append({'path': str(relative), 'sha256': digest(path)})
                            if relative not in listed:
                                pending.append(f'{name}: upstream notice file {relative} is not installed')
        if component.get('absent_pattern'):
            for path in stage.rglob('*'):
                if re.search(component['absent_pattern'], path.name):
                    failures.append(f'{name}: {path.relative_to(stage).as_posix()} must not be installed')
        for item in component['files']:
            installs = enabled(component['when'] if item['when'] is None else item['when'], switches)
            installed, original = inside(stage, item['installed']), inside(source_dir, item['path'])
            if installed is None or original is None:
                failures.append(f'{name}: invalid manifest path {item["path"]} -> {item["installed"]}')
                continue
            registered_files.add(item['installed'])
            source = item['path'] if item['origin'] == 'repository' else f'_deps/{name}-src/{item["path"]}'
            entry = {'origin': item['origin'], 'source': source, 'installed': item['installed'],
                     'expected': installs, 'pinned_sha256': item['sha256'], 'present': installed.is_file()}
            row['files'].append(entry)
            if not installs:
                if installed.exists():
                    failures.append(f'{name}: {item["installed"]} installed although disabled')
                continue
            if not installed.is_file():
                failures.append(f'{name}: missing installed license {item["installed"]}')
                continue
            entry['bytes'] = installed.stat().st_size
            if not entry['bytes']:
                failures.append(f'{name}: empty installed license {item["installed"]}')
                continue
            entry['sha256'] = digest(installed)
            if not original.is_file():
                failures.append(f'{name}: original license source missing {source}')
            elif digest(original) != entry['sha256']:
                failures.append(f'{name}: {item["installed"]} differs from original {source}')
            if item['sha256'] is None and item.get('pinned', True):
                failures.append(f'{name}: {item["installed"]} hash not pinned (observed {entry["sha256"]})')
            elif item['sha256'] is not None and item['sha256'] != entry['sha256']:
                failures.append(f'{name}: {item["installed"]} pinned hash mismatch '
                                f'(pinned {item["sha256"]}, observed {entry["sha256"]})')
    licenses = stage / LICENSES
    for path in sorted(licenses.rglob('*')) if licenses.is_dir() else []:
        relative = path.relative_to(stage).as_posix()
        if path.is_file() and relative not in registered_files:
            failures.append(f'unregistered installed license material: {relative}')
    return {'schema': 1, 'profile': profile, 'scope': SCOPE, 'legal_judgment': 'not performed',
            'materials_check_passed': not failures, 'failures': failures, 'pending': pending,
            'audio_switches': audio, 'layers': layers, 'cache_switches': switches,
            'fetched_dependencies': fetched, 'linked_vendor_archives': sorted(archives),
            'components': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=READING_PROFILES)
    parser.add_argument('build', type=Path)
    parser.add_argument('stage', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = check(args.profile, root, args.build, args.stage)
    report['source_sha'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, indent=2))
    return 0 if report['materials_check_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
