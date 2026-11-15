#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate deterministic CycloneDX 1.5 and SPDX 2.3 SBOMs from CMake and license declarations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests/reader_distribution_inventory'))
import check_reading_licenses as license_registry
import packages as package_registry

DEFAULT_TIMESTAMP = '2026-11-15T00:00:00Z'

SDK_MODULE_VARS = (
    ('exr_core', 'EXR_CORE_VERSION', 'include/exr/core.h'),
    ('exr_pdf', 'EXR_PDF_VERSION', 'include/exr/pdf.h'),
    ('exr_library', 'EXR_LIBRARY_VERSION', 'include/exr/library.h'),
    ('exr_audio', 'EXR_AUDIO_VERSION', 'include/exr/audio.h'),
    ('exr_textindex', 'EXR_TEXTINDEX_VERSION', 'include/exr/textindex.h'),
    ('exr_pdf_edit', 'EXR_PDF_EDIT_VERSION', 'include/exr/pdf_edit.h'),
)

BUNDLE_DOCUMENT_FILES = (
    ('LICENSE', 'MIT'),
    ('THIRD_PARTY_NOTICES.md', 'MIT'),
    ('docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md', 'MIT'),
    ('docs/READING-LICENSES.md', 'MIT'),
    ('docs/READING-LICENSE-REVIEW.md', 'MIT'),
    ('docs/READER-DISTRIBUTION-INVENTORY.md', 'MIT'),
    ('data/hyph-en-us.LICENSE.txt', 'LPPL-1.0+'),
    ('data/hyph-en-us.pat.txt', 'LPPL-1.0+'),
    ('licenses/adobe-glyph-list.txt', 'Apache-2.0'),
    ('licenses/default-cmyk-profile.txt', 'Public-Domain'),
    ('licenses/faad2-notice.txt', 'GPL-2.0-or-later'),
    ('licenses/noto-sans-test-fonts.txt', 'OFL-1.1'),
    ('licenses/pdfjs.txt', 'Apache-2.0'),
    ('licenses/sqlite-public-domain.txt', 'blessing'),
    ('tests/fixtures/unicode/LICENSE.txt', 'Unicode-3.0'),
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def spdx_id(prefix: str, value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9.\-]+', '-', value).strip('-')
    return f'SPDXRef-{prefix}-{cleaned or "item"}'


def parse_versions_cmake(root: Path) -> dict:
    text = (root / 'cmake/versions.cmake').read_text(encoding='utf-8')
    values = {}
    for match in re.finditer(r'set\((EXR_[A-Z0-9_]+)\s+"?([^"\s)]+)"?\)', text):
        values[match.group(1)] = match.group(2)
    required = {'EXR_SDK_VERSION', 'EXR_ABI_VERSION'} | {var for _, var, _ in SDK_MODULE_VARS}
    missing = sorted(required - set(values))
    if missing:
        raise ValueError(f'cmake/versions.cmake missing variables: {missing!r}')
    values['EXR_VERSION'] = values['EXR_SDK_VERSION']
    return values


def parse_deps_cmake(root: Path) -> dict:
    text = (root / 'cmake/deps.cmake').read_text(encoding='utf-8')
    pins = {}
    for match in re.finditer(r'set\((EXR_[A-Z0-9_]+_SHA256)\s+([0-9a-f]{64})\)', text):
        pins[match.group(1)] = match.group(2)
    declared = {}
    for match in re.finditer(r'FetchContent_Declare\(\s*([A-Za-z0-9_]+)(.*?)\)', text, re.S):
        name = match.group(1)
        body = match.group(2)
        url = re.search(r'URL\s+(\S+)', body)
        url_hash = re.search(r'URL_HASH\s+SHA256=([0-9a-f]{64})', body)
        git_repo = re.search(r'GIT_REPOSITORY\s+(\S+)', body)
        git_tag = re.search(r'GIT_TAG\s+(\S+)', body)
        raw_url = url.group(1) if url else (git_repo.group(1) if git_repo else None)
        declared[name] = {
            'name': name,
            'url': raw_url.strip('"') if raw_url else None,
            'sha256': url_hash.group(1) if url_hash else None,
            'git_tag': git_tag.group(1).strip('"') if git_tag else None,
        }
    if not declared:
        raise ValueError('cmake/deps.cmake declared no FetchContent dependencies')
    return {'declared': declared, 'pins': pins}


def parse_cmake_targets(root: Path) -> list:
    mod_text = (root / 'cmake/modules.cmake').read_text(encoding='utf-8')
    layers_doc = json.loads((root / 'tools/layers.json').read_text(encoding='utf-8'))
    layers = list(layers_doc.get('layers', {}).keys())
    if 'add_library(exr_core INTERFACE)' not in mod_text or 'add_library(exreader' not in mod_text:
        raise ValueError('cmake/modules.cmake missing exr_core or exreader library target')
    targets = ['exreader', 'exr_core']
    for layer in layers:
        target = f'exr_{layer}'
        if target not in targets:
            targets.append(target)
    for mod_name, _, _ in SDK_MODULE_VARS:
        if mod_name not in targets:
            raise ValueError(f'SDK module target {mod_name} missing from parsed CMake targets: {targets!r}')
    return targets


def parse_product_packages(root: Path) -> list:
    items = []
    for pkg in package_registry.PACKAGES:
        cmake_file = root / pkg['source'] / 'CMakeLists.txt'
        if not cmake_file.is_file():
            raise ValueError(f'missing product package CMakeLists.txt: {pkg["source"]}')
        cmake_text = cmake_file.read_text(encoding='utf-8')
        proj_match = re.search(
            r'project\(\s*([A-Za-z0-9_]+)(?:\s+VERSION\s+([0-9]+\.[0-9]+\.[0-9]+))?',
            cmake_text,
        )
        if not proj_match:
            raise ValueError(f'cannot parse project() in {pkg["source"]}/CMakeLists.txt')
        observed_version = proj_match.group(2)
        items.append({
            'id': pkg['id'],
            'name': pkg['name'],
            'project': proj_match.group(1),
            'version': observed_version or 'unversioned',
            'license': 'MIT',
            'source': pkg['source'],
            'archives': list(pkg['archives']),
            'headers': list(pkg['headers']),
        })
    return items


def collect_declarations(root: Path = ROOT) -> dict:
    versions = parse_versions_cmake(root)
    deps = parse_deps_cmake(root)
    targets = parse_cmake_targets(root)
    product_packages = parse_product_packages(root)

    by_id = {comp['id']: comp for comp in license_registry.COMPONENTS}
    for dep_name, dep_info in deps['declared'].items():
        if dep_name not in by_id:
            raise ValueError(f'FetchContent dependency {dep_name} missing from check_reading_licenses.py')
        reg = by_id[dep_name]
        if dep_info['url'] and reg['source'] != dep_info['url']:
            raise ValueError(f'dependency {dep_name} URL mismatch between deps.cmake and license registry')
        if dep_info['sha256'] and reg['archive_sha256'] != dep_info['sha256']:
            raise ValueError(f'dependency {dep_name} SHA256 mismatch between deps.cmake and license registry')

    if by_id['exreader']['version'] not in (versions['EXR_VERSION'], 'repository HEAD'):
        raise ValueError(
            f'exreader version mismatch: versions.cmake={versions["EXR_VERSION"]} vs registry={by_id["exreader"]["version"]}'
        )

    sdk_modules = []
    for target_name, version_var, source_file in SDK_MODULE_VARS:
        src_path = root / source_file
        if not src_path.is_file():
            raise ValueError(f'missing SDK module source file: {source_file}')
        sdk_modules.append({
            'id': target_name.replace('_', '-'),
            'name': target_name,
            'version': versions[version_var],
            'license': 'MIT',
            'source': source_file,
            'sha256': sha256_file(src_path),
            'category': 'sdk-module',
            'active_in_reading_profile': target_name in ('exr_core', 'exr_pdf', 'exr_library'),
        })

    registered_components = []
    for comp in license_registry.COMPONENTS:
        comp_id = comp['id']
        active = comp['when'] not in ('EXR_ENABLE_AUDIO AND EXR_ENABLE_MP3', 'EXR_ENABLE_AUDIO AND EXR_ENABLE_AAC')
        pinned_files = []
        for f in comp.get('files', []):
            pinned_files.append({
                'installed': f['installed'],
                'source': f['path'],
                'sha256': f.get('sha256'),
            })
        comp_version = versions['EXR_VERSION'] if comp['version'] == 'repository HEAD' else comp['version']
        registered_components.append({
            'id': comp_id,
            'name': comp['name'],
            'version': comp_version,
            'license': comp['license'],
            'source': comp['source'],
            'archive_sha256': comp.get('archive_sha256'),
            'when': comp['when'],
            'linkage': comp.get('linkage', 'static'),
            'active_in_reading_profile': active,
            'category': 'sdk-dependency',
            'files': pinned_files,
        })

    hyph_pat = root / 'data/hyph-en-us.pat.txt'
    hyph_lic = root / 'data/hyph-en-us.LICENSE.txt'
    if not hyph_pat.is_file() or not hyph_lic.is_file():
        raise ValueError('missing data/hyph-en-us.pat.txt or data/hyph-en-us.LICENSE.txt')

    extra_assets = [
        {
            'id': 'hyph-en-us',
            'name': 'Liang TeX English Hyphenation Patterns (hyph-en-us)',
            'version': '1996-03-01',
            'license': 'LPPL-1.0+',
            'source': 'data/hyph-en-us.pat.txt',
            'sha256': sha256_file(hyph_pat),
            'license_path': 'data/hyph-en-us.LICENSE.txt',
            'license_sha256': sha256_file(hyph_lic),
            'category': 'embedded-data',
            'active_in_reading_profile': True,
        },
        {
            'id': 'noto-sans-cjk-host-font',
            'name': 'Noto Sans CJK SC Regular Host UI Font (Reader.otf)',
            'version': 'NotoSansCJKsc-Regular',
            'license': 'OFL-1.1',
            'source': 'https://github.com/notofonts/noto-cjk',
            'sha256': None,
            'license_path': 'OFL.txt',
            'license_sha256': None,
            'category': 'host-bundle-font',
            'active_in_reading_profile': True,
        },
    ]

    tracked_files = []
    for rel_path, lic in BUNDLE_DOCUMENT_FILES:
        abs_path = root / rel_path
        if not abs_path.is_file() or abs_path.stat().st_size == 0:
            raise ValueError(f'missing or empty required file: {rel_path}')
        tracked_files.append({
            'path': rel_path,
            'license': lic,
            'bytes': abs_path.stat().st_size,
            'sha256': sha256_file(abs_path),
            'sha1': sha1_file(abs_path),
        })

    return {
        'versions': versions,
        'cmake_targets': targets,
        'sdk_modules': sdk_modules,
        'registered_components': registered_components,
        'product_packages': product_packages,
        'extra_assets': extra_assets,
        'tracked_files': tracked_files,
        'deps_cmake_count': len(deps['declared']),
    }


def purl_for(comp_id: str, version: str) -> str:
    return f'pkg:generic/{quote(comp_id, safe="")}@{quote(str(version), safe="")}'


def build_cyclonedx(decl: dict, timestamp: str = DEFAULT_TIMESTAMP) -> dict:
    sdk_version = decl['versions']['EXR_VERSION']
    abi_version = decl['versions']['EXR_ABI_VERSION']
    root_ref = purl_for('exreader-distribution', sdk_version)
    files_by_path = {f['path']: f for f in decl['tracked_files']}

    components = []
    root_deps = []
    dep_entries = []

    for mod in decl['sdk_modules']:
        ref = purl_for(mod['id'], mod['version'])
        root_deps.append(ref)
        dep_entries.append({'ref': ref, 'dependsOn': []})
        components.append({
            'type': 'library',
            'bom-ref': ref,
            'name': mod['name'],
            'version': mod['version'],
            'purl': ref,
            'scope': 'required' if mod['active_in_reading_profile'] else 'optional',
            'hashes': [{'alg': 'SHA-256', 'content': mod['sha256']}],
            'licenses': [{'license': {'id': mod['license']}}],
            'properties': [
                {'name': 'exr:category', 'value': mod['category']},
                {'name': 'exr:source', 'value': mod['source']},
                {'name': 'exr:active_in_reading_profile', 'value': 'true' if mod['active_in_reading_profile'] else 'false'},
            ],
        })

    for comp in decl['registered_components']:
        ref = purl_for(comp['id'], comp['version'])
        root_deps.append(ref)
        dep_entries.append({'ref': ref, 'dependsOn': []})
        hashes = []
        if comp.get('archive_sha256'):
            hashes.append({'alg': 'SHA-256', 'content': comp['archive_sha256']})
        elif comp.get('files'):
            first_sha = next((f['sha256'] for f in comp['files'] if f.get('sha256')), None)
            if first_sha:
                hashes.append({'alg': 'SHA-256', 'content': first_sha})
        entry = {
            'type': 'library',
            'bom-ref': ref,
            'name': comp['name'],
            'version': comp['version'],
            'purl': ref,
            'scope': 'required' if comp['active_in_reading_profile'] else 'excluded',
            'licenses': [{'expression': comp['license']}],
            'properties': [
                {'name': 'exr:category', 'value': comp['category']},
                {'name': 'exr:when', 'value': comp['when']},
                {'name': 'exr:linkage', 'value': comp['linkage']},
                {'name': 'exr:source', 'value': comp['source']},
                {'name': 'exr:active_in_reading_profile', 'value': 'true' if comp['active_in_reading_profile'] else 'false'},
            ],
        }
        if hashes:
            entry['hashes'] = hashes
        components.append(entry)

    for pkg in decl['product_packages']:
        ref = purl_for(f'exreader-pkg-{pkg["id"]}', pkg['version'])
        root_deps.append(ref)
        dep_entries.append({'ref': ref, 'dependsOn': [purl_for('exreader', sdk_version)]})
        components.append({
            'type': 'library',
            'bom-ref': ref,
            'name': pkg['name'],
            'version': pkg['version'],
            'purl': ref,
            'scope': 'optional',
            'licenses': [{'license': {'id': pkg['license']}}],
            'properties': [
                {'name': 'exr:category', 'value': 'product-package'},
                {'name': 'exr:cmake_project', 'value': pkg['project']},
                {'name': 'exr:source', 'value': pkg['source']},
                {'name': 'exr:archives', 'value': ','.join(pkg['archives'])},
            ],
        })

    for asset in decl['extra_assets']:
        ref = purl_for(asset['id'], asset['version'])
        root_deps.append(ref)
        dep_entries.append({'ref': ref, 'dependsOn': []})
        entry = {
            'type': 'data',
            'bom-ref': ref,
            'name': asset['name'],
            'version': asset['version'],
            'purl': ref,
            'scope': 'required',
            'licenses': [{'expression': asset['license']}],
            'properties': [
                {'name': 'exr:category', 'value': asset['category']},
                {'name': 'exr:source', 'value': asset['source']},
                {'name': 'exr:license_path', 'value': asset['license_path']},
            ],
        }
        if asset.get('sha256'):
            entry['hashes'] = [{'alg': 'SHA-256', 'content': asset['sha256']}]
        components.append(entry)

    dependencies = [{'ref': root_ref, 'dependsOn': root_deps}, *dep_entries]

    return {
        'bomFormat': 'CycloneDX',
        'specVersion': '1.5',
        'version': 1,
        'metadata': {
            'timestamp': timestamp,
            'tools': [
                {
                    'vendor': 'EXReader',
                    'name': 'tools/generate_package_sbom.py',
                    'version': sdk_version,
                }
            ],
            'component': {
                'type': 'application',
                'bom-ref': root_ref,
                'name': 'EXReader Distribution',
                'version': sdk_version,
                'purl': root_ref,
                'licenses': [{'license': {'id': 'MIT'}}],
            },
            'properties': [
                {'name': 'exr:sdk_version', 'value': sdk_version},
                {'name': 'exr:abi_version', 'value': str(abi_version)},
                {'name': 'exr:cmake_targets', 'value': ','.join(decl['cmake_targets'])},
                {'name': 'exr:user_guide', 'value': 'docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md'},
                {'name': 'exr:user_guide_sha256', 'value': files_by_path['docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md']['sha256']},
                {'name': 'exr:license_file', 'value': 'LICENSE'},
                {'name': 'exr:license_sha256', 'value': files_by_path['LICENSE']['sha256']},
                {'name': 'exr:third_party_notices', 'value': 'THIRD_PARTY_NOTICES.md'},
                {'name': 'exr:third_party_notices_sha256', 'value': files_by_path['THIRD_PARTY_NOTICES.md']['sha256']},
                {'name': 'exr:hyph_license', 'value': 'data/hyph-en-us.LICENSE.txt'},
                {'name': 'exr:hyph_license_sha256', 'value': files_by_path['data/hyph-en-us.LICENSE.txt']['sha256']},
            ],
        },
        'components': components,
        'dependencies': dependencies,
    }


def build_spdx(decl: dict, timestamp: str = DEFAULT_TIMESTAMP) -> dict:
    sdk_version = decl['versions']['EXR_VERSION']
    root_pkg_id = 'SPDXRef-Package-exreader-distribution'
    packages = [
        {
            'SPDXID': root_pkg_id,
            'name': 'exreader-distribution',
            'versionInfo': sdk_version,
            'downloadLocation': 'NOASSERTION',
            'filesAnalyzed': True,
            'licenseConcluded': 'MIT',
            'licenseDeclared': 'MIT',
            'copyrightText': 'Copyright (c) 2026 EXReader Contributors',
            'externalRefs': [
                {
                    'referenceCategory': 'PACKAGE-MANAGER',
                    'referenceType': 'purl',
                    'referenceLocator': purl_for('exreader-distribution', sdk_version),
                }
            ],
        }
    ]
    relationships = [
        {
            'spdxElementId': 'SPDXRef-DOCUMENT',
            'relationshipType': 'DESCRIBES',
            'relatedSpdxElement': root_pkg_id,
        }
    ]

    for mod in decl['sdk_modules']:
        pid = spdx_id('Module', mod['id'])
        packages.append({
            'SPDXID': pid,
            'name': mod['name'],
            'versionInfo': mod['version'],
            'downloadLocation': 'NOASSERTION',
            'filesAnalyzed': False,
            'licenseConcluded': mod['license'],
            'licenseDeclared': mod['license'],
            'copyrightText': 'NOASSERTION',
            'checksums': [{'algorithm': 'SHA256', 'checksumValue': mod['sha256']}],
            'externalRefs': [
                {
                    'referenceCategory': 'PACKAGE-MANAGER',
                    'referenceType': 'purl',
                    'referenceLocator': purl_for(mod['id'], mod['version']),
                }
            ],
        })
        relationships.append({
            'spdxElementId': root_pkg_id,
            'relationshipType': 'CONTAINS',
            'relatedSpdxElement': pid,
        })

    for comp in decl['registered_components']:
        pid = spdx_id('Component', comp['id'])
        download = comp['source'] if str(comp['source']).startswith(('http://', 'https://')) else 'NOASSERTION'
        pkg_entry = {
            'SPDXID': pid,
            'name': comp['name'],
            'versionInfo': comp['version'],
            'downloadLocation': download,
            'filesAnalyzed': False,
            'licenseConcluded': comp['license'],
            'licenseDeclared': comp['license'],
            'copyrightText': 'NOASSERTION',
            'externalRefs': [
                {
                    'referenceCategory': 'PACKAGE-MANAGER',
                    'referenceType': 'purl',
                    'referenceLocator': purl_for(comp['id'], comp['version']),
                }
            ],
        }
        if comp.get('archive_sha256'):
            pkg_entry['checksums'] = [{'algorithm': 'SHA256', 'checksumValue': comp['archive_sha256']}]
        packages.append(pkg_entry)
        relationships.append({
            'spdxElementId': root_pkg_id,
            'relationshipType': 'DEPENDS_ON' if comp['active_in_reading_profile'] else 'OPTIONAL_DEPENDENCY_OF',
            'relatedSpdxElement': pid,
        })

    for pkg in decl['product_packages']:
        pid = spdx_id('ProductPkg', pkg['id'])
        packages.append({
            'SPDXID': pid,
            'name': pkg['name'],
            'versionInfo': pkg['version'],
            'downloadLocation': 'NOASSERTION',
            'filesAnalyzed': False,
            'licenseConcluded': pkg['license'],
            'licenseDeclared': pkg['license'],
            'copyrightText': 'NOASSERTION',
            'externalRefs': [
                {
                    'referenceCategory': 'PACKAGE-MANAGER',
                    'referenceType': 'purl',
                    'referenceLocator': purl_for(f'exreader-pkg-{pkg["id"]}', pkg['version']),
                }
            ],
        })
        relationships.append({
            'spdxElementId': root_pkg_id,
            'relationshipType': 'CONTAINS',
            'relatedSpdxElement': pid,
        })

    for asset in decl['extra_assets']:
        pid = spdx_id('Asset', asset['id'])
        download = asset['source'] if str(asset['source']).startswith(('http://', 'https://')) else 'NOASSERTION'
        entry = {
            'SPDXID': pid,
            'name': asset['name'],
            'versionInfo': asset['version'],
            'downloadLocation': download,
            'filesAnalyzed': False,
            'licenseConcluded': asset['license'],
            'licenseDeclared': asset['license'],
            'copyrightText': 'NOASSERTION',
            'externalRefs': [
                {
                    'referenceCategory': 'PACKAGE-MANAGER',
                    'referenceType': 'purl',
                    'referenceLocator': purl_for(asset['id'], asset['version']),
                }
            ],
        }
        if asset.get('sha256'):
            entry['checksums'] = [{'algorithm': 'SHA256', 'checksumValue': asset['sha256']}]
        packages.append(entry)
        relationships.append({
            'spdxElementId': root_pkg_id,
            'relationshipType': 'CONTAINS',
            'relatedSpdxElement': pid,
        })

    files = []
    sha1s = []
    for item in decl['tracked_files']:
        fid = spdx_id('File', item['path'])
        sha1s.append(item['sha1'])
        files.append({
            'SPDXID': fid,
            'fileName': item['path'],
            'licenseConcluded': item['license'],
            'copyrightText': 'NOASSERTION',
            'checksums': [
                {'algorithm': 'SHA1', 'checksumValue': item['sha1']},
                {'algorithm': 'SHA256', 'checksumValue': item['sha256']},
            ],
        })
        relationships.append({
            'spdxElementId': root_pkg_id,
            'relationshipType': 'CONTAINS',
            'relatedSpdxElement': fid,
        })

    verif_code = hashlib.sha1(''.join(sorted(sha1s)).encode('ascii')).hexdigest()
    packages[0]['packageVerificationCode'] = {'packageVerificationCodeValue': verif_code}
    packages[0]['hasFiles'] = [f['SPDXID'] for f in files]

    return {
        'spdxVersion': 'SPDX-2.3',
        'dataLicense': 'CC0-1.0',
        'SPDXID': 'SPDXRef-DOCUMENT',
        'name': f'EXReader-Distribution-{sdk_version}',
        'documentNamespace': f'https://exreader.invalid/spdx/exreader-distribution-{sdk_version}',
        'creationInfo': {
            'created': timestamp,
            'creators': [
                'Tool: exreader-generate-package-sbom-1.0',
                'Organization: EXReader',
            ],
            'licenseListVersion': '3.23',
        },
        'packages': packages,
        'files': files,
        'relationships': relationships,
    }


def write_sboms(output_dir: Path, timestamp: str = DEFAULT_TIMESTAMP) -> dict:
    decl = collect_declarations(ROOT)
    cdx = build_cyclonedx(decl, timestamp)
    spdx = build_spdx(decl, timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)
    cdx_path = output_dir / 'sbom.cdx.json'
    spdx_path = output_dir / 'sbom.spdx.json'
    cdx_bytes = (json.dumps(cdx, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    spdx_bytes = (json.dumps(spdx, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    cdx_path.write_bytes(cdx_bytes)
    spdx_path.write_bytes(spdx_bytes)
    return {
        'sdk_version': decl['versions']['EXR_VERSION'],
        'abi_version': int(decl['versions']['EXR_ABI_VERSION']),
        'cyclonedx_path': cdx_path.as_posix(),
        'cyclonedx_components': len(cdx['components']),
        'cyclonedx_sha256': hashlib.sha256(cdx_bytes).hexdigest(),
        'spdx_path': spdx_path.as_posix(),
        'spdx_packages': len(spdx['packages']),
        'spdx_files': len(spdx['files']),
        'spdx_sha256': hashlib.sha256(spdx_bytes).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'docs')
    parser.add_argument('--timestamp', default=DEFAULT_TIMESTAMP)
    args = parser.parse_args()
    summary = write_sboms(args.output_dir.resolve(), args.timestamp)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
