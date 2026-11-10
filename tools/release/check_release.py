#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify an SDK release directory, ZIP or tar.gz without loading target code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/abi'))
from check_exports import inspect_bytes
sys.path.insert(0, str(ROOT / 'tools'))
from sdk_version import source_version

API_HEADERS = {
    'audio.h', 'base.h', 'core.h', 'dictionary.h', 'document.h', 'edit.h',
    'font_manager.h', 'formats.h', 'graphics.h', 'layout.h', 'library.h',
    'pdf.h', 'pdf_edit.h', 'reflow.h', 'render.h', 'text.h', 'textindex.h',
}
PACKAGE_NAME = re.compile(r'exreader-(\d+\.\d+\.\d+)-(win-x64|linux-x64|macos-arm64)')


def portable_path(name):
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or path.is_absolute()
            or str(path) != name or '..' in path.parts
            or any(ord(c) < 32 for c in name)):
        raise ValueError(f'unsafe or noncanonical package path: {name!r}')
    return path


def read_package(path):
    """Read ordinary files only; archives are never extracted."""
    files, modes = {}, {}
    if path.is_dir():
        name = path.name
        for item in sorted(path.rglob('*')):
            if item.is_symlink():
                raise ValueError(f'package contains a symlink: {item}')
            if item.is_file():
                relative = item.relative_to(path).as_posix()
                portable_path(relative)
                files[relative], modes[relative] = item.read_bytes(), item.stat().st_mode
    else:
        suffix = '.zip' if path.name.endswith('.zip') else '.tar.gz'
        if not path.name.endswith(suffix):
            raise ValueError('expected a package directory, .zip or .tar.gz')
        name = path.name[:-len(suffix)]

        def member_path(member):
            parts = portable_path(member.rstrip('/')).parts
            if not parts or parts[0] != name:
                raise ValueError(f'archive member is outside its named package root: {member}')
            return parts

        def add(member, data, mode):
            parts = member_path(member)
            if len(parts) < 2:
                raise ValueError(f'archive member is outside its named package root: {member}')
            relative = '/'.join(parts[1:])
            if relative in files:
                raise ValueError(f'duplicate archive member: {member}')
            files[relative], modes[relative] = data, mode

        if suffix == '.zip':
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    member_path(member.filename)
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise ValueError(f'archive contains a symlink: {member.filename}')
                    if not member.is_dir():
                        add(member.filename, archive.read(member), mode)
        else:
            with tarfile.open(path, 'r:gz') as archive:
                for member in archive:
                    member_path(member.name)
                    if member.isdir():
                        continue
                    if not member.isfile():
                        raise ValueError(f'archive contains a nonregular member: {member.name}')
                    with archive.extractfile(member) as stream:
                        add(member.name, stream.read(), member.mode)
    if len({p.casefold() for p in files}) != len(files):
        raise ValueError('package contains case-colliding filenames')
    return name, files, modes


def check_package(path, source_root=ROOT):
    report = {'package': str(path), 'checks': [], 'passed': False}

    def check(label, action):
        try:
            detail = action()
            report['checks'].append({'check': label, 'passed': True, 'detail': detail})
            return detail
        except (OSError, ValueError, KeyError, IndexError, struct.error, UnicodeError) as error:
            report['checks'].append({'check': label, 'passed': False, 'detail': str(error)})
            return None

    def require(condition, detail):
        if not condition:
            raise ValueError(detail)

    try:
        name, files, modes = read_package(Path(path))
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        report['checks'].append({'check': 'package files and safe paths', 'passed': False, 'detail': str(error)})
        return report
    report['checks'].append({'check': 'package files and safe paths', 'passed': True,
                             'detail': f'{len(files)} ordinary files; {sum(map(len, files.values()))} bytes'})
    identity = PACKAGE_NAME.fullmatch(name)
    if not identity:
        report['checks'].append({'check': 'package name', 'passed': False, 'detail': f'invalid package name: {name}'})
        return report
    version, platform = identity.groups()
    report.update(version=version, platform=platform, file_count=len(files), size_bytes=sum(map(len, files.values())))
    windows = platform == 'win-x64'
    def archive_name():
        suffix = '.zip' if windows else '.tar.gz'
        require(Path(path).is_dir() or Path(path).name == name + suffix,
                f'{platform} release archive must use {suffix}')
        return name
    check('package name and archive format', archive_name)
    library_names = ('lib/exreader.dll', 'lib/libexreader.dll') if windows else (
        ('lib/libexreader.so',) if platform == 'linux-x64' else ('lib/libexreader.dylib',))
    library = next((p for p in library_names if p in files), library_names[0])
    cli = 'bin/exr-info.exe' if windows else 'bin/exr-info'

    def required_files():
        required = {'LICENSE', 'README.md', 'VERSION', 'SHA256SUMS', 'examples/minimal/main.c',
                    'examples/minimal/sample.epub', 'examples/minimal/font.ttf',
                    'examples/minimal/FONT-LICENSE.md', library, cli}
        missing = sorted(p for p in required if not files.get(p))
        require(not missing, f'missing or empty required files: {missing}')
        return ', '.join(sorted(required))
    check('required SDK files', required_files)

    def versions():
        packaged = files['VERSION'].decode('utf-8').strip()
        match = re.search(r'^#define\s+EXR_SDK_VERSION\s+"(\d+\.\d+\.\d+)"\s*$',
                          files['include/exr/version.h'].decode('utf-8'), re.M)
        require(match is not None, 'version.h lacks EXR_SDK_VERSION')
        root_version = (source_root / 'VERSION').read_text(encoding='utf-8').strip()
        canonical = source_version(source_root)
        source_header = (source_root / 'include/exr/version.h').read_text(encoding='utf-8').splitlines()
        require(packaged == version == match[1] == root_version == canonical,
                f'identity mismatch: package={version}, VERSION={packaged}, header={match[1]}, source={root_version}, cmake={canonical}')
        require(files['include/exr/version.h'].decode('utf-8').splitlines() == source_header,
                'packaged version.h differs from source version.h (ignoring line endings)')
        return f'package name = VERSION = version.h = source VERSION = cmake: {version}'
    check('version identity', versions)

    def headers():
        expected = {'include/exr/' + name for name in API_HEADERS | {'version.h'}}
        actual = {p for p in files if p.startswith('include/exr/') and p.endswith('.h')}
        require(actual == expected, f'public header mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}')
        require(all(files[p] for p in expected), 'empty public header')
        return f'{len(API_HEADERS)} API headers + version.h = {len(expected)} files'
    check('public headers', headers)

    def minimal():
        lines = len(files['examples/minimal/main.c'].decode('utf-8').splitlines())
        require(0 < lines <= 80, f'minimal main.c has {lines} lines (limit 80)')
        return f'{lines} lines <= 80'
    check('minimal example line limit', minimal)

    hashes = {}
    def checksums():
        for line in files['SHA256SUMS'].decode('utf-8').splitlines():
            match = re.fullmatch(r'([0-9a-fA-F]{64})  (.+)', line)
            require(match is not None, f'invalid SHA256SUMS entry: {line!r}')
            digest, entry = match.groups()
            portable_path(entry)
            require(entry not in hashes, f'duplicate SHA256SUMS entry: {entry}')
            hashes[entry] = digest.lower()
        expected = set(files) - {'SHA256SUMS'}
        require(set(hashes) == expected,
                f'checksum coverage mismatch: missing={sorted(expected-set(hashes))}, extra={sorted(set(hashes)-expected)}')
        bad = [p for p, digest in hashes.items() if hashlib.sha256(files[p]).hexdigest() != digest]
        require(not bad, f'SHA256 mismatch: {bad}')
        return f'{len(hashes)} SHA256 digests; exact coverage of all files except SHA256SUMS'
    check('SHA256SUMS coverage and content', checksums)

    def architecture():
        expected = {'win-x64': ('PE', '0x8664'), 'linux-x64': ('ELF', '0x3e'),
                    'macos-arm64': ('Mach-O', '0x100000c')}[platform]
        for path in (library, cli):
            parts = inspect_bytes(files[path])
            actual = {(p['format'], p['machine']) for p in parts}
            require(actual == {expected}, f'{path}: expected {expected}, found {sorted(actual)}')
        return f'library and CLI: {expected[0]} {platform}'
    check('library and CLI architecture', architecture)

    def exports():
        counts = [len({s for s in part['symbols'] if s.startswith('exr_')})
                  for part in inspect_bytes(files[library])]
        require(counts and all(count >= 389 for count in counts), f'{library}: exr_* export counts {counts}, minimum 389')
        report['export_counts'] = counts
        return f'{library}: exr_* exports {counts}; minimum 389'
    check('public export count', exports)

    def runtime():
        if windows:
            imports = [p for p in ('lib/exreader.lib', 'lib/libexreader.lib', 'lib/libexreader.dll.a') if p in files]
            require(bool(imports), 'Windows import library is missing')
            require(all(files[p].startswith(b'!<arch>\n') for p in imports), 'invalid Windows import archive')
            runtime_path = 'bin/' + PurePosixPath(library).name
            require(files.get(runtime_path) == files[library], 'bin DLL must match lib DLL for standalone CLI loading')
            return f'import library {imports[0]}; bin DLL matches lib DLL'
        require(modes[cli] & 0o111, f'{cli} is not executable')
        return 'POSIX CLI has executable permission'
    check('CLI runtime layout and import library', runtime)
    report['passed'] = all(row['passed'] for row in report['checks'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--json', type=Path, help='write the complete check report')
    args = parser.parse_args()
    report = check_package(args.package, args.source_root.resolve())
    for row in report['checks']:
        print(f"{'PASS' if row['passed'] else 'FAIL'} {row['check']}: {row['detail']}")
    print(f"{'PASS' if report['passed'] else 'FAIL'} release: {args.package}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
