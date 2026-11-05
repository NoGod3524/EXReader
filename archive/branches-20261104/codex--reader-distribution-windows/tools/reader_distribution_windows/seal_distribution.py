#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Seal an installed Windows stage into a deterministic, audited ZIP.

The seal is independent of the workflow's claims: it re-inventories the stage,
re-scans its bytes for the recorded build-machine roots, verifies that the ZIP
content equals the inventory, and reseals into a scratch directory to prove the
archive digest is reproducible.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib

REQUIRED_CATEGORIES = ('header', 'config', 'license', 'library', 'doc')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--scan', type=Path, required=True, help='scan report of the same stage')
    parser.add_argument('--sanitize', type=Path, required=True)
    parser.add_argument('--archive-out', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--epoch', type=int, default=distlib.SEAL_EPOCH)
    parser.add_argument('--skip-determinism-check', action='store_true')
    args = parser.parse_args()
    distlib.require(len(args.source_sha) == 40 and all(c in '0123456789abcdef' for c in args.source_sha),
                    'source SHA must be a full 40 character commit id')
    sanitize = distlib.load_json(args.sanitize)
    distlib.require(sanitize.get('accepted') is True and not sanitize.get('refused') and
                    sanitize.get('residual', {}).get('binary_hits') == 0 and
                    sanitize.get('residual', {}).get('text_hits') == 0,
                    'stage sanitization did not accept: rebuild with clean parameters')
    scan = distlib.load_json(args.scan)
    needles = {key: value.encode('utf-8') for key, value in scan['patterns'].items()}
    entries = distlib.inventory(args.stage)
    categories = distlib.category_digests(entries)
    distlib.require(sanitize.get('stage_digest_after') == distlib.digest_of_entries(entries),
                    'the stage being sealed is not the sanitized stage that was audited')
    for name in REQUIRED_CATEGORIES:
        distlib.require(categories[name]['files'] > 0 and categories[name]['sha256'],
                        'distribution is missing the %s category' % name)
    records = distlib.scan_tree(args.stage, needles)
    hits = [hit for item in records for hit in item['hits']]
    distlib.require(not hits, 'build-machine paths remain in the sealed stage: ' + json.dumps(hits[:4]))
    distlib.require(not any(item.get('drective_absolute') for item in records),
                    'absolute .drectve directives remain in the sealed stage')
    sealed = distlib.seal_zip(args.stage, args.archive_out, epoch=args.epoch)
    reproducibility = None
    if not args.skip_determinism_check:
        with tempfile.TemporaryDirectory() as temporary:
            again = distlib.seal_zip(args.stage, Path(temporary) / args.archive_out.name,
                                     epoch=args.epoch)
            reproducibility = {'second_sha256': again['sha256'], 'identical': again['sha256'] == sealed['sha256']}
            distlib.require(reproducibility['identical'], 'sealing the same stage is not reproducible')
    packed = distlib.read_zip(args.archive_out)
    expected = {item['path']: (item['bytes'], item['sha256']) for item in entries}
    actual = {item['path']: (item['bytes'], item['sha256']) for item in packed}
    distlib.require(expected == actual, 'archive content differs from the installed stage')
    ci = {name: os.environ[name] for name in
          ('GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB',
           'RUNNER_OS', 'RUNNER_ARCH', 'GITHUB_WORKSPACE') if name in os.environ}
    report = {'schema': 'reader-distribution-windows-archive-v1',
              'accepted': True, 'source_sha': args.source_sha, 'ci': ci,
              'stage': {'files': len(entries), 'bytes': sum(item['bytes'] for item in entries),
                        'digest': distlib.digest_of_entries(entries)},
              'entries': entries, 'categories': categories,
              'archive': dict(sealed, entries=len(packed), content_digest=distlib.digest_of_entries(packed)),
              'epoch': args.epoch, 'reproducibility': reproducibility,
              'scan': {'files': len(records), 'debug_section_count':
                       sum(item.get('debug_section_count', 0) for item in records),
                       'drective_absolute':
                       sum(len(item.get('drective_absolute') or []) for item in records),
                       'member_names_with_separator':
                       sum(len(item.get('member_names_with_separator') or []) for item in records),
                       'member_names_escaping':
                       sum(len(item.get('member_names_escaping') or []) for item in records)},
              'sanitization': {'rewritten': len(sanitize['rewritten']),
                               'refused': len(sanitize['refused']),
                               'stage_digest_after': sanitize['stage_digest_after']},
              'published': False}
    distlib.write_json(args.report, report)
    print(json.dumps({'archive': sealed['archive'], 'bytes': sealed['bytes'],
                      'sha256': sealed['sha256'], 'entries': sealed['entries'],
                      'stage_digest': report['stage']['digest']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
