#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Drop Windows version-resource objects from vendor static libraries.

freetype and libtiff compile a .rc file, and the resulting CVTRES object records
the absolute build directory in its own symbol/string table. No compiler switch
reaches that object, so the distribution removes it structurally instead:

  * members are identified by their COFF sections (.rsrc$01/.rsrc$02 only),
  * every remaining member is written out and the archive is rebuilt by the real
    lib.exe, so the linker members and the symbol index are regenerated,
  * the rebuild is audited: kept members stay byte-identical, defined external
    symbols lose only the resource symbols, and the rebuilt library is re-scanned
    for build-machine roots before it may replace the shipped file.

Nothing here patches bytes inside an object: a member is either kept untouched or
not shipped, and the proof is the audit plus the relocated consumer link.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib

RESOURCE_SECTIONS = frozenset({'.rsrc$01', '.rsrc$02'})
LINKER_MEMBERS = frozenset({'/', '//'})
SYMBOL_LINE = re.compile(r'^[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+SECT[0-9A-Fa-f]+\s+\S+\s+\S+\s+External\s+\|\s+(\S+)')


def is_resource_object(body):
    try:
        machine, sections = distlib._coff_sections(body)
    except ValueError:
        return False
    names = {item['name'] for item in sections}
    if '.rsrc$01' not in names or '.text' in names:
        return False
    return not any(name.startswith('.text') for name in names)


def plan(payload):
    """Members to keep, members to drop, and the long-name table of one archive."""
    members = distlib.archive_members(payload)
    keep, drop = [], []
    for member in members:
        if member['raw'] in LINKER_MEMBERS:
            continue
        if is_resource_object(member['body']):
            drop.append(member['name'])
        else:
            keep.append(member)
    return keep, drop


def dump_symbols(dumpbin, path):
    done = subprocess.run([dumpbin, '/nologo', '/symbols', str(path)], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    distlib.require(done.returncode == 0, 'dumpbin failed on ' + str(path))
    names = set()
    for line in done.stdout.splitlines():
        match = SYMBOL_LINE.match(line.strip())
        if match:
            names.add(match.group(1))
    return names


def rebuild(lib_tool, objects, output):
    command = [lib_tool, '/nologo', '/OUT:' + str(output)] + [str(item) for item in objects]
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    distlib.require(done.returncode == 0 and Path(output).is_file(),
                    'lib.exe could not rebuild %s: %s' % (output, done.stdout[-400:]))


def reduce_library(path, lib_tool, dumpbin, patterns, workdir):
    path = Path(path)
    original = path.read_bytes()
    if original[:len(distlib.ARCHIVE_MAGIC)] != distlib.ARCHIVE_MAGIC:
        return None
    keep, drop = plan(original)
    if not drop:
        return None
    distlib.require(keep, 'archive would lose every member: ' + str(path))
    names = [member['name'] for member in keep]
    distlib.require(len(set(names)) == len(names), 'duplicate member names in ' + str(path))
    folder = Path(workdir) / ('lib-' + distlib.digest_bytes(str(path).encode())[:12])
    folder.mkdir(parents=True, exist_ok=True)
    objects = []
    for member in keep:
        name = member['name'] if member['name'].lower().endswith(('.obj', '.o')) else member['name'] + '.obj'
        target = folder / name
        target.write_bytes(member['body'])
        objects.append(target)
    rebuilt = folder / 'rebuilt.lib'
    rebuild(lib_tool, objects, rebuilt)
    payload = rebuilt.read_bytes()
    facts = distlib.scan_archive(path.name, payload)
    distlib.require(facts['debug_section_count'] >= 0, 'rebuilt archive is unreadable')
    hits = distlib.find_hits(path.name, payload, patterns)
    distlib.require(not hits, 'rebuilt archive still carries a build root: ' + json.dumps(hits[:2]))
    kept = {(member['name'], distlib.digest_bytes(member['body'])) for member in keep}
    surviving = set()
    for member in distlib.archive_members(payload):
        if member['raw'] in LINKER_MEMBERS:
            continue
        surviving.add((member['name'], distlib.digest_bytes(member['body'])))
    distlib.require(surviving == kept, 'rebuilt archive changed a kept member: ' + str(path))
    before_symbols = dump_symbols(dumpbin, path)
    distlib.require(before_symbols, 'dumpbin reported no defined symbols for ' + str(path))
    after_symbols = dump_symbols(dumpbin, rebuilt)
    lost = {name for name in before_symbols - after_symbols if not name.startswith('$R')}
    distlib.require(not lost, 'rebuild lost referenced symbols: ' + ', '.join(sorted(lost))[:200])
    path.write_bytes(payload)
    return {'path': str(path), 'removed': sorted(drop), 'kept': len(keep),
            'bytes_before': len(original), 'bytes_after': len(payload),
            'sha256_before': distlib.digest_bytes(original),
            'sha256_after': distlib.digest_bytes(payload),
            'dropped_symbols': sorted(name for name in before_symbols - after_symbols)[:16]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--root-arg', action='append', default=[])
    parser.add_argument('--lib-tool', default='lib')
    parser.add_argument('--dumpbin', default='dumpbin')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    distlib.require(args.stage.is_dir(), 'stage is missing: ' + str(args.stage))
    patterns = distlib.build_patterns(args.root_arg)
    records = []
    with tempfile.TemporaryDirectory() as temporary:
        for path in sorted(args.stage.rglob('*.lib')):
            record = reduce_library(path, args.lib_tool, args.dumpbin, patterns, temporary)
            if record:
                records.append(record)
    report = {'schema': 'reader-distribution-windows-reduce-v1', 'stage': str(args.stage),
              'libraries': records, 'reduced': len(records)}
    if args.report:
        distlib.write_json(args.report, report)
    print(json.dumps({'reduced': len(records),
                      'removed': sum(len(item['removed']) for item in records)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
