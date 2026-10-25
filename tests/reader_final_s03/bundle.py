#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Dependency, resource and product-library manifest for one macOS .app candidate.

The bundle is assembled by the producer's own tools; this module only reads the
resulting bytes and the recorded tool output. It reuses the offline distribution
contract (tests/reader_distribution_inventory/contract.py) for digests and for
the private-path and test-secret scans instead of restating them.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import posixpath
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'tests/reader_distribution_inventory'))
sys.path.insert(0, str(HERE))
import contract as distribution
import spec

MAX_REPORTED_DEPENDENCIES = 400


def command(*arguments):
    done = subprocess.run([str(item) for item in arguments], capture_output=True, text=True,
                          errors='replace')
    return done.returncode, done.stdout + done.stderr


def macho(path):
    code, text = command('file', path)
    return code == 0 and 'Mach-O' in text


def archs(path):
    code, text = command('lipo', '-archs', path)
    if code == 0:
        return text.split()
    return ['unknown']


def load_commands(path):
    """Return LC_RPATH entries, LC_BUILD_VERSION/LC_VERSION_MIN data and LC_ID_DYLIB."""
    code, text = command('otool', '-l', path)
    if code != 0:
        return [], {}, None
    lines = text.splitlines()
    rpaths, identity = [], None
    build = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'cmd LC_RPATH':
            for follow in lines[index + 1:index + 6]:
                match = re.match(r'\s*path (.+) \(offset \d+\)$', follow)
                if match:
                    rpaths.append(match.group(1))
                    break
        elif stripped == 'cmd LC_BUILD_VERSION':
            for follow in lines[index + 1:index + 9]:
                match = re.match(r'\s*(platform|minos|sdk)\s+(\S+)$', follow)
                if match:
                    build[match.group(1)] = match.group(2)
        elif stripped == 'cmd LC_VERSION_MIN_MACOSX':
            for follow in lines[index + 1:index + 7]:
                match = re.match(r'\s*(version|sdk)\s+(\S+)$', follow)
                if match:
                    key = 'minos' if match.group(1) == 'version' else 'sdk'
                    build.setdefault(key, match.group(2))
                    build.setdefault('platform', '1')
        elif stripped == 'cmd LC_ID_DYLIB':
            for follow in lines[index + 1:index + 5]:
                match = re.match(r'\s*name (.+) \(offset \d+\)$', follow)
                if match:
                    identity = match.group(1)
                    break
    return rpaths, build, identity


def dependencies(path, identity):
    code, text = command('otool', '-L', path)
    if code != 0:
        return None
    names = [entry['name'] for entry in distribution.parse_entries('otool', text)]
    if identity and identity in names:
        names.remove(identity)
    return names


def stage_license_digests(stage):
    digests = {}
    root = stage / 'share/exreader/licenses'
    if not root.is_dir():
        return digests
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink():
            digests[path.relative_to(root).as_posix()] = spec.digest(path)
    return digests


def provenance(app, producer, stage):
    records = []
    resources = app / spec.BUNDLE_RESOURCES
    for name, relative in sorted(spec.CANONICAL_RESOURCE_SOURCES.items()):
        bundled = resources / name
        source = producer / relative
        records.append({'bundle_path': name, 'source': 'producer:' + relative,
                        'expected': spec.digest(source) if source.is_file() else None,
                        'observed': spec.digest(bundled) if bundled.is_file() else None})
    for name, pin in sorted(spec.FONT_PINS.items()):
        bundled = resources / name
        records.append({'bundle_path': name, 'source': 'tools/host_font.py pin',
                        'expected': pin,
                        'observed': spec.digest(bundled) if bundled.is_file() else None})
    for name, digest in sorted(stage_license_digests(stage).items()):
        bundled = resources / spec.LICENSE_DIR / name
        records.append({'bundle_path': spec.LICENSE_DIR + '/' + name,
                        'source': 'installed sdk licences',
                        'expected': digest,
                        'observed': spec.digest(bundled) if bundled.is_file() else None})
    return records


def product_library(producer, app, producer_output, symbols_path, candidate):
    """Re-run the producer's own product checker, then count raw providers again."""
    problems = []
    executable = app / spec.BUNDLE_EXECUTABLE
    mapping = producer_output / 'product-link.map'
    output = symbols_path.parent / ('product-library-' + candidate + '.json')
    code, text = command(sys.executable, producer / 'tools/check_apple_product.py',
                         '--binary', executable, '--map', mapping, '--output', output)
    record = None
    if output.is_file():
        record = json.loads(output.read_text(encoding='utf-8'))
    if code != 0 or record is None or record.get('accepted') is not True:
        problems.append('product_library_rejected')
    code_nm, symbols = command('nm', '-g', executable)
    if code_nm != 0:
        problems.append('product_symbols_unavailable')
        symbols = ''
    symbols_path.write_text(symbols, encoding='utf-8')
    map_text = mapping.read_text(encoding='utf-8', errors='replace') if mapping.is_file() else ''
    raw = {}
    for symbol, archive, unit in spec.RAW_PROVIDERS:
        definitions = re.findall(r'(?m)^.*\b[Tt]\s+_' + symbol + r'\s*$', symbols)
        providers = [line for line in map_text.splitlines()
                     if ('lib' + archive + '.a') in line and (unit + '.cpp.o') in line]
        raw[symbol] = {'definitions': len(definitions), 'providers': len(providers)}
        if spec.candidate(candidate)['selector_bytes']:
            if len(definitions) != 1 or len(providers) != 1:
                problems.append('raw_provider:' + symbol)
        elif symbol in ('reader_revisions_open_raw_v3', 'reader_rc_apply_raw_v3') \
                and definitions:
            problems.append('raw_provider_in_default:' + symbol)
    linked = producer_output / 'product-link.json'
    link = json.loads(linked.read_text(encoding='utf-8')) if linked.is_file() else None
    expected_sha = spec.digest(executable)
    if link is None:
        problems.append('product_link_missing')
    else:
        if link.get('accepted') is not True:
            problems.append('product_link_rejected')
        if link.get('binary_sha256') != expected_sha:
            problems.append('product_link_binary_sha')
        flag = link.get('selector_bytes_candidate')
        if not isinstance(flag, bool) or flag != spec.candidate(candidate)['selector_bytes']:
            problems.append('product_link_selector_flag')
        if record is not None and record.get('binary_sha256') != expected_sha:
            problems.append('product_library_binary_sha')
    return {'record': record, 'product_link': link, 'raw_providers': raw,
            'problems': problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--producer-output', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--candidate', choices=sorted(spec.CANDIDATES), required=True)
    parser.add_argument('--source-sha', default=spec.PRODUCER_SHA)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    app = args.app.absolute()
    producer = args.producer.absolute()
    stage = args.stage.absolute()
    output = args.producer_output.absolute()
    problems = []
    if not app.is_dir():
        raise SystemExit('missing candidate bundle: ' + str(app))

    files, links = spec.file_map(app)
    info_path = app / spec.INFO_PLIST
    info = plistlib.loads(info_path.read_bytes()) if info_path.is_file() else None
    problems += spec.plist_problems(info, args.candidate, args.source_sha)

    symlink_escape = []
    for relative, target in sorted(links.items()):
        if target.startswith('/') or '..' in target.split('/'):
            symlink_escape.append(relative + '->' + target)
    if symlink_escape:
        problems.append('symlink_escape:' + ','.join(symlink_escape))

    machos = [relative for relative in sorted(files) if macho(app / relative)]
    if spec.BUNDLE_EXECUTABLE not in machos:
        problems.append('executable_not_macho')
    arch_map = {relative: archs(app / relative) for relative in machos}
    command_map = {relative: load_commands(app / relative) for relative in machos}
    build_map = {relative: command_map[relative][1] for relative in machos}
    problems += spec.architecture_problems(arch_map)
    problems += spec.build_version_problems(build_map)

    executable_dir = str((app / 'Contents/MacOS').resolve())
    bundle_root = str(app.resolve())
    records = []
    for relative in machos:
        rpaths, _, identity = command_map[relative]
        loader_dir = str((app / relative).parent.resolve())
        names = dependencies(app / relative, identity)
        if names is None:
            problems.append('otool_failed:' + relative)
            continue
        for name in names:
            kind, resolved = spec.resolve_install_name(name, rpaths, executable_dir,
                                                       loader_dir, bundle_root)
            records.append({'owner': relative, 'install_name': name, 'kind': kind,
                            'resolved': resolved})
    problems += spec.dependency_problems(records, files)
    problems += spec.reachability_problems(records, machos)
    problems += spec.sdk_uniqueness_problems(files, records)
    libraries = [path for path in files
                 if path.startswith(spec.BUNDLE_FRAMEWORKS + '/')
                 and posixpath.basename(path).startswith(spec.SDK_LIBRARY_TOKEN)]
    sdk_library = {path: files[path] for path in libraries}
    for path in sdk_library:
        sdk_library[path]['install_name'] = command_map[path][2]

    resources = spec.sub_map(files, spec.BUNDLE_RESOURCES)
    resource_digests = {path: entry['sha256'] for path, entry in resources.items()}
    problems += spec.resource_problems(resources, resource_digests)
    problems += spec.license_copy_problems(stage_license_digests(stage), resource_digests)
    records_provenance = provenance(app, producer, stage)
    problems += spec.provenance_problems(records_provenance)

    manifest_path = output / 'build.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else None
    problems += spec.build_manifest_problems(manifest, files, args.source_sha, args.candidate)

    symbols_path = args.output / ('product-symbols-' + args.candidate + '.txt')
    product = product_library(producer, app, output, symbols_path, args.candidate)
    problems += product['problems']

    payload = {'stage/' + path: (app / path).read_bytes() for path in files}
    private_hits = distribution.scan_private_paths(payload, distribution.GENERIC_PRIVATE_PATHS)
    secret_hits = distribution.scan_test_secrets(payload, 'stage/')
    if secret_hits:
        problems.append('test_secret_in_bundle:' + str(len(secret_hits)))

    report = {
        'schema': 1,
        'candidate': args.candidate,
        'label': spec.candidate(args.candidate)['label'],
        'selector_bytes_candidate': spec.candidate(args.candidate)['selector_bytes'],
        'verifier_package': 'tests/reader_final_s03',
        'producer_sha': args.source_sha,
        'sdk_version': spec.SDK_VERSION,
        'app': str(app),
        'bundle_bytes': sum(entry['bytes'] for entry in files.values()),
        'file_count': len(files),
        'info_plist': info,
        'info_plist_unexpected_keys': spec.plist_unexpected_keys(info) if isinstance(info, dict) else [],
        'architecture': arch_map,
        'build_version': build_map,
        'rpaths': {relative: command_map[relative][0] for relative in machos},
        'dependencies': records[:MAX_REPORTED_DEPENDENCIES],
        'dependency_count': len(records),
        'sdk_library': sdk_library,
        'resources': resources,
        'licenses': {path: digest for path, digest in resource_digests.items()
                     if path.startswith(spec.LICENSE_DIR + '/')},
        'provenance': records_provenance,
        'build_manifest': manifest,
        'product_library': product['record'],
        'product_link': product['product_link'],
        'raw_providers': product['raw_providers'],
        'private_path_hits': private_hits,
        'test_secret_hits': secret_hits,
        'release_ready': not private_hits and not secret_hits,
        'problems': problems,
        'accepted': not problems,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / ('manifest-' + args.candidate + '.json')
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'candidate': args.candidate, 'accepted': report['accepted'],
                      'files': report['file_count'], 'bundle_bytes': report['bundle_bytes'],
                      'executable_arch': arch_map.get(spec.BUNDLE_EXECUTABLE),
                      'dependencies': len(records), 'sdk_library': sorted(sdk_library),
                      'private_path_hits': len(private_hits),
                      'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
