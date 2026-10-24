#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rewrite build-machine roots out of the text surfaces of a distribution stage.

Detection is case-insensitive, so rewriting is too: each matched span is
replaced by a stable token and recorded with its original bytes. The copy is
then audited by rebuilding it byte-for-byte from the recorded occurrences, so a
rewrite can never hide a second edit. Binary containers are never touched: a
binary hit is a refusal and the leaking archive stays blocked.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib


def copy_tree(source, destination):
    source = Path(source)
    distlib.require(source.is_dir(), 'sanitizer source is not a directory: ' + str(source))
    source = source.resolve()
    destination = Path(destination)
    distlib.require(not destination.exists(), 'sanitizer destination already exists')
    distlib.require(not destination.resolve().is_relative_to(source), 'destination inside source')
    shutil.copytree(source, destination, symlinks=False, copy_function=shutil.copyfile)
    count = 0
    for path in sorted(destination.rglob('*')):
        if path.is_dir():
            continue
        distlib.require(not path.is_symlink(), 'symlink copied into the stage: ' + str(path))
        count += 1
        distlib.require(count <= 20000, 'stage has too many files to sanitize safely')
    return destination


def stage_digest(root):
    return distlib.digest_of_entries(distlib.inventory(root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--scan', type=Path, required=True, help='scan report of the source stage')
    parser.add_argument('--text-limit', type=int, default=8 * 1024 * 1024)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    distlib.require(args.text_limit > 0, 'text limit must be positive')
    scan = distlib.load_json(args.scan)
    needles = {key: value.encode('utf-8') for key, value in scan['patterns'].items()}
    distlib.require(needles, 'scan report has no patterns to rewrite')
    before = stage_digest(args.source)
    destination = copy_tree(args.source, args.destination)
    rewritten, refused = [], []
    for record in scan['records']:
        if not record['hits']:
            continue
        path = destination / record['path']
        distlib.require(path.is_file(), 'scanned file disappeared from the stage: ' + record['path'])
        payload = path.read_bytes()
        keys = sorted({hit['pattern'] for hit in record['hits']})
        if not record.get('text') or path.suffix.lower() not in distlib.REWRITABLE_SUFFIXES:
            refused.append({'path': record['path'], 'kind': record['kind'],
                            'patterns': keys, 'reason': 'binary or non-rewritable surface'})
            continue
        distlib.require(len(payload) <= args.text_limit,
                        'rewritable file exceeds the declared text limit: ' + record['path'])
        selected = {key: needles[key] for key in keys}
        replacement, occurrences = distlib.rewrite_occurrences(payload, selected)
        distlib.require(occurrences, 'scan declared hits but no span matched: ' + record['path'])
        distlib.require(distlib.restore_occurrences(replacement, occurrences) == payload,
                        'rewrite is not invertible for ' + record['path'])
        again, extra = distlib.rewrite_occurrences(replacement, selected)
        distlib.require(again == replacement and not extra,
                        'rewrite is not idempotent for ' + record['path'])
        distlib.require(replacement.count(bytes([10])) == payload.count(bytes([10])),
                        'rewrite changed the line count of ' + record['path'])
        path.write_bytes(replacement)
        used = sorted({occurrence['key'] for occurrence in occurrences})
        rewritten.append({'path': record['path'],
                          'patterns': used,
                          'tokens': [distlib.path_token(key).decode('utf-8') for key in used],
                          'occurrences': occurrences,
                          'bytes_before': len(payload), 'bytes_after': len(replacement),
                          'sha256_before': distlib.digest_bytes(payload),
                          'sha256_after': distlib.digest_bytes(replacement)})
    after = stage_digest(destination)
    residual = distlib.scan_tree(destination, needles)
    text_hits = sum(1 for item in residual for hit in item['hits'] if hit['class'] == 'text')
    binary_hits = sum(1 for item in residual for hit in item['hits'] if hit['class'] == 'binary')
    report = {'schema': 'reader-distribution-windows-sanitize-v1',
              'source': str(args.source), 'destination': str(args.destination),
              'stage_digest_before': before, 'stage_digest_after': after,
              'text_limit': args.text_limit,
              'patterns': {key: value.decode('utf-8', 'replace') for key, value in needles.items()},
              'rewritten': rewritten, 'refused': refused,
              'residual': {'text_hits': text_hits, 'binary_hits': binary_hits},
              'accepted': bool(not refused and not text_hits and not binary_hits)}
    distlib.write_json(args.output, report)
    print(json.dumps({'rewritten': len(rewritten), 'refused': len(refused),
                      'residual_text': text_hits, 'residual_binary': binary_hits,
                      'occurrences': sum(len(item['occurrences']) for item in rewritten),
                      'accepted': report['accepted']}))
    if refused:
        print('blocking binary or non-rewritable build-machine paths: ' +
              json.dumps(refused[:4]), file=sys.stderr)
        return 2
    if text_hits or binary_hits:
        print('build-machine paths remain after sanitization', file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
