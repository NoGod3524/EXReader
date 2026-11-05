#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove the installed pkg-config unit links and runs a real public consumer.

The same public C consumer source is compiled twice from the relocated prefix: once
through the installed CMake package and once with `pkg-config --cflags` plus
`pkg-config --libs --static` only. Both programs open the installed book, lay it out
and render it, so a pkg-config unit that merely looks relocatable but cannot link a
real consumer is refused instead of being reported as a passing flag set.
"""
import argparse
import hashlib
import json
from pathlib import Path

FIELDS = ('version', 'abi', 'format', 'pages', 'text_bytes', 'bitmap_width', 'bitmap_height')


def digest(path):
    if path is None:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def compare(reference, probe):
    problems = []
    for name, report in (('CMake', reference), ('pkg-config', probe)):
        if report.get('schema') != 1:
            problems.append(name + ' consumer report schema is not 1')
        if report.get('failures') != 0:
            problems.append('%s consumer reported %s failures' % (name, report.get('failures')))
        if type(report.get('png_bytes')) is not int or report['png_bytes'] <= 0:
            problems.append(name + ' consumer rendered no PNG bytes')
    for field in FIELDS:
        if reference.get(field) != probe.get(field):
            problems.append('pkg-config consumer %s differs from the CMake build: %s != %s'
                            % (field, probe.get(field), reference.get(field)))
    for field in ('pages', 'text_bytes', 'bitmap_width', 'bitmap_height'):
        if type(probe.get(field)) is not int or probe[field] <= 0:
            problems.append('pkg-config consumer ' + field + ' is not a positive integer')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True,
                        help='report of the consumer built through the installed CMake package')
    parser.add_argument('--probe', type=Path, required=True,
                        help='report of the consumer built from the pkg-config unit only')
    parser.add_argument('--reference-png', type=Path)
    parser.add_argument('--probe-png', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        reference, probe = load(args.reference), load(args.probe)
        problems = compare(reference, probe)
    except (OSError, ValueError) as error:
        reference, probe = {}, {}
        problems = ['consumer report unreadable: ' + str(error)]
    reference_png = digest(args.reference_png)
    probe_png = digest(args.probe_png)
    if args.reference_png is not None and reference_png is None:
        problems.append('the CMake consumer PNG is missing')
    if args.probe_png is not None and probe_png is None:
        problems.append('the pkg-config consumer PNG is missing')
    if reference_png and probe_png and reference_png != probe_png:
        problems.append('the two build paths did not render identical PNG bytes')
    result = {
        'schema': 1,
        'accepted': not problems,
        'problems': problems,
        'compared_fields': list(FIELDS),
        'reference': {field: reference.get(field) for field in FIELDS},
        'probe': {field: probe.get(field) for field in FIELDS},
        'reference_png_sha256': reference_png,
        'probe_png_sha256': probe_png,
        'rendered_png_sha256_equal': bool(reference_png) and reference_png == probe_png,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': result['accepted'],
                      'rendered_png_sha256_equal': result['rendered_png_sha256_equal'],
                      'problems': problems}))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
