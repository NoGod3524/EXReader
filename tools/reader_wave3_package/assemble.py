#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Assemble one native delivery archive from an existing build output directory.

The archive holds the untouched build payload plus the checksum list, the short
Chinese operator notes and a manifest. The tool never builds, rewrites or judges
product bytes; it only wraps what the platform build scripts already produced.
"""
import argparse
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

import delivery

ROOT = Path(__file__).absolute().parents[2]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, choices=sorted(delivery.TARGETS))
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--sdk-version', default='3.41.0')
    parser.add_argument('--exclude', action='append', default=[],
                        help='Payload-relative path or directory to leave out (recorded in the manifest)')
    parser.add_argument('--provenance', type=Path, help='Optional JSON with cloud run identity')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--require-build-identity', action='store_true',
                        help='Require the platform producer build.json to bind this source and SDK')
    return parser.parse_args(argv)


def zip_entry(name, mode):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.create_system = 3
    return info


def main(argv=None):
    args = parse_args(argv)
    if not delivery.SOURCE_PATTERN.match(args.source_sha):
        raise SystemExit('source SHA must be the full lowercase 40-hex commit id')
    payload = args.payload.resolve()
    if not payload.is_dir():
        raise SystemExit('payload directory does not exist: ' + str(payload))
    build_identity = {}
    identity_path = payload / 'build.json'
    if identity_path.is_file():
        build_identity = json.loads(identity_path.read_text(encoding='utf-8'))
        if build_identity.get('source_sha') != args.source_sha:
            raise SystemExit('platform producer build.json binds another source')
        if build_identity.get('sdk_version') != args.sdk_version:
            raise SystemExit('platform producer build.json binds another SDK version')
    elif args.require_build_identity:
        raise SystemExit('platform producer build.json is required')
    records = delivery.collect(payload, args.exclude)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive_name = 'EXReader-' + args.target + '-' + args.source_sha[:12] + '.zip'
    archive = output / archive_name
    if archive.exists() and not args.force:
        raise SystemExit('archive already exists; choose a new output directory: ' + str(archive))
    provenance = {}
    if args.provenance:
        provenance = json.loads(args.provenance.read_text(encoding='utf-8'))
    provenance = dict(provenance)
    for key, value in (('run_id', os.environ.get('GITHUB_RUN_ID')),
                       ('attempt', os.environ.get('GITHUB_RUN_ATTEMPT')),
                       ('workflow', os.environ.get('GITHUB_WORKFLOW')),
                       ('runner_os', os.environ.get('RUNNER_OS'))):
        if value and key not in provenance:
            provenance[key] = value
    notes = delivery.instructions(args.target, args.source_sha, args.sdk_version).encode('utf-8')
    covered = dict(records)
    covered[delivery.INSTRUCTIONS] = {'bytes': len(notes), 'sha256': delivery.sha256_file_bytes(notes), 'mode': 0o644}
    sums = delivery.checksums(covered).encode('utf-8')
    inner = delivery.manifest(args.target, args.source_sha, args.sdk_version, covered, args.exclude, archive_name)
    inner['provenance'] = provenance
    if build_identity:
        inner['producer'] = {'source_sha': build_identity['source_sha'],
                             'sdk_version': build_identity['sdk_version'],
                             'build_json_sha256': delivery.sha256_file(identity_path)}
    inner['metadata_files'] = [delivery.MANIFEST, delivery.CHECKSUMS]
    extras = {
        delivery.INSTRUCTIONS: (notes, 0o644),
        delivery.MANIFEST: ((json.dumps(inner, indent=2, sort_keys=True) + '\n').encode('utf-8'), 0o644),
        delivery.CHECKSUMS: (sums, 0o644),
    }
    handle, temporary = tempfile.mkstemp(prefix='s20-archive-', dir=str(output))
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for name in sorted(records):
                source = payload / name
                with source.open('rb') as stream, bundle.open(zip_entry(name, records[name]['mode']), 'w') as target:
                    shutil.copyfileobj(stream, target, 1024 * 1024)
            for name in (delivery.INSTRUCTIONS, delivery.MANIFEST, delivery.CHECKSUMS):
                data, mode = extras[name]
                bundle.writestr(zip_entry(name, mode), data)
        shutil.move(temporary, archive)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    outer = dict(inner)
    outer['archive'] = {'name': archive_name, 'bytes': archive.stat().st_size,
                        'sha256': delivery.sha256_file(archive),
                        'checksums_sha256': delivery.sha256_file_bytes(sums)}
    (output / delivery.MANIFEST).write_text(json.dumps(outer, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    (output / (archive_name + '.sha256')).write_text(outer['archive']['sha256'] + '  ' + archive_name + '\n', encoding='utf-8')
    (output / delivery.INSTRUCTIONS).write_bytes(notes)
    print(json.dumps({'target': args.target, 'archive': str(archive), 'bytes': outer['archive']['bytes'],
                      'sha256': outer['archive']['sha256'], 'files': len(covered),
                      'entry': outer['entry'], 'source_sha': args.source_sha,
                      'instructions_sha256': covered[delivery.INSTRUCTIONS]['sha256']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
