#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove that relocation and duplicate removal did not change observed behaviour.

Two audit reports must agree on the rendered PNG digest, on every public consumer
counter and on every nine-format smoke outcome. Absolute paths never enter the
comparison, so the same report shape works before, after and after extraction.
"""
import argparse
import json
from pathlib import Path
import sys

KEYS = ('version', 'abi', 'pages', 'text_bytes', 'png_bytes', 'headers', 'negative_checks')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def compare(first, second):
    problems = []
    for name in ('source_sha', 'platform', 'profile'):
        if first.get(name) != second.get(name):
            problems.append('audit identity differs: ' + name)
    for report in (first, second):
        if report.get('release_ready') is not True:
            problems.append('audit report for %s is not release ready' % report.get('label'))
    one, two = first.get('png') or {}, second.get('png') or {}
    if not one or not two:
        problems.append('a rendered PNG digest is missing')
    elif one.get('sha256') != two.get('sha256') or one.get('bytes') != two.get('bytes'):
        problems.append('rendered PNG differs between labels')
    for consumer in ('c', 'cxx'):
        left = first.get('consumers', {}).get(consumer) or {}
        right = second.get('consumers', {}).get(consumer) or {}
        if not left or not right:
            problems.append('consumer %s report is missing' % consumer)
            continue
        for key in KEYS:
            if key in left or key in right:
                if left.get(key) != right.get(key):
                    problems.append('consumer %s field %s differs' % (consumer, key))
    left_entries = first.get('smoke', {}).get('entries') or []
    right_entries = second.get('smoke', {}).get('entries') or []
    if len(left_entries) != 9 or len(right_entries) != 9:
        problems.append('nine-format smoke entries are missing')
    else:
        for left, right in zip(left_entries, right_entries):
            if (left.get('path') != right.get('path')
                    or left.get('classification') != right.get('classification')
                    or left.get('observed') != right.get('observed')):
                problems.append('smoke outcome differs for %s' % left.get('path'))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    problems = compare(load(args.first), load(args.second))
    result = {'schema': 1, 'first': str(args.first), 'second': str(args.second),
              'accepted': not problems, 'problems': problems,
              'compared': {'png': True, 'consumers': ['c', 'cxx'], 'smoke_entries': 9}}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
