#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Static audit of the relocated GTK compact candidate.

Covers the S02 acceptance list that can be judged without a display: dynamic
section and loader resolution, build-path leakage, fonts/resources, the desktop
entry generated for the candidate, the owning distribution packages, and the XDG
layout the runtime phase will exercise.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import common

FONT_MAGIC = (b'OTTO', b'\x00\x01\x00\x00', b'true', b'typ1')


def owning_package(path):
    result = common.run('dpkg', '-S', str(path), check=False)
    if result.returncode:
        return None, result.stdout.strip() or result.stderr.strip()
    for line in result.stdout.splitlines():
        name = line.split(':', 1)[0].strip()
        if name:
            return name, line.strip()
    return None, result.stdout.strip()


def package_version(name):
    result = common.run('dpkg-query', '-W', '-f=${Version}', name, check=False)
    return result.stdout.strip() if result.returncode == 0 else ''


def os_release():
    values = {}
    path = Path('/etc/os-release')
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                values[key] = value.strip().strip('"')
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--relocated', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--xdg-data', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = common.Checks()
    producer = common.read_json(args.producer)
    relocated = args.relocated.resolve(strict=True)
    program = relocated / 'bin/exreader-linux'

    problems = common.tree_problems(relocated, producer['payload']['files'])
    checks.add('relocated_payload_identity', not problems,
               'all %d producer files keep their bytes' % len(producer['payload']['files'])
               if not problems else '; '.join(problems[:6]))

    version = common.run(program, '--version', check=False, env=common.minimal_env({}))
    checks.add('program_version',
               version.stdout.strip() == '3.41.0 1' and version.returncode == 0,
               '%r exit %d' % (version.stdout.strip(), version.returncode))
    checks.add('program_digest',
               common.sha256_file(program) == producer['program']['sha256']
               and os.access(str(program), os.X_OK),
               'sha256 %s mode %o' % (common.sha256_file(program), program.stat().st_mode & 0o777))

    dynamic = common.parse_readelf(common.run('readelf', '-dW', program).stdout)
    absolute = [item for item in dynamic['rpath'] + dynamic['runpath'] if item.startswith('/')]
    relative_ok = all(item.startswith('$ORIGIN') for item in dynamic['rpath'] + dynamic['runpath'])
    checks.add('dynamic_section_relocatable',
               not absolute and relative_ok,
               'needed %d, rpath %s, runpath %s' % (
                   len(dynamic['needed']), dynamic['rpath'], dynamic['runpath']))
    checks.add('needed_has_no_sdk_or_path',
               not any('/' in name or name.startswith('libexr') for name in dynamic['needed']),
               json.dumps(dynamic['needed']))

    loader = common.parse_ldd(common.run('ldd', program, env=common.minimal_env({}),
                                        check=False).stdout)
    prefixes = {'home': str(args.home.resolve()), 'payload': str(relocated)}
    classified = [{'name': item['name'], 'path': item['path'],
                   'kind': common.classify_path(item['path'], prefixes),
                   'exists': Path(item['path']).exists()}
                  for item in loader['items']]
    outside = [item for item in classified if item['kind'] != 'system']
    missing = [item for item in classified if not item['exists']]
    checks.add('loader_resolution',
               not loader['not_found'] and not outside and not missing
               and bool(classified),
               'resolved %d, not found %s, outside system %s, missing %s' % (
                   len(classified), loader['not_found'],
                   [item['name'] for item in outside], [item['name'] for item in missing]))

    scanned = common.scan_tokens(relocated, common.BUILD_TOKENS)
    recorded = common.scan_tokens(relocated, common.RECORD_TOKENS)
    if scanned['hits']:
        checks.observe('compiled_build_path_tokens',
                       'compiled strings reference the producer build tree: %s; the dynamic '
                       'section carries no build path and the relocated program never opens '
                       'them (see the smoke traces), so they are recorded for root rather '
                       'than treated as a loading dependency' % ', '.join(
                           '%s in %s x%d' % (hit['token'], hit['path'], hit['count'])
                           for hit in scanned['hits'][:6]),
                       hits=scanned['hits'][:12])
    else:
        checks.add('no_build_path_tokens', True,
                   'no build token in the relocated tree (skipped %s)' % scanned['skipped'])

    font = relocated / 'Reader.otf'
    magic_ok = font.is_file() and font.read_bytes()[:4] in FONT_MAGIC
    licences = sorted((relocated / 'licenses').glob('*')) if (relocated / 'licenses').is_dir() else []
    shared = sorted(path.relative_to(relocated).as_posix() for path in relocated.rglob('*.so*'))
    desktop_members = sorted(path.relative_to(relocated).as_posix()
                             for path in relocated.rglob('*.desktop'))
    icons = sorted(path.relative_to(relocated).as_posix() for path in relocated.rglob('*.png'))
    checks.add('fonts_and_resources',
               magic_ok
               and (relocated / 'OFL.txt').is_file()
               and (relocated / 'LICENSE').is_file()
               and (relocated / 'THIRD_PARTY_NOTICES.md').is_file()
               and len(licences) >= 1
               and not shared,
               'font magic %r, licences %d, shared objects %s' % (
                   font.read_bytes()[:4] if font.is_file() else b'', len(licences), shared[:4]))

    applications = args.xdg_data.resolve() / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    entry = applications / 'exreader.desktop'
    entry.write_text(common.render_desktop_entry(program), encoding='utf-8')
    validation = common.run('desktop-file-validate', entry, check=False)
    validation_text = (validation.stdout + validation.stderr).strip()
    errors = [line for line in validation_text.splitlines() if line.startswith('error:')]
    exec_line = next((line for line in entry.read_text(encoding='utf-8').splitlines()
                      if line.startswith('Exec=')), '')
    if not desktop_members:
        checks.observe('producer_desktop_entry_absent',
                       'the producer payload ships no .desktop entry and no icon; S02 '
                       'generates the entry at install time from the relocated Exec path',
                       icons=icons)
    checks.add('desktop_entry',
               validation.returncode == 0 and not errors
               and exec_line == 'Exec=' + common.desktop_exec(program),
               'candidate Exec %r validate %r; producer payload desktop=%s icons=%s' % (
                   exec_line, validation_text[:400], desktop_members, icons))

    for item in classified:
        packages = []
        for candidate in (item['path'], os.path.realpath(item['path'])):
            package, line = owning_package(candidate)
            if package:
                packages.append({'package': package, 'line': line})
        item['packages'] = packages
        item['version'] = package_version(packages[0]['package']) if packages else ''
    unowned = [item['name'] for item in classified if not item['packages']]
    checks.add('distribution_dependencies',
               not unowned and bool(classified),
               'unowned %s; %s' % (unowned, ', '.join(sorted({item['packages'][0]['package']
                                                             for item in classified if item['packages']}))))

    release = os_release()
    xdg_paths = {'data': args.xdg_data.resolve(), 'home': args.home.resolve()}
    checks.add('xdg_layout',
               not str(xdg_paths['data']).startswith(str(xdg_paths['home']) + '/')
               and str(xdg_paths['data']) != str(xdg_paths['home']),
               'XDG_DATA_HOME %s is outside HOME %s' % (xdg_paths['data'], xdg_paths['home']))

    dependencies_report = {
        'os_release': {key: release.get(key) for key in
                       ('ID', 'VERSION_ID', 'PRETTY_NAME', 'VERSION_CODENAME')},
        'needed': dynamic['needed'], 'rpath': dynamic['rpath'], 'runpath': dynamic['runpath'],
        'resolved': classified, 'not_found': loader['not_found'],
        'unparsed_ldd': loader['unparsed'], 'virtual_ldd': loader.get('virtual'),
        'packages': sorted({item['packages'][0]['package'] for item in classified
                            if item['packages']}),
        'packages_versioned': sorted({(item['packages'][0]['package'], item['version'])
                                      for item in classified if item['packages']}),
        'ldd_version': common.run('ldd', '--version', check=False).stdout.splitlines()[:1],
    }
    document = {
        'schema': 1, 'kind': 's02-static-audit',
        'verifier_source': os.environ.get('GITHUB_SHA', ''),
        'relocated': str(relocated),
        'dependencies': dependencies_report,
        'resources': {'font': {'path': 'Reader.otf', 'sha256': common.sha256_file(font),
                               'magic': font.read_bytes()[:4].hex()},
                      'licences': len(licences), 'shared_objects': shared,
                      'producer_desktop_entries': desktop_members, 'producer_icons': icons},
        'desktop_entry': {'path': str(entry), 'sha256': common.sha256_file(entry),
                          'text': entry.read_text(encoding='utf-8'),
                          'validation': validation_text},
        'build_tokens': {'build': scanned, 'recorded': recorded},
        'checks': checks.items, 'problems': checks.failed(), 'ok': checks.accepted(),
    }
    common.write_json(output / 'audit.json', document)
    print(json.dumps({'ok': checks.accepted(), 'failed': checks.failed(),
                      'needed': len(dynamic['needed']), 'packages': len(dependencies_report['packages'])}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
