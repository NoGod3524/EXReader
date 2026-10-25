#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Distribution licence and SBOM closure for one final candidate install.

This module builds nothing, installs nothing and downloads nothing. It takes the
bytes of an installed candidate (a real stage produced by the reading presets, or
an authenticated distribution-inventory artifact), the inventory document that was
generated beside those bytes, the SPDX and CycloneDX documents, and the registered
licence record. For every installed archive it derives the owning component from
the registry; for every licence original it re-derives the pinned digest; for every
SBOM element it requires the element to be anchored to those bytes and to a
registered source. The producer's own claims are re-derived, never trusted.

Two grants are deliberately never reported: a runtime conclusion (nothing here
executes the shipped binaries) and a legal conclusion (identifiers are inventoried,
not adjudicated).
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INVENTORY_TOOLS = ROOT / 'tests' / 'reader_distribution_inventory'
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(INVENTORY_TOOLS))
import check_reading_licenses as registered
import contract
import packages
import sbom

SCOPE = ('Closure over one installed candidate: every distributed archive, licence original and '
         'SBOM element anchored to a registered component, a pinned source and the real link line. '
         'Materials closure only: no runtime behaviour and no legal conclusion is granted.')
NOT_GRANTED = [
    'Runtime behaviour of the shipped binaries: this closure reads installed bytes and recorded '
    'link lines, it never executes the candidate',
    'Legal conclusion: licence identifiers are inventoried from the registered manifest and the '
    'installed originals, they are not adjudicated',
    'Product, Release, signing, notarization, store publication and tag grants',
    'Android, iOS and Apple host packaging, host bundles and their fonts: separate owners',
    'Optional package behaviour (sync, accounts, import, interface): only installed material is closed',
]

NOTICE_PATHS = ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'share/exreader/LICENSE',
                'share/exreader/THIRD_PARTY_NOTICES.md')
ARCHIVE_PATH = re.compile(r'^lib/(?:exreader/)?[^/]+[.](?:a|lib)$')
COMPONENT_ARCHIVE = re.compile(r'^lib/(?:exreader/[^/]+|(?:lib)?exr_[^/]+)[.](?:a|lib)$')
LIBRARY_TOKEN = re.compile(r'[.](?:a|lib|so|dylib|tbd)(?:[.][0-9]+)*$', re.I)
INVENTORY_NAMES = ('inventory.json', 'combined.json')
SBOM_NAMES = {'spdx': ('inventory.spdx.json', 'combined.spdx.json'),
              'cdx': ('inventory.cdx.json', 'combined.cdx.json')}
CLAIM_KEYS = ('runtime_accepted', 'runtime_ready', 'legal_conclusion', 'legal_advice',
              'product_granted', 'release_granted')


class ClosureError(Exception):
    """A closure input is unusable; the code names the rejected property."""

    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


class Report:
    """Collected problems (stable codes) and checks (pass, fail or reported)."""

    def __init__(self):
        self.problems = []
        self.checks = []

    def add(self, code, detail=''):
        entry = {'code': code, 'detail': detail}
        if entry not in self.problems:
            self.problems.append(entry)

    def item(self, identity, ok, detail='', status=None):
        self.checks.append({'id': identity, 'status': status or ('pass' if ok else 'fail'),
                            'detail': detail})

    def codes(self, prefix=None):
        values = sorted({problem['code'] for problem in self.problems})
        if prefix is None:
            return values
        if isinstance(prefix, str):
            prefix = (prefix,)
        return [code for code in values if code.startswith(tuple(prefix))]


def flags(problems):
    """The four closure verdicts, each from its own problem family."""
    codes = [problem['code'] for problem in problems]
    return {'materials_closed': not [code for code in codes if code.startswith('stage_')],
            'licence_closed': not [code for code in codes if code.startswith('licence_')],
            'link_closed': not [code for code in codes if code.startswith('link_')],
            'sbom_closed': not [code for code in codes if code.startswith(('spdx_', 'cdx_'))],
            'accepted': not codes}


# ---------------------------------------------------------------- installed material

def archive_identity(base):
    """Reduce an installed archive file name to the identity the registry uses."""
    name = re.sub(r'[.](?:a|lib)$', '', base, flags=re.I)
    if name.startswith('lib'):
        name = name[3:]
    if name.startswith('exr_vendor_'):
        return 'vendor', name[len('exr_vendor_'):]
    if name.startswith('exr_'):
        return 'sdk', name[len('exr_'):]
    return 'other', name


def registry_index(components):
    """Vendor file identity -> owning component ids, from the registered manifest."""
    index = {}
    for component in components:
        for name in component.get('vendor_files') or []:
            index.setdefault(name, set()).add(component['id'])
    return index


def package_index(package_table):
    """Archive basename -> optional package id, from the registered package table."""
    index = {}
    for package in package_table or []:
        for name in package.get('archives') or []:
            for extension in ('.a', '.lib'):
                for candidate in (name + extension, 'lib' + name + extension):
                    index.setdefault(candidate, set()).add(package['id'])
    return index


def resolve_owner(path, index, package_map):
    """Candidate owners of one installed archive, from its own file name."""
    base = path.split('/')[-1]
    if package_map and base in package_map:
        return sorted(package_map[base])
    kind, identity = archive_identity(base)
    if kind == 'sdk':
        return ['exreader']
    candidates = set(index.get(identity) or ())
    if not candidates:
        candidates = set(index.get(packages.canonical(identity)) or ())
    if not candidates:
        # An upstream-named copy of a registered library (libwebpmux.a beside the
        # registered webp family) belongs to the component that ships that library.
        for name, owners_of_name in index.items():
            if identity.startswith(name):
                candidates |= set(owners_of_name)
    return sorted(candidates)


def scan_payload(stage):
    """Every installed file, read from the stage bytes themselves."""
    payload, problems = {}, []
    for path in sorted(stage.rglob('*')):
        relative = path.relative_to(stage).as_posix()
        if path.is_symlink():
            problems.append(relative)
            continue
        if not path.is_file():
            continue
        payload['stage/' + relative] = path.read_bytes()
    return payload, problems


def derived_files(payload):
    records = []
    for name in sorted(payload):
        if not name.startswith('stage/'):
            continue
        data = payload[name]
        records.append({'path': name[len('stage/'):], 'bytes': len(data),
                        'sha256': contract.digest(data), 'sha1': contract.digest1(data)})
    return records


def verify_stage(records, inventory_files, report):
    """The inventory must describe exactly the bytes that are installed."""
    stage = {record['path']: record for record in records}
    listed = {record.get('path'): record for record in inventory_files or []}
    for path in sorted(set(listed) - set(stage)):
        report.add('stage_file_missing', path)
    for path in sorted(set(stage) - set(listed)):
        report.add('stage_file_unrecorded', path)
    for path in sorted(set(stage) & set(listed)):
        claimed, observed = listed[path], stage[path]
        for field in ('bytes', 'sha256', 'sha1'):
            if field in claimed and claimed[field] != observed[field]:
                report.add('stage_file_identity', '%s %s' % (path, field))
    for path, record in sorted(stage.items()):
        if not record['bytes']:
            report.add('stage_empty_file', path)
    report.item('stage.files', not report.codes('stage_'), '%d files, %d bytes'
                % (len(stage), sum(record['bytes'] for record in records)))


# ---------------------------------------------------------------- licence materials

def enabled_switches(switches, expression):
    return registered.enabled(expression, switches or {})


def licence_closure(records, payload, components, switches, report):
    """Every registered licence original installed unchanged; nothing unregistered."""
    expected = contract.expected_license_paths(components,
                                               lambda when: enabled_switches(switches, when))
    problems = contract.verify_license_materials(records, payload, expected, components)
    for problem in problems:
        if problem.startswith(('missing installed license', 'registered license not installed',
                               'registered licence material not installed')):
            report.add('licence_material_missing', problem)
        elif problem.startswith('installed license differs from its registered pin'):
            report.add('licence_material_drift', problem)
        elif problem.startswith('installed license identity mismatch'):
            report.add('licence_material_identity', problem)
        elif problem.startswith('unregistered installed license material'):
            report.add('licence_material_unregistered', problem)
        elif problem.startswith('registered license has no pinned hash'):
            report.add('licence_pin_missing', problem)
        elif problem.startswith('empty installed license'):
            report.add('licence_material_empty', problem)
        elif problem.startswith('registered component has no installed notice'):
            report.add('licence_notice_missing', problem)
        else:
            report.add('licence_material_other', problem)
    present = {record['path'] for record in records}
    materials = {}
    for path, entry in expected.items():
        if path in present:
            materials.setdefault(entry['component'], []).append(path)
    report.item('licence.registered_materials', not problems,
                '%d registered materials installed of %d expected'
                % (sum(len(paths) for paths in materials.values()), len(expected)))
    return expected, materials


def package_licences(package_table, payload):
    """Read back each optional package's own or shared licence material."""
    index = {name[len('stage/'):]: data for name, data in payload.items()
             if name.startswith('stage/')}
    result = {}
    for package in package_table or []:
        resolved = packages.resolve(package, index)
        result[package['id']] = {'mode': package['licence'][0],
                                 'path': (resolved['licence'] or {}).get('path'),
                                 'sha256': (resolved['licence'] or {}).get('sha256'),
                                 'missing': list(resolved['missing']),
                                 'archives': resolved['archives'],
                                 'source': package['source'],
                                 'system': package['system']}
    return result


# ---------------------------------------------------------------- real link lines

def link_tokens(payload, record):
    """Re-parse a recorded link command from its own captured output."""
    if not isinstance(record, dict) or not record.get('raw_output_path'):
        raise ClosureError('link_record_missing')
    path = record['raw_output_path']
    if path not in payload:
        raise ClosureError('link_output_missing')
    try:
        text = payload[path].decode('utf-8')
    except UnicodeDecodeError:
        raise ClosureError('link_output_encoding') from None
    try:
        contract.verify_dependency(record, text)
    except contract.InventoryError:
        raise ClosureError('link_output_digest') from None
    return [entry['name'] for entry in contract.parse_entries('ninja-link', text)]


def system_family(token):
    """Canonical library identity of one system token, or None for a linker flag."""
    if token == '-framework':
        return None
    if token.startswith('-l') and len(token) > 2 and not token.startswith(('-libpath', '-link')):
        return packages.canonical(token[2:])
    parts = token.split(',')[1:] if token.startswith('-Wl,') else [token]
    found = None
    for part in parts:
        base = part.replace('\\', '/').split('/')[-1]
        if LIBRARY_TOKEN.search(base):
            found = packages.library_name(base)
    return found


def link_partition(tokens, archive_names):
    """Partition one real link line by installed bytes: bundled archives versus system."""
    distributed, system, other = [], [], []
    for token in tokens:
        base = re.split(r'[\\/]', token)[-1]
        if base in archive_names:
            distributed.append(base)
        elif token.startswith(('-l', '-Wl,', '-framework')) or base.lower().endswith('.lib'):
            system.append(token)
        else:
            other.append(token)
    return sorted(set(distributed)), sorted(set(system)), other


def verify_link(payload, inventory, records, kind, package_table, report):
    """Distinguish bundled archives from system libraries on every real link line."""
    archive_names = {record['path'].split('/')[-1] for record in records
                     if ARCHIVE_PATH.match(record['path'])}
    archive_families = {packages.library_name(name) for name in archive_names}
    # Archives this profile distributes as components: the SDK layers and the vendor
    # copies under lib/exreader/. Upstream-name copies at the top level are their own
    # class: they are reported as duplicate library names, not as component archives.
    component_archives = {record['path'] for record in records
                          if COMPONENT_ARCHIVE.match(record['path'])}
    partition_names = {path.split('/')[-1] for path in component_archives}
    static = inventory.get('static_dependency') or {}
    declared_unlinked = set(static.get('unreferenced_archives') or []) | \
        {entry.get('path') for entry in static.get('foreign_archives') or []}
    before = len(report.problems)
    lines = []
    linked = set()
    if kind == 'sdk':
        link = inventory.get('link') or {}
        if not link.get('record'):
            report.add('link_record_missing', 'the inventory records no consumer link line')
            report.item('link.bundled_vs_system', False, 'no recorded link line')
            return []
        try:
            tokens = link_tokens(payload, link['record'])
        except ClosureError as error:
            report.add(error.code, '')
            report.item('link.bundled_vs_system', False, error.code)
            return []
        distributed, system, other = link_partition(tokens, partition_names)
        if distributed != sorted(link.get('distributed_archives') or []):
            report.add('link_classification_drift',
                       'bundled: recorded %r derived %r'
                       % (sorted(link.get('distributed_archives') or []), distributed))
        if system != sorted(link.get('system_libraries') or []):
            report.add('link_classification_drift',
                       'system: recorded %r derived %r'
                       % (sorted(link.get('system_libraries') or []), system))
        linked |= set(distributed)
        lines.append({'kind': 'sdk', 'record': link['record'], 'token_count': len(tokens),
                      'bundled': distributed, 'system': system, 'other_count': len(other),
                      'source': link['record']['raw_output_path']})
    else:
        for section in inventory.get('packages') or []:
            identifier = section.get('id')
            own = sorted(entry['name'] for entry in section.get('archives') or [])
            if not section.get('link'):
                report.add('link_record_missing', str(identifier))
                continue
            try:
                tokens = link_tokens(payload, section['link'])
            except ClosureError as error:
                report.add(error.code, str(identifier))
                continue
            try:
                expected = list(packages.by_id(identifier)['system'].get(
                    inventory.get('platform'), []))
            except KeyError:
                expected = []
            evidence = packages.link_evidence(tokens, archive_names, expected)
            recorded = section.get('link_evidence') or {}
            if evidence != recorded:
                report.add('link_classification_drift', str(identifier))
            for name in sorted(set(own) - set(evidence['archives'])):
                report.add('link_bundled_not_linked', '%s %s' % (identifier, name))
            for name in evidence['expected_missing']:
                report.add('link_system_unmet', '%s %s' % (identifier, name))
            linked |= set(evidence['archives'])
            lines.append({'kind': 'package', 'id': identifier, 'record': section['link'],
                          'token_count': len(tokens), 'bundled': evidence['archives'],
                          'system': evidence['system_libraries'],
                          'frameworks': evidence['frameworks'],
                          'source': section['link']['raw_output_path']})
    if kind == 'sdk':
        # Every archive this profile ships must be on the real consumer link line, or be
        # declared as an unreferenced or upstream-name copy. Nothing ships unaccounted.
        for path in sorted(component_archives):
            if path.split('/')[-1] not in linked and path not in declared_unlinked:
                report.add('link_bundled_not_linked', path)
    for line in lines:
        for token in line['system']:
            base = re.split(r'[\\/]', token)[-1]
            if base in archive_names:
                report.add('link_bundled_as_system', '%s: %s' % (line['source'], token))
                continue
            family = system_family(token)
            if family is None:
                # A bare linker flag (-framework, -Wl,-rpath,...), not a library reference.
                continue
            if family in archive_families:
                report.add('link_family_overlap', '%s: %s' % (family, token))
    report.item('link.bundled_vs_system', len(report.problems) == before,
                '%d link lines, %d bundled archives, %d system libraries'
                % (len(lines), len(linked), sum(len(line['system']) for line in lines)))
    return lines


# ---------------------------------------------------------------- SPDX fields and sources

def spdx_file_map(document):
    files = {}
    for element in document.get('files') or []:
        name = element.get('fileName') or ''
        files[name[2:] if name.startswith('./') else name] = element
    return files


def spdx_packages(document):
    return {element.get('SPDXID'): element for element in document.get('packages') or []}


def check_spdx(document, inventory, records, components_by_id, materials, owners,
               package_licences_map, active_ids, report, source_sha):
    """SPDX fields, file anchors, licence linkage and per-component source references."""
    before = len(report.problems)
    if document.get('spdxVersion') != 'SPDX-2.3':
        report.add('spdx_document', 'spdxVersion')
    if document.get('dataLicense') != 'CC0-1.0' or document.get('SPDXID') != 'SPDXRef-DOCUMENT':
        report.add('spdx_document', 'document identity')
    namespace = document.get('documentNamespace')
    if not isinstance(namespace, str) or not namespace.startswith('https://') or \
            (source_sha and source_sha not in namespace):
        report.add('spdx_document', 'documentNamespace does not name the source')
    creation = document.get('creationInfo') or {}
    if not isinstance(creation.get('created'), str) or not creation.get('creators'):
        report.add('spdx_document', 'creationInfo')
    files = spdx_file_map(document)
    stage = {record['path']: record for record in records}
    for path in sorted(set(stage) - set(files)):
        report.add('spdx_file_missing', path)
    for path in sorted(set(files) - set(stage)):
        report.add('spdx_file_extra', path)
    for path in sorted(set(stage) & set(files)):
        checksums = {item.get('algorithm'): item.get('checksumValue')
                     for item in files[path].get('checksums') or []}
        if checksums.get('SHA256') != stage[path]['sha256']:
            report.add('spdx_file_checksum', '%s SHA256' % path)
        if checksums.get('SHA1') != stage[path]['sha1']:
            report.add('spdx_file_checksum', '%s SHA1' % path)
    identifiers = {}
    for element in (document.get('packages') or []) + (document.get('files') or []):
        identity = element.get('SPDXID')
        if not isinstance(identity, str) or not re.fullmatch(r'SPDXRef-[A-Za-z0-9.-]+', identity):
            report.add('spdx_identifier', str(identity))
            continue
        if identity in identifiers:
            report.add('spdx_duplicate_id', identity)
        identifiers[identity] = element
    packages_by_id = spdx_packages(document)
    sdk = packages_by_id.get('SPDXRef-Package-EXReader')
    if sdk is None:
        report.add('spdx_sdk_package', 'missing')
    else:
        code = (sdk.get('packageVerificationCode') or {}).get('packageVerificationCodeValue')
        if code != contract.spdx_verification_code([record['sha1'] for record in records]):
            report.add('spdx_verification_code', repr(code))
        if sdk.get('versionInfo') != (inventory.get('identity') or {}).get('version'):
            report.add('spdx_version_info', repr(sdk.get('versionInfo')))
        element_ids = {element.get('SPDXID') for element in (document.get('files') or [])}
        if set(sdk.get('hasFiles') or []) != element_ids:
            report.add('spdx_has_files', 'hasFiles does not cover every file element')
        if sdk.get('licenseConcluded') != sbom.LICENSES['exreader'][0]:
            report.add('spdx_licence_concluded', 'SDK package: %r' % sdk.get('licenseConcluded'))
        for path in NOTICE_PATHS:
            if path in files and files[path].get('SPDXID') not in (sdk.get('hasFiles') or []):
                report.add('spdx_licence_link',
                           'SDK notice element %s is not part of the SDK package' % path)
    for identifier in owners:
        if identifier == 'exreader':
            # The first-party SDK is described by the SDK package itself.
            continue
        reference = sbom.spdx_ref('Package', identifier)
        package = packages_by_id.get(reference)
        if package is None:
            report.add('spdx_component_missing', identifier)
            continue
        if identifier in sbom.LICENSES:
            concluded, declared = sbom.LICENSES[identifier]
            if package.get('licenseConcluded') != concluded:
                report.add('spdx_licence_concluded',
                           '%s: %r' % (identifier, package.get('licenseConcluded')))
            if package.get('licenseDeclared') != declared:
                report.add('spdx_licence_declared',
                           '%s: %r' % (identifier, package.get('licenseDeclared')))
        if package.get('filesAnalyzed') is not False:
            report.add('spdx_files_analyzed', identifier)
        download = str(package.get('downloadLocation') or '')
        info = str(package.get('sourceInfo') or '')
        comment = str(package.get('comment') or '')
        pin = (components_by_id.get(identifier) or {}).get('archive_sha256')
        material_link = any(path in files for path in (materials.get(identifier) or []))
        if pin:
            if pin not in info:
                report.add('spdx_source_reference',
                           '%s: pinned archive hash missing from sourceInfo' % identifier)
        elif identifier != 'exreader':
            if not (download.startswith('http') or comment or material_link):
                report.add('spdx_source_reference', identifier)
    described = {identity for identity in packages_by_id
                 if identity != 'SPDXRef-Package-EXReader'}
    known = {sbom.spdx_ref('Package', identifier) for identifier in active_ids} | \
            {sbom.spdx_ref('Package', identifier) for identifier in owners}
    for reference in sorted(described - known):
        report.add('spdx_component_extra', reference)
    relationships = document.get('relationships') or []
    contains = set()
    for relationship in relationships:
        for field in ('spdxElementId', 'relatedSpdxElement'):
            value = relationship.get(field)
            if field == 'spdxElementId' and value == 'SPDXRef-DOCUMENT':
                continue
            if value not in identifiers:
                report.add('spdx_relationship_target', str(value))
        if relationship.get('relationshipType') == 'CONTAINS':
            contains.add((relationship.get('spdxElementId'), relationship.get('relatedSpdxElement')))
    if not any(relationship.get('relationshipType') == 'DESCRIBES'
               and relationship.get('relatedSpdxElement') == 'SPDXRef-Package-EXReader'
               for relationship in relationships):
        report.add('spdx_describes', 'the document does not describe the SDK package')
    for identifier, paths in sorted((materials or {}).items()):
        if identifier == 'exreader':
            continue
        reference = sbom.spdx_ref('Package', identifier)
        for path in paths:
            if path in files and (reference, files[path].get('SPDXID')) not in contains:
                report.add('spdx_licence_link', '%s is not connected to %s' % (path, identifier))
    for identifier, row in sorted(package_licences_map.items()):
        if row.get('mode') != 'package' or not row.get('path'):
            continue
        reference = sbom.spdx_ref('Package', identifier)
        if row['path'] in files and (reference, files[row['path']].get('SPDXID')) not in contains:
            report.add('spdx_licence_link',
                       '%s is not connected to %s' % (row['path'], identifier))
    report.item('spdx.fields', len(report.problems) == before,
                '%d packages, %d files, %d relationships'
                % (len(packages_by_id), len(files), len(relationships)))
    return {'packages': len(packages_by_id), 'files': len(files),
            'relationships': len(relationships), 'source_referenced': len(owners)}


# ---------------------------------------------------------------- CycloneDX fields

def check_cyclonedx(document, inventory, records, owners, report):
    before = len(report.problems)
    if document.get('bomFormat') != 'CycloneDX' or document.get('specVersion') != '1.5':
        report.add('cdx_document', 'bomFormat or specVersion')
    serial = document.get('serialNumber')
    if not isinstance(serial, str) or not re.fullmatch(r'urn:uuid:[0-9a-f-]{36}', serial):
        report.add('cdx_document', 'serialNumber')
    metadata = document.get('metadata') or {}
    if not isinstance(metadata.get('timestamp'), str) or not metadata['timestamp'].endswith('Z'):
        report.add('cdx_document', 'timestamp')
    sdk = metadata.get('component') or {}
    if sdk.get('version') != (inventory.get('identity') or {}).get('version'):
        report.add('cdx_document', 'metadata component version')
    elements = {element.get('bom-ref'): element for element in document.get('components') or []}
    files = {reference: element for reference, element in elements.items()
             if element.get('type') == 'file'}
    by_name = {(element.get('name') or '')[2:]: element for element in files.values()}
    for record in records:
        element = by_name.get(record['path'])
        if element is None:
            report.add('cdx_file_missing', record['path'])
            continue
        hashes = {item.get('alg'): item.get('content') for item in element.get('hashes') or []}
        if hashes.get('SHA-256') != record['sha256']:
            report.add('cdx_file_checksum', record['path'])
    libraries = {}
    for element in elements.values():
        if element.get('type') != 'library':
            continue
        identifier = None
        for property_item in element.get('properties') or []:
            if property_item.get('name') == 'exreader:component_id':
                identifier = property_item.get('value')
        if identifier:
            libraries[identifier] = element
    for identifier in owners:
        if identifier == 'exreader':
            # The first-party SDK is the metadata component, not a library element.
            if not sdk.get('licenses'):
                report.add('cdx_licence_missing', identifier)
            continue
        element = libraries.get(identifier)
        if element is None:
            report.add('cdx_component_missing', identifier)
            continue
        if not element.get('licenses'):
            report.add('cdx_licence_missing', identifier)
        else:
            stated = element['licenses'][0].get('expression')
            if identifier in sbom.LICENSES and stated != sbom.LICENSES[identifier][1]:
                report.add('cdx_licence_expression', '%s: %r' % (identifier, stated))
        purl = element.get('purl')
        if not isinstance(purl, str) or not re.fullmatch(
                r'pkg:generic/[a-z0-9._+-]+@[A-Za-z0-9._+-]+', purl):
            report.add('cdx_purl', '%s: %r' % (identifier, purl))
    known = set(elements) | {'sdk'}
    for dependency in document.get('dependencies') or []:
        if dependency.get('ref') not in known:
            report.add('cdx_dependency_ref', str(dependency.get('ref')))
        for target in dependency.get('dependsOn') or []:
            if target not in elements:
                report.add('cdx_dependency_ref', str(target))
    report.item('cdx.fields', len(report.problems) == before,
                '%d components, %d file elements' % (len(elements), len(files)))
    return {'components': len(elements), 'files': len(files)}


# ---------------------------------------------------------------- claims

def claim_scan(documents):
    """No document may assert a runtime or legal conclusion for this closure."""
    hits = []
    for name in ('inventory', 'licenses'):
        document = documents.get(name) or {}
        for key in CLAIM_KEYS:
            if document.get(key) is True:
                hits.append({'document': name, 'key': key})
    cdx = documents.get('cdx') or {}
    properties = ((cdx.get('metadata') or {}).get('component') or {}).get('properties') or []
    for property_item in properties:
        name = property_item.get('name') or ''
        if name.startswith('exreader:') and name[len('exreader:'):] in CLAIM_KEYS and \
                str(property_item.get('value')).lower() == 'true':
            hits.append({'document': 'cdx', 'key': name})
    return hits


# ---------------------------------------------------------------- verification entry point

def verify(documents, payload, kind='sdk', platform='linux', components=None,
           package_table=None, switches=None, source_sha=None, verifier=None):
    """Re-derive the whole closure from bytes plus the registry. Returns the report."""
    components = list(registered.COMPONENTS if components is None else components)
    package_table = list(packages.PACKAGES if (package_table is None and kind == 'combined')
                         else (package_table or []))
    components_by_id = {component['id']: component for component in components}
    inventory = documents['inventory']
    report = Report()
    records = derived_files(payload)
    verify_stage(records, inventory.get('installed_files'), report)

    claims = claim_scan(documents)
    for claim in claims:
        report.add('claim_legal' if 'legal' in claim['key'] else 'claim_runtime',
                   '%s.%s' % (claim['document'], claim['key']))
    report.item('claim.no_conclusion', not claims, repr(claims))

    expected_paths, materials = licence_closure(records, payload, components, switches, report)
    active_ids = [component['id'] for component in components
                  if enabled_switches(switches, component.get('when'))]
    package_licences_map = package_licences(package_table, payload) if package_table else {}
    for identifier, licence in sorted(package_licences_map.items()):
        if licence['missing'] or not licence['path']:
            report.add('licence_package_material', identifier)
    report.item('licence.package_materials', not report.codes('licence_package'),
                '%d optional packages, modes %r'
                % (len(package_licences_map),
                   sorted({row['mode'] for row in package_licences_map.values()})))

    checker = (inventory.get('license_materials') or {}).get('checker') or {}
    licenses_document = documents.get('licenses') or {}
    ready = licenses_document.get('release_ready') is True and \
        not licenses_document.get('failures') and not licenses_document.get('pending') and \
        not licenses_document.get('mandatory_missing')
    if not ready:
        report.add('licence_checker_not_ready',
                   'release_ready=%r failures=%r pending=%r missing=%r'
                   % (licenses_document.get('release_ready'), licenses_document.get('failures'),
                      licenses_document.get('pending'),
                      licenses_document.get('mandatory_missing')))
    if source_sha and licenses_document.get('source_sha') != source_sha:
        report.add('licence_checker_source',
                   'licences %r expected %r' % (licenses_document.get('source_sha'), source_sha))
    if checker and source_sha and checker.get('source_sha') != source_sha:
        report.add('licence_checker_source', 'inventory checker %r' % checker.get('source_sha'))
    report.item('licence.checker', ready,
                'release_ready=%r' % licenses_document.get('release_ready'))

    index = registry_index(components)
    package_map = package_index(package_table)
    owners, unowned, ambiguous = {}, [], []
    archives = sorted(record['path'] for record in records if ARCHIVE_PATH.match(record['path']))
    for path in archives:
        candidates = resolve_owner(path, index, package_map)
        if not candidates:
            unowned.append(path)
        elif len(candidates) > 1:
            ambiguous.append({'path': path, 'owners': candidates})
        else:
            owners.setdefault(candidates[0], []).append(path)
    for path in unowned:
        report.add('archive_unowned', path)
    for row in ambiguous:
        report.add('archive_ambiguous_owner', '%s %r' % (row['path'], row['owners']))
    absent = []
    for component in components:
        wanted = set(component.get('vendor_files') or ())
        if not wanted or component['id'] not in active_ids:
            continue
        if not any(archive_identity(path.split('/')[-1])[1] in wanted
                   for paths in owners.values() for path in paths):
            absent.append(component['id'])
    report.item('archives.registered_vendor_files', not absent,
                'registered components without their own installed archive: %r' % absent,
                status='reported' if absent else None)
    groups = {}
    for path in archives:
        groups.setdefault(archive_identity(path.split('/')[-1])[1], []).append(path)
    duplicates = []
    for identity in sorted(groups):
        paths = sorted(groups[identity])
        if len(paths) < 2:
            continue
        entries = []
        for path in paths:
            record = next(item for item in records if item['path'] == path)
            entries.append({'path': path,
                            'owner': next((owner for owner, owned in owners.items()
                                           if path in owned), None),
                            'bytes': record['bytes'], 'sha256': record['sha256']})
        duplicates.append({'library': identity, 'copies': entries})
    static = inventory.get('static_dependency') or {}
    declared_archives = {entry.get('path') for entry in static.get('archives') or []} | \
        {entry.get('path') for entry in static.get('foreign_archives') or []}
    for path in archives:
        if path not in declared_archives:
            report.add('archive_undeclared', path)
    report.item('archives.owners', not unowned and not ambiguous,
                '%d archives, %d owners, %d duplicate library names'
                % (len(archives), len(owners), len(duplicates)))
    report.item('archives.duplicates_declared', True,
                '%d library names ship more than one archive: %r'
                % (len(duplicates), [group['library'] for group in duplicates]),
                status='reported')

    owner_ids = sorted(set(owners) | set(package_licences_map))
    lines = verify_link(payload, inventory, records, kind, package_table, report)
    spdx = check_spdx(documents['spdx'], inventory, records, components_by_id, materials,
                      owner_ids, package_licences_map, active_ids, report, source_sha)
    cdx = check_cyclonedx(documents['cdx'], inventory, records, owner_ids, report)

    verdict = flags(report.problems)
    result = {
        'schema': 1, 'scope': SCOPE, 'kind': kind, 'platform': platform,
        'sources': dict({'producer_sha': source_sha} if source_sha else {}),
        'verifier': verifier or {},
        'totals': {'files': len(records), 'bytes': sum(record['bytes'] for record in records),
                   'archives': len(archives), 'owners': len(owners),
                   'duplicates': len(duplicates), 'link_lines': len(lines)},
        'owners': {owner: sorted(paths) for owner, paths in sorted(owners.items())},
        'duplicates': duplicates,
        'optional_packages': {identifier: {'licence_mode': row['mode'],
                                           'licence_path': row['path'],
                                           'licence_sha256': row['sha256'],
                                           'source': row['source'],
                                           'archives': [entry['name'] for entry in row['archives']]}
                              for identifier, row in sorted(package_licences_map.items())},
        'link': lines, 'spdx': spdx, 'cyclonedx': cdx,
        'checks': report.checks, 'problems': report.problems,
        'runtime_accepted': False, 'legal_conclusion': False, 'product_granted': False,
        'not_granted': list(NOT_GRANTED), 'pending': [],
    }
    result.update(verdict)
    return result


# ---------------------------------------------------------------- command line

def load_document(path):
    return contract.decode_json(Path(path).read_bytes())


def artifact_documents(directory):
    directory = Path(directory)
    documents = {}
    for name in INVENTORY_NAMES:
        if (directory / name).is_file():
            documents['inventory'] = load_document(directory / name)
            documents['inventory_name'] = name
            break
    if 'inventory' not in documents:
        raise ClosureError('inventory_missing')
    for key, names in SBOM_NAMES.items():
        for name in names:
            if (directory / name).is_file():
                documents[key] = load_document(directory / name)
                break
        if key not in documents:
            raise ClosureError(key + '_missing')
    if (directory / 'licenses.json').is_file():
        documents['licenses'] = load_document(directory / 'licenses.json')
    else:
        raise ClosureError('licenses_missing')
    return documents


def artifact_payload(directory):
    directory = Path(directory)
    payload, problems = scan_payload(directory / 'stage')
    tools = directory / 'tools'
    if tools.is_dir():
        for path in sorted(tools.iterdir()):
            if path.is_file():
                payload['tools/' + path.name] = path.read_bytes()
    return payload, problems


def write_report(result, output):
    output.mkdir(parents=True, exist_ok=True)
    data = json.dumps(result, indent=2, ensure_ascii=False).encode('utf-8') + b'\n'
    (output / 'closure.json').write_bytes(data)
    return {'bytes': len(data), 'sha256': contract.digest(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', required=True, type=Path,
                        help='directory holding stage/, inventory.json or combined.json, both SBOMs')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--platform', required=True, choices=list(contract.PLATFORMS))
    parser.add_argument('--kind', choices=('sdk', 'combined'), default=None)
    parser.add_argument('--producer-source-sha', default=None)
    parser.add_argument('--producer-run', default=None)
    parser.add_argument('--producer-attempt', default=None)
    parser.add_argument('--producer-artifact', default=None)
    parser.add_argument('--preset', default=None,
                        help='compare the recorded switches with this repository preset')
    args = parser.parse_args()

    documents = artifact_documents(args.artifact)
    payload, symlinks = artifact_payload(args.artifact)
    inventory = documents['inventory']
    kind = args.kind or ('combined' if (inventory.get('profile') == 'combined'
                                        or documents.get('inventory_name') == 'combined.json')
                         else 'sdk')
    config = inventory.get('config') or {}
    switches = dict(config.get('cache_switches') or config.get('sdk_switches') or {})
    result = verify(documents, payload, kind=kind, platform=args.platform, switches=switches,
                    source_sha=args.producer_source_sha,
                    verifier={'source_sha': os.environ.get('GITHUB_SHA'),
                              'run_id': os.environ.get('GITHUB_RUN_ID'),
                              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                              'job': os.environ.get('GITHUB_JOB')})
    for path in symlinks:
        result['problems'].append({'code': 'stage_symlink', 'detail': path})
    if args.preset:
        preset = registered.preset_switches(ROOT, args.preset)
        mismatch = sorted(key for key in preset if switches.get(key) != preset[key])
        result['checks'].append({'id': 'config.preset',
                                 'status': 'pass' if not mismatch else 'fail',
                                 'detail': '%d switches compared with %s: %r'
                                           % (len(preset), args.preset, mismatch)})
        if mismatch:
            result['problems'].append({'code': 'config_switches_mismatch', 'detail': repr(mismatch)})
    result['sources'].update({'run': args.producer_run, 'attempt': args.producer_attempt,
                              'artifact': args.producer_artifact})
    result.update(flags(result['problems']))
    result['report'] = write_report(result, args.output)
    summary = {key: result[key] for key in ('kind', 'platform', 'totals', 'accepted',
                                            'materials_closed', 'licence_closed',
                                            'sbom_closed', 'link_closed', 'report')}
    summary['problem_count'] = len(result['problems'])
    summary['problems'] = result['problems'][:24]
    print(json.dumps(summary, indent=2))
    return 0 if not result['problems'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
