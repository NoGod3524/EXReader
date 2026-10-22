#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record Windows/macOS reading profile identity, installed files and native dependencies.

Exported target composition is enforced by tests/reading_core/CMakeLists.txt.
This records the configured preset, compiler, installed files, program hashes and the
raw output of the platform dependency tool (dumpbin /dependents or otool -L), and
rejects forbidden or unresolved runtime dependencies. No size budget is judged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

ROOT = Path(__file__).absolute().parents[1]
FORBIDDEN = ['webview', 'webkit', 'chromium', 'electron', 'faad', 'minimp3']


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


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


def compiler_identity(build):
    found = {}
    for language in ('C', 'CXX'):
        for path in sorted((build/'CMakeFiles').glob(f'*/CMake{language}Compiler.cmake')):
            text = path.read_text(encoding='utf-8', errors='replace')
            for key in ('COMPILER', 'COMPILER_ID', 'COMPILER_VERSION', 'COMPILER_ARCHITECTURE_ID'):
                match = re.search(rf'set\(CMAKE_{language}_{key} "([^"]*)"\)', text)
                found[f'{language}_{key}'] = match.group(1) if match else None
    return found


def dependencies(program):
    if platform.system() == 'Windows':
        command = ['dumpbin', '/nologo', '/dependents', str(program)]
    else:
        command = ['otool', '-L', str(program)]
    result = subprocess.run(command, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if platform.system() == 'Windows':
        listed = [line.strip() for line in result.stdout.splitlines() if line.strip().lower().endswith('.dll')]
        unresolved = []  # The loader resolved these when ctest/smoke ran the same file.
    else:
        listed = [line.split(' (compatibility', 1)[0].strip() for line in result.stdout.splitlines()[1:] if line.strip()]
        # System libraries live in the dyld shared cache; anything else must exist on disk.
        unresolved = [item for item in listed if not item.startswith(('/usr/lib/', '/System/Library/')) and
                      (item.startswith('@') or not Path(item).exists())]
    return {'command': command, 'exit_code': result.returncode, 'raw_output': output,
            'dependencies': listed, 'unresolved': unresolved}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile')
    parser.add_argument('build', type=Path)
    parser.add_argument('sdk', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--program', type=Path, action='append', default=[], help='built consumer program to inspect')
    parser.add_argument('--input', type=Path, action='append', default=[], help='font/manifest/fixture to hash')
    parser.add_argument('--toolchain', type=Path, help='raw toolchain version log to embed')
    args = parser.parse_args()
    problems = []
    expected = preset_variables(args.profile)
    cache = cache_values(args.build)
    observed = {key: cache.get(key) for key in expected}
    problems += [f'{key}: expected {value}, observed {observed[key]}' for key, value in expected.items() if observed[key] != value]
    forbidden = FORBIDDEN + (['sqlite'] if args.profile == 'reading-core' else [])
    programs = {}
    for program in args.program:
        if not program.is_file():
            problems.append(f'Missing program {program.as_posix()}')
            continue
        record = {'bytes': program.stat().st_size, 'sha256': digest(program), **dependencies(program)}
        if record['exit_code']:
            problems.append(f'Dependency tool failed for {program.name}')
        if any(word in item.lower() for item in record['dependencies'] for word in forbidden):
            problems.append(f'Forbidden runtime dependency in {program.name}')
        if record['unresolved']:
            problems.append(f'Unresolved runtime dependency in {program.name}')
        programs[program.as_posix()] = record
    files = [{'path': path.relative_to(args.sdk).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)}
             for path in sorted(args.sdk.rglob('*')) if path.is_file()]
    archives = [item for item in files if item['path'].startswith('lib/') and re.search(r'\.(?:a|lib)$', item['path'])]
    if not archives:
        problems.append('Installed library archives are missing')
    env = {key: os.environ.get(key) for key in ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_REF', 'GITHUB_RUN_ID',
           'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB', 'RUNNER_OS', 'RUNNER_ARCH', 'ImageOS', 'ImageVersion')}
    git = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    report = {
        'schema': 1, 'profile': args.profile, 'accepted': not problems, 'problems': problems,
        'scope': 'installed static SDK files and native dependencies of built consumer programs; no size or performance budget',
        'source_sha': git, 'ci': env, 'platform': platform.platform(),
        'preset_cache_variables': expected, 'observed_cache_variables': observed,
        'generator': cache.get('CMAKE_GENERATOR'), 'build_type': cache.get('CMAKE_BUILD_TYPE'),
        'compiler': compiler_identity(args.build),
        'toolchain_log': args.toolchain.read_text(encoding='utf-8', errors='replace') if args.toolchain else None,
        'inputs': {path.as_posix(): digest(path) for path in args.input},
        'programs': programs,
        'installed_files': files, 'installed_file_count': len(files),
        'installed_bytes_total': sum(item['bytes'] for item in files),
        'installed_archive_bytes': sum(item['bytes'] for item in archives),
        'size_note': 'Installed totals include headers, docs, examples and static archives; '
                     'they are not a reading executable size. Consumer programs are test hosts.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({'profile': args.profile, 'accepted': report['accepted'], 'problems': problems,
                      'installed_bytes_total': report['installed_bytes_total']}))
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
