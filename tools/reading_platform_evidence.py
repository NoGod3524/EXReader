#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record and gate Windows/macOS reading profile identity, programs and native dependencies.

  snapshot OUT --program P...    hash consumer programs before ctest/smoke execute them
  run OUT -- PROGRAM ARGS...     execute an existing program once and record the outcome
  verify PROFILE BUILD SDK CONSUMER OUTPUT --platform NAME ...   write the gated report

Exported target composition is enforced by tests/reading_core/CMakeLists.txt. verify
requires the exact consumer program set of the profile, checks that each program is a
native linker output of the consumer Ninja graph, embeds the raw dependency tool output
(dumpbin /dependents or otool -L), and binds every program to a successful recorded
execution. dumpbin only lists imported DLL names; loader resolution is claimed only for
programs that actually ran. No size or performance budget is judged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).absolute().parents[1]
FORBIDDEN = ['webview', 'webkit', 'chromium', 'electron', 'faad', 'minimp3']
# Executables declared by tests/reading_core/CMakeLists.txt and tests/sdk_components/CMakeLists.txt
# for the reading presets: core/pdf and exreader are exported, audio/pdf_edit/textindex are not,
# and only reading-library exports exr_library. Paths are relative to the consumer build tree.
CORE_PROGRAMS = ('reading-document', 'reading-benchmark', 'components/core-consumer',
                 'components/chapter-consumer', 'components/convert-consumer')
REQUIRED_PROGRAMS = {
    'reading-core': CORE_PROGRAMS,
    'reading-library': CORE_PROGRAMS + ('components/library-consumer',
                                       'reading-library-source', 'reading-library-chapter-probe'),
}
HOSTS = {'Windows': 'Windows', 'Darwin': 'macOS'}
ARCHES = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def same_file(a, b):
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


def load_json(path, problems, what):
    if path is None:
        problems.append(f'execution-record-missing: no {what} was supplied')
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        problems.append(f'execution-record-missing: {what} {path.as_posix()} unreadable ({error})')
        return None


def preset_variables(name):
    presets = {p['name']: p for p in json.loads((ROOT/'CMakePresets.json').read_text(encoding='utf-8'))['configurePresets']}
    chain = []
    while name:
        chain.append(presets[name])
        name = presets[name].get('inherits')
    values = {}
    for preset in reversed(chain):
        values.update(preset.get('cacheVariables', {}))
    return {key: value for key, value in values.items() if key.startswith('EXR_')}


def cache_values(build):
    values = {}
    for line in (build/'CMakeCache.txt').read_text(encoding='utf-8', errors='replace').splitlines():
        if line and not line.startswith(('#', '//')) and '=' in line and ':' in line:
            key, value = line.split('=', 1)
            values[key.split(':', 1)[0]] = value
    return values


def ninja_tokens(line):
    """Split a Ninja build line; an unescaped ':' becomes None."""
    tokens, current, i = [], '', 0
    while i < len(line):
        c = line[i]
        if c == '$' and i + 1 < len(line):
            current += line[i+1]
            i += 2
            continue
        if c in ' :':
            if current:
                tokens.append(current)
            current = ''
            if c == ':':
                tokens.append(None)
        else:
            current += c
        i += 1
    if current:
        tokens.append(current)
    return tokens


def ninja_graph(build_file):
    graph = {}
    text = re.sub(r'(?<!\$)\$\r?\n\s*', ' ', build_file.read_text(encoding='utf-8', errors='replace'))
    for line in text.splitlines():
        if not line.startswith('build '):
            continue
        tokens = ninja_tokens(line[6:])
        if None not in tokens:
            continue
        split = tokens.index(None)
        outputs = tokens[:split]
        outputs = outputs[:outputs.index('|')] if '|' in outputs else outputs
        rest = tokens[split+1:]
        if not rest:
            continue
        inputs = []
        for token in rest[1:]:
            if token in ('|', '||', '|@'):
                break
            inputs.append(token.replace('\\', '/'))
        for output in outputs:
            graph[output.replace('\\', '/')] = (rest[0], inputs)
    return graph


def native_format(path):
    with path.open('rb') as stream:
        head = stream.read(4096)
    if head[:2] == b'MZ' and len(head) >= 0x40:
        offset = int.from_bytes(head[0x3c:0x40], 'little')
        if head[offset:offset+4] == b'PE\0\0':
            machine = int.from_bytes(head[offset+4:offset+6], 'little')
            characteristics = int.from_bytes(head[offset+22:offset+24], 'little')
            kind = 'dll' if characteristics & 0x2000 else 'executable' if characteristics & 0x2 else 'object'
            return {'format': 'PE', 'arch': {0x8664: 'x64', 0xaa64: 'arm64'}.get(machine, hex(machine)), 'kind': kind}
    if head[:4] == b'\xcf\xfa\xed\xfe' and len(head) >= 16:
        cpu = int.from_bytes(head[4:8], 'little')
        filetype = int.from_bytes(head[12:16], 'little')
        return {'format': 'Mach-O', 'arch': {0x01000007: 'x64', 0x0100000c: 'arm64'}.get(cpu, hex(cpu)),
                'kind': 'executable' if filetype == 2 else f'filetype {filetype}'}
    return {'format': None, 'arch': None, 'kind': None}


def compiler_identity(build):
    found = {}
    for language in ('C', 'CXX'):
        for path in sorted((build/'CMakeFiles').glob(f'*/CMake{language}Compiler.cmake')):
            text = path.read_text(encoding='utf-8', errors='replace')
            for key in ('COMPILER', 'COMPILER_ID', 'COMPILER_VERSION', 'COMPILER_ARCHITECTURE_ID',
                        'COMPILER_LINKER', 'COMPILER_LINKER_ID', 'COMPILER_LINKER_VERSION',
                        'COMPILER_LINKER_FRONTEND_VARIANT', 'COMPILER_AR'):
                match = re.search(rf'set\(CMAKE_{language}_{key}\s+"?([^")]*)"?\)', text)
                found[f'{language}_{key}'] = match.group(1) if match else None
    return found


def probe(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=60)
        return {'command': command, 'exit_code': result.returncode, 'raw_output': result.stdout + result.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'command': command, 'exit_code': None, 'raw_output': '', 'error': str(error)}


def within(path, folder):
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except (OSError, ValueError):
        return False


def toolchain(label, build, host, problems):
    """Record the compiler and linker CMake selected for one build tree; never infer from PATH order."""
    try:
        cache = cache_values(build)
    except OSError as error:
        problems.append(f'cache-missing: {label} {error}')
        return {}
    detected = compiler_identity(build)
    tools = {key: cache.get(key) for key in ('CMAKE_C_COMPILER', 'CMAKE_CXX_COMPILER', 'CMAKE_LINKER', 'CMAKE_AR',
                                              'CMAKE_MT', 'CMAKE_RC_COMPILER', 'CMAKE_MAKE_PROGRAM')}
    record = {'cache': tools, 'detected': detected, 'linker_probes': {}}
    rules = build/'CMakeFiles'/'rules.ninja'
    if rules.is_file():
        lines = rules.read_text(encoding='utf-8', errors='replace').splitlines()
        record['ninja_link_rules'] = [{'rule': lines[i][5:].strip(), 'command': next(
            (l.strip()[10:] for l in lines[i+1:i+8] if l.strip().startswith('command = ')), None)}
            for i, line in enumerate(lines) if line.startswith('rule ') and 'LINKER' in line]
    for language in ('C', 'CXX'):
        if not detected.get(f'{language}_COMPILER_ID'):
            problems.append(f'toolchain-compiler: {label} has no detected {language} compiler identity')
    linkers = sorted({value for value in (tools['CMAKE_LINKER'], detected.get('C_COMPILER_LINKER'),
                                          detected.get('CXX_COMPILER_LINKER')) if value})
    if not linkers:
        problems.append(f'toolchain-path: {label} records no linker path')
    for linker in linkers:
        if not Path(linker).is_file():
            problems.append(f'toolchain-path: {label} linker {linker} does not exist')
            continue
        resolved = str(Path(linker).resolve())  # CMake may record 8.3 and long spellings of one file
        if resolved not in record['linker_probes']:
            record['linker_probes'][resolved] = probe([linker] if host == 'Windows' else [linker, '-v'])
        record['linker_probes'][resolved].setdefault('cmake_spellings', []).append(linker)
    if host == 'Windows':
        vc = os.environ.get('VCToolsInstallDir')
        version = os.environ.get('VCToolsVersion', '')
        record['msvc_environment'] = {key: os.environ.get(key) for key in (
            'VCToolsInstallDir', 'VCToolsVersion', 'VSINSTALLDIR', 'WindowsSDKVersion', 'VSCMD_ARG_TGT_ARCH')}
        bin_dir = Path(vc)/'bin'/'Hostx64'/'x64' if vc else None
        if not bin_dir or not bin_dir.is_dir():
            problems.append(f'toolchain-environment: {label} VCToolsInstallDir={vc} has no bin/Hostx64/x64')
        for language in ('C', 'CXX'):
            if detected.get(f'{language}_COMPILER_ID') != 'MSVC' or detected.get(f'{language}_COMPILER_ARCHITECTURE_ID') != 'x64':
                problems.append(f'toolchain-compiler: {label} {language} is {detected.get(f"{language}_COMPILER_ID")} '
                                f'{detected.get(f"{language}_COMPILER_ARCHITECTURE_ID")}, expected MSVC x64')
            linker_id = detected.get(f'{language}_COMPILER_LINKER_ID')
            if linker_id and linker_id != 'MSVC':
                problems.append(f'toolchain-linker: {label} {language} linker id {linker_id}, expected MSVC')
            compiler_version = (detected.get(f'{language}_COMPILER_VERSION') or '').split('.')
            if len(compiler_version) < 2 or compiler_version[1] != (version.split('.') + ['', ''])[1]:
                problems.append(f'toolchain-version: {label} {language} cl {detected.get(f"{language}_COMPILER_VERSION")} '
                                f'does not belong to VCToolsVersion {version}')
        if bin_dir:
            for key in ('CMAKE_C_COMPILER', 'CMAKE_CXX_COMPILER', 'CMAKE_AR'):
                if not tools[key] or not within(tools[key], bin_dir):
                    problems.append(f'toolchain-path: {label} {key}={tools[key]} is outside {bin_dir.as_posix()}')
            for linker in linkers:
                if not within(linker, bin_dir):
                    problems.append(f'toolchain-path: {label} linker {linker} is outside {bin_dir.as_posix()}')
        for linker, result in record['linker_probes'].items():
            match = re.search(r'Incremental Linker Version (\S+)', result['raw_output'])
            result['version'] = match.group(1) if match else None
            # The toolset directory (VCToolsVersion 14.44.35207) and tool build (14.44.35229) differ;
            # require the toolset major.minor and the same build number as the selected cl.
            banner = (result['version'] or '').split('.')
            builds = {((detected.get(f'{language}_COMPILER_VERSION') or '').split('.') + ['', '', ''])[2]
                      for language in ('C', 'CXX')}
            if len(banner) < 3 or banner[:2] != version.split('.')[:2] or builds != {banner[2]}:
                problems.append(f'toolchain-version: {label} linker {linker} banner version {result["version"]} '
                                f'does not match VCToolsVersion {version} and cl build {sorted(builds)}')
        # Observation only: every link.exe on PATH, in order, so shadowing is visible.
        record['path_link_candidates'] = [str(Path(d)/'link.exe') for d in os.environ.get('PATH', '').split(os.pathsep)
                                          if d and (Path(d)/'link.exe').is_file()]
    else:
        record['developer_dir'] = probe(['xcode-select', '-p'])['raw_output'].strip()
        record['driver_linker'] = probe([tools['CMAKE_C_COMPILER'] or 'cc', '-print-prog-name=ld'])['raw_output'].strip()
        for language in ('C', 'CXX'):
            if detected.get(f'{language}_COMPILER_ID') != 'AppleClang':
                problems.append(f'toolchain-compiler: {label} {language} is {detected.get(f"{language}_COMPILER_ID")}, expected AppleClang')
        for linker, result in record['linker_probes'].items():
            match = re.search(r'PROJECT:(\S+)', result['raw_output'])
            result['version'] = match.group(1) if match else None
            if not match:
                problems.append(f'toolchain-version: {label} linker {linker} -v printed no version')
    return record


def dependencies(program, host, problems):
    name = 'dumpbin' if host == 'Windows' else 'otool'
    tool = shutil.which(name)
    record = {'tool': tool, 'command': None, 'exit_code': None, 'raw_output': ''}
    if not tool:
        problems.append(f'dependency-tool-missing: {name} not found for {program.name}')
        return record
    if host == 'Windows':
        vc = os.environ.get('VCToolsInstallDir')
        if not vc or not within(tool, Path(vc)/'bin'/'Hostx64'/'x64'):
            problems.append(f'dependency-tool-path: {tool} is outside VCToolsInstallDir {vc}')
    record['command'] = [tool, '/nologo', '/dependents', str(program)] if host == 'Windows' else [tool, '-L', str(program)]
    record.update(probe(record['command']))
    if record['exit_code'] != 0:
        problems.append(f'dependency-tool-failed: {name} exited {record["exit_code"]} for {program.name}')
    lines = record['raw_output'].splitlines()
    if host == 'Windows':
        headers = [i for i, line in enumerate(lines) if line.strip() == 'Image has the following dependencies:']
        names = []
        for line in lines[headers[0]+1:] if headers else []:
            if line.strip() and not line.strip().lower().endswith('.dll'):
                break
            if line.strip():
                names.append(line.strip())
        delay = [line.strip() for i, line in enumerate(lines) if i and 'delay load dependencies' in lines[i-1]]
        record['dependency_names'] = names
        record['delay_load_section_present'] = bool(delay)
        record['resolution'] = 'names only: dumpbin /dependents does not locate or load DLLs'
    else:
        names = [line.split(' (compatibility', 1)[0].strip() for line in lines[1:] if line.strip()] \
            if lines and lines[0].rstrip().endswith(':') else []
        record['dependency_names'] = names
        # System libraries live in the dyld shared cache; anything else must exist on disk.
        record['unresolved'] = [item for item in names if not item.startswith(('/usr/lib/', '/System/Library/')) and
                                (item.startswith('@') or not Path(item).exists())]
        record['resolution'] = 'otool -L names; non-system paths checked for existence'
        if record['unresolved']:
            problems.append(f'unresolved-dependency: {program.name} {record["unresolved"]}')
    if not names:
        problems.append(f'dependency-output-missing: {name} output for {program.name} lists no dependencies')
    forbidden = [item for item in names for word in FORBIDDEN if word in item.lower()]
    if forbidden:
        problems.append(f'forbidden-dependency: {program.name} {forbidden}')
    return record


def executions(programs, args, problems):
    """Map recorded ctest, smoke and direct runs onto programs by resolved path and hash."""
    events = {key: [] for key in programs}

    def owner(path):
        return next((key for key, item in programs.items() if same_file(item['path'], path)), None)

    snapshot = load_json(args.snapshot, problems, 'pre-execution snapshot') or {}
    for key, item in programs.items():
        before = next((value for path, value in snapshot.get('programs', {}).items() if same_file(path, item['path'])), None)
        item['sha256_before_execution'] = before['sha256'] if before else None
        if before and before['sha256'] != item['sha256']:
            problems.append(f'changed-after-execution: {key} differs from its pre-execution snapshot')
    tests = load_json(args.ctest_tests, problems, 'ctest --show-only=json-v1 listing') or {}
    commands = {test.get('name'): test.get('command') or [] for test in tests.get('tests', [])}
    junit = {}
    if args.ctest_junit is None:
        problems.append('execution-record-missing: no ctest JUnit result was supplied')
    else:
        try:
            for case in ET.parse(args.ctest_junit).getroot().iter('testcase'):
                failed = any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped'))
                junit[case.get('name')] = 'passed' if case.get('status') == 'run' and not failed else case.get('status') or 'unknown'
        except (OSError, ET.ParseError) as error:
            problems.append(f'execution-record-missing: ctest JUnit {args.ctest_junit} unreadable ({error})')
    for name, command in commands.items():
        key = owner(command[0]) if command else None
        if key:
            events[key].append({'via': 'ctest', 'test': name, 'argv': command, 'status': junit.get(name, 'no result'),
                                'sha256': programs[key]['sha256_before_execution'],
                                'success': junit.get(name) == 'passed' and programs[key]['sha256_before_execution'] is not None})
    smoke = load_json(args.smoke_summary, problems, 'nine-format smoke summary') or {}
    for path, sha in (smoke.get('identities') or {}).items():
        key = owner(path)
        if key:
            events[key].append({'via': 'smoke', 'accepted': smoke.get('accepted'), 'counts': smoke.get('counts'),
                                'checked_entries': smoke.get('checked_entries'), 'sha256': sha,
                                'success': smoke.get('accepted') is True and smoke.get('identities_unchanged') is True and
                                           sha == programs[key]['sha256']})
    for path in args.run:
        record = load_json(path, problems, 'program run record') or {}
        key = owner(record['program']) if record.get('program') else None
        if key:
            events[key].append({'via': 'run', 'record': path.as_posix(), 'argv': record.get('argv'),
                                'exit_code': record.get('exit_code'), 'sha256': record.get('sha256_before'),
                                'stdout_sha256': record.get('stdout_sha256'),
                                'success': record.get('exit_code') == 0 and
                                           record.get('sha256_before') == record.get('sha256_after') == programs[key]['sha256']})
        elif record:
            problems.append(f'unknown-program: run record {path.as_posix()} names {record.get("program")}')
    for key, item in programs.items():
        item['executions'] = events[key]
        item['executed'] = any(event['success'] for event in events[key])
        if not item['executed']:
            problems.append(f'not-executed: {key} has no successful execution record bound to its hash')


def verify(args):
    problems, host = [], HOSTS.get(platform.system(), platform.system())
    if args.platform not in HOSTS.values():
        problems.append(f'unsupported-platform: {args.platform}')
    if args.platform != host or os.environ.get('RUNNER_OS', host) != args.platform:
        problems.append(f'platform-mismatch: requested {args.platform}, host {host}, RUNNER_OS {os.environ.get("RUNNER_OS")}')
    required = REQUIRED_PROGRAMS.get(args.profile)
    expected = {}
    if required is None:
        problems.append(f'unknown-profile: {args.profile}; known {sorted(REQUIRED_PROGRAMS)}')
        required = ()
    else:
        expected = preset_variables(args.profile)
    try:
        cache = cache_values(args.build)
    except OSError as error:
        problems.append(f'cache-missing: {error}')
        cache = {}
    observed = {key: cache.get(key) for key in expected}
    problems += [f'preset-mismatch: {key} expected {value}, observed {observed[key]}'
                 for key, value in expected.items() if observed[key] != value]
    suffix = '.exe' if host == 'Windows' else ''
    graph_file = args.consumer/'build.ninja'
    graph = ninja_graph(graph_file) if graph_file.is_file() else {}
    if not graph:
        problems.append(f'not-build-output: consumer Ninja graph {graph_file.as_posix()} is missing or empty')
    if not args.program:
        problems.append('empty-program-set: no --program was supplied')
    programs, seen, named = {}, {}, set()
    for program in args.program:
        resolved = program.resolve()
        identity = os.path.normcase(str(resolved))
        if identity in seen:
            problems.append(f'duplicate-program: {program.as_posix()} repeats {seen[identity]}')
            continue
        seen[identity] = program.as_posix()
        relative = resolved.relative_to(args.consumer.resolve()).as_posix() if within(resolved, args.consumer) else None
        name = relative[:-len(suffix)] if relative and suffix and relative.lower().endswith(suffix) else relative
        if name not in required:
            problems.append(f'unknown-program: {program.as_posix()} is not a required {args.profile} program')
            continue
        named.add(name)
        if not program.is_file():
            problems.append(f'program-not-found: {program.as_posix()}')
            continue
        record = {'path': program.as_posix(), 'bytes': program.stat().st_size, 'sha256': digest(program),
                  'native': native_format(program)}
        expected_format = {'format': 'PE' if host == 'Windows' else 'Mach-O',
                           'arch': ARCHES.get(platform.machine().lower(), platform.machine()), 'kind': 'executable'}
        if record['native'] != expected_format:
            problems.append(f'not-native-program: {name} is {record["native"]}, expected {expected_format}')
        node = graph.get(relative)
        if not node or 'EXECUTABLE_LINKER' not in node[0]:
            problems.append(f'not-build-output: {name} is not an executable linker output of {graph_file.as_posix()}')
        else:
            sources = []
            for item in node[1]:
                source = graph.get(item, (None, []))[1][:1]
                for path in source:
                    path = Path(path) if Path(path).is_absolute() else args.consumer/path
                    if not within(path, ROOT) or not path.is_file():
                        problems.append(f'source-outside-repo: {name} compiles {path.as_posix()}')
                        continue
                    sources.append({'path': path.resolve().relative_to(ROOT.resolve()).as_posix(), 'sha256': digest(path)})
            record['link_rule'] = node[0]
            record['sources'] = sources
            if not sources:
                problems.append(f'not-build-output: {name} has no compiled source in the Ninja graph')
        record['dependencies'] = dependencies(program, host, problems)
        programs[name] = record
    for name in required:
        if name not in named:
            problems.append(f'missing-program: {name} is required for {args.profile}')
    executions(programs, args, problems)
    loader = ('all required programs were started by the OS loader and exited successfully in the recorded '
              'invocations' if required and programs and all(item['executed'] for item in programs.values())
              and len(programs) == len(required) else
              'not established: programs without a successful execution have dependency names only')
    toolchains = {'sdk': toolchain('sdk', args.build, host, problems),
                  'consumer': toolchain('consumer', args.consumer, host, problems)}
    try:
        files = [{'path': path.relative_to(args.sdk).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)}
                 for path in sorted(args.sdk.rglob('*')) if path.is_file()]
    except OSError:
        files = []
    archives = [item for item in files if item['path'].startswith('lib/') and re.search(r'\.(?:a|lib)$', item['path'])]
    if not archives:
        problems.append('archives-missing: installed library archives are missing')
    env = {key: os.environ.get(key) for key in ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_REF', 'GITHUB_RUN_ID',
           'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB', 'RUNNER_OS', 'RUNNER_ARCH', 'ImageOS', 'ImageVersion')}
    git = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    if env['GITHUB_SHA'] and env['GITHUB_SHA'] != git:
        problems.append(f'source-mismatch: checkout {git} differs from GITHUB_SHA {env["GITHUB_SHA"]}')
    report = {
        'schema': 2, 'profile': args.profile, 'platform_requested': args.platform, 'host': host,
        'accepted': not problems, 'problems': problems,
        'invocation': sys.argv[1:],
        'scope': 'installed static SDK files, exact consumer program set, native dependency tool output and '
                 'recorded program executions; no size or performance budget',
        'source_sha': git, 'ci': env, 'platform': platform.platform(),
        'preset_cache_variables': expected, 'observed_cache_variables': observed,
        'generator': cache.get('CMAKE_GENERATOR'), 'build_type': cache.get('CMAKE_BUILD_TYPE'),
        'required_programs': list(required),
        'toolchains': toolchains,
        'toolchain_log': args.toolchain.read_text(encoding='utf-8', errors='replace') if args.toolchain else None,
        'inputs': {path.as_posix(): digest(path) for path in args.input},
        'programs': programs, 'loader_conclusion': loader,
        'installed_files': files, 'installed_file_count': len(files),
        'installed_bytes_total': sum(item['bytes'] for item in files),
        'installed_archive_bytes': sum(item['bytes'] for item in archives),
        'size_note': 'Installed totals include headers, docs, examples and static archives; '
                     'they are not a reading executable size. Consumer programs are test hosts.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    # Job-log copy of the per-program and toolchain evidence, so it is readable without the artifact.
    for name, item in programs.items():
        print(f'## program {name}\n' + json.dumps({
            'sha256': item['sha256'], 'bytes': item['bytes'], 'native': item['native'], 'sources': item.get('sources'),
            'executed': item.get('executed'),
            'executions': [{k: e.get(k) for k in ('via', 'test', 'status', 'exit_code', 'success')} for e in item.get('executions', [])],
            'dependency_command': item['dependencies']['command'], 'dependency_exit_code': item['dependencies']['exit_code'],
            'dependency_resolution': item['dependencies'].get('resolution')}, ensure_ascii=False))
        print(item['dependencies']['raw_output'].rstrip())
    for label, item in toolchains.items():
        detected = item.get('detected', {})
        print(f'## toolchain {label}\n' + json.dumps({
            'compilers': {lang: [detected.get(f'{lang}_COMPILER'), detected.get(f'{lang}_COMPILER_ID'),
                                 detected.get(f'{lang}_COMPILER_VERSION'), detected.get(f'{lang}_COMPILER_ARCHITECTURE_ID')]
                          for lang in ('C', 'CXX')},
            'CMAKE_LINKER': item.get('cache', {}).get('CMAKE_LINKER'), 'CMAKE_AR': item.get('cache', {}).get('CMAKE_AR'),
            'compiler_linker': [detected.get('C_COMPILER_LINKER'), detected.get('C_COMPILER_LINKER_ID'),
                                detected.get('C_COMPILER_LINKER_VERSION')],
            'linker_probes': {path: probe.get('version') for path, probe in item.get('linker_probes', {}).items()},
            'msvc_environment': item.get('msvc_environment'), 'path_link_candidates': item.get('path_link_candidates'),
            'developer_dir': item.get('developer_dir'), 'driver_linker': item.get('driver_linker')}, ensure_ascii=False))
    print(json.dumps({'profile': args.profile, 'accepted': report['accepted'], 'problems': problems,
                      'executed': {key: item['executed'] for key, item in programs.items()},
                      'loader_conclusion': loader, 'installed_bytes_total': report['installed_bytes_total']}))
    return 0 if report['accepted'] else 1


def snapshot(args):
    programs = {str(p.resolve()): {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in args.program}
    args.output.write_text(json.dumps({'schema': 1, 'programs': programs}, indent=2)+'\n', encoding='utf-8')
    return 0


def run(args):
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    program = Path(command[0])
    before = digest(program)
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, timeout=args.timeout)
    record = {'schema': 1, 'program': str(program.resolve()), 'argv': command, 'exit_code': result.returncode,
              'wall_seconds': time.monotonic() - started, 'sha256_before': before, 'sha256_after': digest(program),
              'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(), 'stdout': result.stdout.decode('utf-8', 'replace'),
              'stderr': result.stderr.decode('utf-8', 'replace')}
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({key: record[key] for key in ('program', 'exit_code', 'sha256_before')}))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='action', required=True)
    item = commands.add_parser('snapshot')
    item.add_argument('output', type=Path)
    item.add_argument('--program', type=Path, action='append', required=True)
    item.set_defaults(handler=snapshot)
    item = commands.add_parser('run')
    item.add_argument('output', type=Path)
    item.add_argument('--timeout', type=float, default=120)
    item.add_argument('command', nargs=argparse.REMAINDER)
    item.set_defaults(handler=run)
    item = commands.add_parser('verify')
    item.add_argument('profile')
    item.add_argument('build', type=Path)
    item.add_argument('sdk', type=Path)
    item.add_argument('consumer', type=Path)
    item.add_argument('output', type=Path)
    item.add_argument('--platform', required=True, help='Windows or macOS; must match the host')
    item.add_argument('--program', type=Path, action='append', default=[], help='consumer program; exact set required')
    item.add_argument('--snapshot', type=Path, help='pre-execution program hashes')
    item.add_argument('--ctest-tests', type=Path, help='ctest --show-only=json-v1 output')
    item.add_argument('--ctest-junit', type=Path, help='ctest --output-junit result')
    item.add_argument('--smoke-summary', type=Path, help='check_corpus.py summary.json')
    item.add_argument('--run', type=Path, action='append', default=[], help='run record of a direct program execution')
    item.add_argument('--input', type=Path, action='append', default=[], help='font/manifest/fixture to hash')
    item.add_argument('--toolchain', type=Path, help='raw toolchain version log to embed')
    item.set_defaults(handler=verify)
    args = parser.parse_args()
    return args.handler(args)


if __name__ == '__main__':
    raise SystemExit(main())
