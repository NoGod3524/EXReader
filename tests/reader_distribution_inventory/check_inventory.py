#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reject missing, empty, misplaced, altered or unproven distribution evidence.

The fixtures fabricate one installed platform, its captured tool output and its
SBOM, then mutate exactly one property per case. Each mutation must be rejected
with a named code; the untouched fixtures must be granted. Nothing here builds or
installs the SDK, so the protocol job runs it without a compiler.
"""
import hashlib
import io
import json
from pathlib import Path, PurePath
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(HERE))
import aggregate
import contract
import sbom

SHA = 'f43baf9182d75907c0cb5d6f77048f27bca8c950'
RUN_ID = 40000000001
ATTEMPT = 1
LICENSES = contract.LICENSES
HEADER = b'#define EXR_VERSION "3.40.0"\n#define EXR_ABI_VERSION 1u\n#define EXR_CORE_VERSION "3.39.0"\n'
MINIZ_LICENSE = b'miniz license text\n'
DEPENDENCIES_CMAKE = (b'add_library(EXReader::vendor_file_miniz STATIC IMPORTED)\n'
                      b'set_target_properties(EXReader::vendor_file_miniz PROPERTIES IMPORTED_LOCATION '
                      b'"${PACKAGE_PREFIX_DIR}")\n')
TARGETS_CMAKE = (b'add_library(EXReader::exr_render STATIC IMPORTED)\n'
                 b'add_library(EXReader::exr_core INTERFACE IMPORTED)\n')
NM_SDK = ('libexr_core.a(main.o):\n'
          '0000000000000000 T exr_open\n'
          '0000000000000000 T exr_close\n'
          '                 U mz_deflate\n')
NM_VENDOR = ('libexr_vendor_miniz.a(miniz.o):\n'
             '0000000000000000 T mz_deflate\n'
             '0000000000000000 T mz_inflate\n')
AR_SDK = 'main.o\nrender.o\n'
AR_VENDOR = 'miniz.o\nminiz_tdef.o\n'
LINK_TEXT = ('cc -O2 -o probe probe.c.o /ws/stage/lib/libexr_core.a '
             '/ws/stage/lib/exreader/libexr_vendor_miniz.a -lm\n')
READELF_TEXT = ('Dynamic section at offset 0x2e20 contains 27 entries:\n'
                ' 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]\n'
                ' 0x0000000000000001 (NEEDED)             Shared library: [libm.so.6]\n')
DUMPBIN_TEXT = ('Dump of file probe.exe\n\nFile Type: EXECUTABLE IMAGE\n\n'
                '  Image has the following dependencies:\n\n    KERNEL32.dll\n    msvcrt.dll\n\n'
                '  Summary\n')
OTOOL_TEXT = ('/tmp/probe:\n'
              '\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1345.0.0)\n')
SWITCHES = {'EXR_ENABLE_PDF': 'ON', 'EXR_ENABLE_PDF_CRYPTO': 'ON', 'EXR_ENABLE_PDF_JPX': 'ON',
            'EXR_ENABLE_ICC': 'ON', 'EXR_ENABLE_IMAGE_WEBP': 'ON', 'EXR_ENABLE_IMAGE_TIFF': 'ON',
            'EXR_ENABLE_IMAGE_AVIF': 'ON', 'EXR_ENABLE_AUDIO': 'OFF', 'EXR_ENABLE_MP3': 'OFF',
            'EXR_ENABLE_AAC': 'OFF', 'EXR_ENABLE_LIBRARY': 'OFF'}
SDK = 'lib/libexr_core.a'
VENDOR = 'lib/exreader/libexr_vendor_miniz.a'


def record(path, data):
    return {'path': path, 'bytes': len(data), 'sha256': contract.digest(data),
            'sha1': contract.digest1(data)}


def components():
    return [
        {'id': 'exreader', 'name': 'EXReader (first party)', 'version': 'repository HEAD',
         'license': 'MIT', 'when': '', 'notice_marker': None,
         'files': [{'path': 'LICENSE', 'installed': 'LICENSE', 'sha256': None, 'pinned': False,
                    'when': None}]},
        {'id': 'miniz', 'name': 'miniz', 'version': '3.1.2', 'license': 'MIT', 'when': '',
         'notice_marker': 'miniz', 'vendor_files': ['miniz'],
         'files': [{'path': '_deps/miniz-src/LICENSE', 'installed': LICENSES + 'miniz/LICENSE',
                    'sha256': contract.digest(MINIZ_LICENSE), 'pinned': True, 'when': None}]},
    ]


class Recorder:
    def __init__(self, payload):
        self.payload = payload
        self.records = []

    def run(self, kind, purpose, text, archive=None):
        record_ = contract.dependency_record(kind, purpose, ['fixture-tool', purpose], 0, text)
        record_['raw_output_path'] = 'tools/%02d.txt' % (len(self.records) + 1)
        if archive:
            record_['archive'] = archive
        self.payload[record_['raw_output_path']] = text.encode('utf-8')
        self.records.append(record_)
        return record_


def dump(document):
    return (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def build(platform='linux', profile='reading-core'):
    payload = {}
    stage = {'include/exr/base.h': HEADER,
             SDK: b'!<arch>\ncore-archive',
             VENDOR: b'!<arch>\nminiz-archive',
             'lib/cmake/EXReader/EXReaderTargets.cmake': TARGETS_CMAKE,
             'lib/cmake/EXReader/EXReaderDependencies.cmake': DEPENDENCIES_CMAKE,
             'lib/cmake/EXReader/EXReaderConfigVersion.cmake': b'set(PACKAGE_VERSION "3.40.0")\n',
             'LICENSE': b'MIT License\n',
             'THIRD_PARTY_NOTICES.md': b'miniz\n',
             LICENSES + 'miniz/LICENSE': MINIZ_LICENSE}
    for path, data in stage.items():
        payload['stage/' + path] = data
    files = [record(path, data) for path, data in sorted(stage.items())]

    commands = Recorder(payload)
    commands.run('ar', 'archive members libexr_core.a', AR_SDK)
    commands.run('ar', 'archive members libexr_vendor_miniz.a', AR_VENDOR)
    commands.run('nm', 'archive symbols libexr_core.a', NM_SDK, archive=SDK)
    commands.run('nm', 'archive symbols libexr_vendor_miniz.a', NM_VENDOR, archive=VENDOR)
    link = commands.run('ninja-link', 'link command probe', LINK_TEXT)
    kind, dynamic_text = {
        'linux': ('readelf-dynamic', READELF_TEXT),
        'windows': ('dumpbin-dependents', DUMPBIN_TEXT),
        'macos': ('otool', OTOOL_TEXT),
    }[platform]
    dynamic = commands.run(kind, 'dynamic dependencies', dynamic_text)

    symbols = {SDK: contract.symbol_summary(contract.parse_entries('nm', NM_SDK)),
               VENDOR: contract.symbol_summary(contract.parse_entries('nm', NM_VENDOR))}
    edges = contract.symbol_edges(symbols, symbols)
    archive_names = {PurePath(SDK).name, PurePath(VENDOR).name}
    distributed, system, _ = contract.classify_link_tokens(
        [entry['name'] for entry in contract.parse_entries('ninja-link', LINK_TEXT)], archive_names)
    archives = []
    for path, members in ((SDK, ['main.o', 'render.o']), (VENDOR, ['miniz.o', 'miniz_tdef.o'])):
        summary = symbols[path]
        archives.append({'path': path, 'name': PurePath(path).name,
                         'bytes': len(payload['stage/' + path]),
                         'sha256': contract.digest(payload['stage/' + path]), 'members': members,
                         'defined_count': len(summary['defined']),
                         'undefined_count': len(summary['undefined']),
                         'defined_sha256': contract.text_digest(summary['defined']),
                         'undefined_sha256': contract.text_digest(summary['undefined'])})
    inventory = {
        'schema': 1, 'scope': 'fixture', 'profile': profile, 'platform': platform,
        'runner_os': aggregate.PLATFORMS[platform][1], 'architecture': 'X64', 'source_sha': SHA,
        'identity': {'version': '3.40.0', 'abi': 1, 'core_version': '3.39.0',
                     'config_version': '3.40.0', 'targets': ['exr_core', 'exr_render'],
                     'probe': {'version': '3.40.0', 'abi': 1, 'core_version': '3.39.0'}},
        'config': {'cache_switches': dict(SWITCHES), 'preset_switches': dict(SWITCHES),
                   'layers': ['base', 'render'], 'modules_json_sha256': '0' * 64},
        'installed_files': files,
        'totals': {'files': len(files), 'bytes': sum(item['bytes'] for item in files),
                   'archives': len(archives), 'archive_bytes': sum(item['bytes'] for item in archives)},
        'license_materials': {
            'checker': {'release_ready': True, 'materials_check_passed': True, 'failures': [],
                        'pending': [], 'mandatory_missing': [], 'source_sha': SHA, 'components': 2},
            'components': [
                {'id': 'exreader', 'name': 'EXReader (first party)', 'version': 'repository HEAD',
                 'license': 'MIT', 'source': 'repository', 'archive_sha256': None, 'when': '',
                 'linkage': 'component archives', 'active': True, 'vendor_files': [],
                 'notice_marker': None, 'archives': [],
                 'files': [{'installed': 'LICENSE', 'origin': 'repository', 'source': 'LICENSE',
                            'expected': True, 'bytes': len(payload['stage/LICENSE']),
                            'sha256': contract.digest(payload['stage/LICENSE']),
                            'pinned_sha256': None}],
                 'notice': {'notices_path': 'THIRD_PARTY_NOTICES.md', 'notices_sha256': '1' * 64,
                            'marker': None, 'described': True}},
                {'id': 'miniz', 'name': 'miniz', 'version': '3.1.2', 'license': 'MIT',
                 'source': 'https://example.invalid/miniz.tar.gz', 'archive_sha256': 'a' * 64,
                 'when': '', 'linkage': 'private static archive', 'active': True,
                 'vendor_files': ['miniz'], 'notice_marker': 'miniz',
                 'archives': [{'path': VENDOR, 'name': PurePath(VENDOR).name,
                               'bytes': len(payload['stage/' + VENDOR]),
                               'sha256': contract.digest(payload['stage/' + VENDOR])}],
                 'files': [{'installed': LICENSES + 'miniz/LICENSE', 'origin': 'upstream',
                            'source': '_deps/miniz-src/LICENSE', 'expected': True,
                            'bytes': len(MINIZ_LICENSE), 'sha256': contract.digest(MINIZ_LICENSE),
                            'pinned_sha256': contract.digest(MINIZ_LICENSE)}],
                 'notice': {'notices_path': 'THIRD_PARTY_NOTICES.md', 'notices_sha256': '1' * 64,
                            'marker': 'miniz', 'described': True}}]},
        'static_dependency': {'sdk_archives': [SDK], 'archives': archives, 'edges': edges,
                              'foreign_archives': [],
                              'unreferenced_archives': [], 'reachable_archives': [SDK, VENDOR],
                              'owners': {VENDOR: 'miniz'}, 'unreferenced_justified': {}},
        'link': {'record': link, 'distributed_archives': distributed, 'system_libraries': system},
        'dynamic_dependencies': {'record': dynamic, 'resolution': None, 'entries': dynamic['entries']},
        'dependency_commands': commands.records, 'not_covered': ['mobile packaging'],
        'checks': [{'id': 'fixture.check', 'status': 'pass', 'detail': ''}],
        'problems': [], 'release_blockers': [], 'observations': {}, 'sbom': {},
        'materials_complete': True, 'release_ready': True,
        'run': {'id': str(RUN_ID), 'attempt': str(ATTEMPT), 'job': 'inventory'}}
    fixture = {'payload': payload, 'inventory': inventory,
               'licenses_doc': {'schema': 1, 'source_sha': SHA, 'release_ready': True,
                                'materials_check_passed': True, 'failures': [], 'pending': [],
                                'mandatory_missing': []},
               'run': {'id': RUN_ID, 'run_attempt': ATTEMPT, 'head_sha': SHA},
               'components': components(), 'switches': dict(SWITCHES)}
    refresh(fixture)
    return fixture


def refresh(fixture, created='2026-10-24T00:00:00Z'):
    """Rebuild the derived sections so a mutation stays internally consistent."""
    inventory = fixture['inventory']
    payload = fixture['payload']
    _, observations = contract.scan_forbidden(payload, inventory)
    hits = contract.scan_private_paths(payload, contract.GENERIC_PRIVATE_PATHS)
    leaked = sorted({hit['path'] for hit in hits})
    inventory['observations'] = observations
    inventory['private_paths'] = {'generic_needles': list(contract.GENERIC_PRIVATE_PATHS),
                                  'needles_checked': len(contract.GENERIC_PRIVATE_PATHS),
                                  'needle_digests': [],
                                  'hits': [{'path': path, 'needle_digests': []} for path in leaked]}
    inventory['release_blockers'] = contract.private_path_blockers(hits)
    inventory['release_ready'] = not inventory['release_blockers'] and not inventory['problems']
    for name, document in (('inventory.spdx.json', sbom.build_spdx(inventory, created)),
                           ('inventory.cdx.json', sbom.build_cyclonedx(inventory, created))):
        data = dump(document)
        payload[name] = data
        inventory['sbom'][name] = {'bytes': len(data), 'sha256': contract.digest(data)}
    return fixture


def verify(fixture):
    return aggregate.verify_platform(fixture['inventory']['platform'], fixture['inventory']['profile'],
                                     fixture['payload'], fixture['inventory'], fixture['licenses_doc'],
                                     fixture['run'], components=fixture['components'],
                                     switches=fixture['switches'])


def verify_ok(fixture):
    """Accept a fixture, naming every problem when it is rejected instead."""
    try:
        return verify(fixture)
    except contract.InventoryError as error:
        raise RuntimeError('fixture rejected: %s %s' % (error.code, error.detail)) from None


def mutate_sbom(fixture, name, mutate):
    document = contract.decode_json(fixture['payload'][name])
    mutate(document)
    data = dump(document)
    fixture['payload'][name] = data
    fixture['inventory']['sbom'][name] = {'bytes': len(data), 'sha256': contract.digest(data)}


def add_file(fixture, path, data):
    """Add an installed file the way a real install would, then re-derive."""
    fixture['payload']['stage/' + path] = data
    fixture['inventory']['installed_files'].append(record(path, data))
    fixture['inventory']['installed_files'].sort(key=lambda item: item['path'])
    refresh(fixture)


def declared_blocker(fixture):
    add_file(fixture, 'docs/NOTES.md', b'/home/runner/work/EXReader/EXReader\n')
    fixture['inventory']['checks'].append({'id': 'inclusions.no_machine_paths',
                                           'status': 'blocked', 'detail': '1 file'})


CASES = [
    ('missing installed file', 'missing installed file',
     lambda f: f['payload'].pop('stage/' + SDK)),
    ('unrecorded installed file', 'unrecorded installed file',
     lambda f: f['payload'].__setitem__('stage/extra.txt', b'extra\n')),
    ('altered installed file', 'installed file identity mismatch',
     lambda f: f['payload'].__setitem__('stage/include/exr/base.h', HEADER + b'\n')),
    ('empty installed file', 'installed file identity mismatch',
     lambda f: f['payload'].__setitem__('stage/LICENSE', b'')),
    ('missing license material', 'missing installed license',
     lambda f: f['payload'].pop('stage/' + LICENSES + 'miniz/LICENSE')),
    ('altered license text', 'installed license differs from its registered pin',
     lambda f: f['payload'].__setitem__('stage/' + LICENSES + 'miniz/LICENSE', b'edited\n')),
    ('unregistered license material', 'unregistered installed license material',
     lambda f: add_file(f, LICENSES + 'extra/LICENSE', b'extra\n')),
    ('missing file in the SBOM', 'spdx file coverage',
     lambda f: mutate_sbom(f, 'inventory.spdx.json', lambda doc: doc['files'].pop())),
    ('wrong SBOM hash', 'spdx file checksum',
     lambda f: mutate_sbom(f, 'inventory.spdx.json',
                           lambda doc: doc['files'][0]['checksums'][1].__setitem__(
                               'checksumValue', '0' * 64))),
    ('SBOM identity mismatch', 'sbom_identity',
     lambda f: f['inventory']['sbom']['inventory.cdx.json'].__setitem__('sha256', '0' * 64)),
    ('dependency entry mismatch', 'dependency_entries_mismatch',
     lambda f: f['inventory']['dependency_commands'][4].__setitem__('entries', [])),
    ('dependency output altered', 'dependency_output_digest',
     lambda f: f['payload'].__setitem__(f['inventory']['dependency_commands'][5]['raw_output_path'],
                                        b'different\n')),
    ('invented static edge', 'static_edges_mismatch',
     lambda f: f['inventory']['static_dependency']['edges'].append(
         {'from': SDK, 'to': SDK, 'symbols': ['absent']})),
    ('archive hash mismatch', 'archive_identity',
     lambda f: f['inventory']['static_dependency']['archives'][0].__setitem__('sha256', '0' * 64)),
    ('undefined symbol digest', 'archive_undefined_symbols',
     lambda f: f['inventory']['static_dependency']['archives'][0].__setitem__(
         'undefined_sha256', '0' * 64)),
    ('archive coverage', 'archive_coverage',
     lambda f: f['inventory']['static_dependency']['archives'].pop()),
    ('sdk archive list', 'sdk_archives',
     lambda f: f['inventory']['static_dependency'].__setitem__('sdk_archives', [])),
    ('unreferenced archive claim', 'unreferenced_archives',
     lambda f: f['inventory']['static_dependency'].__setitem__('unreferenced_archives', [VENDOR])),
    ('foreign archive claim', 'foreign_archive',
     lambda f: f['inventory']['static_dependency'].__setitem__(
         'foreign_archives', [{'path': 'lib/libalpha.a', 'name': 'libalpha.a', 'bytes': 1,
                               'sha256': '0' * 64, 'members': ['alpha.o']}])),
    ('reported check status', 'check_status',
     lambda f: f['inventory']['checks'].append({'id': 'x', 'status': 'unknown', 'detail': ''})),
    ('link distribution claim', 'link_distributed',
     lambda f: f['inventory']['link'].__setitem__('distributed_archives', ['libexr_core.a'])),
    ('system library claim', 'link_system_libraries',
     lambda f: f['inventory']['link'].__setitem__('system_libraries', [])),
    ('link record binding', 'link_record',
     lambda f: f['inventory']['link'].__setitem__(
         'record', dict(f['inventory']['link']['record'], purpose='other'))),
    ('dynamic entries claim', 'dynamic_entries',
     lambda f: f['inventory']['dynamic_dependencies'].__setitem__('entries', [])),
    ('audio switch enabled', 'audio codec switch is not OFF',
     lambda f: (f['inventory']['config']['cache_switches'].__setitem__('EXR_ENABLE_AUDIO', 'ON'),
                refresh(f))),
    ('undeclared private path', 'release_blockers',
     lambda f: (add_file(f, 'docs/NOTES.md', b'/home/runner/work/x\n'),
                f['inventory'].__setitem__('release_blockers', []),
                f['inventory'].__setitem__('release_ready', True))),
    ('inventory problems', 'inventory_problems',
     lambda f: f['inventory'].__setitem__('problems', ['declared failure'])),
    ('materials claim', 'materials_complete',
     lambda f: f['inventory'].__setitem__('materials_complete', False)),
    ('release claim', 'release_ready_claim',
     lambda f: f['inventory'].__setitem__('release_ready', False)),
    ('licence record not ready', 'licenses_not_release_ready',
     lambda f: (f['licenses_doc'].__setitem__('release_ready', False),
                f['inventory']['license_materials']['checker'].__setitem__('release_ready', False))),
    ('licence record mismatch', 'inventory_checker_release_ready',
     lambda f: f['inventory']['license_materials']['checker'].__setitem__('release_ready', False)),
    ('runtime identity divergence', 'runtime version',
     lambda f: f['inventory']['identity']['probe'].__setitem__('version', '3.39.0')),
    ('package configuration divergence', 'package configuration version',
     lambda f: f['inventory']['identity'].__setitem__('config_version', '3.41.0')),
    ('unexpected artifact path', 'artifact_path',
     lambda f: f['payload'].__setitem__('junk.txt', b'x')),
    ('run identity', 'inventory_run',
     lambda f: f['inventory']['run'].__setitem__('id', '1')),
    ('source identity', 'inventory_source',
     lambda f: f['inventory'].__setitem__('source_sha', '0' * 40)),
    ('check status', 'check_status',
     lambda f: f['inventory']['checks'].append({'id': 'x', 'status': 'fail', 'detail': ''})),
]


def cases_report():
    """Accept every consistent fixture and name every inconsistent claim."""
    accepted, rejected, errors = [], [], []
    try:
        verify_ok(build())
        accepted.append('base fixture granted')
    except RuntimeError as error:
        errors.append(str(error))
    try:
        blocker = build()
        declared_blocker(blocker)
        result = verify(blocker)
        if result['release_ready'] or not result['release_blockers']:
            errors.append('declared private path was not retained as a release blocker')
        else:
            accepted.append('declared private path blocks release without failing the evidence')
    except contract.InventoryError as error:
        errors.append('declared blocker rejected: %s %s' % (error.code, error.detail))
    for platform, profile in (('windows', 'reading-library'), ('macos', 'reading-core')):
        try:
            verify_ok(build(platform=platform, profile=profile))
            accepted.append('%s/%s fixture granted' % (platform, profile))
        except RuntimeError as error:
            errors.append(str(error))
    for label, expected, mutate in CASES:
        try:
            fixture = build()
            mutate(fixture)
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
        raise RuntimeError('%d fixture problems: %s' % (len(errors), ' | '.join(errors)[:3000]))
    return accepted, rejected

def tool_parsers():
    assert [entry['name'] for entry in contract.parse_entries('ar', AR_SDK)] == ['main.o', 'render.o']
    assert [entry['name'] for entry in contract.parse_entries('lib-list',
                                                             'miniz.obj\nminiz_tdef.obj\n')] == \
        ['miniz.obj', 'miniz_tdef.obj']
    ldd = 'libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x0)\nlibmissing.so => not found\n'
    parsed = contract.parse_entries('ldd', ldd)
    assert parsed[0]['state'] == 'resolved' and parsed[1]['state'] == 'unresolved'
    otool = '/private/tmp/probe:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n'
    assert contract.parse_entries('otool', otool)[0]['name'] == '/usr/lib/libSystem.B.dylib'
    dumpbin = ('Dump of file probe.exe\n\nFile Type: EXECUTABLE IMAGE\n\n'
               '  Image has the following dependencies:\n\n    KERNEL32.dll\n    msvcrt.dll\n\n'
               '  Image has the following delay load dependencies:\n\n    USER32.dll\n\n  Summary\n')
    assert [entry['name'] for entry in contract.parse_entries('dumpbin-dependents', dumpbin)] == \
        ['KERNEL32.dll', 'msvcrt.dll', 'USER32.dll']
    symbols = contract.parse_entries('nm', NM_VENDOR)
    assert [entry['name'] for entry in symbols if entry['state'] == 'defined'] == ['mz_deflate', 'mz_inflate']
    assert [entry['name'] for entry in contract.parse_entries('nm', NM_SDK)
            if entry['state'] == 'undefined'] == ['mz_deflate']
    darwin = '0000000000000020 T _exr_open\n                 U _mz_deflate\n'
    assert {entry['name'] for entry in contract.parse_entries('nm', darwin, True)} == \
        {'exr_open', 'mz_deflate'}
    ms = ('Dump of file exr_vendor_miniz.lib\n\nCOFF SYMBOL TABLE\n'
          '000 00000000 SECT1  notype       Static       | .text\n'
          '008 00000000 UNDEF  notype ()    External     | mz_deflate\n'
          '009 00000000 SECT3  notype ()    External     | mz_inflate\n')
    assert [(entry['name'], entry['state']) for entry in contract.parse_entries('dumpbin-symbols', ms)] == \
        [('mz_deflate', 'undefined'), ('mz_inflate', 'defined')]
    link = contract.parse_entries('ninja-link',
                                  'cl /c probe.c\nlink.exe /out:probe.exe probe.obj a.lib\n')
    assert link[-1]['name'] == 'a.lib'
    distributed, system, other = contract.classify_link_tokens(
        ['/ws/stage/lib/libexr_core.a', '-lm', 'probe.c.o'], {'libexr_core.a'})
    assert distributed == ['libexr_core.a'] and system == ['-lm'] and other == ['probe.c.o']
    assert contract.spdx_verification_code(['b' * 40, 'a' * 40]) == hashlib.sha1(
        (('a' * 40) + ('b' * 40)).encode('ascii')).hexdigest()
    try:
        sbom.licence_expression('unregistered-component')
    except sbom.SbomError:
        pass
    else:
        raise RuntimeError('unmapped component identifier was accepted')
    return ['dependency parsers', 'link classifier', 'verification code', 'licence identifier table']


def artifact_contract():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('stage/include/exr/base.h', HEADER)
        archive.writestr('inventory.json', dump({'schema': 1}))
    blob = buffer.getvalue()
    artifact = {'id': 7, 'name': 'reader-distribution-inventory-linux-reading-core-1-1',
                'size_in_bytes': len(blob), 'digest': 'sha256:' + contract.digest(blob),
                'expired': False, 'expires_at': '2030-01-01T00:00:00Z',
                'workflow_run': {'id': 1, 'head_sha': SHA, 'repository_id': 3,
                                 'head_repository_id': 3}}
    run = {'id': 1, 'head_sha': SHA, 'repository': {'id': 3}, 'head_repository': {'id': 3}}
    now = aggregate.datetime.now(aggregate.timezone.utc)
    contract.artifact_identity(artifact, run, now)
    assert 'stage/include/exr/base.h' in contract.archive_files(blob, artifact)
    log = (b'SHA256 digest of uploaded artifact zip is ' + contract.digest(blob).encode('ascii')
           + b'\nArtifact %s has been successfully uploaded! Final size is %d bytes. Artifact ID is 7\n'
           % (artifact['name'].encode('ascii'), artifact['size_in_bytes']))
    contract.upload_binding(log, artifact)
    rejected = []
    for label, mutate, code in (
            ('ZIP digest', lambda a: a.__setitem__('digest', 'sha256:' + '0' * 64), 'zip_digest'),
            ('expired artifact', lambda a: a.__setitem__('expired', True), 'artifact_expired_or_empty'),
            ('foreign origin', lambda a: a.__setitem__('workflow_run', {'id': 2, 'head_sha': SHA,
                                                                       'repository_id': 3,
                                                                       'head_repository_id': 3}),
             'artifact_origin')):
        target = dict(artifact)
        mutate(target)
        try:
            contract.artifact_identity(target, run, now)
            contract.archive_files(blob if code == 'zip_digest' else b'not-a-zip', target)
        except contract.InventoryError as error:
            if error.code != code:
                raise RuntimeError('%s rejected with %s instead of %s'
                                   % (label, error.code, code)) from None
            rejected.append(label)
            continue
        raise RuntimeError(label + ' was accepted')
    for label, replacement, code in (
            ('uploaded size', log.replace(b'Final size is %d' % artifact['size_in_bytes'],
                                          b'Final size is 1'), 'producer_artifact_binding'),
            ('uploaded digest', log.replace(contract.digest(blob).encode('ascii'),
                                            b'0' * 64), 'producer_digest_binding')):
        try:
            contract.upload_binding(replacement, artifact)
        except contract.InventoryError as error:
            if error.code != code:
                raise RuntimeError('%s rejected with %s instead of %s'
                                   % (label, error.code, code)) from None
            rejected.append(label)
            continue
        raise RuntimeError(label + ' was accepted')
    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, 'w') as archive:
        archive.writestr('stage/a.txt', b'a')
        archive.writestr('stage/A.txt', b'b')
    odd = dict(artifact, size_in_bytes=len(duplicate.getvalue()),
               digest='sha256:' + contract.digest(duplicate.getvalue()))
    try:
        contract.archive_files(duplicate.getvalue(), odd)
    except contract.InventoryError as error:
        if error.code != 'zip_duplicate_path':
            raise
        rejected.append('duplicate archive path')
    else:
        raise RuntimeError('duplicate archive path was accepted')
    return rejected


def main():
    accepted, rejected = cases_report()
    parsers = tool_parsers()
    artifact_rejected = artifact_contract()
    print(json.dumps({'inventory_self_check': True, 'accepted_cases': len(accepted),
                      'rejected_cases': len(rejected), 'parser_checks': len(parsers),
                      'artifact_rejections': len(artifact_rejected),
                      'dependency_parsers': len(contract.PARSERS)}, indent=2))


if __name__ == '__main__':
    main()
