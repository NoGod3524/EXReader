#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Write or strictly verify a release directory's SHA256SUMS (Python 3.9+)."""
import argparse
import hashlib
from pathlib import Path
import re
import sys

METADATA = {'SHA256SUMS', 'SHA256SUMS.asc', 'SHA256SUMS.minisig'}


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def safe_name(name):
    parts = name.split('/')
    if (not name or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or '\\' in name or ':' in name
            or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts)):
        raise ValueError(f'unsafe artifact path: {name!r}')
    return name


def inventory(directory):
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('artifact directory required')
    files, folded = {}, set()
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or not path.resolve().is_relative_to(root):
            raise ValueError(f'linked/escaping artifact: {path}')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f'not a regular file: {path}')
        name = safe_name(path.relative_to(root).as_posix())
        if name.casefold() in folded:
            raise ValueError(f'case-colliding artifact: {name}')
        folded.add(name.casefold())
        if name not in METADATA:
            files[name] = path
    if not files:
        raise ValueError('empty artifact directory')
    return files


def write_sums(directory):
    root = Path(directory)
    files = inventory(root)
    if any((root / name).exists() for name in METADATA - {'SHA256SUMS'}):
        raise ValueError('remove detached signatures before regenerating SHA256SUMS')
    raw = ''.join(f'{digest(path)}  {name}\n' for name, path in files.items())
    (root / 'SHA256SUMS').write_bytes(raw.encode('utf-8'))
    return len(files)


def verify(directory):
    root = Path(directory)
    files = inventory(root)
    expected, folded = {}, set()
    for line in (root / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *](.+)', line)
        if not match:
            raise ValueError(f'malformed checksum line: {line!r}')
        checksum, name = match.groups()
        safe_name(name)
        if name in METADATA or name.casefold() in folded:
            raise ValueError(f'reserved/duplicate checksum entry: {name}')
        folded.add(name.casefold())
        expected[name] = checksum.lower()
    if not expected or expected.keys() != files.keys():
        raise ValueError(f'inventory mismatch: missing={sorted(expected.keys() - files.keys())}, '
                         f'unlisted={sorted(files.keys() - expected.keys())}')
    bad = [name for name, path in files.items() if digest(path) != expected[name]]
    if bad:
        raise ValueError('SHA256 mismatch: ' + ', '.join(bad))
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--write', action='store_true', help='generate SHA256SUMS, then verify it')
    args = parser.parse_args()
    try:
        if args.write:
            write_sums(args.directory)
        count = verify(args.directory)
    except (OSError, ValueError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print(f'PASS: {count} files verified against SHA256SUMS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
