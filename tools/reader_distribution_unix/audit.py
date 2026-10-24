#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Audit one Unix distribution tree: relocatability, materials and real consumers.

The audit is the same code in every job: the build job runs it against the staged,
relocated, deduplicated and extracted prefixes with binaries and smoke output, and
the same-source report re-runs it against bytes extracted from the uploaded archive.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract

CONSUMER_KEYS = {'c': ('version', 'abi', 'pages', 'text_bytes', 'png_bytes', 'negative_checks'),
                 'cxx': ('version', 'abi', 'pages', 'text_bytes', 'headers', 'negative_checks')}


def run(command, env=None):
    return subprocess.run(command, capture_output=True, text=True, env=env, timeout=300)


def dynamic_entries(binary, platform, tokens, prefix):
    problems, entries, rpaths = [], [], []
    if platform == 'linux':
        done = run(['readelf', '-d', str(binary)])
        if done.returncode:
            return ['readelf failed: ' + done.stderr.strip()[:200]], [], []
        for line in done.stdout.splitlines():
            match = re.search(r'\((NEEDED|RPATH|RUNPATH|SONAME)\).*\[([^\]]+)\]', line)
            if not match:
                continue
            kind, value = match.groups()
            if kind == 'NEEDED':
                entries.append(value)
            elif kind in ('RPATH', 'RUNPATH'):
                rpaths.append(value)
    else:
        done = run(['otool', '-L', str(binary)])
        if done.returncode:
            return ['otool -L failed: ' + done.stderr.strip()[:200]], [], []
        for line in done.stdout.splitlines()[1:]:
            value = line.strip().split(' (')[0]
            if value:
                entries.append(value)
        done = run(['otool', '-l', str(binary)])
        if done.returncode == 0:
            lines = done.stdout.splitlines()
            for index, line in enumerate(lines):
                if line.strip() == 'cmd LC_RPATH':
                    for follow in lines[index:index + 4]:
                        match = re.search(r'path (\S+)', follow)
                        if match:
                            rpaths.append(match.group(1))
                            break
    for entry in entries:
        if any(token and token in entry for token in tokens) or entry.startswith(str(prefix)):
            problems.append('runtime dependency leaks a workspace path: ' + entry)
        elif entry.startswith('/') and not entry.startswith(('/usr/lib/', '/System/')):
            problems.append('runtime dependency is an absolute non-system path: ' + entry)
    for rpath in rpaths:
        if not rpath.startswith('@'):
            problems.append('absolute runtime search path: ' + rpath)
    return problems, entries, rpaths


def pkgconfig_query(prefix, platform, tokens, stage):
    env = dict(os.environ)
    env['PKG_CONFIG_PATH'] = str(prefix / 'lib/pkgconfig')
    env.pop('PKG_CONFIG_LIBDIR', None)
    done = run(['pkg-config', '--cflags', '--libs', '--static', 'exreader'], env=env)
    problems = []
    if done.returncode:
        return ['pkg-config query failed: ' + done.stderr.strip()[:300]], ''
    output = done.stdout.strip()
    tokens_flags = output.split()
    for token in tokens_flags:
        if token.startswith(('-I', '-L')):
            path = token[2:]
            if any(bad and bad in path for bad in tokens):
                problems.append('pkg-config flag leaks a workspace path: ' + token)
            if not path.startswith(str(prefix)):
                problems.append('pkg-config flag resolves outside the relocated prefix: ' + token)
        if token.startswith('-Wl,'):
            problems.append('pkg-config emits a linker wrapper flag: ' + token)
    for required in ('-I' + str(prefix / 'include'), '-L' + str(prefix / 'lib')):
        if required not in tokens_flags:
            problems.append('pkg-config output is missing ' + required)
    for flag in ('-lexr_render', '-lexr_pdf', '-lexr_vendor_miniz', '-pthread', '-lm'):
        if flag not in tokens_flags:
            problems.append('pkg-config output is missing ' + flag)
    for name in stage.get('link_order') or []:
        if contract.archive_flag(name) not in tokens_flags:
            problems.append('pkg-config output is missing component ' + name)
    return problems, output


def consumer_report(name, path, stage):
    problems = []
    try:
        report = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return ['consumer report unreadable: ' + str(error)], None
    expected = CONSUMER_KEYS[name]
    for key in expected:
        if key not in report:
            problems.append('%s consumer report is missing %s' % (name, key))
    if report.get('schema') != 1:
        problems.append(name + ' consumer report schema is not 1')
    if report.get('version') != stage.get('sdk_version'):
        problems.append(name + ' consumer version differs from the installed SDK')
    if report.get('abi') != stage.get('abi'):
        problems.append(name + ' consumer ABI differs from the installed SDK')
    for key in ('pages', 'text_bytes', 'negative_checks'):
        value = report.get(key)
        if type(value) is not int or value <= 0:
            problems.append('%s consumer %s is not a positive integer' % (name, key))
    if name == 'c':
        if type(report.get('png_bytes')) is not int or report['png_bytes'] <= 0:
            problems.append('c consumer rendered no PNG bytes')
    else:
        if type(report.get('headers')) is not int or report['headers'] < 13:
            problems.append('cxx consumer did not include every public header')
    return problems, report


def smoke_evidence(path):
    problems = []
    try:
        summary = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return ['nine-format smoke summary unreadable: ' + str(error)], None
    results = summary.get('results') or []
    if summary.get('accepted') is not True:
        problems.append('nine-format smoke did not accept the run')
    if summary.get('source_dirty') is not False:
        problems.append('nine-format smoke saw a dirty source tree')
    if summary.get('identities_unchanged') is not True:
        problems.append('nine-format smoke inputs or tools changed during the run')
    if len(results) != 9 or summary.get('manifest_entries') != 9:
        problems.append('nine-format smoke did not cover nine manifest entries')
    for result in results:
        if result.get('classification') not in ('passed', 'expected_rejection'):
            problems.append('nine-format smoke entry %s: %s' % (result.get('path'),
                                                                result.get('classification')))
        observed = result.get('observed') or {}
        if observed.get('status') != 0 or observed.get('complete') is not True:
            problems.append('nine-format smoke entry %s did not complete' % result.get('path'))
    return problems, summary


def doc_identity(prefix, repo):
    problems, compared = [], []
    pairs = [('README.md', repo / 'README.md'), ('CHANGELOG.md', repo / 'CHANGELOG.md'),
             ('LICENSE', repo / 'LICENSE'),
             ('THIRD_PARTY_NOTICES.md', repo / 'THIRD_PARTY_NOTICES.md')]
    for name, source in pairs:
        installed = prefix / name
        if installed.is_file() and source.is_file():
            compared.append(name)
            if contract.digest(installed) != contract.digest(source):
                problems.append('installed %s differs from the source bytes' % name)
    docs = prefix / 'docs'
    if docs.is_dir():
        for path in sorted(docs.iterdir()):
            source = repo / 'docs' / path.name
            if path.is_file() and source.is_file():
                compared.append('docs/' + path.name)
                if contract.digest(path) != contract.digest(source):
                    problems.append('installed docs/%s differs from the source bytes' % path.name)
    if len(compared) < 5:
        problems.append('fewer than five installed documents could be compared with sources')
    return problems, compared


def cmake_relocatable(prefix, tokens):
    problems = []
    directory = prefix / 'lib/cmake/EXReader'
    if not directory.is_dir():
        return ['installed CMake package directory is missing']
    targets = 0
    for path in sorted(directory.glob('*.cmake')):
        text = path.read_text(encoding='utf-8')
        name = path.name
        if 'CMAKE_INSTALL_PREFIX' in text:
            problems.append(name + ' mentions CMAKE_INSTALL_PREFIX')
        for token in tokens:
            if token and token in text:
                problems.append(name + ' embeds the workspace token ' + token)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(('IMPORTED_LOCATION', 'INTERFACE_INCLUDE_DIRECTORIES',
                                    'IMPORTED_LINK_INTERFACE_LIBRARIES')):
                if '${_IMPORT_PREFIX}' not in stripped and 'PACKAGE_PREFIX_DIR' not in stripped:
                    problems.append('%s: %s is not relative to the package prefix' % (name, stripped[:80]))
        if 'EXReaderTargets.cmake' in name:
            targets = text.count('add_library(EXReader::')
            if '${_IMPORT_PREFIX}' not in text:
                problems.append('EXReaderTargets.cmake never references the import prefix')
    if targets < 3:
        problems.append('EXReaderTargets.cmake exports fewer targets than expected')
    return problems


def build_report(args):
    prefix = Path(args.prefix).resolve(strict=True)
    stage = contract.decode_json(args.stage)
    tokens = [token for token in (args.token or []) if token]
    prefix_text = str(prefix)
    problems = []
    checks = []

    def record(name, issues, detail):
        checks.append({'id': name, 'status': 'pass' if not issues else 'fail', 'detail': detail})
        problems.extend(issues)

    records = contract.walk(prefix)
    inventory_problems = contract.tree_problems(prefix, stage['files'])
    record('tree_inventory', inventory_problems,
           '%d files; every recorded digest is present' % len(records))

    layout_problems = []
    for relative in ('include/exr/base.h', 'lib/pkgconfig/exreader.pc',
                     'lib/cmake/EXReader/EXReaderConfig.cmake', 'docs/SUPPORT_MATRIX.md',
                     'share/exreader/licenses', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
        if not (prefix / relative).exists():
            layout_problems.append('missing ' + relative)
    for forbidden in ('CMakeCache.txt', 'CMakeFiles', 'build.ninja', '.ninja_log'):
        if (prefix / forbidden).exists():
            layout_problems.append('build artefact inside the prefix: ' + forbidden)
    record('install_layout', layout_problems, 'required installed paths and no build artefacts')

    pc_text = (prefix / stage['pkgconfig']['path']).read_text(encoding='utf-8')
    pc_fields, pc_problems = contract.pc_contract(pc_text, stage['sdk_version'],
                                                  stage['link_order'], stage['private_archives'],
                                                  stage['system_libraries'])
    if contract.digest_bytes(pc_text.encode('utf-8')) != stage['pkgconfig']['sha256']:
        pc_problems.append('installed pkg-config bytes differ from the staged unit')
    if 'pcfiledir' not in pc_fields.get('prefix', ''):
        pc_problems.append('pkg-config prefix is not pcfiledir-relative')
    record('pkgconfig_contract', pc_problems, 'pcfiledir-relative prefix; no absolute install flag')

    hits = contract.scan_tokens(prefix, tokens + [prefix_text])
    record('absolute_path_scan', ['%s contains %s' % (hit['path'], hit['token']) for hit in hits],
           'no workspace, build or prefix token in %d installed text files' % sum(
               1 for _ in contract.text_files(prefix)))

    cmake_problems = cmake_relocatable(prefix, tokens + [prefix_text])
    record('cmake_relocatable', cmake_problems, 'installed CMake package resolves through the prefix')

    doc_problems, compared = doc_identity(prefix, Path(args.repo).resolve(strict=True))
    record('document_bytes', doc_problems,
           '%d installed documents match their source bytes' % len(compared))

    licence_problems = []
    if not args.licenses:
        licence_problems.append('licence report path is required')
    else:
        report = contract.decode_json(args.licenses)
        if report.get('release_ready') is not True:
            licence_problems.append('licence report is not release ready')
        for field in ('failures', 'pending', 'mandatory_missing'):
            if report.get(field):
                licence_problems.append('licence report lists ' + field)
        if report.get('source_sha') != stage.get('source_sha'):
            licence_problems.append('licence report belongs to another source')
        if report.get('profile') != stage.get('profile'):
            licence_problems.append('licence report belongs to another profile')
    licences = prefix / 'share/exreader/licenses'
    licence_files = [path for path in licences.rglob('*') if path.is_file()] if licences.is_dir() else []
    if len(licence_files) < 10:
        licence_problems.append('fewer than ten installed licence materials')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'share/exreader/THIRD_PARTY_NOTICES.md'):
        path = prefix / name
        if not path.is_file() or path.stat().st_size == 0:
            licence_problems.append('missing or empty licence material ' + name)
    record('licence_materials', licence_problems,
           '%d licence files; notices and LICENSE preserved' % len(licence_files))

    plan = stage.get('dedupe_plan') or []
    dedupe_problems, dedupe_detail = [], 'no duplicate archive material was planned'
    if plan:
        by_path = {record['path']: record for record in records}
        groups = {}
        for item in plan:
            groups.setdefault(item['primary'], []).append(item)
        verified = 0
        for primary, items in sorted(groups.items()):
            inodes = {(prefix / primary).stat().st_ino}
            for item in items:
                duplicate = prefix / item['duplicate']
                if not duplicate.is_file():
                    dedupe_problems.append('duplicate copy disappeared: ' + item['duplicate'])
                    continue
                if contract.digest(duplicate) != item['sha256']:
                    dedupe_problems.append('duplicate copy changed: ' + item['duplicate'])
                inodes.add(duplicate.stat().st_ino)
                verified += 1
            if args.label == 'after' and len(inodes) != 1:
                dedupe_problems.append('duplicate copies do not share one inode: ' + primary)
            if args.label == 'after' and len(inodes) == 1 and (prefix / primary).stat().st_nlink < 2:
                dedupe_problems.append('hardlink count did not increase: ' + primary)
            if by_path.get(primary) is None:
                dedupe_problems.append('dedupe primary is not part of the stage inventory')
        dedupe_detail = '%d duplicate copies, %d bytes, %d groups' % (
            verified, sum(item['bytes'] for item in plan), len(groups))
        if args.label == 'report':
            dedupe_detail += ' (content identity re-derived from the uploaded archive)'
    record('duplicate_material', dedupe_problems, dedupe_detail)

    dynamic_problems, dynamic_text, rpath_text = [], '', ''
    consumers = args.consumer or []
    dynamic_report = {'entries': [], 'rpaths': []}
    if args.skip_dynamic:
        checks.append({'id': 'runtime_dependencies', 'status': 'reported',
                       'detail': 're-derived in the build job; binaries are not uploaded'})
    elif not consumers:
        dynamic_problems.append('no consumer binary was supplied for dynamic checking')
        record('runtime_dependencies', dynamic_problems, 'dynamic dependency check')
    else:
        for item in consumers:
            name, _, value = item.partition('=')
            binary = Path(value)
            if not binary.is_file():
                dynamic_problems.append('missing consumer binary ' + value)
                continue
            issues, entries, rpaths = dynamic_entries(binary, args.platform,
                                                      tokens + [prefix_text], prefix)
            dynamic_problems.extend(name + ': ' + issue for issue in issues)
            dynamic_text += name + '=' + ' '.join(entries) + '\n'
            rpath_text += name + '=' + ' '.join(rpaths) + '\n'
        record('runtime_dependencies', dynamic_problems,
               'no consumer dependency or RPATH resolves into the workspace')
        dynamic_report = {'entries': dynamic_text.splitlines(), 'rpaths': rpath_text.splitlines()}

    flag_problems, flags = pkgconfig_query(prefix, args.platform, tokens + [prefix_text], stage)
    record('pkgconfig_query', flag_problems, 'pkg-config resolves flags inside the relocated prefix')

    consumer_reports, consumer_problems, png = {}, [], None
    for item in args.consumer_report or []:
        name, _, value = item.partition('=')
        if name not in CONSUMER_KEYS:
            consumer_problems.append('unknown consumer report ' + name)
            continue
        issues, report = consumer_report(name, value, stage)
        consumer_problems.extend(issues)
        if report is not None:
            consumer_reports[name] = report
    if not consumer_reports:
        consumer_problems.append('no installed consumer report was supplied')
    if 'c' in consumer_reports and args.png:
        png_path = Path(args.png)
        if png_path.is_file():
            png = {'path': str(png_path), 'bytes': png_path.stat().st_size,
                   'sha256': contract.digest(png_path)}
            if png['bytes'] != consumer_reports['c'].get('png_bytes'):
                consumer_problems.append('rendered PNG size differs from the consumer report')
        else:
            consumer_problems.append('rendered PNG is missing: ' + args.png)
    record('installed_consumers', consumer_problems,
           'C and C++ consumers ran against the installed prefix')

    smoke_problems, smoke = [], None
    if args.smoke:
        smoke_problems, smoke = smoke_evidence(args.smoke)
    else:
        smoke_problems = ['nine-format smoke summary is required']
    record('nine_format_smoke', smoke_problems,
           'nine original fixtures opened, rendered and extracted through the installed consumer')

    report = {
        'schema': 1,
        'label': args.label,
        'source_sha': stage.get('source_sha'),
        'platform': args.platform,
        'profile': stage.get('profile'),
        'prefix': str(prefix),
        'prefix_length': len(prefix_text),
        'files': len(records),
        'bytes': sum(record['bytes'] for record in records),
        'checks': checks,
        'problems': problems,
        'release_ready': not problems,
        'pkgconfig': {'flags': flags, 'fields': pc_fields},
        'png': png,
        'dynamic': dynamic_report,
        'consumers': consumer_reports,
        'smoke': {'accepted': (smoke or {}).get('accepted'),
                  'counts': (smoke or {}).get('counts'),
                  'entries': [{'path': item.get('path'), 'classification': item.get('classification'),
                               'observed': {key: (item.get('observed') or {}).get(key) for key in
                                            ('status', 'complete', 'parts', 'completed_parts',
                                             'pages', 'text_bytes')}}
                              for item in (smoke or {}).get('results') or []]},
        'tokens_checked': tokens + [prefix_text],
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'label': args.label, 'release_ready': report['release_ready'],
                      'checks': len(checks), 'files': len(records), 'problems': problems}))
    return 0 if report['release_ready'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--label', choices=('before', 'after', 'extracted', 'report'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--platform', choices=('linux', 'macos'), required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--licenses', type=Path)
    parser.add_argument('--token', action='append', default=[])
    parser.add_argument('--consumer', action='append', default=[],
                        help='name=path of an installed consumer binary')
    parser.add_argument('--consumer-report', action='append', default=[],
                        help='name=path of the JSON printed by that consumer')
    parser.add_argument('--png')
    parser.add_argument('--smoke', type=Path)
    parser.add_argument('--skip-dynamic', action='store_true')
    args = parser.parse_args()
    contract.need(os.environ.get('GITHUB_ACTIONS') == 'true',
                  'distribution audits run in cloud CI only')
    try:
        return build_report(args)
    except contract.ContractError as error:
        print('audit: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
