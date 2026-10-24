#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reject unproven composed-prefix evidence: SDK plus thirteen optional packages.

The fixture fabricates one composed install, its captured archive symbols, one
link command per package and both SBOM documents, then mutates exactly one
property per case. Every mutation must be rejected with a named code and the
untouched fixture must be granted.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(HERE))
import aggregate
import contract
import inventory as sdk
import packages
import sbom

SHA = 'f43baf9182d75907c0cb5d6f77048f27bca8c950'
RUN_ID = 40000000001
ATTEMPT = 1
HEADER = b'#define EXR_VERSION "3.40.0"\n#define EXR_ABI_VERSION 1u\n#define EXR_CORE_VERSION "3.39.0"\n'
LICENSES = contract.LICENSES
TARGETS = b'add_library(EXReader::exr_base STATIC IMPORTED)\n'
DEPENDENCIES = (b'set_target_properties(EXReader::vendor_file_miniz PROPERTIES IMPORTED_LOCATION '
                b'"${PACKAGE_PREFIX_DIR}")\n')
FAMILY_SYMBOL = {
    'libcurl': 'curl_easy_init', 'libxml2': 'xmlReadMemory', 'libcrypto': 'EVP_DigestInit_ex',
    'bcrypt': 'BCryptGenRandom', 'libsecret-1': 'secret_password_store_sync',
    'advapi32': 'CredWriteW', 'winhttp': 'WinHttpOpen', 'xmllite': 'CreateXmlReader',
    'shlwapi': 'PathFileExistsW', 'Security': 'SecItemAdd', 'CoreFoundation': 'CFRelease',
    'Foundation': 'NSURLRequest', 'Threads': 'pthread_create',
}
SWITCHES = {'EXR_ENABLE_PDF': 'ON', 'EXR_ENABLE_LIBRARY': 'ON', 'EXR_ENABLE_AUDIO': 'OFF',
            'EXR_ENABLE_MP3': 'OFF', 'EXR_ENABLE_AAC': 'OFF'}
ARCHIVE = re.compile(r'lib/(?:exreader/)?[^/]+[.](?:a|lib)')
EMPTY = {'defined': [], 'undefined': []}


def extension(platform):
    return '.lib' if platform == 'windows' else '.a'


def dump(document):
    return (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def record(path, data):
    return {'path': path, 'bytes': len(data), 'sha256': contract.digest(data),
            'sha1': contract.digest1(data)}


LINK_NAME = {'libcurl': 'curl', 'libxml2': 'xml2', 'libcrypto': 'crypto', 'libsecret-1': 'secret-1'}
FRAMEWORKS = ('Security', 'CoreFoundation', 'Foundation')


def link_text(package, platform, drop=None):
    ext = extension(platform)
    parts = ['cc', '-o', 'consumer-%s' % package['id'], 'main.o',
             'stage/lib/libexr_base%s' % ext]
    for name in package['archives']:
        parts.append('stage/lib/%s%s' % (name, ext))
    for library in package['system'][platform]:
        if library == drop:
            continue
        if library in FRAMEWORKS:
            parts.extend(['-framework', library])
        else:
            parts.append('-l%s' % LINK_NAME.get(library, library))
    return ' '.join(parts) + '\n'


def symbols_text(defined, undefined, kind='nm'):
    if kind == 'dumpbin-symbols':
        lines = ['Dump of file archive.lib', '', 'File Type: LIBRARY', '', 'COFF SYMBOL TABLE']
        for index, name in enumerate(defined):
            lines.append('%03X 00000000 SECT%d  notype ()    External     | %s'
                         % (index + 1, index + 1, name))
        for index, name in enumerate(undefined):
            lines.append('%03X 00000000 UNDEF  notype ()    External     | %s'
                         % (len(defined) + index + 1, name))
        return '\n'.join(lines) + '\n'
    lines = ['archive.a(member.o):']
    lines += ['%016x T %s' % (index * 16, name) for index, name in enumerate(defined)]
    lines += ['                 U %s' % name for name in undefined]
    return '\n'.join(lines) + '\n'


def build(platform='linux'):
    ext = extension(platform)
    payload = {}

    def add(path, data):
        payload['stage/' + path] = data

    add('include/exr/base.h', HEADER)
    add('lib/libexr_base%s' % ext, b'!<arch>\nsdk-base')
    add('lib/cmake/EXReader/EXReaderConfigVersion.cmake', b'set(PACKAGE_VERSION "3.40.0")\n')
    add('lib/cmake/EXReader/EXReaderTargets.cmake', TARGETS)
    add('lib/cmake/EXReader/EXReaderDependencies.cmake', DEPENDENCIES)
    add('share/exreader/LICENSE', b'MIT License\n')
    add('share/exreader/THIRD_PARTY_NOTICES.md', b'miniz\n')
    add('LICENSE', b'MIT License\n')
    add('THIRD_PARTY_NOTICES.md', b'miniz\n')
    add(LICENSES + 'miniz/LICENSE', b'miniz license text\n')

    records = []

    def run(kind, purpose, text, archive=None):
        item = contract.dependency_record(kind, purpose, ['fixture-tool', purpose], 0, text)
        item['raw_output_path'] = 'tools/%02d.txt' % (len(records) + 1)
        if archive:
            item['archive'] = archive
        payload[item['raw_output_path']] = text.encode('utf-8')
        records.append(item)
        return item

    sdk_archive = 'lib/libexr_base%s' % ext
    if platform == 'windows':
        run('lib-list', 'archive members sdk', 'base.obj\n')
        run('dumpbin-symbols', 'archive symbols sdk',
            symbols_text(['exr_open'], [], 'dumpbin-symbols'), archive=sdk_archive)
        run('dumpbin-directives', 'archive directives sdk', '', archive=sdk_archive)
    else:
        run('ar', 'archive members sdk', 'base.o\n')
        run('nm', 'archive symbols sdk', symbols_text(['exr_open'], []), archive=sdk_archive)

    for package in packages.PACKAGES:
        config = package['config']
        add(config + '/' + package['find'] + 'Config.cmake', b'# config\n')
        if package['version'] is not None:
            add(config + '/' + package['find'] + 'ConfigVersion.cmake',
                ('set(PACKAGE_VERSION "%s")\n' % package['version']).encode())
        add(config + '/' + package['find'] + 'Targets.cmake',
            ('add_library(%s STATIC IMPORTED)\n' % package['archives'][0]).encode())
        for header in package['headers']:
            add(header, b'/* public header */\n')
        for asset in package['assets']:
            add(asset, b'asset bytes\n')
        for index, name in enumerate(package['archives']):
            path = 'lib/%s%s' % (name, ext)
            defined = ['%s_open' % name]
            if package['id'] == 'catalog' and name == 'reader_catalog_sqlite':
                defined = ['sqlite3_open_v2', 'sqlite3_exec']
            add(path, ('!<arch>\n' + name).encode())
            run('lib-list' if platform == 'windows' else 'ar', 'archive members ' + name,
                ('member.obj\n' if platform == 'windows' else 'member.o\n'))
            undefined = []
            if index == 0 and package['system'][platform]:
                undefined = [FAMILY_SYMBOL.get(package['system'][platform][0], 'unknown_external')]
            run('dumpbin-symbols' if platform == 'windows' else 'nm',
                'archive symbols ' + name,
                symbols_text(defined, undefined,
                             'dumpbin-symbols' if platform == 'windows' else 'nm'),
                archive=path)
            if platform == 'windows':
                directive = ''.join('/DEFAULTLIB:"%s.lib"\n' % LINK_NAME.get(library, library)
                                    for library in (package['system'][platform] if index == 0 else []))
                run('dumpbin-directives', 'archive directives ' + name, directive, archive=path)
        run('ninja-link', 'link command consumer-%s' % package['id'], link_text(package, platform))

    fixture = {'payload': payload, 'platform': platform, 'records': records, 'inventory': None,
               'licenses_doc': {'schema': 1, 'source_sha': SHA, 'release_ready': True,
                                'materials_check_passed': True, 'failures': [], 'pending': [],
                                'mandatory_missing': []},
               'run': {'id': RUN_ID, 'run_attempt': ATTEMPT, 'head_sha': SHA},
               'switches': dict(SWITCHES)}
    assemble(fixture)
    return fixture


def assemble(fixture):
    """Recompute every derived section from the current payload and records."""
    payload = fixture['payload']
    platform = fixture['platform']
    ext = extension(platform)
    files = [record(path[len('stage/'):], payload[path]) for path in sorted(payload)
             if path.startswith('stage/')]
    index = {row['path']: payload['stage/' + row['path']] for row in files}
    symbols, directives = {}, {}
    for item in fixture['records']:
        text = payload[item['raw_output_path']].decode('utf-8')
        if item['kind'] in contract.SYMBOL_KINDS:
            symbols[item['archive']] = contract.symbol_summary(
                contract.parse_entries(item['kind'], text, item.get('strip_underscore', False)))
        elif item['kind'] == 'dumpbin-directives':
            directives[item['archive']] = [entry['name'] for entry in item['entries']]
    archives = sorted(path for path in index if ARCHIVE.fullmatch(path))
    for path in archives:
        directives.setdefault(path, [])
    edges = contract.symbol_edges(symbols, symbols)
    sdk_archives = [path for path in archives
                    if re.fullmatch(r'lib/(?:lib)?exr_.+[.](?:a|lib)', path)]
    unreferenced = sorted(path for path in symbols if path not in sdk_archives
                          and not any(edge['to'] == path for edge in edges))
    owners = {}
    for package in packages.PACKAGES:
        for name in package['archives']:
            candidate = 'lib/%s%s' % (name, ext)
            if candidate in index:
                owners[candidate] = package['id']
    archive_names = {path.split('/')[-1] for path in archives}

    providers = packages.symbol_providers(symbols)
    sections = []
    for package in packages.PACKAGES:
        resolved = packages.resolve(package, index)
        own = [entry['path'] for entry in resolved['archives']]
        external = packages.external_from_symbols(own, symbols)
        expected = [packages.canonical(name) for name in package['system'][platform]]
        directive_names = sorted({packages.canonical(name) for path in own
                                  for name in directives.get(path, [])})
        observed = sorted(set(packages.canonical(name) for name in external['families'])
                          | set(directive_names))
        missing = sorted(name for name in expected if name not in observed)
        link = next((item for item in fixture['records']
                     if item['purpose'] == 'link command consumer-%s' % package['id']), None)
        tokens = [entry['name'] for entry in contract.parse_entries(
            'ninja-link', payload[link['raw_output_path']].decode('utf-8'))] if link else []
        evidence = packages.link_evidence(tokens, archive_names, package['system'][platform])
        bundled = [{'library': entry['library'], 'archive': entry['archive'],
                    'material': entry['material'],
                    'providers': providers.get(entry['library'], []),
                    'material_present': entry['material'] in index}
                   for entry in package['bundled']]
        sections.append({'id': package['id'], 'name': package['name'],
                         'project': package['project'], 'find': package['find'],
                         'source': package['source'], 'registered_version': package['version'],
                         'version': resolved['version'],
                         'version_source': resolved.get('version_source'),
                         'config_files': resolved['config_files'], 'headers': resolved['headers'],
                         'archives': resolved['archives'], 'assets': resolved['assets'],
                         'licence': resolved['licence'], 'missing': resolved['missing'],
                         'external': external, 'external_expected': expected,
                         'external_observed': observed, 'external_missing': missing,
                         'directives': directive_names, 'bundled': bundled,
                         'link': link, 'link_evidence': evidence})

    observations, _ = contract.scan_forbidden(
        payload, {'config': {'cache_switches': fixture['switches']},
                  'identity': {'targets': []}, 'dynamic_dependencies': {'entries': []}},
        allow_credentials=True)
    hits = contract.scan_private_paths(payload, contract.GENERIC_PRIVATE_PATHS)
    leaked = sorted({hit['path'] for hit in hits})
    generic = set(contract.GENERIC_PRIVATE_PATHS)

    components = [{'id': 'exreader', 'name': 'EXReader (first party)', 'version': '3.40.0',
                   'license': 'MIT', 'source': 'repository', 'archive_sha256': None, 'when': '',
                   'linkage': 'component archives', 'active': True, 'vendor_files': [],
                   'notice_marker': None, 'archives': [],
                   'files': [{'installed': 'share/exreader/LICENSE', 'origin': 'repository',
                              'path': 'LICENSE', 'source': 'LICENSE', 'expected': True,
                              'bytes': len(index['share/exreader/LICENSE']),
                              'sha256': contract.digest(index['share/exreader/LICENSE']),
                              'pinned_sha256': None}],
                   'notice': {'notices_path': 'share/exreader/LICENSE',
                              'notices_sha256': '0' * 64, 'marker': None, 'described': True}},
                  {'id': 'miniz', 'name': 'miniz', 'version': '3.1.2', 'license': 'MIT',
                   'source': 'https://example.invalid/miniz.tar.gz', 'archive_sha256': 'a' * 64,
                   'when': '', 'linkage': 'private static archive', 'active': True,
                   'vendor_files': [], 'notice_marker': 'miniz', 'archives': [],
                   'files': [{'installed': LICENSES + 'miniz/LICENSE', 'origin': 'upstream',
                              'path': '_deps/miniz-src/LICENSE',
                              'source': '_deps/miniz-src/LICENSE', 'expected': True,
                              'bytes': len(index[LICENSES + 'miniz/LICENSE']),
                              'sha256': contract.digest(index[LICENSES + 'miniz/LICENSE']),
                              'pinned_sha256': contract.digest(index[LICENSES + 'miniz/LICENSE'])}],
                   'notice': {'notices_path': 'THIRD_PARTY_NOTICES.md',
                              'notices_sha256': '0' * 64, 'marker': 'miniz', 'described': True}}]
    for section in sections:
        installed = []
        if section['licence']:
            installed = [{'installed': section['licence']['path'], 'origin': 'repository',
                          'path': 'LICENSE', 'source': 'LICENSE', 'expected': True,
                          'bytes': section['licence']['bytes'],
                          'sha256': section['licence']['sha256'], 'pinned_sha256': None}]
        components.append({'id': section['id'], 'name': section['name'],
                           'version': section['registered_version'] or 'unversioned',
                           'license': 'MIT', 'source': 'repository', 'archive_sha256': None,
                           'when': 'combined profile', 'linkage': 'private static archive',
                           'active': True, 'vendor_files': [], 'files': installed,
                           'archives': [{'path': entry['path'], 'name': entry['name'],
                                         'bytes': entry['bytes'], 'sha256': entry['sha256']}
                                        for entry in section['archives']],
                           'notice': {'notices_path': section['licence']['path']
                                      if section['licence'] else None,
                                      'notices_sha256': section['licence']['sha256']
                                      if section['licence'] else None,
                                      'marker': 'MIT', 'described': bool(section['licence'])}})

    inventory = {
        'schema': 1, 'scope': 'fixture', 'profile': 'combined', 'platform': platform,
        'runner_os': aggregate.PLATFORMS[platform][1], 'architecture': 'X64',
        'source_sha': SHA,
        'identity': {'version': '3.40.0', 'abi': 1, 'core_version': '3.39.0',
                     'config_version': '3.40.0', 'targets': ['exr_base'], 'probe': None},
        'config': {'sdk_preset': 'reading-library', 'sdk_switches': fixture['switches'],
                   'packages': [section['id'] for section in sections]},
        'installed_files': files,
        'totals': {'files': len(files), 'bytes': sum(row['bytes'] for row in files),
                   'packages': len(sections),
                   'package_archives': sum(len(section['archives']) for section in sections),
                   'all_archives': len(archives)},
        'license_materials': {'checker': dict(fixture['licenses_doc'], components=1),
                              'components': components},
        'packages': sections,
        'static_dependency': {
            'sdk_archives': sdk_archives,
            'archives': [{'path': path, 'name': path.split('/')[-1],
                          'bytes': len(index[path]), 'sha256': contract.digest(index[path]),
                          'members': [],
                          'defined_count': len(symbols.get(path, EMPTY)['defined']),
                          'undefined_count': len(symbols.get(path, EMPTY)['undefined']),
                          'defined_sha256': contract.text_digest(symbols.get(path, EMPTY)['defined']),
                          'undefined_sha256': contract.text_digest(symbols.get(path, EMPTY)['undefined'])}
                         for path in archives],
            'edges': edges, 'unreferenced_archives': unreferenced, 'owners': owners,
            'foreign_archives': [], 'directives': directives},
        'dependency_commands': fixture['records'],
        'observations': observations,
        'private_paths': {'generic_needles': list(contract.GENERIC_PRIVATE_PATHS),
                          'needles_checked': len(contract.GENERIC_PRIVATE_PATHS),
                          'needle_digests': [],
                          'hits': [{'path': path,
                                    'needles': sorted({hit['needle'] for hit in hits
                                                       if hit['path'] == path
                                                       and hit['needle'] in generic}),
                                    'needle_digests': []} for path in leaked]},
        'not_covered': ['mobile packaging'],
        'sbom': {},
    }
    inventory['release_blockers'] = contract.private_path_blockers(hits)
    for name, document in (('combined.spdx.json', sbom.build_spdx(inventory, '2026-10-24T00:00:00Z')),
                           ('combined.cdx.json',
                            sbom.build_cyclonedx(inventory, '2026-10-24T00:00:00Z'))):
        data = dump(document)
        payload[name] = data
        inventory['sbom'][name] = {'bytes': len(data), 'sha256': contract.digest(data)}
    inventory.update({'checks': [{'id': 'fixture.check', 'status': 'pass', 'detail': ''}],
                      'problems': [],
                      'materials_complete': True,
                      'release_ready': not inventory['release_blockers'],
                      'run': {'id': str(RUN_ID), 'attempt': str(ATTEMPT), 'job': 'combined'}})
    fixture['inventory'] = inventory
    return fixture


def verify(fixture):
    return aggregate.verify_combined(fixture['platform'], fixture['payload'],
                                     fixture['inventory'], fixture['licenses_doc'],
                                     fixture['run'],
                                     components=fixture['inventory']['license_materials']['components'],
                                     switches=fixture['switches'])


def verify_ok(fixture):
    try:
        return verify(fixture)
    except contract.InventoryError as error:
        raise RuntimeError('combined fixture rejected: %s %s'
                           % (error.code, error.detail)) from None


def section_of(fixture, identifier):
    return next(section for section in fixture['inventory']['packages']
                if section['id'] == identifier)


def rewrite_link(identifier, drop=None):
    def mutate(fixture):
        package = packages.by_id(identifier)
        purpose = 'link command consumer-%s' % identifier
        item = next(entry for entry in fixture['records'] if entry['purpose'] == purpose)
        text = link_text(package, fixture['platform'], drop=drop)
        fixture['payload'][item['raw_output_path']] = text.encode('utf-8')
        replacement = contract.dependency_record('ninja-link', purpose, item['command'], 0, text)
        replacement['raw_output_path'] = item['raw_output_path']
        fixture['records'][fixture['records'].index(item)] = replacement
        fixture['inventory']['dependency_commands'] = fixture['records']
        assemble(fixture)
    return mutate


def mutate_sbom(fixture, name, mutate):
    document = contract.decode_json(fixture['payload'][name])
    mutate(document)
    data = dump(document)
    fixture['payload'][name] = data
    fixture['inventory']['sbom'][name] = {'bytes': len(data), 'sha256': contract.digest(data)}


def drop(fixture, path):
    key = 'stage/' + path
    if key not in fixture['payload']:
        raise RuntimeError('fixture has no %s; installed: %r'
                           % (key, sorted(name for name in fixture['payload']
                                          if name.startswith(('stage/lib/', 'stage/include/')))))
    fixture['payload'].pop(key)


def archive_path(fixture, identifier):
    return 'lib/%s%s' % (packages.by_id(identifier)['archives'][0], extension(fixture['platform']))


CASES = [
    ('missing package archive', 'combined_package_archives',
     lambda f: drop(f, archive_path(f, 'search'))),
    ('archive hash changed', 'combined_package_archives',
     lambda f: f['payload'].__setitem__('stage/' + archive_path(f, 'preferences'),
                                        b'!<arch>\ntampered')),
    ('package version changed', 'combined_package_version',
     lambda f: f['payload'].__setitem__(
         'stage/' + packages.by_id('commands')['config']
         + '/EXReaderCommandsConfigVersion.cmake', b'set(PACKAGE_VERSION "9.9.9")\n')),
    ('package header removed', 'combined_package_headers',
     lambda f: drop(f, packages.by_id('session')['headers'][0])),
    ('package licence removed', 'combined_package_licence',
     lambda f: drop(f, 'share/exreader/LICENSE')),
    ('package configuration changed', 'combined_package_config_files',
     lambda f: f['payload'].__setitem__(
         'stage/' + packages.by_id('webdav')['config'] + '/EXReaderWebDAVConfig.cmake',
         b'# different config\n')),
    ('system dependency not observed', 'combined_package_external',
     lambda f: section_of(f, 'credentials')['external'].__setitem__('families', {})),
    ('expected system dependency unmet', 'combined_package_unmet',
     lambda f: section_of(f, 'webdav').__setitem__('external_missing', ['libxml2'])),
    ('link evidence mismatch', 'combined_link_evidence',
     lambda f: section_of(f, 'sync')['link_evidence'].__setitem__('system_libraries', [])),
    ('link drops a registered library', 'combined_link_expected',
     rewrite_link('webdav', drop='libcurl')),
    ('test secret in the prefix', 'combined_test_secrets',
     lambda f: f['payload'].__setitem__('stage/share/exreader-product/001_catalog.sql',
                                        b'password=hunter2\n')),
    ('unregistered archive in the prefix', 'combined_archive_coverage',
     lambda f: f['payload'].__setitem__('stage/lib/reader_bogus'
                                        + extension(f['platform']), b'!<arch>\nbogus')),
    ('invented dependency edge', 'combined_edges',
     lambda f: f['inventory']['static_dependency']['edges'].append(
         {'from': 'lib/libexr_base' + extension(f['platform']),
          'to': 'lib/libexr_base' + extension(f['platform']), 'symbols': ['absent']})),
    ('archive symbol digest', 'combined_archive_defined',
     lambda f: f['inventory']['static_dependency']['archives'][0].__setitem__(
         'defined_sha256', '0' * 64)),
    ('sdk archive list', 'combined_sdk_archives',
     lambda f: f['inventory']['static_dependency'].__setitem__('sdk_archives', [])),
    ('directive evidence', 'combined_directives',
     lambda f: f['inventory']['static_dependency']['directives'].__setitem__(
         'lib/libexr_base' + extension(f['platform']), ['bogus'])),
    ('SBOM file coverage', 'combined_sbom_structure',
     lambda f: mutate_sbom(f, 'combined.spdx.json', lambda doc: doc['files'].pop())),
    ('SBOM identity', 'combined_sbom_identity',
     lambda f: f['inventory']['sbom']['combined.cdx.json'].__setitem__('sha256', '0' * 64)),
    ('credential material outside the package', 'combined_credential_scope',
     lambda f: f['payload'].__setitem__('stage/share/other/credentials.txt', b'opaque\n')),
    ('undeclared private path', 'combined_release_blockers',
     lambda f: (f['payload'].__setitem__('stage/docs/NOTES.md', b'/home/runner/work/x\n'),
                assemble(f), f['inventory'].__setitem__('release_blockers', []),
                f['inventory'].__setitem__('release_ready', True))),
    ('declared problems', 'combined_problems',
     lambda f: f['inventory'].__setitem__('problems', ['declared failure'])),
    ('materials claim', 'combined_materials_complete',
     lambda f: f['inventory'].__setitem__('materials_complete', False)),
    ('release claim', 'combined_release_ready_claim',
     lambda f: f['inventory'].__setitem__('release_ready', False)),
    ('registered package dropped', 'combined_registered',
     lambda f: f['inventory']['packages'].pop()),
    ('check status', 'combined_check_status',
     lambda f: f['inventory']['checks'].append({'id': 'x', 'status': 'unknown', 'detail': ''})),
]


REBUILD = ('test secret in the prefix', 'unregistered archive in the prefix',
           'credential material outside the package')


def cases_report():
    accepted, rejected, errors = [], [], []
    for platform in ('linux', 'windows', 'macos'):
        try:
            verify_ok(build(platform))
            accepted.append('%s composed prefix granted' % platform)
        except RuntimeError as error:
            errors.append(str(error))
    for label, expected, mutate in CASES:
        fixture = build()
        try:
            mutate(fixture)
            if label in REBUILD:
                assemble(fixture)
            verify(fixture)
        except contract.InventoryError as error:
            detail = error.detail if isinstance(error.detail, (list, str)) else []
            text = ' '.join(detail) if isinstance(detail, list) else str(detail)
            if expected not in (text + ' ' + str(error.code) + ' ' + str(error.args[0])):
                errors.append('%s: rejected with %s/%s instead of %s'
                              % (label, error.code, text[:120], expected))
            else:
                rejected.append(label)
            continue
        except Exception as error:
            errors.append('%s: unexpected %r' % (label, error))
            continue
        errors.append(label + ' was accepted')
    if errors:
        raise RuntimeError('%d composed fixture problems: %s'
                           % (len(errors), ' | '.join(errors)[:3000]))
    return accepted, rejected


def main():
    accepted, rejected = cases_report()
    print(json.dumps({'combined_self_check': True, 'accepted_cases': len(accepted),
                      'rejected_cases': len(rejected),
                      'registered_packages': len(packages.REGISTERED_IDS)}, indent=2))


if __name__ == '__main__':
    main()
