# SPDX-License-Identifier: MIT
"""Installed-prefix audit for the module composition gate (Actions only).

Three separate questions, each answered from the installed tree alone:

* manifest  - exactly which files, byte sizes and SHA-256 the install produced;
* scan      - does any installed CMake file or exported usage requirement point
              outside the prefix (a leaked source include, or a non-relocatable
              absolute path)?
* snapshot  - does the prefix taken right after the frozen SDK install stay
              free of every optional module (the default reading build)?
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

MODULES = [
    'EXReaderProductCatalog', 'EXReaderRevisions', 'EXReaderCommands',
    'EXReaderDesktopMetadata', 'EXReaderReadingState', 'EXReaderSearch',
    'EXReaderSession', 'EXReaderSync', 'EXReaderPreferences',
    'EXReaderBatchImport', 'EXReaderSideload', 'EXReaderWebDAV', 'EXReaderCredentials',
]

# package -> (public headers, library name fragments)
PACKAGES = {
    'EXReader': (['include/exreader.h', 'include/exr/library.h', 'include/exr/document.h'],
                 ['exr_base', 'exr_render', 'exr_library', 'exr_pdf']),
    'EXReaderProductCatalog': (['include/exreader-product/catalog.h', 'include/exreader-product/sqlite3.h'],
                               ['reader_catalog', 'reader_catalog_sqlite']),
    'EXReaderRevisions': (['include/reader_revisions.h', 'include/reader_projection.h'],
                          ['reader_revisions', 'reader_revision_hash']),
    'EXReaderCommands': (['include/reader_commands.h'], ['reader_commands']),
    'EXReaderDesktopMetadata': (['include/reader_metadata.h'], ['reader_desktop_metadata']),
    'EXReaderReadingState': (['include/reader_reading_state.h'], ['reader_reading_state']),
    'EXReaderSearch': (['include/reader_search.h'], ['reader_search']),
    'EXReaderSession': (['include/reader_session.h'], ['reader_session']),
    'EXReaderSync': (['include/reader_sync.h'], ['reader_sync']),
    'EXReaderPreferences': (['include/reader_preferences.h'], ['reader_preferences']),
    'EXReaderBatchImport': (['include/reader_batch_import.h'], ['reader_batch_import']),
    'EXReaderSideload': (['include/exr_sideload.h'], ['exr_sideload']),
    'EXReaderWebDAV': (['include/exr_webdav.h'], ['exr_webdav']),
    'EXReaderCredentials': (['include/exr_credentials.h'], ['exr_credentials']),
}

MODULE_HEADERS = ['reader_revisions.h', 'reader_projection.h', 'reader_commands.h',
                  'reader_metadata.h', 'reader_reading_state.h', 'reader_search.h',
                  'reader_session.h', 'reader_sync.h', 'reader_preferences.h',
                  'reader_batch_import.h', 'exr_sideload.h', 'exr_webdav.h',
                  'exr_credentials.h']


def normalized(path):
    return os.path.normcase(os.path.normpath(str(path))).replace('\\', '/')


def under(prefix, candidate):
    prefix = normalized(prefix).rstrip('/')
    candidate = normalized(candidate).rstrip('/')
    return candidate == prefix or candidate.startswith(prefix + '/')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(prefix):
    prefix = Path(prefix)
    files = {}
    for path in sorted(prefix.rglob('*')):
        if path.is_file():
            files[str(path.relative_to(prefix)).replace('\\', '/')] = {
                'bytes': path.stat().st_size, 'sha256': digest(path)}
    return files


def package_findings(prefix):
    prefix = Path(prefix)
    problems = []
    evidence = {}
    for package, (headers, libraries) in PACKAGES.items():
        entry = {'config': None, 'targets': None, 'headers': [], 'libraries': []}
        config = prefix / 'lib' / 'cmake' / package / (package + 'Config.cmake')
        targets = prefix / 'lib' / 'cmake' / package / (package + 'Targets.cmake')
        # EXReaderSideload writes its config without configure_package_config_file.
        if not config.is_file():
            problems.append(package + ': missing ' + str(config.relative_to(prefix)).replace('\\', '/'))
        else:
            entry['config'] = str(config.relative_to(prefix)).replace('\\', '/')
        if targets.is_file():
            entry['targets'] = str(targets.relative_to(prefix)).replace('\\', '/')
        elif package != 'EXReader':
            problems.append(package + ': missing targets export')
        for header in headers:
            if (prefix / header).is_file():
                entry['headers'].append(header)
            else:
                problems.append(package + ': missing installed header ' + header)
        for fragment in libraries:
            matches = [str(path.relative_to(prefix)).replace('\\', '/')
                       for path in (prefix / 'lib').rglob('*')
                       if path.is_file() and fragment + '.' in path.name + '.'
                       and path.suffix in ('.a', '.lib')]
            if matches:
                entry['libraries'].extend(matches)
            elif package != 'EXReader' or fragment != 'exr_pdf':
                problems.append(package + ': missing installed library for ' + fragment)
        evidence[package] = entry
    return problems, evidence


def scan(prefix, source_root, interface=None):
    prefix = Path(prefix)
    problems = []
    inspected = 0
    root_forms = {normalized(source_root)}
    root_forms.add(str(Path(source_root).resolve()))
    root_forms.add(str(Path(source_root).resolve()).replace('/', '\\'))
    for path in sorted((prefix / 'lib' / 'cmake').rglob('*.cmake')):
        text = path.read_text(encoding='utf-8', errors='replace')
        lowered = text.lower()
        inspected += 1
        relative = str(path.relative_to(prefix)).replace('\\', '/')
        for form in root_forms:
            if form and (form in text or form.lower() in lowered):
                problems.append(relative + ': names the source tree ' + form)
                break
        if '/src/' in text.replace('\\', '/'):
            problems.append(relative + ': names a source subdirectory')
    if interface is not None and Path(interface).is_file():
        data = json.loads(Path(interface).read_text(encoding='utf-8'))
        for target in data.get('targets', []):
            for directory in target.get('includes', []):
                inspected += 1
                if not under(prefix, directory):
                    problems.append(target.get('target', '?') + ': include outside the prefix: ' + directory)
    return problems, inspected


def snapshot(prefix, report=None):
    prefix = Path(prefix)
    problems = []
    if not (prefix / 'include' / 'exreader.h').is_file():
        problems.append('snapshot has no public SDK header')
    if not (prefix / 'lib' / 'cmake' / 'EXReader' / 'EXReaderConfig.cmake').is_file():
        problems.append('snapshot has no EXReader package config')
    for package in MODULES:
        if (prefix / 'lib' / 'cmake' / package).exists():
            problems.append('snapshot already contains package ' + package)
        if list((prefix / 'lib').rglob('*' + package.split('EXReader')[-1].lower() + '*.a')):
            problems.append('snapshot already contains a ' + package + ' archive')
    for header in MODULE_HEADERS:
        if (prefix / 'include' / header).exists():
            problems.append('snapshot already installs optional header ' + header)
    for marker in ('exreader-product', 'reader_commands.h', 'exr_webdav.h', 'exr_sideload.h',
                   'exr_credentials.h'):
        if list(prefix.rglob(marker)):
            problems.append('snapshot already contains ' + marker)
    if report is not None and Path(report).is_file():
        data = json.loads(Path(report).read_text(encoding='utf-8'))
        if data.get('optional_packages_found'):
            problems.append('the SDK-only consumer discovered ' + ', '.join(data['optional_packages_found']))
        if data.get('optional_targets_visible'):
            problems.append('the SDK-only consumer saw targets ' + ', '.join(data['optional_targets_visible']))
        if not data.get('core_found') or not data.get('library_found'):
            problems.append('the SDK-only consumer did not find the core and library components')
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--manifest-output', type=Path)
    parser.add_argument('--prefix', type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--interface', type=Path)
    parser.add_argument('--scan-output', type=Path)
    parser.add_argument('--sdk-snapshot', type=Path)
    parser.add_argument('--sdk-report', type=Path)
    parser.add_argument('--snapshot-output', type=Path)
    parser.add_argument('--expect', choices=['clean', 'leak'], default='clean')
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'installed-prefix audit is cloud only'
    failures = 0

    if args.manifest:
        files = manifest(args.manifest)
        assert files, 'empty install manifest'
        if args.manifest_output:
            args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
            args.manifest_output.write_text(json.dumps(files, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        print('install manifest: %d files' % len(files))

    if args.prefix:
        problems, evidence = package_findings(args.prefix)
        scanned = 0
        if args.source_root:
            leaks, scanned = scan(args.prefix, args.source_root, args.interface)
            problems.extend(leaks)
        if args.scan_output:
            args.scan_output.parent.mkdir(parents=True, exist_ok=True)
            args.scan_output.write_text(json.dumps({'problems': problems, 'inspected': scanned,
                                                    'packages': evidence}, indent=1) + '\n', encoding='utf-8')
        acceptable = bool(problems) if args.expect == 'leak' else not problems
        for problem in problems:
            print(('finding: ' if args.expect == 'leak' else 'PROBLEM: ') + problem)
        if not acceptable:
            failures += 1
            print('installed prefix is not composed as required (%d findings)' % len(problems))
        else:
            print('installed prefix accepted as ' + args.expect + ' (%d packages, %d cmake files inspected)'
                  % (len(evidence), scanned))

    if args.sdk_snapshot:
        problems = snapshot(args.sdk_snapshot, args.sdk_report)
        if args.snapshot_output:
            args.snapshot_output.parent.mkdir(parents=True, exist_ok=True)
            args.snapshot_output.write_text(json.dumps({'problems': problems}, indent=1) + '\n', encoding='utf-8')
        for problem in problems:
            print('PROBLEM: ' + problem)
        if problems:
            failures += 1
            print('the default reading snapshot already carries optional modules')
        else:
            print('default reading build carries no optional module')

    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
