#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Seal the authenticated GTK compact payload and relocate it out of the workspace.

The archive, manifest and extraction steps are the reviewed J24 distribution
primitives (tools/reader_distribution_unix/contract.py at the pinned J24 source),
reused unchanged: single-root tar, no links in input, per-file digest manifest,
and re-extraction that re-verifies every member.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import common

NAME = 'EXReader-Linux-3.41.0-linux-x86_64-relocatable.tar.gz'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--j24', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--relocated', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = common.Checks()
    producer = common.read_json(args.producer)
    payload = args.payload.resolve(strict=True)
    workspace = args.workspace.resolve()

    problems = common.tree_problems(payload, producer['payload']['files'])
    checks.add('payload_matches_authenticated_bytes', not problems,
               'producer payload files unchanged' if not problems else '; '.join(problems[:6]))

    j24 = args.j24.resolve(strict=True)
    sys.path.insert(0, str(j24))
    import contract  # noqa: E402  (the pinned J24 distribution primitives)
    checks.add('j24_primitives_reused',
               all(hasattr(contract, name) for name in ('seal', 'extract', 'walk', 'tree_problems')),
               'imported %s' % contract.__file__)

    epoch = int(common.git('show', '-s', '--format=%ct', 'HEAD'))
    identity = {
        'schema': 1,
        'kind': 's02-gtk-compact-relocatable-candidate',
        'verifier_source': os.environ.get('GITHUB_SHA', ''),
        'epoch': epoch,
        'producer': {'repository': producer.get('repository'),
                     'run': producer['run']['id'],
                     'attempt': producer['run']['attempt'],
                     'source': producer['run']['head_sha'],
                     'artifact': producer['selected_artifact']['id'],
                     'artifact_name': producer['selected_artifact']['name'],
                     'artifact_digest': producer['selected_artifact'].get('digest'),
                     'artifact_expires_at': producer['selected_artifact'].get('expires_at'),
                     'zip_sha256': producer['zip']['sha256'],
                     'program_sha256': producer['program']['sha256']},
        'j24': {'source': '2f5677f13efc34b200af697f1b6f7bff2b656e3b',
                'contract': common.sha256_file(j24 / 'contract.py')},
    }
    archive_dir = output / 'archive'
    manifest = contract.seal(payload, archive_dir, NAME, epoch, identity)
    archive = archive_dir / NAME
    archive_sha = common.sha256_file(archive)
    manifest = common.read_json(archive_dir / 'manifest.json')
    checks.add('archive_identity',
               manifest['archive']['sha256'] == archive_sha
               and manifest['archive']['bytes'] == archive.stat().st_size
               and manifest['root'] == NAME[:-len('.tar.gz')],
               '%s %d bytes sha256 %s' % (NAME, archive.stat().st_size, archive_sha))

    destination = args.relocated
    outside = not (os.path.realpath(str(destination)) + '/').startswith(
        os.path.realpath(str(workspace)) + '/')
    checks.add('relocated_outside_workspace', outside,
               'destination %s workspace %s' % (destination, workspace))

    report = contract.extract(archive, destination, manifest)
    checks.add('relocated_extract_identity',
               report['accepted'] is True and report['members'] == len(manifest['files'])
               and not report['problems'],
               '%d members, problems %s' % (report['members'], report['problems'][:4]))

    problems = contract.tree_problems(destination, manifest['files'])
    checks.add('relocated_tree_identity', not problems,
               'every relocated byte keeps its sealed digest' if not problems
               else '; '.join(problems[:6]))

    program = destination / 'bin/exreader-linux'
    checks.add('relocated_program_identity',
               program.is_file()
               and common.sha256_file(program) == producer['program']['sha256']
               and os.access(str(program), os.X_OK),
               'sha256 %s expected %s executable %s' % (
                   common.sha256_file(program) if program.is_file() else 'missing',
                   producer['program']['sha256'], os.access(str(program), os.X_OK)))

    document = {
        'schema': 1,
        'kind': 's02-relocatable-candidate',
        'verifier_source': os.environ.get('GITHUB_SHA', ''),
        'payload': {'path': str(payload), 'files': len(manifest['files']),
                    'bytes': sum(item['bytes'] for item in manifest['files'])},
        'archive': {'name': NAME, 'path': str(archive), 'bytes': archive.stat().st_size,
                    'sha256': archive_sha, 'manifest_sha256': common.sha256_file(archive_dir / 'manifest.json'),
                    'root': manifest['root'], 'members': len(manifest['files'])},
        'relocated': {'path': str(destination), 'moved': True,
                      'source_length': len(str(payload)), 'destination_length': len(str(destination)),
                      'files': report['members'],
                      'program_sha256': producer['program']['sha256']},
        'identity': identity,
        'checks': checks.items,
        'problems': checks.failed(),
        'ok': checks.accepted(),
    }
    common.write_json(output / 'package.json', document)
    print(json.dumps({'archive_sha256': archive_sha, 'bytes': archive.stat().st_size,
                      'relocated': str(destination), 'files': report['members'],
                      'ok': checks.accepted(), 'failed': checks.failed()}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
