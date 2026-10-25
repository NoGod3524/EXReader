#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rejection protocol for the distribution licence and SBOM closure.

The fixture install is generated here, inside the job: a small stage, its inventory,
both SBOM documents built by the shared builder and the registered licence record.
One untouched fixture must close; every single mutation must be rejected with a named
code. Nothing here is evidence about a real candidate: it only proves that each
closure property is enforced by closure.py.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests' / 'reader_distribution_inventory'))
sys.path.insert(0, str(HERE))
import check_reading_licenses as registered
import closure
import contract
import sbom

FIXTURE_SHA = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
NOTICE_PATHS = ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'share/exreader/LICENSE',
                'share/exreader/THIRD_PARTY_NOTICES.md')
STAGE = {
    'LICENSE': b'EXReader first-party licence fixture\n',
    'THIRD_PARTY_NOTICES.md': b'Fixture notices: miniz, Expat.\n',
    'share/exreader/LICENSE': b'EXReader first-party licence fixture\n',
    'share/exreader/THIRD_PARTY_NOTICES.md': b'Fixture notices: miniz, Expat.\n',
    'share/exreader/licenses/miniz/LICENSE': b'miniz licence fixture text\n',
    'share/exreader/licenses/expat/COPYING': b'Expat licence fixture text\n',
    'lib/libexr_core.a': b'!<arch>\ncore object\n',
    'lib/libexr_pdf.a': b'!<arch>\npdf object\n',
    'lib/exreader/libexr_vendor_miniz.a': b'!<arch>\nvendor miniz object\n',
    'lib/exreader/libexr_vendor_expat.a': b'!<arch>\nvendor expat object\n',
    'lib/libminiz.a': b'!<arch>\nupstream-named miniz copy\n',
    'lib/cmake/EXReader/EXReaderConfig.cmake': b'# fixture package configuration\n',
}
LINK_COMMAND = ('[1/1] : && /usr/bin/c++ -O2 CMakeFiles/probe.dir/main.o -o probe '
                'lib/libexr_core.a lib/libexr_pdf.a lib/exreader/libexr_vendor_miniz.a '
                'lib/exreader/libexr_vendor_expat.a -lz && :\n')
SWITCHES = {'EXR_ENABLE_PDF': 'ON', 'EXR_ENABLE_IMAGE_WEBP': 'OFF', 'EXR_ENABLE_AUDIO': 'OFF'}


def fixture_components():
    """Registered components with fixture licence pins, so the checks are exercised."""
    base = {component['id']: copy.deepcopy(component) for component in registered.COMPONENTS}
    components = []
    exreader = base['exreader']
    exreader['files'] = [{'origin': 'repository', 'path': path, 'installed': path,
                          'sha256': None, 'when': None, 'pinned': False}
                         for path in NOTICE_PATHS]
    components.append(exreader)
    for identifier, installed in (('miniz', 'share/exreader/licenses/miniz/LICENSE'),
                                  ('expat', 'share/exreader/licenses/expat/COPYING')):
        component = base[identifier]
        component['files'] = [{'origin': 'upstream', 'path': installed.split('/')[-1],
                               'installed': installed,
                               'sha256': contract.digest(STAGE[installed]), 'when': None}]
        components.append(component)
    return components


def build():
    """The untouched fixture: one install that must close."""
    payload = {'stage/' + path: data for path, data in STAGE.items()}
    payload['tools/01-link.txt'] = LINK_COMMAND.encode('utf-8')
    records = closure.derived_files(payload)
    by_path = {record['path']: record for record in records}
    components = fixture_components()
    link_record = contract.dependency_record(
        'ninja-link', 'link command probe',
        ['ninja', '-C', 'build/probe', '-t', 'commands', 'probe'], 0, LINK_COMMAND)
    link_record['raw_output_path'] = 'tools/01-link.txt'
    archive_names = {path.split('/')[-1] for path in STAGE
                     if closure.ARCHIVE_PATH.match(path)}
    distributed, system, _ = closure.link_partition(
        [entry['name'] for entry in link_record['entries']], archive_names)
    inventory_components = []
    for component in components:
        files = []
        for item in component['files']:
            data = payload['stage/' + item['installed']]
            files.append({'installed': item['installed'], 'origin': item['origin'],
                          'source': item['path'], 'expected': True,
                          'bytes': len(data), 'sha256': contract.digest(data)})
        wanted = set(component.get('vendor_files') or ())
        archives = [{'path': path, 'name': path.split('/')[-1],
                     'bytes': by_path[path]['bytes'], 'sha256': by_path[path]['sha256']}
                    for path in sorted(by_path)
                    if closure.ARCHIVE_PATH.match(path)
                    and closure.archive_identity(path.split('/')[-1])[1] in wanted]
        inventory_components.append({
            'id': component['id'], 'name': component['name'], 'version': component['version'],
            'license': component['license'], 'source': component['source'],
            'archive_sha256': component.get('archive_sha256'), 'when': component.get('when'),
            'linkage': component.get('linkage'), 'active': True,
            'vendor_files': list(component.get('vendor_files') or []),
            'notice_marker': component.get('notice_marker'), 'files': files,
            'archives': archives})
    inventory = {
        'schema': 1, 'scope': closure.SCOPE, 'profile': 'reading-core', 'platform': 'linux',
        'runner_os': 'Linux', 'architecture': 'X64', 'source_sha': FIXTURE_SHA,
        'identity': {'version': '3.40.0', 'abi': 1, 'core_version': '3.39.0',
                     'config_version': '3.40.0', 'targets': ['exreader', 'exr_pdf'],
                     'probe': {'version': '3.40.0', 'abi': 1}},
        'config': {'cache_switches': dict(SWITCHES), 'preset_switches': dict(SWITCHES),
                   'layers': ['core', 'pdf']},
        'installed_files': records,
        'totals': {'files': len(records), 'bytes': sum(record['bytes'] for record in records)},
        'license_materials': {
            'checker': {'release_ready': True, 'materials_check_passed': True, 'failures': [],
                        'pending': [], 'mandatory_missing': [], 'source_sha': FIXTURE_SHA,
                        'components': len(inventory_components)},
            'components': inventory_components},
        'static_dependency': {
            'sdk_archives': ['lib/libexr_core.a', 'lib/libexr_pdf.a'],
            'archives': [{'path': path, 'name': path.split('/')[-1],
                          'bytes': by_path[path]['bytes'], 'sha256': by_path[path]['sha256']}
                         for path in ('lib/libexr_core.a', 'lib/libexr_pdf.a',
                                      'lib/exreader/libexr_vendor_miniz.a',
                                      'lib/exreader/libexr_vendor_expat.a')],
            'edges': [], 'unreferenced_archives': [], 'owners': {},
            'foreign_archives': [{'path': 'lib/libminiz.a', 'name': 'libminiz.a',
                                  'bytes': by_path['lib/libminiz.a']['bytes'],
                                  'sha256': by_path['lib/libminiz.a']['sha256']}]},
        'link': {'record': link_record, 'distributed_archives': distributed,
                 'system_libraries': system},
        'dynamic_dependencies': {'record': None, 'resolution': None, 'entries': []},
        'dependency_commands': [link_record],
        'observations': {}, 'private_paths': {'hits': []}, 'release_blockers': [],
        'checks': [], 'problems': [], 'materials_complete': True, 'release_ready': False,
        'run': {'id': '40000000000', 'attempt': '1', 'job': 'fixture'},
        'not_covered': []}
    licenses = {'schema': 1, 'scope': registered.SCOPE, 'release_ready': True,
                'materials_check_passed': True, 'failures': [], 'pending': [],
                'mandatory_missing': [], 'source_sha': FIXTURE_SHA,
                'components': [{'id': component['id'], 'name': component['name'],
                                'version': component['version'],
                                'license': component['license'],
                                'source': component['source'],
                                'archive_sha256': component.get('archive_sha256'),
                                'when': component.get('when'), 'active': True,
                                'files': component['files']}
                               for component in components]}
    documents = {'inventory': inventory, 'licenses': licenses,
                 'spdx': sbom.build_spdx(inventory, '2026-01-01T00:00:00Z'),
                 'cdx': sbom.build_cyclonedx(inventory, '2026-01-01T00:00:00Z'),
                 'inventory_name': 'inventory.json'}
    return {'documents': documents, 'payload': payload, 'components': components,
            'switches': dict(SWITCHES)}


def verify(state):
    return closure.verify(state['documents'], state['payload'], kind='sdk', platform='linux',
                          components=state['components'], package_table=[],
                          switches=state['switches'], source_sha=FIXTURE_SHA,
                          verifier={'source_sha': 'fixture'})


# ---------------------------------------------------------------- single mutations

def mutation_licence_missing(state):
    del state['payload']['stage/share/exreader/licenses/miniz/LICENSE']


def mutation_licence_drift(state):
    state['payload']['stage/share/exreader/licenses/expat/COPYING'] = b'altered expat text\n'


def mutation_licence_unregistered(state):
    state['payload']['stage/share/exreader/licenses/unknown/LICENSE'] = b'unregistered text\n'


def mutation_licence_checker(state):
    state['documents']['licenses']['release_ready'] = False
    state['documents']['licenses']['failures'] = ['fixture failure']


def mutation_licence_source(state):
    state['documents']['licenses']['source_sha'] = '0' * 40


def mutation_stage_file_unrecorded(state):
    state['payload']['stage/lib/libmystery.a'] = b'!<arch>\nmystery\n'


def mutation_stage_identity(state):
    state['payload']['stage/lib/libexr_pdf.a'] = b'!<arch>\ntampered pdf\n'


def mutation_archive_ambiguous(state):
    extra = copy.deepcopy(state['components'][1])
    extra['id'] = 'zlib'
    extra['vendor_files'] = ['miniz']
    state['components'].append(extra)


def mutation_archive_undeclared(state):
    state['documents']['inventory']['static_dependency']['foreign_archives'] = []


def mutation_link_record_missing(state):
    state['documents']['inventory']['link'] = {}


def mutation_link_output(state):
    state['payload']['tools/01-link.txt'] = LINK_COMMAND.replace('-lz', '-lm').encode('utf-8')


def mutation_link_drift(state):
    state['documents']['inventory']['link']['system_libraries'] = ['-lz', '-lm']


def mutation_link_family_overlap(state):
    state['documents']['inventory']['link']['system_libraries'] = ['-lminiz']


def mutation_link_bundled_as_system(state):
    state['documents']['inventory']['link']['system_libraries'] = ['lib/libexr_pdf.a']


def mutation_spdx_file_missing(state):
    document = state['documents']['spdx']
    document['files'] = [element for element in document['files']
                         if element['fileName'] != './lib/libexr_pdf.a']
    sdk = next(element for element in document['packages']
               if element['SPDXID'] == 'SPDXRef-Package-EXReader')
    sdk['hasFiles'] = [identity for identity in sdk['hasFiles']
                       if identity in {element['SPDXID'] for element in document['files']}]


def mutation_spdx_file_checksum(state):
    element = next(item for item in state['documents']['spdx']['files']
                   if item['fileName'] == './lib/libminiz.a')
    for checksum in element['checksums']:
        if checksum['algorithm'] == 'SHA1':
            checksum['checksumValue'] = '0' * 40


def mutation_spdx_verification_code(state):
    sdk = next(element for element in state['documents']['spdx']['packages']
               if element['SPDXID'] == 'SPDXRef-Package-EXReader')
    sdk['packageVerificationCode']['packageVerificationCodeValue'] = '0' * 40


def mutation_spdx_has_files(state):
    sdk = next(element for element in state['documents']['spdx']['packages']
               if element['SPDXID'] == 'SPDXRef-Package-EXReader')
    sdk['hasFiles'] = sdk['hasFiles'][:-1]


def mutation_spdx_document(state):
    state['documents']['spdx']['documentNamespace'] = 'https://example.invalid/spdx/unknown'


def mutation_spdx_component_missing(state):
    document = state['documents']['spdx']
    document['packages'] = [element for element in document['packages']
                            if element['SPDXID'] != 'SPDXRef-Package-miniz']


def mutation_spdx_licence_concluded(state):
    element = next(item for item in state['documents']['spdx']['packages']
                   if item['SPDXID'] == 'SPDXRef-Package-expat')
    element['licenseConcluded'] = 'Apache-2.0'


def mutation_spdx_licence_declared(state):
    element = next(item for item in state['documents']['spdx']['packages']
                   if item['SPDXID'] == 'SPDXRef-Package-expat')
    element['licenseDeclared'] = 'Apache-2.0'


def mutation_spdx_files_analyzed(state):
    element = next(item for item in state['documents']['spdx']['packages']
                   if item['SPDXID'] == 'SPDXRef-Package-miniz')
    element['filesAnalyzed'] = True


def mutation_spdx_source_reference(state):
    element = next(item for item in state['documents']['spdx']['packages']
                   if item['SPDXID'] == 'SPDXRef-Package-miniz')
    element.pop('sourceInfo', None)
    element['downloadLocation'] = 'NOASSERTION'


def mutation_spdx_licence_link(state):
    document = state['documents']['spdx']
    document['relationships'] = [row for row in document['relationships']
                                 if not (row['relationshipType'] == 'CONTAINS'
                                         and row['spdxElementId'] == 'SPDXRef-Package-miniz')]


def mutation_cdx_component_missing(state):
    document = state['documents']['cdx']
    document['components'] = [element for element in document['components']
                              if not any(item.get('value') == 'miniz'
                                         for item in element.get('properties') or [])]


def mutation_cdx_licence_missing(state):
    element = next(item for item in state['documents']['cdx']['components']
                   if any(property_item.get('value') == 'expat'
                          for property_item in item.get('properties') or []))
    element.pop('licenses', None)


def mutation_cdx_licence_expression(state):
    element = next(item for item in state['documents']['cdx']['components']
                   if any(property_item.get('value') == 'expat'
                          for property_item in item.get('properties') or []))
    element['licenses'] = [{'expression': 'Apache-2.0'}]


def mutation_cdx_file_checksum(state):
    element = next(item for item in state['documents']['cdx']['components']
                   if item.get('name') == './lib/libminiz.a')
    element['hashes'] = [{'alg': 'SHA-256', 'content': '0' * 64}]


def mutation_cdx_purl(state):
    element = next(item for item in state['documents']['cdx']['components']
                   if any(property_item.get('value') == 'expat'
                          for property_item in item.get('properties') or []))
    element['purl'] = 'not-a-purl'


def mutation_cdx_document(state):
    state['documents']['cdx']['specVersion'] = '1.4'


def mutation_claim_legal(state):
    state['documents']['licenses']['legal_conclusion'] = True


def mutation_claim_runtime(state):
    state['documents']['inventory']['runtime_accepted'] = True


CASES = [
    ('licence_missing', mutation_licence_missing, {'licence_material_missing'}),
    ('licence_drift', mutation_licence_drift, {'licence_material_drift'}),
    ('licence_unregistered', mutation_licence_unregistered, {'licence_material_unregistered'}),
    ('licence_checker_not_ready', mutation_licence_checker, {'licence_checker_not_ready'}),
    ('licence_checker_source', mutation_licence_source, {'licence_checker_source'}),
    ('stage_file_unrecorded', mutation_stage_file_unrecorded,
     {'stage_file_unrecorded', 'archive_unowned'}),
    ('stage_file_tampered', mutation_stage_identity, {'stage_file_identity'}),
    ('archive_ambiguous_owner', mutation_archive_ambiguous, {'archive_ambiguous_owner'}),
    ('archive_undeclared', mutation_archive_undeclared, {'archive_undeclared'}),
    ('link_record_missing', mutation_link_record_missing, {'link_record_missing'}),
    ('link_output_tampered', mutation_link_output, {'link_output_digest'}),
    ('link_classification_drift', mutation_link_drift, {'link_classification_drift'}),
    ('link_family_overlap', mutation_link_family_overlap, {'link_family_overlap'}),
    ('link_bundled_as_system', mutation_link_bundled_as_system, {'link_bundled_as_system'}),
    ('spdx_file_missing', mutation_spdx_file_missing, {'spdx_file_missing'}),
    ('spdx_file_checksum', mutation_spdx_file_checksum, {'spdx_file_checksum'}),
    ('spdx_verification_code', mutation_spdx_verification_code, {'spdx_verification_code'}),
    ('spdx_has_files', mutation_spdx_has_files, {'spdx_has_files'}),
    ('spdx_document', mutation_spdx_document, {'spdx_document'}),
    ('spdx_component_missing', mutation_spdx_component_missing, {'spdx_component_missing'}),
    ('spdx_licence_concluded', mutation_spdx_licence_concluded, {'spdx_licence_concluded'}),
    ('spdx_licence_declared', mutation_spdx_licence_declared, {'spdx_licence_declared'}),
    ('spdx_files_analyzed', mutation_spdx_files_analyzed, {'spdx_files_analyzed'}),
    ('spdx_source_reference', mutation_spdx_source_reference, {'spdx_source_reference'}),
    ('spdx_licence_link', mutation_spdx_licence_link, {'spdx_licence_link'}),
    ('cdx_component_missing', mutation_cdx_component_missing, {'cdx_component_missing'}),
    ('cdx_licence_missing', mutation_cdx_licence_missing, {'cdx_licence_missing'}),
    ('cdx_licence_expression', mutation_cdx_licence_expression, {'cdx_licence_expression'}),
    ('cdx_file_checksum', mutation_cdx_file_checksum, {'cdx_file_checksum'}),
    ('cdx_purl', mutation_cdx_purl, {'cdx_purl'}),
    ('cdx_document', mutation_cdx_document, {'cdx_document'}),
    ('claim_legal', mutation_claim_legal, {'claim_legal'}),
    ('claim_runtime', mutation_claim_runtime, {'claim_runtime'}),
]


def artifact_identity_cases():
    """The artifact gates this package relies on must reject a forged identity."""
    run = {'id': 40095313750, 'run_attempt': 1, 'head_sha': 'a' * 40,
           'repository': {'id': 1, 'full_name': 'NoGod3524/EXReader'},
           'head_repository': {'id': 1}}
    good = {'id': 12560228214, 'name': 'fixture', 'size_in_bytes': 16, 'expired': False,
            'expires_at': '2027-01-22T12:46:21Z', 'digest': 'sha256:' + 'b' * 64,
            'workflow_run': {'id': 40095313750, 'head_sha': 'a' * 40,
                             'repository_id': 1, 'head_repository_id': 1}}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cases = []
    contract.artifact_identity(good, run, now)
    cases.append(('artifact_identity_authentic', True, 'accepted'))

    def expired(artifact):
        artifact['expired'] = True

    def past(artifact):
        artifact['expires_at'] = '2020-01-01T00:00:00Z'

    def digest(artifact):
        artifact['digest'] = 'sha256:nothex'

    def origin(artifact):
        artifact['workflow_run']['head_sha'] = 'c' * 40

    for name, mutate in (('artifact_expired', expired), ('artifact_expiry', past),
                         ('artifact_digest', digest), ('artifact_origin', origin)):
        artifact = copy.deepcopy(good)
        mutate(artifact)
        try:
            contract.artifact_identity(artifact, run, now)
        except contract.InventoryError as error:
            cases.append((name, True, error.code))
        else:
            cases.append((name, False, 'accepted a forged identity'))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir', default='build/final-s09/fixtures')
    args = parser.parse_args()
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    state = build()
    for name, data in state['payload'].items():
        target = workdir / 'fixture-artifact' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for name in ('inventory', 'spdx', 'cdx', 'licenses'):
        target = workdir / 'fixture-artifact' / ('%s.json' % name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(state['documents'][name], indent=2, ensure_ascii=False),
                          encoding='utf-8')

    result = verify(state)
    failures = 0
    print('positive control: accepted=%r problems=%r checks=%d'
          % (result['accepted'], [problem['code'] for problem in result['problems']],
             len(result['checks'])))
    if not result['accepted']:
        failures += 1
        print('POSITIVE CONTROL FAILED')
        for problem in result['problems']:
            print('  %s: %s' % (problem['code'], problem['detail']))
    for check in result['checks']:
        print('  check %-34s %-8s %s' % (check['id'], check['status'], check['detail']))

    for name, mutate, expected in CASES:
        mutated = copy.deepcopy(state)
        mutate(mutated)
        outcome = verify(mutated)
        codes = {problem['code'] for problem in outcome['problems']}
        missing = sorted(expected - codes)
        status = 'ok' if not missing and not outcome['accepted'] else 'MISSING'
        if status != 'ok':
            failures += 1
        print('%-30s %-7s accepted=%-5r codes=%s'
              % (name, status, outcome['accepted'], ','.join(sorted(codes))))
        if missing:
            print('   not rejected by %r' % missing)

    for name, ok, detail in artifact_identity_cases():
        if not ok:
            failures += 1
        print('%-30s %-7s %s' % (name, 'ok' if ok else 'MISSING', detail))

    summary = {'fixture': 'generated-in-job', 'positive_control': result['accepted'],
               'rejections': len(CASES) + 4, 'failures': failures, 'workdir': str(workdir),
               'accepted': failures == 0}
    (workdir / 'protocol.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
