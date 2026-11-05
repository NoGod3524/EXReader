#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Dependency closure of a relocated Windows distribution.

Reads the reals import tables of the consumer binaries that were just built
against the extracted prefix, then checks the exported vendor closure: every
static library named by EXReaderDependencies.cmake must be installed, and no
import may name a directory, a drive or a build-machine file.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib

VENDOR_REFERENCE = re.compile(r'lib/exreader/([A-Za-z0-9_.+\-]+\.lib)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--pe', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    distlib.require(len(args.pe) >= 3,
                    'at least three installed consumer binaries are required for the closure')
    imports, absolute, machines, checked = set(), [], {}, []
    for path in args.pe:
        distlib.require(Path(path).is_file(), 'consumer binary is missing: ' + str(path))
        facts = distlib.scan_pe(Path(path).name, Path(path).read_bytes())
        imports.update(facts['imports'])
        absolute.extend(facts['absolute_imports'])
        machines[Path(path).name] = facts['machine']
        checked.append({'name': Path(path).name, 'bytes': Path(path).stat().st_size,
                        'sha256': distlib.digest(path), 'imports': facts['imports']})
    config = args.stage / 'lib/cmake/EXReader/EXReaderDependencies.cmake'
    distlib.require(config.is_file(), 'exported dependency config is missing: ' + str(config))
    referenced = sorted(set(VENDOR_REFERENCE.findall(config.read_text(encoding='utf-8'))))
    installed_dir = args.stage / 'lib/exreader'
    installed = sorted(path.name for path in installed_dir.glob('*.lib')) if installed_dir.is_dir() else []
    missing = [name for name in referenced if name not in installed]
    unused = [name for name in installed if name not in referenced]
    report = {'schema': 'reader-distribution-windows-dependencies-v1',
              'stage': str(args.stage), 'checked_pe_files': len(checked),
              'imports': sorted(imports), 'absolute_imports': absolute,
              'machines': machines, 'consumers': checked,
              'vendor_closure': {'declared': len(referenced), 'installed': len(installed),
                                 'missing': missing, 'unreferenced': unused,
                                 'referenced': referenced[:12]},
              'accepted': not absolute and not missing and len(checked) >= 3}
    distlib.write_json(args.output, report)
    print(json.dumps({'imports': len(imports), 'absolute': len(absolute),
                      'vendor': report['vendor_closure']['declared'], 'accepted': report['accepted']}))
    if not report['accepted']:
        print('dependency closure is incomplete or path-bearing', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
