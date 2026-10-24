#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate one install's offline distribution inventory, SBOM and notices list.

The generator only reads an installed stage produced by a reading preset plus the
shared registered licence record. Every dependency claim comes from a recorded
tool invocation whose captured output is stored beside the report, so the
same-source aggregate can re-derive each list from those raw bytes.
"""
import argparse
import datetime
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
import sbom

SCOPE = ('One installed reading SDK (file inventory, registered third-party materials, observed '
         'static and dynamic dependencies, licence originals and notice sources). Materials '
         'inventory, not a legal conclusion. Mobile packaging, host bundles and publication are '
         'outside this document.')
NOT_COVERED = [
    'Android, iOS and Apple native host packaging: separate owners, not built or packed here',
    'GTK/Linux, Windows and macOS native host bundles and their Noto Sans CJK host font',
    'Audio builds: EXR_ENABLE_AUDIO and the MP3/AAC codecs are excluded from the reading presets',
    'PDF editing, text index, shared compatibility library, JNI bindings, tools and test binaries',
    'Offline installer, code signing, notarization, tag, Release and store publication',
    'Legal review: the registered licence identifiers are inventoried, not adjudicated',
]
def run_command(argv, cwd=None):
    done = subprocess.run([str(item) for item in argv], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, errors='replace')
    return {'command': [str(item) for item in argv], 'exit_code': done.returncode,
            'output': done.stdout + done.stderr}


class Commands:
    """Every dependency claim is one recorded invocation with its captured output."""

    def __init__(self, directory):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.records = []

    def run(self, purpose, kind, argv, strip_underscore=False, archive=None):
        slug = re.sub(r'[^a-z0-9]+', '-', purpose.lower()).strip('-')[:56]
        name = '%02d-%s.txt' % (len(self.records) + 1, slug)
        result = run_command(argv)
        text = result['output']
        (self.directory / name).write_bytes(text.encode('utf-8'))
        record = contract.dependency_record(kind, purpose, result['command'], result['exit_code'],
                                          text, strip_underscore)
        record['raw_output_path'] = 'tools/' + name
        if archive:
            record['archive'] = archive
        self.records.append(record)
        return record, text, result['exit_code']


def scan_stage(stage):
    records, problems = [], []
    for path in sorted(stage.rglob('*')):
        if path.is_symlink():
            problems.append('installed tree contains a symbolic link: ' + path.relative_to(stage).as_posix())
            continue
        if not path.is_file():
            continue
        records.append({'path': path.relative_to(stage).as_posix(), 'bytes': path.stat().st_size,
                        'sha256': contract.digest(path), 'sha1': contract.digest1(path)})
    return records, problems


def payload_of(stage, records):
    return {'stage/' + record['path']: (stage / record['path']).read_bytes() for record in records}


def archive_key(name):
    base = name
    if base.startswith('lib'):
        base = base[3:]
    base = re.sub(r'\.(?:a|lib)$', '', base)
    for prefix, kind in (('exr_vendor_', 'vendor'), ('exr_', 'sdk')):
        if base.startswith(prefix):
            return kind, base[len(prefix):]
    return 'other', base


def inventory_archives(stage):
    sdk, vendor, other = [], [], []
    base = stage / 'lib'
    for path in sorted(base.iterdir()) if base.is_dir() else []:
        if path.is_file() and re.fullmatch(r'(?:lib)?exr_.+\.(?:a|lib)', path.name):
            kind = archive_key(path.name)[0]
            (sdk if kind == 'sdk' else other).append(path)
    nested = base / 'exreader'
    for path in sorted(nested.iterdir()) if nested.is_dir() else []:
        if path.is_file() and re.fullmatch(r'(?:lib)?exr_vendor_.+\.(?:a|lib)', path.name):
            kind = archive_key(path.name)[0]
            (vendor if kind == 'vendor' else other).append(path)
    return sdk, vendor, other


def static_section(stage, commands, host, installed):
    sdk_paths_list, vendor_paths, others = inventory_archives(stage)
    problems = []
    if not sdk_paths_list:
        problems.append('installed SDK component archives are missing')
    if others:
        problems.append('unrecognized archive names in lib/: ' + repr([path.name for path in others]))
    entries, symbols = [], {}
    for path in sdk_paths_list + vendor_paths:
        relative = path.relative_to(stage).as_posix()
        record = next((item for item in installed if item['path'] == relative), None)
        if record is None:
            problems.append('installed archive is not in the file inventory: ' + relative)
            continue
        if host == 'Windows':
            members, _, code = commands.run('archive members %s' % path.name, 'lib-list',
                                            ['lib', '/nologo', '/list', str(path)])
        else:
            members, _, code = commands.run('archive members %s' % path.name, 'ar', ['ar', 't', str(path)])
        if code != 0:
            problems.append('cannot list members of ' + relative)
        if host == 'Windows':
            symbol_record, symbol_text, code = commands.run(
                'archive symbols %s' % path.name, 'dumpbin-symbols', ['dumpbin', '/nologo', '/symbols', str(path)],
                archive=relative)
        else:
            symbol_record, symbol_text, code = commands.run(
                'archive symbols %s' % path.name, 'nm', ['nm', str(path)],
                strip_underscore=(host == 'Darwin'), archive=relative)
        if code != 0:
            problems.append('cannot read symbols of ' + relative)
        symbols[relative] = contract.symbol_summary(
            contract.parse_entries(symbol_record['kind'], symbol_text, symbol_record['strip_underscore']))
        entries.append({'path': relative, 'name': path.name, 'bytes': record['bytes'],
                        'sha256': record['sha256'],
                        'members': [item['name'] for item in members['entries']],
                        'defined_count': symbol_record['summary']['defined_count'],
                        'undefined_count': symbol_record['summary']['undefined_count'],
                        'defined_sha256': symbol_record['summary']['defined_sha256'],
                        'undefined_sha256': symbol_record['summary']['undefined_sha256']})
    sdk_archives = [path.relative_to(stage).as_posix() for path in sdk_paths_list]
    edges = contract.symbol_edges(symbols, symbols)
    reached = contract.reachable(edges, [path for path in sdk_archives if path in symbols], set(symbols))
    unreferenced = sorted(path for path in symbols
                          if path not in sdk_archives and not any(edge['to'] == path for edge in edges))
    return {'sdk_archives': sdk_archives, 'archives': entries, 'edges': edges,
            'unreferenced_archives': unreferenced, 'reachable_archives': sorted(reached)}, problems


def link_section(commands, build, target, installed_archives):
    record = None
    for name in (target, target + '.exe'):
        candidate, _, code = commands.run('link command %s' % name, 'ninja-link',
                                          ['ninja', '-C', str(build), '-t', 'commands', name])
        if code == 0 and candidate.get('entries'):
            record = candidate
            break
    if record is None:
        return None, [], []
    distributed, system, _ = contract.classify_link_tokens(
        [entry['name'] for entry in record['entries']], set(installed_archives))
    record['distributed_archives'] = distributed
    record['system_libraries'] = system
    return record, distributed, system


def dynamic_section(commands, consumer, host):
    if host == 'Windows':
        record, _, _ = commands.run('dynamic dependencies', 'dumpbin-dependents',
                                    ['dumpbin', '/nologo', '/dependents', str(consumer)])
        return {'record': record, 'resolution': None}
    if host == 'Darwin':
        record, _, _ = commands.run('dynamic dependencies', 'otool', ['otool', '-L', str(consumer)])
        return {'record': record, 'resolution': None}
    record, _, _ = commands.run('dynamic dependencies', 'readelf-dynamic', ['readelf', '-d', str(consumer)])
    resolution, _, _ = commands.run('dynamic resolution', 'ldd', ['ldd', str(consumer)])
    return {'record': record, 'resolution': resolution}


def identity_section(stage, probe):
    problems = []
    header = stage / 'include/exr/base.h'
    text = header.read_text(encoding='utf-8') if header.is_file() else ''
    version = re.search(r'#define\s+EXR_VERSION\s+"([^"]+)"', text)
    abi = re.search(r'#define\s+EXR_ABI_VERSION\s+(\d+)', text)
    core = re.search(r'#define\s+EXR_CORE_VERSION\s+"([^"]+)"', text)
    if not version or not abi:
        problems.append('installed public header does not declare the SDK version or ABI')
    config = stage / 'lib/cmake/EXReader/EXReaderConfigVersion.cmake'
    config_text = config.read_text(encoding='utf-8') if config.is_file() else ''
    config_version = re.search(r'set\(PACKAGE_VERSION\s+"([^"]+)"\)', config_text)
    if not config_version:
        problems.append('installed package configuration has no version')
    targets = stage / 'lib/cmake/EXReader/EXReaderTargets.cmake'
    target_text = targets.read_text(encoding='utf-8') if targets.is_file() else ''
    exported = sorted(set(re.findall(
        r'add_library\(EXReader::([A-Za-z0-9_]+)\s+(?:STATIC|INTERFACE|SHARED)\s+IMPORTED\)', target_text)))
    if not exported:
        problems.append('installed package exports no targets')
    runtime = {}
    if probe is not None and Path(probe).is_file():
        done = subprocess.run([str(probe)], capture_output=True, text=True, errors='replace')
        if done.returncode != 0:
            problems.append('installed-API probe failed with exit code %d' % done.returncode)
        else:
            try:
                runtime = json.loads(done.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                problems.append('installed-API probe did not report JSON')
    else:
        problems.append('installed-API probe is missing')
    return {'version': version.group(1) if version else None,
            'abi': int(abi.group(1)) if abi else None,
            'core_version': core.group(1) if core else None,
            'config_version': config_version.group(1) if config_version else None,
            'targets': exported, 'probe': runtime}, problems


def license_section(licenses_doc):
    by_id = {component['id']: component for component in registered.COMPONENTS}
    components = []
    for row in licenses_doc.get('components', []):
        source = by_id.get(row['id'], {})
        components.append({
            'id': row['id'], 'name': row['name'], 'version': row['version'],
            'license': row['license'], 'source': row['source'],
            'archive_sha256': row['archive_sha256'], 'when': row['when'],
            'linkage': row.get('linkage'), 'active': bool(row.get('active')),
            'vendor_files': list(source.get('vendor_files') or []),
            'notice_marker': source.get('notice_marker'),
            'files': [{'installed': item['installed'], 'origin': item['origin'],
                       'source': item['source'], 'expected': item['expected'],
                       'bytes': item.get('bytes'), 'sha256': item.get('sha256'),
                       'pinned_sha256': item.get('pinned_sha256')}
                      for item in row.get('files', [])],
            'archives': []})
    notices = ROOT / 'THIRD_PARTY_NOTICES.md'
    notices_sha = contract.digest(notices) if notices.is_file() else None
    notices_text = notices.read_text(encoding='utf-8') if notices.is_file() else ''
    for component in components:
        marker = component.get('notice_marker')
        component['notice'] = {'notices_path': 'THIRD_PARTY_NOTICES.md',
                               'notices_sha256': notices_sha, 'marker': marker,
                               'described': bool(marker) and marker in notices_text}
    return {'checker': {'release_ready': bool(licenses_doc.get('release_ready')),
                        'materials_check_passed': bool(licenses_doc.get('materials_check_passed')),
                        'failures': list(licenses_doc.get('failures') or []),
                        'pending': list(licenses_doc.get('pending') or []),
                        'mandatory_missing': list(licenses_doc.get('mandatory_missing') or []),
                        'source_sha': licenses_doc.get('source_sha'),
                        'components': len(licenses_doc.get('components') or [])},
            'components': components}


def item(check_id, status, detail=''):
    return {'id': check_id, 'status': status, 'detail': detail}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, choices=list(contract.PROFILES))
    parser.add_argument('--platform', required=True, choices=list(contract.PLATFORMS))
    parser.add_argument('--runner-os', required=True)
    parser.add_argument('--architecture', default='')
    parser.add_argument('--build', required=True, type=Path)
    parser.add_argument('--stage', required=True, type=Path)
    parser.add_argument('--licenses', required=True, type=Path)
    parser.add_argument('--consumer', required=True, type=Path)
    parser.add_argument('--probe', required=True, type=Path)
    parser.add_argument('--probe-build', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()

    build = args.build.resolve()
    stage = args.stage.resolve()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    commands = Commands(output / 'tools')
    checks, problems, blockers = [], [], []

    stage_files, stage_problems = scan_stage(stage)
    problems += stage_problems
    payload = payload_of(stage, stage_files)
    cache = registered.read_cache(build / 'CMakeCache.txt')
    switches = {key: contract.config_switch(value) for key, value in cache.items() if key.startswith('EXR_')}
    preset = registered.preset_switches(ROOT, args.profile)
    modules_path = build / 'exr-modules.json'
    modules = json.loads(modules_path.read_text(encoding='utf-8')) if modules_path.is_file() else {}
    layers = modules.get('layers') or []

    switch_problems = contract.verify_module_switches({'config': {'cache_switches': switches}}, preset)
    problems += switch_problems
    checks.append(item('config.cache_matches_preset', 'pass' if not switch_problems else 'fail',
                       '%d observed EXR_* switches equal the %s preset' % (len(switches), args.profile)))
    audio = {key: switches.get(key) for key in ('EXR_ENABLE_AUDIO', 'EXR_ENABLE_MP3', 'EXR_ENABLE_AAC')}
    audio_ok = all(value == 'OFF' for value in audio.values())
    checks.append(item('config.audio_disabled', 'pass' if audio_ok else 'fail', repr(audio)))
    layer_ok = not ({'audio', 'textindex', 'pdf_edit'} & set(layers))
    if not layer_ok:
        problems.append('optional module layer built into the reading profile: ' + repr(layers))
    checks.append(item('config.layers', 'pass' if layer_ok else 'fail', repr(layers)))
    library_ok = ('library' in layers) == (switches.get('EXR_ENABLE_LIBRARY') == 'ON')
    if not library_ok:
        problems.append('library layer does not match EXR_ENABLE_LIBRARY')
    checks.append(item('config.library_layer_matches_profile', 'pass' if library_ok else 'fail',
                       'library=%r EXR_ENABLE_LIBRARY=%s' % ('library' in layers,
                                                             switches.get('EXR_ENABLE_LIBRARY'))))

    identity, identity_problems = identity_section(stage, args.probe.resolve())
    problems += identity_problems
    identity_checks = contract.verify_identity(identity)
    problems += identity_checks
    checks.append(item('identity.installed_header', 'pass' if identity['version'] and identity['abi'] else 'fail',
                       'version %s ABI %s core %s' % (identity['version'], identity['abi'],
                                                      identity['core_version'])))
    probe_ok = identity.get('probe', {}).get('version') == identity['version'] and \
        identity.get('probe', {}).get('abi') == identity['abi']
    checks.append(item('identity.runtime_probe', 'pass' if probe_ok else 'fail', repr(identity.get('probe'))))
    config_ok = identity.get('config_version') == identity['version']
    checks.append(item('identity.package_config', 'pass' if config_ok else 'fail',
                       'config %r header %r' % (identity.get('config_version'), identity['version'])))

    file_problems = contract.verify_installed(payload, stage_files)
    problems += file_problems
    checks.append(item('files.complete', 'pass' if not file_problems else 'fail',
                       '%d installed files, %d bytes'
                       % (len(stage_files), sum(record['bytes'] for record in stage_files))))
    empty = [record['path'] for record in stage_files if not record['bytes']]
    if empty:
        problems.append('zero-byte installed file: ' + repr(empty[:8]))
    checks.append(item('files.nonempty', 'pass' if not empty else 'fail', repr(empty[:8])))

    licenses_doc = contract.decode_json(args.licenses.read_bytes())
    licenses = license_section(licenses_doc)

    def enabled(expression):
        return registered.enabled(expression, switches)

    expected = contract.expected_license_paths(registered.COMPONENTS, enabled)
    license_problems = contract.verify_license_materials(stage_files, payload, expected, registered.COMPONENTS)
    problems += license_problems
    checks.append(item('licenses.installed_matches_pin', 'pass' if not license_problems else 'fail',
                       '%d registered licence materials for %s' % (len(expected), args.profile)))
    undescribed = [row['id'] for row in licenses['components']
                   if row['active'] and row['notice']['marker'] and not row['notice']['described']]
    if undescribed:
        problems.append('THIRD_PARTY_NOTICES.md does not describe active components: ' + repr(undescribed))
    checks.append(item('licenses.notices_described', 'pass' if not undescribed else 'fail', repr(undescribed)))
    checker = licenses['checker']
    licensed = checker['release_ready'] and not checker['failures'] and not checker['pending'] \
        and not checker['mandatory_missing']
    if not licensed:
        problems.append('registered licence record is not release ready: failures=%r pending=%r missing=%r'
                        % (checker['failures'], checker['pending'], checker['mandatory_missing']))
    checks.append(item('licenses.registered_record', 'pass' if licensed else 'fail',
                       'release_ready=%s failures=%d pending=%d missing=%d'
                       % (checker['release_ready'], len(checker['failures']), len(checker['pending']),
                          len(checker['mandatory_missing']))))

    static, static_problems = static_section(stage, commands, args.runner_os, stage_files)
    problems += static_problems
    installed_archives = [entry['name'] for entry in static['archives']]
    link, distributed, system = link_section(commands, args.probe_build.resolve(), 'probe', installed_archives)
    if link is None:
        problems.append('cannot obtain the installed-API probe link command')
        checks.append(item('archives.link_line_complete', 'fail', 'link command unavailable'))
    else:
        missing = sorted(set(installed_archives) - set(distributed))
        if missing:
            problems.append('installed archives are not on the consumer link line: ' + repr(missing))
        checks.append(item('archives.link_line_complete', 'pass' if not missing else 'fail',
                           '%d distributed archives, %d system libraries'
                           % (len(distributed), len(system))))
    checks.append(item('archives.symbol_edges', 'pass' if static['edges'] else 'fail',
                       '%d symbol edges over %d archives'
                       % (len(static['edges']), len(static['archives']))))
    checks.append(item('archives.reachability',
                       'pass' if not static['unreferenced_archives'] else 'reported',
                       '%d archives, unreferenced: %r'
                       % (len(static['archives']), static['unreferenced_archives'])))
    static['owners'] = {}
    for component in licenses['components']:
        for path in static['archives']:
            if archive_key(path['name'])[1] in set(component['vendor_files']):
                static['owners'][path['path']] = component['id']

    dynamic = dynamic_section(commands, args.consumer.resolve(), args.runner_os)
    entries = dynamic['record']['entries']
    dynamic_ok = bool(entries)
    if not dynamic_ok:
        problems.append('consumer reports no native dynamic dependency')
    checks.append(item('dynamic.dependencies_parsed', 'pass' if dynamic_ok else 'fail',
                       '%d native dependencies of %s' % (len(entries), args.consumer.name)))

    inventory = {'schema': 1, 'scope': SCOPE, 'profile': args.profile, 'platform': args.platform,
                 'runner_os': args.runner_os, 'architecture': args.architecture,
                 'source_sha': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(ROOT),
                                              capture_output=True, text=True).stdout.strip() or None,
                 'identity': identity,
                 'config': {'cache_switches': switches, 'preset_switches': preset, 'layers': layers,
                            'modules_json_sha256': contract.digest(modules_path) if modules_path.is_file() else None},
                 'installed_files': stage_files,
                 'totals': {'files': len(stage_files),
                            'bytes': sum(record['bytes'] for record in stage_files),
                            'archives': len(installed_archives),
                            'archive_bytes': sum(entry['bytes'] for entry in static['archives'])},
                 'license_materials': licenses, 'static_dependency': static,
                 'link': {'record': link, 'distributed_archives': distributed,
                          'system_libraries': system} if link else None,
                 'dynamic_dependencies': {'record': dynamic['record'], 'resolution': dynamic['resolution'],
                                          'entries': entries},
                 'dependency_commands': commands.records, 'not_covered': NOT_COVERED}

    for component in inventory['license_materials']['components']:
        wanted = set(component['vendor_files'])
        component['archives'] = [{'path': entry['path'], 'name': entry['name'], 'bytes': entry['bytes'],
                                  'sha256': entry['sha256']}
                                 for entry in static['archives']
                                 if archive_key(entry['name'])[1] in wanted]

    forbidden, observations = contract.scan_forbidden(payload, inventory)
    problems += forbidden
    audio_leak = bool(observations['audio_files']) or not all(
        value == 'OFF' for value in observations['audio_switches'].values())
    web_leak = bool(observations['webview_files']) or bool(observations['webview_dependencies'])
    checks.append(item('inclusions.no_audio_or_gpl_options', 'pass' if not audio_leak else 'fail',
                       'audio files %r' % (observations['audio_files'],)))
    checks.append(item('inclusions.no_webview', 'pass' if not web_leak else 'fail',
                       'files %r dependencies %r' % (observations['webview_files'],
                                                     observations['webview_dependencies'])))
    credential_leak = bool(observations['credential_targets']) or bool(observations['credential_files'])
    if credential_leak:
        problems.append('credential module material is part of the reading distribution')
    checks.append(item('inclusions.no_test_credentials', 'pass' if not credential_leak else 'fail',
                       'targets %r files %r' % (observations['credential_targets'],
                                                observations['credential_files'])))

    needles = list(contract.GENERIC_PRIVATE_PATHS)
    for extra in (os.environ.get('GITHUB_WORKSPACE'), str(ROOT), str(build), str(stage),
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
    inventory['private_paths'] = {
        'generic_needles': list(contract.GENERIC_PRIVATE_PATHS), 'needles_checked': len(needles),
        'needle_digests': sorted({contract.digest(needle.encode('utf-8'))[:16] for needle in needles}),
        'hits': [{'path': path,
                  'needles': sorted({hit['needle'] for hit in hits
                                     if hit['path'] == path and hit['needle'] in generic}),
                  'needle_digests': sorted({contract.digest(hit['needle'].encode('utf-8'))[:16]
                                            for hit in hits if hit['path'] == path})}
                 for path in leaked]}

    epoch = os.environ.get('SOURCE_DATE_EPOCH')
    if epoch and epoch.isdigit():
        stamp = datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc)
    else:
        stamp = datetime.datetime.now(datetime.timezone.utc)
    created = stamp.strftime('%Y-%m-%dT%H:%M:%SZ')

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
    for name, document in (('inventory.spdx.json', spdx), ('inventory.cdx.json', cdx)):
        data = json.dumps(document, indent=2, ensure_ascii=False).encode('utf-8') + b'\n'
        (output / name).write_bytes(data)
        generated[name] = {'bytes': len(data), 'sha256': contract.digest(data)}
        if any(needle.encode('utf-8') in data for needle in contract.GENERIC_PRIVATE_PATHS):
            leaks.append(name)
    if leaks:
        problems.append('generated SBOM contains a build-machine path: ' + repr(leaks))
    checks.append(item('sbom.no_machine_paths', 'pass' if not leaks else 'fail', repr(leaks)))

    inventory.update({'checks': checks, 'problems': problems, 'release_blockers': blockers,
                      'observations': observations, 'sbom': generated,
                      'generated': {'inventory': True, 'sbom': not spdx_problems and not cdx_problems},
                      'materials_complete': not problems,
                      'release_ready': not problems and not blockers,
                      'run': {'id': os.environ.get('GITHUB_RUN_ID'),
                              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                              'job': os.environ.get('GITHUB_JOB')}})
    (output / 'inventory.json').write_bytes(
        (json.dumps(inventory, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))
    print(json.dumps({'profile': args.profile, 'platform': args.platform,
                      'files': inventory['totals']['files'], 'bytes': inventory['totals']['bytes'],
                      'checks': len(checks), 'problems': problems, 'release_blockers': blockers,
                      'release_ready': inventory['release_ready'], 'sbom': generated}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
