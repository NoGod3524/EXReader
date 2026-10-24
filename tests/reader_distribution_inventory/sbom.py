#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a standard SPDX 2.3 document and a CycloneDX 1.5 BOM from one install.

Both documents describe only what the install stage actually contains: every
installed file with its bytes and SHA-256/SHA-1, every registered third-party
component with its pinned source, and the archived runtime identity. Licence
identifiers come from an explicit table so a new dependency cannot inherit a
wrong identifier silently.
"""
import hashlib
import re
import uuid

TOOL_NAME = 'exreader-distribution-inventory'
TOOL_VERSION = '1.0.0'
TOOL_URL = 'https://github.com/NoGod3524/EXReader'
SPDX_NAMESPACE_NAMESPACE = uuid.UUID('6f9619ff-8b86-d011-b42d-00c04fc964ff')
SCOPE = ('Installed reading SDK file inventory, registered third-party materials and observed '
         'static/dynamic dependencies. Materials inventory, not a legal conclusion.')

# component id -> (concluded, declared). Every registered component must appear:
# the builder raises for an unknown id instead of guessing an identifier.
LICENSES = {
    'exreader': ('MIT', 'MIT'),
    'freetype': ('FTL', 'FTL OR GPL-2.0-only'),
    'expat': ('MIT', 'MIT'),
    'miniz': ('MIT', 'MIT'),
    'stb': ('MIT', 'MIT OR LicenseRef-Public-Domain'),
    'libwebp': ('BSD-3-Clause', 'BSD-3-Clause'),
    'zlib': ('Zlib', 'Zlib'),
    'libtiff': ('LicenseRef-libtiff', 'LicenseRef-libtiff'),
    'libaom': ('BSD-2-Clause AND LicenseRef-AOM-Patent-License-1.0',
               'BSD-2-Clause AND LicenseRef-AOM-Patent-License-1.0'),
    'libavif': ('BSD-2-Clause', 'BSD-2-Clause'),
    'mbedtls': ('Apache-2.0', 'Apache-2.0 OR GPL-2.0-or-later'),
    'openjpeg': ('BSD-2-Clause', 'BSD-2-Clause'),
    'lcms': ('MIT', 'MIT'),
    'sqlite': ('LicenseRef-Public-Domain', 'LicenseRef-Public-Domain'),
    'minimp3': ('CC0-1.0', 'CC0-1.0'),
    'faad2': ('GPL-2.0-or-later', 'GPL-2.0-or-later'),
    'unicode': ('Unicode-3.0', 'Unicode-3.0'),
    'argyll-cmyk': ('LicenseRef-Public-Domain', 'LicenseRef-Public-Domain'),
    'adobe-glyph-list': ('BSD-3-Clause', 'BSD-3-Clause'),
    'pdfjs-data': ('Apache-2.0', 'Apache-2.0'),
    'pdf-calculator-names': ('LicenseRef-Adobe-Permission-Notice', 'LicenseRef-Adobe-Permission-Notice'),
    'noto-test-fonts': ('OFL-1.1', 'OFL-1.1'),
    # First-party optional application packages: the same MIT grant as the SDK.
    'catalog': ('MIT', 'MIT'),
    'revisions': ('MIT', 'MIT'),
    'commands': ('MIT', 'MIT'),
    'desktop-metadata': ('MIT', 'MIT'),
    'webdav': ('MIT', 'MIT'),
    'session': ('MIT', 'MIT'),
    'sync': ('MIT', 'MIT'),
    'credentials': ('MIT', 'MIT'),
    'reading-state': ('MIT', 'MIT'),
    'search': ('MIT', 'MIT'),
    'preferences': ('MIT', 'MIT'),
    'batch-import': ('MIT', 'MIT'),
    'sideload': ('MIT', 'MIT'),
}
DATA_ONLY = ('unicode', 'argyll-cmyk', 'adobe-glyph-list', 'pdfjs-data', 'pdf-calculator-names',
             'noto-test-fonts')
FILE_TYPES = {'.a': 'ARCHIVE', '.lib': 'ARCHIVE', '.zip': 'ARCHIVE',
              '.exe': 'BINARY', '.dll': 'BINARY', '.so': 'BINARY', '.dylib': 'BINARY',
              '.ttf': 'BINARY', '.otf': 'BINARY', '.ttc': 'BINARY',
              '.c': 'SOURCE', '.h': 'SOURCE', '.hpp': 'SOURCE', '.inc': 'SOURCE', '.cmake': 'SOURCE',
              '.modulemap': 'SOURCE',
              '.md': 'TEXT', '.txt': 'TEXT', '.json': 'TEXT', '.yml': 'TEXT', '.yaml': 'TEXT',
              '.png': 'IMAGE', '.jpg': 'IMAGE', '.jpeg': 'IMAGE'}


class SbomError(Exception):
    pass


def licence_expression(component_id):
    if component_id not in LICENSES:
        raise SbomError('unmapped license identifier: ' + str(component_id))
    return LICENSES[component_id]


def purl(name, version):
    token = re.sub(r'[^A-Za-z0-9._+-]', '_', str(version)).strip('_') or 'unknown'
    return 'pkg:generic/%s@%s' % (re.sub(r'[^A-Za-z0-9._+-]', '-', str(name)).lower(), token)


def spdx_ref(prefix, value):
    return 'SPDXRef-%s-%s' % (prefix, re.sub(r'[^A-Za-z0-9.-]', '-', str(value)))


def file_type(path):
    match = re.search(r'(\.[A-Za-z0-9]+)$', path)
    extension = match.group(1).lower() if match else ''
    return FILE_TYPES.get(extension)


def build_spdx(inventory, created):
    """inventory: the generated inventory document for one install."""
    identity = inventory['identity']
    version = identity['version']
    files = inventory['installed_files']
    components = inventory['license_materials']['components']
    active = [component for component in components if component['active']]
    ids = {}
    file_elements = []
    for index, record in enumerate(files):
        spdx_id = spdx_ref('File', '%04d' % index)
        ids[record['path']] = spdx_id
        element = {'fileName': './' + record['path'], 'SPDXID': spdx_id,
                   'checksums': [{'algorithm': 'SHA1', 'checksumValue': record['sha1']},
                                 {'algorithm': 'SHA256', 'checksumValue': record['sha256']}],
                   'licenseConcluded': 'NOASSERTION', 'licenseInfoInFiles': ['NOASSERTION'],
                   'copyrightText': 'NOASSERTION'}
        kind = file_type(record['path'])
        if kind:
            element['fileTypes'] = [kind]
        file_elements.append(element)
    code = hashlib.sha1(''.join(sorted(record['sha1'] for record in files)).encode('ascii')).hexdigest()
    sdk = {'name': 'EXReader reading SDK', 'SPDXID': 'SPDXRef-Package-EXReader',
           'versionInfo': version, 'downloadLocation': 'NOASSERTION', 'filesAnalyzed': True,
           'packageVerificationCode': {'packageVerificationCodeValue': code},
           'licenseConcluded': 'MIT', 'licenseDeclared': 'MIT',
           'licenseInfoFromFiles': ['NOASSERTION'], 'copyrightText': 'NOASSERTION',
           'supplier': 'Organization: EXReader contributors',
           'primaryPackagePurpose': 'LIBRARY',
           'hasFiles': [element['SPDXID'] for element in file_elements],
           'externalRefs': [{'referenceCategory': 'PACKAGE-MANAGER', 'referenceType': 'purl',
                             'referenceLocator': purl('exreader', version)}],
           'comment': ('%s Profile %s on %s from source %s; ABI %s.'
                       % (SCOPE, inventory['profile'], inventory['platform'],
                          inventory['source_sha'], identity.get('abi')))}
    packages = [sdk]
    relationships = [{'spdxElementId': 'SPDXRef-DOCUMENT',
                      'relationshipType': 'DESCRIBES', 'relatedSpdxElement': sdk['SPDXID']}]
    for element in file_elements:
        relationships.append({'spdxElementId': sdk['SPDXID'], 'relationshipType': 'CONTAINS',
                              'relatedSpdxElement': element['SPDXID']})
    for component in active:
        if component['id'] == 'exreader':
            continue
        concluded, declared = licence_expression(component['id'])
        source = component.get('source') or ''
        package = {'name': component['name'], 'SPDXID': spdx_ref('Package', component['id']),
                   'versionInfo': component['version'],
                   'downloadLocation': source if str(source).startswith('http') else 'NOASSERTION',
                   'filesAnalyzed': False, 'licenseConcluded': concluded,
                   'licenseDeclared': declared, 'copyrightText': 'NOASSERTION',
                   'comment': ('Enable condition %r; linkage %s; %s.'
                               % (component.get('when') or 'always', component.get('linkage'),
                                  ('data only: ' + component['id']) if component['id'] in DATA_ONLY
                                  else 'linked into the shipped static SDK'))}
        if component.get('archive_sha256'):
            package['sourceInfo'] = 'Pinned as %s with archive SHA-256 %s.' % (
                source, component['archive_sha256'])
        packages.append(package)
        relationships.append({'spdxElementId': sdk['SPDXID'], 'relationshipType': 'DEPENDS_ON',
                              'relatedSpdxElement': package['SPDXID']})
        for item in component.get('files', []):
            installed = item.get('installed')
            if installed in ids:
                relationships.append({'spdxElementId': package['SPDXID'],
                                      'relationshipType': 'CONTAINS',
                                      'relatedSpdxElement': ids[installed]})
    document = {'spdxVersion': 'SPDX-2.3', 'dataLicense': 'CC0-1.0', 'SPDXID': 'SPDXRef-DOCUMENT',
                'name': 'EXReader %s %s' % (inventory['profile'], inventory['platform']),
                'documentNamespace': '%s/spdx/%s/%s-%s' % (TOOL_URL, inventory['source_sha'],
                                                           inventory['platform'], inventory['profile']),
                'creationInfo': {'created': created,
                                 'creators': ['Tool: %s-%s' % (TOOL_NAME, TOOL_VERSION),
                                              'Organization: EXReader contributors'],
                                 'comment': SCOPE},
                'packages': packages, 'files': file_elements, 'relationships': relationships}
    return document


def build_cyclonedx(inventory, created):
    identity = inventory['identity']
    version = identity['version']
    components = inventory['license_materials']['components']
    active = [component for component in components if component['active']]
    key = '%s/%s/%s' % (inventory['source_sha'], inventory['platform'], inventory['profile'])
    properties = [{'name': 'exreader:profile', 'value': inventory['profile']},
                  {'name': 'exreader:platform', 'value': inventory['platform']},
                  {'name': 'exreader:source_sha', 'value': inventory['source_sha']},
                  {'name': 'exreader:abi', 'value': str(identity.get('abi'))},
                  {'name': 'exreader:installed_files', 'value': str(len(inventory['installed_files']))}]
    sdk = {'type': 'library', 'bom-ref': 'sdk', 'name': 'EXReader reading SDK', 'version': version,
           'purl': purl('exreader', version),
           'licenses': [{'expression': 'MIT'}], 'properties': properties}
    elements = []
    archive_owner = {}
    for component in active:
        for name in component.get('vendor_files') or []:
            archive_owner[name] = component['id']
    for component in active:
        if component['id'] == 'exreader':
            continue
        concluded, declared = licence_expression(component['id'])
        element = {'type': 'library', 'bom-ref': 'component-' + component['id'],
                   'name': component['name'], 'version': component['version'],
                   'purl': purl(component['name'], component['version']),
                   'licenses': [{'expression': declared}], 'scope': 'required',
                   'properties': [{'name': 'exreader:component_id', 'value': component['id']},
                                  {'name': 'exreader:enable_condition',
                                   'value': component.get('when') or 'always'},
                                  {'name': 'exreader:linkage', 'value': component.get('linkage') or ''},
                                  {'name': 'exreader:concluded_license', 'value': concluded}]}
        archives = component.get('archives') or []
        if archives:
            element['hashes'] = [{'alg': 'SHA-256', 'content': item['sha256']} for item in archives]
            element['properties'].append({'name': 'exreader:installed_bytes',
                                          'value': str(sum(item['bytes'] for item in archives))})
        elements.append(element)
    for record in inventory['installed_files']:
        elements.append({'type': 'file', 'bom-ref': 'file-' + record['path'].replace('/', '~'),
                         'name': './' + record['path'],
                         'hashes': [{'alg': 'SHA-256', 'content': record['sha256']}],
                         'properties': [{'name': 'exreader:bytes', 'value': str(record['bytes'])}]})
    sdk_archives = set(inventory.get('static_dependency', {}).get('sdk_archives') or [])
    known = {element['bom-ref'] for element in elements}
    involved = {}
    for edge in inventory.get('static_dependency', {}).get('edges', []):
        if edge['from'] in sdk_archives:
            source = 'sdk'
        elif edge['from'] in archive_owner:
            source = 'component-' + archive_owner[edge['from']]
        else:
            continue
        if edge['to'] not in archive_owner:
            continue
        involved.setdefault(source, set()).add('component-' + archive_owner[edge['to']])
    dependencies = []
    for source in sorted(involved, key=lambda value: (value != 'sdk', value)):
        targets = sorted(target for target in involved[source] if target in known)
        if targets and (source == 'sdk' or source in known):
            dependencies.append({'ref': source, 'dependsOn': targets})
    document = {'bomFormat': 'CycloneDX', 'specVersion': '1.5',
                'serialNumber': 'urn:uuid:%s' % uuid.uuid5(SPDX_NAMESPACE_NAMESPACE, key),
                'version': 1,
                'metadata': {'timestamp': created,
                             'tools': [{'vendor': 'EXReader', 'name': TOOL_NAME,
                                        'version': TOOL_VERSION}],
                             'component': sdk},
                'components': elements, 'dependencies': dependencies}
    return document


def validate_spdx(document, inventory):
    """Structural checks that must hold for every produced SPDX document."""
    problems = []
    if document.get('spdxVersion') != 'SPDX-2.3':
        problems.append('spdx version')
    if document.get('dataLicense') != 'CC0-1.0' or document.get('SPDXID') != 'SPDXRef-DOCUMENT':
        problems.append('spdx document identity')
    namespace = document.get('documentNamespace')
    if not isinstance(namespace, str) or not namespace.startswith('https://') or \
            inventory['source_sha'] not in namespace:
        problems.append('spdx document namespace')
    packages = document.get('packages') or []
    files = document.get('files') or []
    seen = set()
    for element in packages + files:
        identity = element.get('SPDXID')
        if not isinstance(identity, str) or not re.fullmatch(r'SPDXRef-[A-Za-z0-9.-]+', identity):
            problems.append('spdx identifier syntax')
        if identity in seen:
            problems.append('duplicate spdx identifier: ' + str(identity))
        seen.add(identity)
    by_name = {element['fileName']: element for element in files}
    for record in inventory['installed_files']:
        element = by_name.get('./' + record['path'])
        if element is None:
            problems.append('spdx file coverage: ' + record['path'])
            continue
        checksums = {item['algorithm']: item['checksumValue'] for item in element.get('checksums', [])}
        if checksums.get('SHA256') != record['sha256'] or checksums.get('SHA1') != record['sha1']:
            problems.append('spdx file checksum: ' + record['path'])
    if len(files) != len(inventory['installed_files']):
        problems.append('spdx file count differs from the installed inventory')
    sdk = next((element for element in packages if element.get('SPDXID') == 'SPDXRef-Package-EXReader'), None)
    if sdk is None:
        problems.append('spdx sdk package missing')
    else:
        code = (sdk.get('packageVerificationCode') or {}).get('packageVerificationCodeValue')
        expected = hashlib.sha1(''.join(sorted(record['sha1'] for record in
                                               inventory['installed_files'])).encode('ascii')).hexdigest()
        if code != expected:
            problems.append('spdx package verification code')
        if sdk.get('versionInfo') != inventory['identity']['version']:
            problems.append('spdx sdk version')
        if set(sdk.get('hasFiles') or []) != {element['SPDXID'] for element in files}:
            problems.append('spdx hasFiles coverage')
    registered = {component['id'] for component in inventory['license_materials']['components']
                  if component['active'] and component['id'] != 'exreader'}
    described = set()
    for element in packages:
        if element is sdk:
            continue
        described.add(element['SPDXID'])
        stated = element.get('licenseConcluded')
        if not isinstance(stated, str) or not stated or stated == 'NOASSERTION':
            problems.append('spdx package license: ' + str(element.get('name')))
        if element.get('filesAnalyzed') is not False:
            problems.append('spdx third-party package must not analyze files: ' + str(element.get('name')))
    expected_ids = {spdx_ref('Package', name) for name in registered}
    if described != expected_ids:
        problems.append('spdx package coverage differs from the registered components')
    return problems


def validate_cyclonedx(document, inventory):
    problems = []
    if document.get('bomFormat') != 'CycloneDX' or document.get('specVersion') != '1.5':
        problems.append('cyclonedx format or version')
    serial = document.get('serialNumber')
    if not isinstance(serial, str) or not re.fullmatch(r'urn:uuid:[0-9a-f-]{36}', serial):
        problems.append('cyclonedx serial number')
    metadata = document.get('metadata') or {}
    if not isinstance(metadata.get('timestamp'), str) or not metadata.get('timestamp').endswith('Z'):
        problems.append('cyclonedx timestamp')
    sdk = metadata.get('component') or {}
    if sdk.get('version') != inventory['identity']['version'] or sdk.get('name') != 'EXReader reading SDK':
        problems.append('cyclonedx metadata component')
    components = document.get('components') or []
    refs = set()
    for element in components:
        reference = element.get('bom-ref')
        if not isinstance(reference, str) or not reference or reference in refs:
            problems.append('cyclonedx bom-ref')
        refs.add(reference)
    files = {element['name']: element for element in components if element.get('type') == 'file'}
    for record in inventory['installed_files']:
        element = files.get('./' + record['path'])
        if element is None:
            problems.append('cyclonedx file coverage: ' + record['path'])
            continue
        hashes = {item['alg']: item['content'] for item in element.get('hashes', [])}
        if hashes.get('SHA-256') != record['sha256']:
            problems.append('cyclonedx file checksum: ' + record['path'])
    registered = {component['id'] for component in inventory['license_materials']['components']
                  if component['active'] and component['id'] != 'exreader'}
    described = set()
    for element in components:
        if element.get('type') != 'library':
            continue
        for item in element.get('properties') or []:
            if item.get('name') == 'exreader:component_id':
                described.add(item.get('value'))
    if described != registered:
        problems.append('cyclonedx component coverage differs from the registered components')
    for element in components:
        if element.get('type') != 'library':
            continue
        if not element.get('licenses'):
            problems.append('cyclonedx component without a license: ' + str(element.get('name')))
    for dependency in document.get('dependencies') or []:
        if dependency.get('ref') not in refs | {'sdk'}:
            problems.append('cyclonedx dependency ref is unknown: ' + str(dependency.get('ref')))
        for target in dependency.get('dependsOn') or []:
            if target not in refs:
                problems.append('cyclonedx dependency target is unknown: ' + str(target))
    return problems
