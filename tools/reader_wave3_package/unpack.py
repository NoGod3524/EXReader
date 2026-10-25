#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unpack one delivery archive into a fresh directory and verify every byte.

The unpack target must not exist. Every file is compared with the manifest that
travelled inside the archive, the outer manifest must describe exactly the same
archive, and the SHA256SUMS list is re-checked the way an operator would.
"""
import argparse
import json
import os
import stat
import zipfile
from pathlib import Path

import delivery


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, choices=sorted(delivery.TARGETS))
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--into', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    return parser.parse_args(argv)


def safe_name(name):
    relative = delivery.normalise(name)
    parts = [part for part in relative.split('/') if part not in ('', '.')]
    if not parts or relative.startswith('/') or any(part == '..' for part in parts):
        raise SystemExit('refusing an archive path outside the delivery root: ' + name)
    return '/'.join(parts)


def parse_checksums(text):
    values = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition('  ')
        if len(digest) != 64 or not name:
            raise SystemExit('malformed SHA256SUMS line: ' + line[:80])
        values[name] = digest.strip()
    return values


def main(argv=None):
    args = parse_args(argv)
    archive = args.archive.resolve()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    if manifest.get('schema') != delivery.SCHEMA or manifest.get('kind') != 'exreader-native-delivery':
        raise SystemExit('not an S20 delivery manifest')
    if manifest.get('target') != args.target:
        raise SystemExit('manifest target differs from the requested target')
    if not delivery.SOURCE_PATTERN.match(manifest.get('source_sha', '')):
        raise SystemExit('manifest source SHA is not an immutable commit id')
    block = manifest.get('archive') or {}
    if block.get('name') != archive.name:
        raise SystemExit('archive name differs from the manifest')
    if archive.stat().st_size != block.get('bytes'):
        raise SystemExit('archive size differs from the manifest')
    digest = delivery.sha256_file(archive)
    if digest != block.get('sha256'):
        raise SystemExit('archive SHA-256 differs from the manifest')
    into = args.into.resolve()
    if into.exists():
        raise SystemExit('unpack destination must be a fresh directory: ' + str(into))
    into.mkdir(parents=True)
    written = set()
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = safe_name(info.filename)
            if info.is_dir():
                continue
            if name in written:
                raise SystemExit('duplicate archive entry: ' + name)
            written.add(name)
            destination = into / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as stream, destination.open('wb') as target:
                while True:
                    block_bytes = stream.read(1024 * 1024)
                    if not block_bytes:
                        break
                    target.write(block_bytes)
    files = manifest.get('files') or {}
    metadata = set(manifest.get('metadata_files') or [])
    if set(files) | metadata != written:
        missing = sorted((set(files) | metadata) - written)
        extra = sorted(written - (set(files) | metadata))
        raise SystemExit('archive inventory differs from the manifest; missing=' + str(missing[:5]) +
                         ' extra=' + str(extra[:5]))
    modes = {}
    for name, record in sorted(files.items()):
        path = into / name
        if path.stat().st_size != record.get('bytes'):
            raise SystemExit('unpacked size differs: ' + name)
        if delivery.sha256_file(path) != record.get('sha256'):
            raise SystemExit('unpacked SHA-256 differs: ' + name)
        mode = int(record.get('mode') or 0o644) & 0o777
        os.chmod(path, mode | stat.S_IRUSR | stat.S_IWUSR)
        modes[name] = mode
    checksums = parse_checksums((into / delivery.CHECKSUMS).read_text(encoding='utf-8'))
    if set(checksums) != set(files):
        raise SystemExit('SHA256SUMS does not list every packed file')
    for name, expected in checksums.items():
        if checksums[name] != files[name]['sha256']:
            raise SystemExit('SHA256SUMS entry differs from the manifest: ' + name)
    inner = json.loads((into / delivery.MANIFEST).read_text(encoding='utf-8'))
    outer = dict(manifest)
    outer.pop('archive', None)
    if inner != outer:
        raise SystemExit('inner manifest differs from the outer manifest')
    entry = manifest.get('entry')
    if entry not in files:
        raise SystemExit('declared launch entry is not part of the archive: ' + str(entry))
    report = {
        'schema': 1,
        'target': args.target,
        'source_sha': manifest['source_sha'],
        'sdk_version': manifest.get('sdk_version'),
        'archive': {'path': str(archive), 'name': archive.name, 'bytes': archive.stat().st_size,
                    'sha256': digest},
        'files': len(files),
        'digests': {name: record['sha256'] for name, record in files.items()},
        'modes': modes,
        'entry': entry,
        'entry_sha256': files[entry]['sha256'],
        'into': str(into),
        'checksums_checked': len(checksums),
        'inner_matches_outer': True,
        'limits': manifest.get('limits', []),
        'provenance': manifest.get('provenance', {}),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'target': args.target, 'files': len(files), 'entry': entry,
                      'archive_sha256': digest, 'into': str(into)}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
