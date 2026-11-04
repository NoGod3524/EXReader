#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check SDK identity and exact, evidence-bound historical literal exceptions."""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from sdk_version import ROOT, source_version

MANIFEST = 'tools/version_literal_exceptions.json'
LITERAL = re.compile(r'(?<![0-9])3\.4[0-9]\.0(?![0-9])')
CONSUMER_VERSION = re.compile(r'find_package\s*\(\s*EXReader\s+"?(\d+(?:\.\d+){0,3})"?(?=[\s)])', re.I)


def sha(data):
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=512)
def object_bytes(root, commit, path):
    return subprocess.check_output(['git', '-C', str(root), 'show', commit + ':' + path])


def tracked(root):
    return subprocess.check_output(['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard'], text=True).splitlines()


def check(root):
    version = source_version(root)
    errors = []

    def error(path, line, actual, expected):
        errors.append(f'{path}:{line} -> {actual} vs expected {expected}')

    def read(path):
        if Path(path).is_absolute() or '\\' in path or '..' in Path(path).parts:
            raise ValueError('exception references must use portable repository paths')
        target = (root / path).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError('exception path escapes repository')
        return target.read_text(encoding='utf-8').splitlines()

    def reference(ref):
        lines = read(ref['file'])
        first, last = ref['line'], ref.get('end_line', ref['line'])
        if not (1 <= first <= last <= len(lines)):
            raise ValueError('missing evidence lines')
        text = '\n'.join(lines[first - 1:last])
        if sha(text.encode()) != ref['sha256']:
            raise ValueError('evidence bytes changed')
        if 'file_sha256' in ref and sha((root / ref['file']).read_bytes()) != ref['file_sha256']:
            raise ValueError('test/workflow evidence file changed')
        return text

    source = (root / 'cmake/versions.cmake').read_text(encoding='utf-8')
    abi = re.search(r'set\(EXR_ABI_VERSION\s+(\d+)\)', source)[1]
    template = (root / 'cmake/version.h.in').read_text(encoding='utf-8')
    expected = template.replace('@EXR_SDK_VERSION@', version).replace('@EXR_ABI_VERSION@', abi)
    if (root / 'include/exr/version.h').read_bytes() != expected.encode('utf-8'):
        error('include/exr/version.h', 1, 'generated header differs', f'SDK {version}, ABI {abi}; run --sync-generated')
    cmake = read('CMakeLists.txt')
    project = next((i for i, line in enumerate(cmake, 1) if re.search(r'^project\(EXReader\b', line)), 0)
    if not project or cmake[project - 1] != 'project(EXReader VERSION ${EXR_SDK_VERSION} LANGUAGES C)':
        error('CMakeLists.txt', project or 1, cmake[project - 1] if project else 'missing project()', version + ' from ${EXR_SDK_VERSION}')
    if 'include(cmake/versions.cmake)' not in cmake[:max(0, project - 1)]:
        error('CMakeLists.txt', 1, 'missing include before project', 'cmake/versions.cmake')
    for number, line in enumerate(cmake, 1):
        if number != project and LITERAL.search(line):
            error('CMakeLists.txt', number, line, 'version variables from cmake/versions.cmake, not bare literals')
    base = read('include/exr/base.h')
    if '#define EXR_VERSION EXR_SDK_VERSION' not in base or '#include <exr/version.h>' not in base:
        error('include/exr/base.h', 1, 'SDK macro does not use generated header', version)
    if 'Version: @PROJECT_VERSION@' not in read('cmake/exreader.pc.in'):
        error('cmake/exreader.pc.in', 1, 'pkg-config version does not use project identity', version)
    if not re.search(r'write_basic_package_version_file\([^\n]*VERSION\s+\$\{PROJECT_VERSION\}', '\n'.join(cmake)):
        error('CMakeLists.txt', 1, 'package version does not use project identity', version)
    for i, line in enumerate(read('README.md'), 1):
        if '开发版' in line:
            found = re.search(r'(\d+\.\d+\.\d+) 开发版', line)
            if not found or found[1] != version:
                error('README.md', i, found[1] if found else line, version)
            break
    else:
        error('README.md', 1, 'missing development version line', version)

    exceptions = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    allowed = set()
    object_cache = {}
    for entry in exceptions:
        key = (entry['file'], entry['line'], entry['literal'])
        try:
            if key in allowed or entry['purpose'] not in {'frozen_baseline', 'migration_compat', 'negative_case'}:
                raise ValueError('duplicate triple or unknown purpose')
            line = reference({'file': entry['file'], 'line': entry['line'], 'sha256': entry['line_sha256']})
            if entry['literal'] not in line or not entry['explanation'].strip():
                raise ValueError('stale literal or empty explanation')
            purpose = entry['purpose']
            if purpose == 'frozen_baseline':
                proof = entry['frozen_object']
                if not re.fullmatch(r'[0-9a-f]{40}', proof['commit']):
                    raise ValueError('frozen object needs immutable commit')
                identity = (proof['commit'], proof['path'])
                if identity not in object_cache:
                    object_cache[identity] = object_bytes(root, *identity)
                raw = object_cache[identity]
                if sha(raw) != proof['sha256'] or entry['literal'].encode() not in raw:
                    raise ValueError('frozen object bytes/literal mismatch')
                fixture = entry['frozen_fixture']
                fixture_key = (fixture['commit'], fixture['path'])
                if not re.fullmatch(r'[0-9a-f]{40}', fixture['commit']) or fixture['path'] != entry['file']:
                    raise ValueError('invalid historical fixture identity')
                if fixture_key not in object_cache:
                    object_cache[fixture_key] = object_bytes(root, *fixture_key)
                fixture_raw = object_cache[fixture_key]
                fixture_lines = fixture_raw.decode('utf-8').splitlines()
                if not 1 <= fixture['line'] <= len(fixture_lines) or sha(fixture_raw) != fixture['sha256'] or fixture_lines[fixture['line'] - 1] != line:
                    raise ValueError('historical fixture bytes/line mismatch')
            elif purpose == 'migration_compat':
                proof = entry['migration_test']
                invocation = reference(proof['invocation'])
                workflow = reference(proof['workflow'])
                if Path(entry['file']).stem not in invocation or proof['invocation']['file'] not in workflow:
                    raise ValueError('migration test is not referenced by active workflow')
                if not proof['removal_condition'].strip():
                    raise ValueError('missing migration removal condition')
            else:
                proof = entry['rejection_assertion']
                assertion = reference(proof)
                if proof['kind'] == 'java_policy':
                    if 'false);' not in line or 'ReadingParserPolicy.accepts(recorded, actual) != expected' not in assertion or 'throw new AssertionError' not in assertion:
                        raise ValueError('missing policy refusal assertion')
                elif proof['kind'] == 'python_guard':
                    if not re.search(r'assert\s+negative\.returncode\s*!=\s*0', assertion):
                        raise ValueError('missing guard return-code refusal assertion')
                elif proof['kind'] == 'python_mutation':
                    if 'except (OSError, ValueError, KeyError, TypeError)' not in assertion or "raise AssertionError('accepted incomplete or changed native package files')" not in assertion:
                        raise ValueError('missing mutation refusal assertion')
                elif proof['kind'] == 'guard_refusal':
                    markers = proof['required_text']
                    if len(markers) < 2 or not all(marker and marker in assertion for marker in markers):
                        raise ValueError('guard refusal assertion markers missing')
                    if not re.search(r'\b(assert|require|expect|raise|throw)\b', assertion) or not re.search(r'returncode|refus|reject|ValueError|EXR_OK|accepted', assertion, re.I):
                        raise ValueError('assertion does not express a guard refusal')
                    if 'invocation' in proof:
                        reference(proof['invocation'])
                else:
                    raise ValueError('unrecognised rejection assertion')
            allowed.add(key)
        except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
            error(entry['file'], entry['line'], str(exc), f'live {entry["purpose"]} evidence for {entry["literal"]}')

    seen = set()
    for name in tracked(root):
        consumer = Path(name).name == 'CMakeLists.txt' or name.endswith(('.cmake', '.cmake.in'))
        if not (consumer or name.startswith('tests/') or (name.startswith('.github/workflows/') and name.endswith(('.yml', '.yaml')))):
            continue
        if not consumer and Path(name).suffix not in {'.py', '.c', '.h', '.cpp', '.java', '.swift', '.json', '.md', '.sh', '.cmake', '.txt', '.yml', '.yaml'} and Path(name).name != 'CMakeLists.txt':
            continue
        try:
            lines = read(name)
        except UnicodeError:
            continue
        if consumer:
            text = '\n'.join(lines)
            for match in CONSUMER_VERSION.finditer(text):
                number = text.count('\n', 0, match.start(1)) + 1
                literal = match[1]
                key = (name, number, literal)
                seen.add(key)
                if literal != version and key not in allowed:
                    error(name, number, literal, version + '; 改为读取安装包 version file，或登记豁免')
        if not (name.startswith('tests/') or name.startswith('.github/workflows/')):
            continue
        for number, line in enumerate(lines, 1):
            if name.startswith('.github/') and not re.search(r'EXR_(?:HOST_)?SDK_VERSION', line):
                continue
            for literal in set(LITERAL.findall(line)):
                key = (name, number, literal)
                seen.add(key)
                if literal != version and key not in allowed:
                    error(name, number, literal, version + ' or an exact evidence-bound exception')
    for path, line, literal in allowed - seen:
        error(path, line, 'unused exception ' + literal, 'remove stale exception')
    for message in errors:
        print(message)
    if not errors:
        print(f'PASS: SDK {version}; ABI {abi}; {len(allowed)} live exact literal exceptions')
    return bool(errors)


def sync(root):
    source = (root / 'cmake/versions.cmake').read_text(encoding='utf-8')
    version = source_version(root)
    abi = re.search(r'set\(EXR_ABI_VERSION\s+(\d+)\)', source)[1]
    header = (root / 'cmake/version.h.in').read_text(encoding='utf-8').replace('@EXR_SDK_VERSION@', version).replace('@EXR_ABI_VERSION@', abi)
    (root / 'include/exr/version.h').write_text(header, encoding='utf-8', newline='\n')
    readme = root / 'README.md'
    text = re.sub(r'\d+\.\d+\.\d+(?= 开发版)', version, readme.read_text(encoding='utf-8'))
    readme.write_text(text, encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sync-generated', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.sync_generated:
        sync(ROOT)
    if args.self_test:
        if check(ROOT):
            return 1
        path = ROOT / 'CMakeLists.txt'
        original = path.read_bytes()
        version = source_version()
        major, minor, patch = map(int, version.split('.'))
        wrong = f'{major}.{minor - 1}.{patch}'
        try:
            path.write_text(original.decode().replace('${EXR_SDK_VERSION}', wrong, 1), encoding='utf-8', newline='\n')
            result = subprocess.run([sys.executable, __file__], text=True, capture_output=True)
            print(result.stdout, end='')
            if result.returncode != 1 or 'CMakeLists.txt:3' not in result.stdout or version not in result.stdout:
                raise AssertionError('wrong version was not rejected at exact location')
            print('PASS: deliberate version drift rejected (exit 1)')
        finally:
            path.write_bytes(original)
        path = ROOT / 'tests/reading_corpus/CMakeLists.txt'
        original = path.read_bytes()
        try:
            path.write_text(original.decode().replace('find_package(EXReader CONFIG', f'find_package(EXReader {wrong} EXACT CONFIG', 1), encoding='utf-8', newline='\n')
            result = subprocess.run([sys.executable, __file__], text=True, capture_output=True, encoding='utf-8', errors='replace')
            print(result.stdout, end='')
            expected = f'tests/reading_corpus/CMakeLists.txt:3 -> {wrong} vs expected {version}; 改为读取安装包 version file，或登记豁免'
            if result.returncode != 1 or expected not in result.stdout:
                raise AssertionError('wrong consumer literal was not rejected with version-file guidance')
            print('PASS: deliberate consumer version drift rejected (exit 1)')
        finally:
            path.write_bytes(original)
        return 0
    return int(check(ROOT))


if __name__ == '__main__':
    raise SystemExit(main())
