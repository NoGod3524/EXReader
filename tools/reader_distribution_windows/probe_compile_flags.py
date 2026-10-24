#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Select the external compile parameters that remove build-machine paths.

Git-bash rewrites arguments that look like POSIX paths, so every native tool is
invoked here with an argument list instead of a shell. Each candidate flag set is
compiled for real and the resulting object is scanned for the build root: only a
candidate whose object carries no build root and still emits usable debug
information is adopted. The verdict is evidence, not an assumption.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib


def candidates(workspace):
    windows = workspace.replace('/', '\\')
    posix = workspace.replace('\\', '/')
    return [
        ['/utf-8', '/experimental:deterministic', '/pathmap:%s=exreader-src' % windows],
        ['/utf-8', '/experimental:deterministic', '/pathmap:%s=exreader-src' % posix],
        ['/utf-8', '/experimental:deterministic', '/pathmap:%s=-' % windows],
        ['/utf-8'],
    ]


def compile_candidate(flags, source, scratch, tag):
    target = scratch / (tag + '.obj')
    command = ['cl', '/nologo', '/c', '/Z7', '/Fo' + str(target)] + flags + [str(source)]
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    record = {'flags': flags, 'returncode': done.returncode, 'output': done.stdout.strip()[-600:]}
    if target.is_file():
        record['bytes'] = target.stat().st_size
        record['sha256'] = distlib.digest(target)
        try:
            machine, sections = distlib.coff_section_names(target.read_bytes())
            record['machine'] = hex(machine)
            record['debug_sections'] = [item['name'] for item in sections
                                        if item['name'].startswith('.debug')]
        except ValueError as error:
            record['error'] = str(error)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    distlib.require(args.source.is_file(), 'probe source is missing: ' + str(args.source))
    args.scratch.mkdir(parents=True, exist_ok=True)
    patterns = distlib.build_patterns([args.workspace])
    results, chosen = [], None
    for index, flags in enumerate(candidates(args.workspace)):
        record = compile_candidate(flags, args.source, args.scratch, 'candidate-%d' % index)
        target = args.scratch / ('candidate-%d.obj' % index)
        if target.is_file():
            facts = distlib.scan_file(target, patterns)
            record['hits'] = len(facts['hits'])
            record['hit_sample'] = facts['hits'][:2]
        else:
            record['hits'] = None
        results.append(record)
        if record['returncode'] == 0 and record.get('hits') == 0 and chosen is None:
            chosen = flags
    report = {'schema': 'reader-distribution-windows-compile-flags-v1',
              'workspace': args.workspace, 'candidates': results,
              'supported': chosen is not None, 'chosen': chosen or []}
    distlib.write_json(args.output, report)
    print(json.dumps({'supported': report['supported'], 'chosen': report['chosen'],
                      'candidates': [(item['returncode'], item.get('hits'),
                                      item.get('debug_sections')) for item in results]}))
    return 0 if chosen is not None else 1


if __name__ == '__main__':
    sys.exit(main())
