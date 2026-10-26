#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare desktop entry points and verify relocated native dependencies in Actions."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

import delivery

DESKTOP = ('windows', 'linux', 'macos')
LINUX_LAUNCHER = '''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$root/bin/exreader-linux"
'''


def prepare(target, root):
    """Only supplement the delivery payload; never change the compiled program."""
    root = Path(root)
    if target == 'linux':
        launcher = root / 'EXReader-Linux/Start-EXReader.sh'
        launcher.write_text(LINUX_LAUNCHER, encoding='utf-8', newline='\n')
        launcher.chmod(0o755)


def command(*args):
    return subprocess.check_output([str(arg) for arg in args], text=True, stderr=subprocess.STDOUT)


def linux_dependencies(text, root):
    """ldd includes transitive shared dependencies; only system or packed paths qualify."""
    if 'not found' in text:
        raise ValueError('unresolved Linux runtime dependency')
    paths = re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', text, re.MULTILINE)
    for name in paths:
        path = Path(name).resolve()
        if not (path.is_relative_to(root.resolve()) or str(path).startswith(('/usr/lib/', '/lib/'))):
            raise ValueError('Linux runtime dependency outside the archive/system: ' + name)
    if not paths:
        raise ValueError('ldd did not identify any runtime dependency')
    return paths


def macos_dependencies(text, frameworks):
    paths = []
    for line in text.splitlines()[1:]:
        name = line.strip().split(' (', 1)[0]
        if not name:
            continue
        paths.append(name)
        if name.startswith(('/usr/lib/', '/System/Library/')):
            continue
        if name.startswith('@rpath/') and (frameworks / name.removeprefix('@rpath/')).is_file():
            continue
        if name.startswith('@executable_path/../Frameworks/') and (frameworks / name.rsplit('/', 1)[-1]).is_file():
            continue
        raise ValueError('macOS runtime dependency is not bundled/system: ' + name)
    return paths


def windows_dependencies(text, directory, system_directory):
    paths = []
    for name in re.findall(r'^\s+([\w.+-]+\.dll)\s*$', text, re.MULTILINE | re.IGNORECASE):
        if name.lower().startswith(('api-ms-win-', 'ext-ms-win-')):
            paths.append({'name': name, 'resolution': 'Windows API set'})
            continue
        found = next((base / name for base in (directory, system_directory) if (base / name).is_file()), None)
        if found is None:
            raise ValueError('Windows runtime dependency is not bundled/system: ' + name)
        paths.append({'name': name, 'resolution': str(found)})
    if not paths:
        raise ValueError('dumpbin did not identify any runtime dependency')
    return paths


def verify(target, root, source_sha, sdk_version):
    root = Path(root).resolve()
    build_path = root / 'build.json'
    build = json.loads(build_path.read_text(encoding='utf-8'))
    if build.get('source_sha') != source_sha or build.get('sdk_version') != sdk_version:
        raise ValueError('packaged platform build source/SDK differs from candidate')
    entry = root / delivery.TARGETS[target]['entry']
    relative = entry.relative_to(root).as_posix()
    build_entry = {'windows': 'EXReader.exe', 'linux': 'bin/exreader-linux',
                   'macos': 'Contents/MacOS/EXReader'}[target]
    entry_digest = delivery.sha256_file(entry)
    if build.get('files', {}).get(build_entry) != entry_digest:
        raise ValueError('relocated program differs from the platform build manifest')
    logs = {}
    if target == 'linux':
        identity = command(entry, '--version').strip()
        if identity != sdk_version + ' 1':
            raise ValueError('relocated Linux native program reports another SDK/ABI')
        logs['ldd'] = command('ldd', entry)
        dependencies = linux_dependencies(logs['ldd'], root)
        if not (root / 'EXReader-Linux/Start-EXReader.sh').is_file():
            raise ValueError('Linux user entry point is missing')
    elif target == 'windows':
        identity = 'platform manifest and exact executable SHA-256; GUI checked separately'
        system = Path(os.environ['SystemRoot']) / 'System32'
        dependencies = {}
        for binary in [entry, *sorted(entry.parent.glob('*.dll'))]:
            logs[binary.name] = command('dumpbin', '/nologo', '/dependents', binary)
            dependencies[binary.name] = windows_dependencies(logs[binary.name], entry.parent, system)
    else:
        identity = 'platform manifest and exact executable SHA-256; GUI checked separately'
        frameworks = root / 'EXReader.app/Contents/Frameworks'
        dependencies = {}
        for binary in [entry, *sorted(frameworks.glob('*.dylib'))]:
            logs[binary.name] = command('otool', '-L', binary)
            dependencies[binary.name] = macos_dependencies(logs[binary.name], frameworks)
    return {'schema': 1, 'target': target, 'source_sha': source_sha, 'sdk_version': sdk_version,
            'entry': relative, 'entry_sha256': entry_digest,
            'platform_manifest_sha256': delivery.sha256_file(build_path),
            'native_identity': identity, 'runtime_dependencies': dependencies, 'dependency_logs': logs,
            'scope': 'relocated dependency/identity check; native GUI acceptance is reported separately'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'verify'))
    parser.add_argument('--target', choices=DESKTOP, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source-sha')
    parser.add_argument('--sdk-version', default='3.41.0')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('desktop preparation and verification run in GitHub Actions only')
    if args.operation == 'prepare':
        prepare(args.target, args.root)
        return 0
    if not delivery.SOURCE_PATTERN.fullmatch(args.source_sha or '') or not args.report:
        parser.error('verify requires a full --source-sha and --report')
    report = {'schema': 1, 'target': args.target, 'passed': False}
    try:
        report.update(verify(args.target, args.root, args.source_sha, args.sdk_version))
        report['passed'] = True
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        report['failure'] = str(error)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if not report['passed']:
        raise SystemExit(report['failure'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

