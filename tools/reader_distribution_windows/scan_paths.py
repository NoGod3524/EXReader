#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Scan an installed Windows stage or a distribution ZIP for build-machine paths.

Every COFF/PE container fact is recorded as well: archive member names, debug
sections and absolute .drectve directives. A binary hit is blocking; a text hit
is reported for the sanitizer and is still a failure for a shipped artifact.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib


def iterate_zip(path, patterns):
    import zipfile
    records = []
    with zipfile.ZipFile(Path(path)) as archive:
        for info in archive.infolist():
            name = info.filename
            distlib.require('\\' not in name and not name.startswith('/') and
                            '..' not in name.split('/'), 'escaping zip entry: ' + name)
            payload = archive.read(info)
            distlib.require(len(payload) <= distlib.DEFAULT_SCAN_LIMIT,
                            'zip entry exceeds the declared scan limit: ' + name)
            facts = distlib.scan_bytes(name, payload, patterns)
            facts['sha256'] = distlib.digest_bytes(payload)
            facts['category'] = distlib.category_of(name)
            records.append(facts)
    distlib.require(records, 'empty distribution archive: ' + str(path))
    return records


def summarise(records):
    summary = {'files': len(records), 'bytes': sum(item['bytes'] for item in records),
               'text_hits': 0, 'binary_hits': 0, 'archives': 0, 'pe_files': 0,
               'debug_section_count': 0, 'drective_absolute': 0,
               'member_names_with_separator': 0, 'categories': {}}
    for item in records:
        summary['categories'].setdefault(item['category'], 0)
        summary['categories'][item['category']] += 1
        for hit in item['hits']:
            summary['text_hits' if hit['class'] == 'text' else 'binary_hits'] += 1
        if item['kind'] == 'archive':
            summary['archives'] += 1
            summary['debug_section_count'] += item['debug_section_count']
            summary['drective_absolute'] += len(item['drective_absolute'])
            summary['member_names_with_separator'] += len(item['member_names_with_separator'])
        elif item['kind'] == 'pe':
            summary['pe_files'] += 1
    summary['hits'] = summary['text_hits'] + summary['binary_hits']
    summary['accepted'] = summary['hits'] == 0 and summary['drective_absolute'] == 0
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, action='append', default=[], help='directory to scan')
    parser.add_argument('--zip', type=Path, action='append', default=[], help='archive to scan')
    parser.add_argument('--root-arg', action='append', default=[],
                        help='absolute path that must never appear in the scanned bytes')
    parser.add_argument('--label', default='', help='source label recorded in the report')
    parser.add_argument('--source-sha', default='')
    parser.add_argument('--limit', type=int, default=distlib.DEFAULT_SCAN_LIMIT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-clean', action='store_true',
                        help='exit nonzero on any hit, not only on binary hits')
    parser.add_argument('--print-leaks', type=int, default=0,
                        help='print this many leaking files with their surfaces')
    args = parser.parse_args()
    if not args.root and not args.zip:
        parser.error('Provide at least one --root or --zip target')
    if args.limit <= 0:
        parser.error('--limit must be positive')
    patterns = distlib.build_patterns(args.root_arg or [str(Path.cwd())])
    records = []
    for root in args.root:
        records.extend(distlib.scan_tree(root, patterns, limit=args.limit))
    for archive in args.zip:
        records.extend(iterate_zip(archive, patterns))
    summary = summarise(records)
    report = {'schema': 'reader-distribution-windows-scan-v1', 'label': args.label,
              'source_sha': args.source_sha, 'roots': list(args.root_arg),
              'patterns': {key: value.decode('utf-8', 'replace') for key, value in patterns.items()},
              'limit': args.limit, 'summary': summary,
              'records': [{key: value for key, value in item.items() if key != 'hits'} |
                          {'hits': item['hits']} for item in records]}
    distlib.write_json(args.output, report)
    if args.print_leaks:
        leaking = sorted((item for item in records if item['hits']),
                         key=lambda item: (-len(item['hits']), item['path']))
        for item in leaking[:args.print_leaks]:
            print('LEAK %-45s kind=%s hits=%d patterns=%s debug_sections=%d drective=%d members=%s' % (
                item['path'], item['kind'], len(item['hits']),
                ','.join(sorted({hit['pattern'] for hit in item['hits']})),
                item.get('debug_section_count', 0), len(item.get('drective_absolute', [])),
                item.get('member_names_sample', [])[:4]))
            for hit in item['hits'][:2]:
                print('     %s @%d %s' % (hit['pattern'], hit['offset'], hit['context'][:120]))
        if len(leaking) > args.print_leaks:
            print('LEAK ... %d more leaking files' % (len(leaking) - args.print_leaks))
        by_suffix = {}
        for item in leaking:
            suffix = Path(item['path']).suffix.lower() or '<none>'
            by_suffix[suffix] = by_suffix.get(suffix, 0) + len(item['hits'])
        print('LEAK total_files=%d total_hits=%d by_suffix=%s' % (
            len(leaking), sum(len(item['hits']) for item in leaking),
            sorted(by_suffix.items(), key=lambda pair: -pair[1])[:8]))
    blocking = [hit for item in records for hit in item['hits'] if hit['class'] == 'binary']
    surfaces = ({'drective_absolute': summary['drective_absolute'],
                 'member_names_with_separator': summary['member_names_with_separator'],
                 'absolute_imports': sum(len(item.get('absolute_imports', [])) for item in records)})
    print(json.dumps({'files': summary['files'], 'hits': summary['hits'],
                      'text_hits': summary['text_hits'], 'binary_hits': summary['binary_hits'],
                      'debug_section_count': summary['debug_section_count'],
                      'archives': summary['archives'], 'pe_files': summary['pe_files'],
                      'surfaces': surfaces}))
    if args.require_clean:
        if blocking or any(surfaces.values()):
            print('blocking binary build-machine surfaces: ' +
                  json.dumps({'hits': blocking[:4], 'surfaces': surfaces}), file=sys.stderr)
            return 2
        if summary['hits']:
            print('build-machine paths remain in a shipped artifact', file=sys.stderr)
            return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
