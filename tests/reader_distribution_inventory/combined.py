#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Distribution inventory for the composed prefix: SDK plus optional packages.

The prefix is built by installing the reading-library preset and then each of the
thirteen registered optional packages into the same install tree. Everything this
document claims is read back from that tree: package configuration versions,
public headers, archives, licence material, the symbol universe of every archive,
and the real link command of a consumer that links exactly one package.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(HERE))
import check_reading_licenses as registered
import contract
import inventory as sdk
import packages
import sbom

PREFIX = 'stage/'
SCOPE = ('Composed install: the reading-library SDK plus the thirteen registered optional '
         'application packages with their public headers, archives, package configuration, '
         'licence material and observed static and dynamic dependencies. Materials inventory, '
         'not a legal conclusion. Mobile targets, host bundles and publication are outside '
         'this document.')
NOT_COVERED = [
    'Android, iOS and Apple native host packaging: separate owners, not built or packed here',
    'GTK/Linux, Windows and macOS native host bundles and their Noto Sans CJK host font',
    'Audio builds: EXR_ENABLE_AUDIO and the MP3/AAC codecs are excluded from every profile',
    'PDF editing, text index, shared compatibility library, JNI bindings, tools and test binaries',
    'Offline installer, code signing, notarization, tag, Release and store publication',
    'Legal review: the registered licence identifiers are inventoried, not adjudicated',
]

ARCHIVE = re.compile(r'lib/(?:exreader/)?[^/]+[.](?:a|lib)')
CREDENTIAL = ('exr_credentials', 'exreader-credentials', 'exreadercredentials')


def item(check_id, status, detail=''):
    return {'id': check_id, 'status': status, 'detail': detail}


def digest_text(values):
    return hashlib.sha256(('\n'.join(values) + '\n').encode('utf-8')).hexdigest()


def archive_evidence(commands, prefix, relative, host):
    path = prefix / relative
    if host == 'Windows':
        members, _, _ = commands.run('archive members %s' % path.name, 'lib-list',
                                     ['lib', '/nologo', '/list', str(path)])
        symbols, text, code = commands.run('archive symbols %s' % path.name, 'dumpbin-symbols',
                                           ['dumpbin', '/nologo', '/symbols', str(path)],
                                           archive=relative)
        directives, _, _ = commands.run('archive directives %s' % path.name, 'dumpbin-directives',
                                        ['dumpbin', '/nologo', '/directives', str(path)],
                                        archive=relative)
    else:
        members, _, _ = commands.run('archive members %s' % path.name, 'ar', ['ar', 't', str(path)])
        symbols, text, code = commands.run('archive symbols %s' % path.name, 'nm',
                                           ['nm', '-g', str(path)],
                                           strip_underscore=(host == 'Darwin'), archive=relative)
        directives = {'entries': []}
    summary = contract.symbol_summary(contract.parse_entries(symbols['kind'], text,
                                                             symbols['strip_underscore']))
    return {'members': [entry['name'] for entry in members['entries']], 'symbols': summary,
            'directives': [entry['name'] for entry in directives['entries']], 'exit': code}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True, type=Path)
    parser.add_argument('--platform', required=True, choices=list(contract.PLATFORMS))
    parser.add_argument('--runner-os', required=True)
    parser.add_argument('--architecture', default='')
    parser.add_argument('--sdk-build', required=True, type=Path)
    parser.add_argument('--sdk-licenses', required=True, type=Path)
    parser.add_argument('--consumers', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()

    prefix = args.prefix.resolve()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    commands = sdk.Commands(output / 'tools')
    checks, problems, blockers = [], [], []
    host = args.runner_os

    files, stage_problems = sdk.scan_stage(prefix)
    problems += stage_problems
    payload = {PREFIX + record['path']: (prefix / record['path']).read_bytes() for record in files}
    index = {record['path']: payload[PREFIX + record['path']] for record in files}
    by_path = {record['path']: record for record in files}

    cache = registered.read_cache(args.sdk_build.resolve() / 'CMakeCache.txt')
    switches = {key: contract.config_switch(value) for key, value in cache.items()
                if key.startswith('EXR_')}

    header = prefix / 'include/exr/base.h'
    text = header.read_text(encoding='utf-8') if header.is_file() else ''
    version = re.search(r'#define\s+EXR_VERSION\s+"([^"]+)"', text)
    abi = re.search(r'#define\s+EXR_ABI_VERSION\s+(\d+)', text)
    core = re.search(r'#define\s+EXR_CORE_VERSION\s+"([^"]+)"', text)
    config_path = prefix / 'lib/cmake/EXReader/EXReaderConfigVersion.cmake'
    config_version = re.search(r'set\(PACKAGE_VERSION\s+"([^"]+)"\)',
                               config_path.read_text(encoding='utf-8', errors='replace')
                               if config_path.is_file() else '')
    targets_path = prefix / 'lib/cmake/EXReader/EXReaderTargets.cmake'
    sdk_targets = sorted(set(re.findall(
        r'add_library\(EXReader::([A-Za-z0-9_]+)\s+(?:STATIC|INTERFACE|SHARED)\s+IMPORTED\)',
        targets_path.read_text(encoding='utf-8', errors='replace') if targets_path.is_file() else '')))
    identity = {'version': version.group(1) if version else None,
                'abi': int(abi.group(1)) if abi else None,
                'core_version': core.group(1) if core else None,
                'config_version': config_version.group(1) if config_version else None,
                'targets': sdk_targets, 'probe': None}
    identity_ok = bool(identity['version']) and isinstance(identity['abi'], int) \
        and identity['config_version'] == identity['version'] and bool(identity['targets'])
    if not identity_ok:
        problems.append('the composed prefix does not carry a complete SDK identity')
    checks.append(item('identity.sdk', 'pass' if identity_ok else 'fail',
                       '%s ABI %s core %s; %d SDK targets'
                       % (identity['version'], identity['abi'], identity['core_version'],
                          len(sdk_targets))))

    licenses_doc = contract.decode_json(args.sdk_licenses.read_bytes())
    sdk_licences = sdk.license_section(licenses_doc)
    sdk_checker = sdk_licences['checker']
    sdk_ready = sdk_checker['release_ready'] and not sdk_checker['failures'] \
        and not sdk_checker['pending'] and not sdk_checker['mandatory_missing']
    if not sdk_ready:
        problems.append('the SDK licence record is not release ready inside the composed prefix')
    checks.append(item('licenses.sdk_record', 'pass' if sdk_ready else 'fail',
                       'release_ready=%s failures=%d pending=%d'
                       % (sdk_checker['release_ready'], len(sdk_checker['failures']),
                          len(sdk_checker['pending']))))

    def enabled(expression):
        return registered.enabled(expression, switches)

    expected_sdk = contract.expected_license_paths(registered.COMPONENTS, enabled)
    sdk_license_problems = contract.verify_license_materials(files, payload, expected_sdk,
                                                             registered.COMPONENTS)
    problems += sdk_license_problems
    checks.append(item('licenses.sdk_materials', 'pass' if not sdk_license_problems else 'fail',
                       '%d SDK licence materials' % len(expected_sdk)))

    archives = sorted(record['path'] for record in files if ARCHIVE.fullmatch(record['path']))
    archive_names = {path.split('/')[-1] for path in archives}
    symbols, members, directives = {}, {}, {}
    for relative in archives:
        evidence = archive_evidence(commands, prefix, relative, host)
        symbols[relative] = evidence['symbols']
        members[relative] = evidence['members']
        directives[relative] = evidence['directives']
        if evidence['exit'] != 0:
            problems.append('cannot read symbols of ' + relative)
    blind = [path for path in symbols
             if not symbols[path]['defined'] and not symbols[path]['undefined']]
    checks.append(item('archives.symbols', 'pass' if symbols and not blind else 'fail',
                       '%d archives, %d without symbols' % (len(archives), len(blind))))

    edges = contract.symbol_edges(symbols, symbols)
    sdk_archives = [path for path in archives
                    if re.fullmatch(r'lib/(?:lib)?exr_.+[.](?:a|lib)', path)]
    unreferenced = sorted(path for path in symbols if path not in sdk_archives
                          and not any(edge['to'] == path for edge in edges))
    owners = {}
    for component in sdk_licences['components']:
        for path in archives:
            if sdk.archive_key(path.split('/')[-1])[1] in set(component['vendor_files']):
                owners[path] = component['id']
    for package in packages.PACKAGES:
        for name in package['archives']:
            for extension in ('.a', '.lib'):
                candidate = 'lib/%s%s' % (name, extension)
                if candidate in by_path:
                    owners[candidate] = package['id']

    providers = packages.symbol_providers(symbols)
    package_sections = []
    for package in packages.PACKAGES:
        resolved = packages.resolve(package, index)
        section = {'id': package['id'], 'name': package['name'], 'project': package['project'],
                   'find': package['find'], 'source': package['source'],
                   'registered_version': package['version'], 'version': resolved['version'],
                   'version_source': resolved.get('version_source'),
                   'config_files': resolved['config_files'], 'headers': resolved['headers'],
                   'archives': resolved['archives'], 'assets': resolved['assets'],
                   'licence': resolved['licence'], 'missing': resolved['missing']}
        package_checks = []
        if resolved['missing']:
            problems.append('package %s is missing registered material: %r'
                            % (package['id'], resolved['missing']))
        package_checks.append(item('package.%s.installed' % package['id'],
                                   'pass' if not resolved['missing'] else 'fail',
                                   '%d config, %d header, %d archive, %d asset'
                                   % (len(resolved['config_files']), len(resolved['headers']),
                                      len(resolved['archives']), len(resolved['assets']))))
        if package['version'] is None:
            version_ok = resolved.get('version_source') == 'none'
            version_status = 'reported' if version_ok else 'fail'
            version_detail = 'registered as unversioned: no package version file is installed'
            if not version_ok:
                problems.append('package %s installs no version file but declares %r'
                                % (package['id'], resolved['version']))
        else:
            version_ok = resolved['version'] == package['version']
            version_status = 'pass' if version_ok else 'fail'
            version_detail = 'installed %r registered %r' % (resolved['version'],
                                                             package['version'])
            if not version_ok:
                problems.append('package %s version %r differs from the registered %r'
                                % (package['id'], resolved['version'], package['version']))
        package_checks.append(item('package.%s.version' % package['id'], version_status,
                                   version_detail))

        licence_ok = bool(resolved['licence'])
        if not licence_ok:
            problems.append('package %s has no installed licence material' % package['id'])
        package_checks.append(item('package.%s.licence' % package['id'],
                                   'pass' if licence_ok else 'fail',
                                   ('%s %s' % (resolved['licence']['mode'],
                                               resolved['licence']['path']))
                                   if licence_ok else 'none'))

        own = [entry['path'] for entry in resolved['archives']]
        external = packages.external_from_symbols(own, symbols)
        expected = [packages.canonical(name) for name in package['system'][args.platform]]
        directive_names = sorted({packages.canonical(name) for path in own
                                  for name in directives.get(path, [])})
        observed = sorted(set(packages.canonical(name) for name in external['families'])
                          | set(directive_names))
        expected_missing = sorted(name for name in expected if name not in observed)
        section.update({'external': external, 'external_expected': expected,
                        'external_observed': observed, 'external_missing': expected_missing,
                        'directives': directive_names})
        if expected_missing:
            problems.append('package %s does not show its registered system dependency: %r'
                            % (package['id'], expected_missing))
        package_checks.append(item('package.%s.external' % package['id'],
                                   'pass' if not expected_missing else 'fail',
                                   'expected %r observed %r' % (expected, observed)))

        bundled_ok = True
        section['bundled'] = []
        for bundled in package['bundled']:
            library_providers = providers.get(bundled['library'], [])
            material_present = bundled['material'] in index
            if bundled['archive'] not in ' '.join(library_providers) or not material_present:
                bundled_ok = False
                problems.append('package %s does not ship its bundled %s provider or material'
                                % (package['id'], bundled['library']))
            section['bundled'].append({'library': bundled['library'],
                                       'archive': bundled['archive'],
                                       'material': bundled['material'],
                                       'providers': library_providers,
                                       'material_present': material_present})
        package_checks.append(item('package.%s.bundled' % package['id'],
                                   'pass' if bundled_ok else 'fail',
                                   '%r' % [entry['library'] for entry in package['bundled']]))

        target = 'consumer-%s' % package['id']
        record = None
        for candidate_name in (target, target + '.exe'):
            candidate, _, code = commands.run('link command %s' % candidate_name, 'ninja-link',
                                              ['ninja', '-C', str(args.consumers.resolve()),
                                               '-t', 'commands', candidate_name])
            if code == 0 and candidate.get('entries'):
                record = candidate
                break
        if record is None:
            problems.append('no recorded link command for ' + target)
            section.update({'link': None, 'link_evidence': None})
            package_checks.append(item('package.%s.link' % package['id'], 'fail',
                                       'link command unavailable'))
        else:
            tokens = [entry['name'] for entry in record['entries']]
            evidence = packages.link_evidence(tokens, archive_names,
                                              package['system'][args.platform])
            own_names = {entry['name'] for entry in resolved['archives']}
            own_linked = sorted(own_names & set(evidence['archives']))
            if sorted(own_names) != own_linked:
                problems.append('package %s archive is not on its own link line: %r'
                                % (package['id'], sorted(own_names - set(own_linked))))
            if evidence['expected_missing']:
                problems.append('package %s link line lacks %r'
                                % (package['id'], evidence['expected_missing']))
            linked_ok = sorted(own_names) == own_linked and not evidence['expected_missing']
            package_checks.append(item('package.%s.link' % package['id'],
                                       'pass' if linked_ok else 'fail',
                                       '%d prefix archives, system %r, frameworks %r'
                                       % (len(evidence['archives']),
                                          evidence['system_libraries'], evidence['frameworks'])))
            section.update({'link': record, 'link_evidence': evidence})
        section['checks'] = package_checks
        checks.extend(package_checks)
        package_sections.append(section)

    present = {section['id'] for section in package_sections}
    registered_ok = present == set(packages.REGISTERED_IDS)
    if not registered_ok:
        problems.append('registered packages differ from the installed prefix')
    checks.append(item('packages.registered', 'pass' if registered_ok else 'fail',
                       '%d registered, %d present'
                       % (len(packages.REGISTERED_IDS), len(present))))

    secrets = contract.scan_test_secrets(payload, PREFIX)
    if secrets:
        problems.append('test secret material inside the distributed prefix: '
                        + repr([hit['path'] for hit in secrets]))
    checks.append(item('inclusions.no_test_secrets', 'pass' if not secrets else 'fail',
                       '%d hits' % len(secrets)))

    forbidden, observations = contract.scan_forbidden(
        payload, {'config': {'cache_switches': switches}, 'identity': identity,
                  'dynamic_dependencies': {'entries': []}}, allow_credentials=True)
    problems += forbidden
    credential_material = sorted(observations['credential_files'])
    credential_ok = bool(credential_material) and all(
        any(marker in path for marker in CREDENTIAL) for path in credential_material)
    if not credential_ok:
        problems.append('the only credential material in the prefix must be the registered package')
    checks.append(item('packages.credentials_registered', 'pass' if credential_ok else 'fail',
                       '%d credential material files: %r'
                       % (len(credential_material), credential_material[:6])))
    audio_web = [problem for problem in forbidden
                 if 'audio' in problem or 'web engine' in problem]
    checks.append(item('inclusions.no_audio_or_webview', 'pass' if not audio_web else 'fail',
                       'audio %r web %r' % (observations['audio_files'],
                                            observations['webview_files'])))

    needles = list(contract.GENERIC_PRIVATE_PATHS)
    for extra in (os.environ.get('GITHUB_WORKSPACE'), str(ROOT), str(prefix),
                  os.environ.get('HOME'), os.environ.get('USERPROFILE')):
        if extra:
            cleaned = str(extra).replace('/', os.sep).rstrip(os.sep)
            needles.extend([cleaned + os.sep, cleaned])
    hits = contract.scan_private_paths(payload, needles)
    leaked = sorted({hit['path'] for hit in hits})
    blockers.extend(contract.private_path_blockers(hits))
    checks.append(item('inclusions.no_machine_paths', 'pass' if not leaked else 'blocked',
                       '%d installed files contain a private absolute path' % len(leaked)))
    generic = set(contract.GENERIC_PRIVATE_PATHS)
    private_paths = {'generic_needles': list(contract.GENERIC_PRIVATE_PATHS),
                     'needles_checked': len(needles),
                     'needle_digests': sorted({contract.digest(n.encode('utf-8'))[:16]
                                               for n in needles}),
                     'hits': [{'path': path,
                               'needles': sorted({hit['needle'] for hit in hits
                                                  if hit['path'] == path
                                                  and hit['needle'] in generic}),
                               'needle_digests': sorted({contract.digest(hit['needle'].encode('utf-8'))[:16]
                                                         for hit in hits
                                                         if hit['path'] == path})}
                              for path in leaked]}

    components = list(sdk_licences['components'])
    for section in package_sections:
        installed = []
        if section['licence']:
            installed = [{'installed': section['licence']['path'], 'origin': 'repository',
                          'source': 'LICENSE', 'expected': True,
                          'bytes': section['licence']['bytes'],
                          'sha256': section['licence']['sha256'], 'pinned_sha256': None}]
        components.append({
            'id': section['id'], 'name': section['name'],
            'version': section['registered_version'] or 'unversioned',
            'license': 'MIT', 'source': 'repository', 'archive_sha256': None,
            'when': 'combined profile', 'linkage': 'private static archive', 'active': True,
            'vendor_files': [], 'notice_marker': None, 'files': installed,
            'archives': [{'path': entry['path'], 'name': entry['name'],
                          'bytes': entry['bytes'], 'sha256': entry['sha256']}
                         for entry in section['archives']],
            'notice': {'notices_path': section['licence']['path'] if section['licence'] else None,
                       'notices_sha256': section['licence']['sha256'] if section['licence'] else None,
                       'marker': 'MIT', 'described': bool(section['licence'])}})

    created = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    inventory = {
        'schema': 1, 'scope': SCOPE, 'profile': 'combined', 'platform': args.platform,
        'runner_os': args.runner_os, 'architecture': args.architecture,
        'source_sha': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(ROOT),
                                     capture_output=True, text=True).stdout.strip() or None,
        'identity': identity,
        'config': {'sdk_preset': 'reading-library', 'sdk_switches': switches,
                   'packages': [section['id'] for section in package_sections]},
        'installed_files': files,
        'totals': {'files': len(files), 'bytes': sum(record['bytes'] for record in files),
                   'packages': len(package_sections),
                   'package_archives': sum(len(section['archives'])
                                           for section in package_sections),
                   'all_archives': len(archives)},
        'license_materials': {'checker': sdk_checker, 'components': components},
        'packages': package_sections,
        'static_dependency': {
            'sdk_archives': sdk_archives,
            'archives': [{'path': path, 'name': path.split('/')[-1],
                          'bytes': by_path[path]['bytes'], 'sha256': by_path[path]['sha256'],
                          'members': members[path],
                          'defined_count': len(symbols[path]['defined']),
                          'undefined_count': len(symbols[path]['undefined']),
                          'defined_sha256': digest_text(symbols[path]['defined']),
                          'undefined_sha256': digest_text(symbols[path]['undefined'])}
                         for path in archives],
            'edges': edges, 'unreferenced_archives': unreferenced, 'owners': owners,
            'foreign_archives': [], 'directives': directives},
        'dependency_commands': commands.records,
        'observations': observations, 'private_paths': private_paths,
        'not_covered': NOT_COVERED,
    }
    spdx = sbom.build_spdx(inventory, created)
    cdx = sbom.build_cyclonedx(inventory, created)
    spdx_problems = sbom.validate_spdx(spdx, inventory)
    cdx_problems = sbom.validate_cyclonedx(cdx, inventory)
    problems += spdx_problems + cdx_problems
    checks.append(item('sbom.spdx', 'pass' if not spdx_problems else 'fail',
                       '%d packages, %d files' % (len(spdx['packages']), len(spdx['files']))))
    checks.append(item('sbom.cyclonedx', 'pass' if not cdx_problems else 'fail',
                       '%d components' % len(cdx['components'])))

    generated, leaks = {}, []
    for name, document in (('combined.spdx.json', spdx), ('combined.cdx.json', cdx)):
        data = json.dumps(document, indent=2, ensure_ascii=False).encode('utf-8') + b'\n'
        (output / name).write_bytes(data)
        generated[name] = {'bytes': len(data), 'sha256': contract.digest(data)}
        if any(needle.encode('utf-8') in data for needle in contract.GENERIC_PRIVATE_PATHS):
            leaks.append(name)
    if leaks:
        problems.append('generated SBOM contains a build-machine path: ' + repr(leaks))
    checks.append(item('sbom.no_machine_paths', 'pass' if not leaks else 'fail', repr(leaks)))

    inventory.update({'checks': checks, 'problems': problems, 'release_blockers': blockers,
                      'sbom': generated,
                      'generated': {'inventory': True,
                                    'sbom': not spdx_problems and not cdx_problems},
                      'materials_complete': not problems,
                      'release_ready': not problems and not blockers,
                      'run': {'id': os.environ.get('GITHUB_RUN_ID'),
                              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                              'job': os.environ.get('GITHUB_JOB')}})
    (output / 'combined.json').write_bytes(
        (json.dumps(inventory, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))
    print(json.dumps({'platform': args.platform, 'files': len(files),
                      'packages': [section['id'] for section in package_sections],
                      'checks': len(checks), 'problems': problems,
                      'release_blockers': len(blockers),
                      'release_ready': inventory['release_ready'], 'sbom': generated}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
