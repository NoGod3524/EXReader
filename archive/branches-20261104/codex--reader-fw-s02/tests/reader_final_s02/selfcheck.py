#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline protocol self-check for the S02 tooling.

Every decision helper used against the producer artefact and the relocated tree
is exercised here on synthetic input, so a later failure cannot be a parser
surprise. No producer bytes and no GUI are involved.
"""
import argparse
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path

import common


def expect_error(call, label):
    try:
        call()
    except common.S02Error:
        return
    raise AssertionError(label + ' did not raise')


def make_tar(path, members):
    with tarfile.open(str(path), 'w:gz') as tar:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            info.mtime = 0
            if kind == 'dir':
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            elif kind == 'sym':
                info.type = tarfile.SYMTYPE
                info.linkname = 'target'
                info.mode = 0o777
                tar.addfile(info)
            else:
                info.size = len(data)
                info.mode = 0o755 if name.endswith('exreader-linux') else 0o644
                tar.addfile(info, io.BytesIO(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = common.Checks()
    work = Path(tempfile.mkdtemp(prefix='s02-selfcheck-'))

    readelf = '''Dynamic section at offset 0x2f000 contains 29 entries:
  0x0000000000000001 (NEEDED)             Shared library: [libgtk-3.so.0]
  0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
  0x000000000000001d (RUNPATH)            Library runpath: [/opt/example/lib:$ORIGIN/../lib]
  0x000000000000000e (SONAME)             Library soname: [libsample.so.1]
'''
    parsed = common.parse_readelf(readelf)
    checks.add('selfcheck_parse_readelf',
               parsed['needed'] == ['libgtk-3.so.0', 'libc.so.6']
               and parsed['runpath'] == ['/opt/example/lib', '$ORIGIN/../lib']
               and parsed['soname'] == 'libsample.so.1', json.dumps(parsed))

    ldd = '''	linux-vdso.so.1 (0x00007ffd1c3d4000)
	libgtk-3.so.0 => /usr/lib/x86_64-linux-gnu/libgtk-3.so.0 (0x00007f6d1c000000)
	libmissing.so.9 => not found
'''
    parsed = common.parse_ldd(ldd)
    checks.add('selfcheck_parse_ldd',
               parsed['not_found'] == ['libmissing.so.9']
               and parsed['items'][0]['path'] == '/usr/lib/x86_64-linux-gnu/libgtk-3.so.0',
               json.dumps(parsed['items']))

    entry = common.render_desktop_entry('/tmp/S02 Portable (space)/bin/exreader-linux')
    checks.add('selfcheck_desktop_entry',
               'Exec="/tmp/S02 Portable (space)/bin/exreader-linux"' in entry
               and entry.startswith('[Desktop Entry]')
               and entry.endswith('\n'), entry.splitlines()[6])
    expect_error(lambda: common.desktop_exec('bin/exreader-linux'),
                 'relative desktop Exec')

    values = common.parse_observation('[host]\nsequence=7\nerror=0\nbook=3\nreader_visible=1\n')
    checks.add('selfcheck_observation',
               values.get('reader_visible') == '1'
               and common.observation_int(values, 'book') == 3
               and common.observation_int(values, 'page', -1) == -1,
               json.dumps(values))

    tokens = work / 'tokens'
    tokens.mkdir()
    (tokens / 'binary').write_bytes(b'\x7fELF\x00EXReader/EXReader/build/compact-desktop\x00')
    (tokens / 'clean').write_text('no build path here\n', encoding='utf-8')
    scanned = common.scan_tokens(tokens, common.BUILD_TOKENS)
    found = sorted(hit['token'] for hit in scanned['hits'])
    checks.add('selfcheck_scan_tokens',
               found == ['EXReader/EXReader/build', 'compact-desktop']
               and {hit['path'] for hit in scanned['hits']} == {'binary'},
               json.dumps(scanned['hits']))

    archive = work / 'candidate.tar.gz'
    make_tar(archive, [('EXReader-Linux', b'', 'dir'),
                       ('EXReader-Linux/bin/exreader-linux', b'#!binary', 'file'),
                       ('EXReader-Linux/Reader.otf', b'font-bytes', 'file')])
    extracted = common.safe_extract_tar(archive, work / 'extract1', expect_root='EXReader-Linux')
    checks.add('selfcheck_safe_extract',
               [member['path'] for member in extracted['members']]
               == ['bin/exreader-linux', 'Reader.otf']
               and (work / 'extract1/bin/exreader-linux').stat().st_mode & 0o111,
               json.dumps(extracted['members']))

    flat = work / 'flat.tar.gz'
    make_tar(flat, [('.', b'', 'dir'),
                    ('./bin/exreader-linux', b'#!binary', 'file'),
                    ('./Reader.otf', b'font-bytes', 'file')])
    flat_extract = common.safe_extract_tar(flat, work / 'extract-flat',
                                           expect_root='EXReader-Linux')
    checks.add('selfcheck_safe_extract_dot_root',
               flat_extract['root'] == '.'
               and [member['path'] for member in flat_extract['members']]
               == ['bin/exreader-linux', 'Reader.otf'],
               json.dumps(flat_extract))

    escaping = work / 'escaping.tar.gz'
    make_tar(escaping, [('EXReader-Linux', b'', 'dir'),
                        ('EXReader-Linux/../escape', b'x', 'file')])
    expect_error(lambda: common.safe_extract_tar(escaping, work / 'extract2'),
                 'escaping tar member')
    linked = work / 'linked.tar.gz'
    make_tar(linked, [('EXReader-Linux', b'', 'dir'),
                      ('EXReader-Linux/link', b'', 'sym')])
    expect_error(lambda: common.safe_extract_tar(linked, work / 'extract3'),
                 'symlink tar member')
    multi = work / 'multi.tar.gz'
    make_tar(multi, [('one', b'', 'dir'), ('one/a', b'a', 'file'),
                     ('two', b'', 'dir'), ('two/b', b'b', 'file')])
    expect_error(lambda: common.safe_extract_tar(multi, work / 'extract4'),
                 'multiple tar roots')

    tree = work / 'tree'
    (tree / 'bin').mkdir(parents=True)
    (tree / 'bin/app').write_bytes(b'app')
    os.chmod(str(tree / 'bin/app'), 0o755)
    (tree / 'data.txt').write_text('data\n', encoding='utf-8')
    records = common.walk_tree(tree)
    checks.add('selfcheck_walk_tree',
               common.tree_problems(tree, records) == []
               and any(record['executable'] for record in records), json.dumps(records))
    (tree / 'data.txt').write_text('changed\n', encoding='utf-8')
    checks.add('selfcheck_tree_tamper',
               common.tree_problems(tree, records) == ['file changed: data.txt'],
               json.dumps(common.tree_problems(tree, records)))

    prefixes = {'payload': '/tmp/s02-portable', 'home': '/tmp/s02-home'}
    checks.add('selfcheck_classify_path',
               common.classify_path('/tmp/s02-portable/bin/x', prefixes) == 'payload'
               and common.classify_path('/tmp/s02-home/.local/lib/x', prefixes) == 'home'
               and common.classify_path('/usr/lib/x86_64-linux-gnu/libc.so.6', prefixes) == 'system',
               'classification')

    loads = common.library_loads('\t123:\tcalling init: /usr/lib/x86_64-linux-gnu/libc.so.6\n'
                                 '\t456:\tcalling init: /tmp/s02-home/libevil.so\n')
    checks.add('selfcheck_library_loads',
               loads == ['/usr/lib/x86_64-linux-gnu/libc.so.6', '/tmp/s02-home/libevil.so'],
               json.dumps(loads))

    accumulator = common.Checks(stream=False)
    accumulator.add('one', True, 'ok')
    accumulator.add('two', False, 'bad')
    checks.add('selfcheck_checks',
               accumulator.accepted() is False and accumulator.failed() == ['two'],
               json.dumps(accumulator.failed()))

    report = {'schema': 1, 'kind': 's02-selfcheck', 'checks': checks.items,
              'problems': checks.failed(), 'ok': checks.accepted()}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'selfcheck.json').write_text(json.dumps(report, indent=2) + '\n',
                                                encoding='utf-8')
    print(json.dumps({'selfcheck': 'pass' if checks.accepted() else 'fail',
                      'checks': len(checks.items), 'failed': checks.failed()}))
    return 0 if checks.accepted() else 1


if __name__ == '__main__':
    raise SystemExit(main())
