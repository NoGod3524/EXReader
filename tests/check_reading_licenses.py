#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reject missing, empty, misplaced, altered or unregistered license materials."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_reading_licenses as licenses

LICENSES = licenses.LICENSES
ALPHA = b'alpha license\n'
NOTICE = b'repository notice\n'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def components():
    return [
        {'id': 'alpha', 'name': 'Alpha', 'version': '1.0', 'source': 'https://example.invalid/alpha.tar.gz',
         'archive_sha256': 'a' * 64, 'license': 'MIT', 'when': '', 'fetch': True,
         'vendor_files': ['alpha'], 'notice_marker': 'Alpha',
         'files': [licenses.upstream('LICENSE', LICENSES + 'alpha/LICENSE', sha256(ALPHA))]},
        {'id': 'beta', 'name': 'Beta AAC', 'version': '1.0', 'source': 'https://example.invalid/beta.tar.gz',
         'archive_sha256': 'b' * 64, 'license': 'GPL-2.0-or-later', 'when': 'EXR_ENABLE_AUDIO&EXR_ENABLE_AAC',
         'fetch': True, 'vendor_files': ['beta'], 'notice_marker': 'Beta',
         'files': [licenses.upstream('COPYING', LICENSES + 'beta/COPYING')]},
        {'id': 'notice', 'name': 'Notice', 'version': 'data', 'source': 'repository', 'archive_sha256': None,
         'license': 'BSD-3-Clause', 'when': '', 'fetch': False, 'vendor_files': [],
         'files': [licenses.repo('licenses/notice.txt', LICENSES + 'notice.txt', sha256(NOTICE))]},
    ]


def tree(directory, profile):
    root, build, stage = directory / 'root', directory / 'build', directory / 'stage'
    (root / 'cmake').mkdir(parents=True)
    (root / 'licenses').mkdir()
    (root / 'CMakePresets.json').write_bytes((ROOT / 'CMakePresets.json').read_bytes())
    (root / 'cmake/deps.cmake').write_text(
        'FetchContent_Declare(alpha URL "https://example.invalid/alpha.tar.gz" URL_HASH SHA256=' + 'a' * 64 + ')\n'
        'FetchContent_Declare(beta URL "https://example.invalid/beta.tar.gz" URL_HASH SHA256=' + 'b' * 64 + ')\n')
    (root / 'CMakeLists.txt').write_text(
        'install(FILES ${alpha_SOURCE_DIR}/LICENSE DESTINATION share/exreader/licenses/alpha)\n'
        'install(FILES ${beta_SOURCE_DIR}/COPYING DESTINATION share/exreader/licenses/beta)\n'
        'install(FILES licenses/notice.txt DESTINATION share/exreader/licenses)\n')
    (root / 'THIRD_PARTY_NOTICES.md').write_text('Alpha\nBeta\n')
    (root / 'licenses/notice.txt').write_bytes(NOTICE)
    build.mkdir()
    switches = licenses.preset_switches(ROOT, profile)
    (build / 'CMakeCache.txt').write_text(''.join(f'{key}:BOOL={value}\n' for key, value in switches.items()))
    layers = ['base', 'pdf'] + (['library'] if profile == 'reading-library' else [])
    (build / 'exr-modules.json').write_text(json.dumps({'layers': layers, 'files': {}}))
    (build / '_deps/alpha-src').mkdir(parents=True)
    (build / '_deps/alpha-src/LICENSE').write_bytes(ALPHA)
    (stage / 'lib/cmake/EXReader').mkdir(parents=True)
    (stage / 'lib/cmake/EXReader/EXReaderDependencies.cmake').write_text(
        'add_library(EXReader::vendor_file_alpha STATIC IMPORTED)\n')
    (stage / 'lib/exreader').mkdir()
    (stage / 'lib/exreader/libexr_vendor_alpha.a').write_bytes(b'archive')
    (stage / LICENSES / 'alpha').mkdir(parents=True)
    (stage / LICENSES / 'alpha/LICENSE').write_bytes(ALPHA)
    (stage / LICENSES / 'notice.txt').write_bytes(NOTICE)
    return root, build, stage


def run(mutate=None, profile='reading-core'):
    with tempfile.TemporaryDirectory() as name:
        root, build, stage = tree(Path(name), profile)
        manifest = components()
        if mutate:
            mutate(root, build, stage, manifest)
        return licenses.check(profile, root, build, stage, manifest)


def add_vendor(stage, name):
    (stage / f'lib/exreader/libexr_vendor_{name}.a').write_bytes(b'archive')
    with (stage / 'lib/cmake/EXReader/EXReaderDependencies.cmake').open('a') as stream:
        stream.write(f'add_library(EXReader::vendor_file_{name} STATIC IMPORTED)\n')


def replace(path, old, new):
    path.write_text(path.read_text().replace(old, new))


def setitem(item, key, value):
    item[key] = value


def add_notice(root, build, stage, manifest, source, installed):
    data = b'additional upstream material\n'
    (build / '_deps/alpha-src' / source).write_bytes(data)
    destination = stage / LICENSES / installed
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    manifest[0]['files'].append(licenses.upstream(source, LICENSES + installed, sha256(data)))
    with (root / 'CMakeLists.txt').open('a') as stream:
        stream.write(f'install(FILES ${{alpha_SOURCE_DIR}}/{source} DESTINATION '
                     f'{LICENSES}{Path(installed).parent.as_posix()})\n')


def update_statement(root, stage, manifest, data):
    (root / 'licenses/notice.txt').write_bytes(data)
    (stage / LICENSES / 'notice.txt').write_bytes(data)
    manifest[2]['files'][0]['sha256'] = sha256(data)


def source_statement(root, build, stage, manifest):
    component = manifest[0]
    component['source_statement'] = ['LICENSE', 'licenses/notice.txt', ALPHA.decode()]
    component['version_header'] = ['alpha.h', 'ALPHA_VERSION']
    (build / '_deps/alpha-src/alpha.h').write_text('#define ALPHA_VERSION "1.0"\n')
    data = ('Version: ' + component['version'] + '\nSource: ' + component['source'] + '\nSHA-256: ' +
            component['archive_sha256'] + '\n').encode() + ALPHA
    update_statement(root, stage, manifest, data)


def repository_material(root, build, stage, manifest):
    manifest[0]['files'].append(licenses.repo('licenses/notice.txt', LICENSES + 'alpha/notice.txt', sha256(NOTICE)))
    (stage / LICENSES / 'alpha/notice.txt').write_bytes(NOTICE)
    with (root / 'CMakeLists.txt').open('a') as stream:
        stream.write('install(FILES licenses/notice.txt DESTINATION share/exreader/licenses/alpha)\n')


CASES = [
    ('missing license file', 'missing installed license',
     lambda r, b, s, m: (s / LICENSES / 'alpha/LICENSE').unlink()),
    ('empty license file', 'empty installed license',
     lambda r, b, s, m: (s / LICENSES / 'alpha/LICENSE').write_bytes(b'')),
    ('license installed at wrong path', 'missing installed license',
     lambda r, b, s, m: (s / LICENSES / 'alpha/LICENSE').rename(s / LICENSES / 'alpha/COPYING')),
    ('license installed at wrong path is unregistered', 'unregistered installed license material',
     lambda r, b, s, m: (s / LICENSES / 'alpha/LICENSE').rename(s / LICENSES / 'alpha/COPYING')),
    ('manifest path escapes stage', 'invalid manifest path',
     lambda r, b, s, m: setitem(m[0]['files'][0], 'installed', '../LICENSE')),
    ('manifest names wrong upstream file', 'original license source missing',
     lambda r, b, s, m: setitem(m[0]['files'][0], 'path', 'LICENCE')),
    ('installed text altered', 'differs from original',
     lambda r, b, s, m: (s / LICENSES / 'alpha/LICENSE').write_bytes(b'alpha license, edited\n')),
    ('unpinned license hash', 'hash not pinned',
     lambda r, b, s, m: setitem(m[0]['files'][0], 'sha256', None)),
    ('pinned hash differs', 'pinned hash mismatch',
     lambda r, b, s, m: setitem(m[0]['files'][0], 'sha256', '0' * 64)),
    ('unregistered license file', 'unregistered installed license material',
     lambda r, b, s, m: (s / LICENSES / 'extra.txt').write_bytes(b'extra\n')),
    ('manifest misses a component', 'unregistered installed license material',
     lambda r, b, s, m: m.pop(2)),
    ('manifest misses a fetched dependency', 'unregistered fetched dependency',
     lambda r, b, s, m: (b / '_deps/gamma-src').mkdir()),
    ('manifest misses a linked archive', 'unregistered linked vendor archive',
     lambda r, b, s, m: add_vendor(s, 'gamma')),
    ('archive not in package configuration', 'differ from package configuration',
     lambda r, b, s, m: (s / 'lib/exreader/libexr_vendor_beta.a').write_bytes(b'archive')),
    ('disabled AAC dependency fetched', 'disabled dependency was fetched',
     lambda r, b, s, m: (b / '_deps/beta-src').mkdir()),
    ('disabled AAC archive linked', 'installed although disabled',
     lambda r, b, s, m: add_vendor(s, 'beta')),
    ('disabled AAC license installed', 'installed although disabled',
     lambda r, b, s, m: ((s / LICENSES / 'beta').mkdir(), (s / LICENSES / 'beta/COPYING').write_bytes(b'gpl\n'))),
    ('audio enabled in cache', 'audio codecs are not disabled',
     lambda r, b, s, m: replace(b / 'CMakeCache.txt', 'EXR_ENABLE_AUDIO:BOOL=OFF', 'EXR_ENABLE_AUDIO:BOOL=ON')),
    ('audio layer built', 'audio layer is built',
     lambda r, b, s, m: replace(b / 'exr-modules.json', '"pdf"', '"pdf", "audio"')),
    ('archive pin drifted', 'not pinned in cmake/deps.cmake',
     lambda r, b, s, m: replace(r / 'cmake/deps.cmake', 'a' * 64, 'c' * 64)),
    ('dependency not registered', 'FetchContent declaration not registered',
     lambda r, b, s, m: replace(r / 'cmake/deps.cmake', 'FetchContent_Declare(beta', 'FetchContent_Declare(delta')),
    ('notice row missing', 'not described in THIRD_PARTY_NOTICES.md',
     lambda r, b, s, m: (r / 'THIRD_PARTY_NOTICES.md').write_text('Beta\n')),
    ('install rule missing', 'no install rule',
     lambda r, b, s, m: replace(r / 'CMakeLists.txt', 'licenses/notice.txt', 'licenses/other.txt')),
    ('registered PATENTS missing', 'missing installed license',
     lambda r, b, s, m: (add_notice(r, b, s, m, 'PATENTS', 'alpha/PATENTS'),
                         (s / LICENSES / 'alpha/PATENTS').unlink())),
    ('separate upstream root COPYING missing', 'missing installed license',
     lambda r, b, s, m: (add_notice(r, b, s, m, 'COPYING', 'alpha/upstream-root/COPYING'),
                         (s / LICENSES / 'alpha/upstream-root/COPYING').unlink())),
    ('obsolete zlib copy in libtiff directory', 'unregistered installed license material',
     lambda r, b, s, m: ((s / LICENSES / 'libtiff').mkdir(),
                         (s / LICENSES / 'libtiff/LICENSE').write_bytes(ALPHA))),
    ('installed source statement missing', 'missing installed license',
     lambda r, b, s, m: (source_statement(r, b, s, m), (s / LICENSES / 'notice.txt').unlink())),
    ('source dedication changed', 'source statement differs from the fixed source header',
     lambda r, b, s, m: (source_statement(r, b, s, m),
                         (b / '_deps/alpha-src/LICENSE').write_bytes(b'changed dedication\n'))),
    ('repacked source statement changed', 'source statement differs from the fixed source header',
     lambda r, b, s, m: (source_statement(r, b, s, m),
                         update_statement(r, s, m, (r / 'licenses/notice.txt').read_bytes().replace(ALPHA, b'changed\n')))),
    ('source statement provenance missing', 'source statement provenance is missing or changed',
     lambda r, b, s, m: (source_statement(r, b, s, m),
                         update_statement(r, s, m, ALPHA))),
    ('source version header changed', 'version header differs from the fixed source version',
     lambda r, b, s, m: (source_statement(r, b, s, m),
                         (b / '_deps/alpha-src/alpha.h').write_text('#define ALPHA_VERSION "2.0"\n'))),
]


def main():
    for profile in licenses.READING_PROFILES:
        report = run(profile=profile)
        if not report['materials_check_passed'] or report['pending'] or not report['release_ready'] or report['mandatory_missing']:
            raise RuntimeError(f'Valid {profile} materials rejected: {report["failures"]} {report["pending"]}')
        if report['legal_judgment'] != 'not performed':
            raise RuntimeError('Report must not make a legal judgment')
    for label, expected, mutate in CASES:
        report = run(mutate)
        if report['materials_check_passed'] or report['release_ready'] or not any(expected in item for item in report['failures']):
            raise RuntimeError(f'{label} accepted or reported unexpectedly: {report["failures"]}')
    report = run(lambda r, b, s, m: (b / '_deps/alpha-src/PATENTS').write_bytes(b'grant\n'))
    if not report['materials_check_passed'] or report['release_ready'] or \
            not any('PATENTS' in item for item in report['mandatory_missing']) or report['pending'] != report['mandatory_missing']:
        raise RuntimeError(f'Uninstalled upstream notice did not block release: {report}')
    for mutate in (source_statement, repository_material,
                   lambda r, b, s, m: add_notice(r, b, s, m, 'COPYING', 'alpha/upstream-root/COPYING')):
        report = run(mutate)
        if not report['materials_check_passed'] or not report['release_ready'] or report['mandatory_missing']:
            raise RuntimeError(f'Complete source statement/root notice rejected: {report}')

    # The real manifest must match the pinned sources and keep audio codecs out
    # of both reading presets.
    problems = licenses.manifest_problems(ROOT)
    if problems:
        raise RuntimeError(f'Registered manifest is inconsistent: {problems}')
    by_id = {component['id']: component for component in licenses.COMPONENTS}
    for profile in licenses.READING_PROFILES:
        switches = licenses.preset_switches(ROOT, profile)
        if any(licenses.enabled(by_id[name]['when'], switches) for name in ['minimp3', 'faad2']):
            raise RuntimeError(f'{profile} enables an audio codec')
        if licenses.enabled(by_id['sqlite']['when'], switches) != (profile == 'reading-library'):
            raise RuntimeError(f'{profile} SQLite selection differs from the bookshelf profile')
    print(json.dumps({'license_checker_self_check': True, 'negative_cases': len(CASES),
                      'mandatory_missing_cases': 1, 'source_material_positive_cases': 3,
                      'manifest_components': len(licenses.COMPONENTS)}))


if __name__ == '__main__':
    main()
