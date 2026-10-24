#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove, per surface, what an external compile/archive parameter controls.

Three surfaces are proven separately on real MSVC output:
  * COFF debug sections record the source path as spelled on the command line;
  * the __FILE__ macro repeats that same spelling at run time;
  * archive member names stay basenames, while a .drectve directive can carry an
    absolute library path and therefore has to be detected and refused.
The control pair is what makes the shipped-stage scan meaningful: the scanner
must see a deliberate leak before its silence on the distribution is credited.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib


def scan(path, patterns):
    payload = Path(path).read_bytes()
    facts = distlib.scan_bytes(Path(path).name, payload, patterns)
    facts['sha256'] = distlib.digest_bytes(payload)
    return facts


def flatten(path):
    return str(path).replace('\\', '/').lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', default=[],
                        help='absolute build root that controls must reproduce')
    parser.add_argument('--raw-obj', type=Path, required=True)
    parser.add_argument('--bare-obj', type=Path, required=True)
    parser.add_argument('--raw-lib', type=Path, required=True)
    parser.add_argument('--bare-lib', type=Path, required=True)
    parser.add_argument('--nested-lib', type=Path, required=True)
    parser.add_argument('--drective-lib', type=Path, required=True)
    parser.add_argument('--raw-run', type=Path, required=True)
    parser.add_argument('--bare-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    distlib.require(args.root, 'at least one --root is required')
    patterns = distlib.build_patterns(args.root)
    facts = {name: scan(path, patterns) for name, path in {
        'raw_obj': args.raw_obj, 'bare_obj': args.bare_obj, 'raw_lib': args.raw_lib,
        'bare_lib': args.bare_lib, 'nested_lib': args.nested_lib,
        'drective_lib': args.drective_lib}.items()}
    raw_run = distlib.load_json(args.raw_run)
    bare_run = distlib.load_json(args.bare_run)
    roots = [flatten(item) for item in args.root]
    results = []

    control_debug = facts['raw_obj']['debug_section_count'] >= 1 and bool(facts['raw_obj']['hits'])
    distlib.named(results, 'coff-debug-control-records-absolute-path', control_debug,
                  {'debug_sections': facts['raw_obj']['debug_section_count'],
                   'hits': len(facts['raw_obj']['hits']),
                   'sections': facts['raw_obj']['debug_sections'][:3]})
    relative_debug = (facts['bare_obj']['debug_section_count'] >= 1 and not facts['bare_obj']['hits'])
    distlib.named(results, 'coff-debug-relative-spelling-avoids-root', relative_debug,
                  {'debug_sections': facts['bare_obj']['debug_section_count'],
                   'hits': len(facts['bare_obj']['hits'])})

    macro = flatten(raw_run.get('file_macro', ''))
    distlib.named(results, 'file-macro-control-is-absolute',
                  any(flat in macro for flat in roots), {'file_macro': raw_run.get('file_macro')})
    distlib.named(results, 'file-macro-relative-spelling-preserved',
                  flatten(bare_run.get('file_macro', '')) == 'path_surface.c',
                  {'file_macro': bare_run.get('file_macro')})

    names = (facts['raw_lib']['member_names_with_separator'] +
             facts['nested_lib']['member_names_with_separator'])
    distlib.named(results, 'archive-member-names-are-basenames', not names,
                  {'members': facts['raw_lib']['members'] + facts['nested_lib']['members'],
                   'sample': facts['nested_lib']['member_names_sample'], 'separated': names[:4]})

    absolute = facts['drective_lib']['drective_absolute']
    distlib.named(results, 'archive-drective-absolute-detected', bool(absolute),
                  {'directives': absolute[:3]})

    blocked = (bool(facts['drective_lib']['hits']) or bool(absolute) or
               bool(facts['raw_lib']['hits']) or
               any(item.get('member_names_with_separator') for item in facts.values()))
    distlib.named(results, 'control-surfaces-would-block-shipping', blocked,
                  {'raw_lib_hits': len(facts['raw_lib']['hits']),
                   'drective': len(absolute)})

    report = {'schema': 'reader-distribution-windows-surfaces-v1', 'roots': args.root,
              'facts': {name: {key: value for key, value in item.items() if key != 'hits'} |
                        {'hits': item['hits'][:3], 'hit_count': len(item['hits'])}
                        for name, item in facts.items()},
              'runs': {'raw': raw_run, 'bare': bare_run}, 'results': results}
    distlib.write_json(args.output, report)
    distlib.require_named_pass(
        results, ['coff-debug-control-records-absolute-path',
                  'coff-debug-relative-spelling-avoids-root', 'file-macro-control-is-absolute',
                  'file-macro-relative-spelling-preserved', 'archive-member-names-are-basenames',
                  'archive-drective-absolute-detected', 'control-surfaces-would-block-shipping'])
    print(json.dumps({'results': len(results), 'accepted': True}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
