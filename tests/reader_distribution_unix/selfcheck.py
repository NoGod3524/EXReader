#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud protocol: exercise every distribution decision on synthetic fixtures.

These cases prove the judgement code, not a real SDK build: real installed-stage
behaviour is granted only by the platform jobs. Each case prints its own name so a
failure is attributable without parsing a total.
"""
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools' / 'reader_distribution_unix'))
import contract

CASES = []


def case(name):
    def register(function):
        CASES.append((name, function))
        return function
    return register


def expect_error(function, needle):
    try:
        function()
    except contract.ContractError as error:
        assert needle in str(error), 'unexpected error: ' + str(error)
        return
    raise AssertionError('expected a contract error containing ' + needle)


TARGETS = '''
add_library(EXReader::exr_base STATIC IMPORTED)
set_target_properties(EXReader::exr_base PROPERTIES
  INTERFACE_COMPILE_DEFINITIONS "EXR_STATIC"
  INTERFACE_INCLUDE_DIRECTORIES "${_IMPORT_PREFIX}/include"
  INTERFACE_LINK_LIBRARIES "EXReader::vendor_base;m"
)
add_library(EXReader::exr_text STATIC IMPORTED)
set_target_properties(EXReader::exr_text PROPERTIES
  INTERFACE_LINK_LIBRARIES "EXReader::exr_base;EXReader::vendor_text"
)
add_library(EXReader::exr_render STATIC IMPORTED)
set_target_properties(EXReader::exr_render PROPERTIES
  INTERFACE_LINK_LIBRARIES "EXReader::exr_text;EXReader::vendor_render"
)
add_library(EXReader::exr_pdf STATIC IMPORTED)
set_target_properties(EXReader::exr_pdf PROPERTIES
  INTERFACE_LINK_LIBRARIES "EXReader::exr_render;EXReader::vendor_pdf"
)
add_library(EXReader::exr_core INTERFACE IMPORTED)
set_target_properties(EXReader::exr_core PROPERTIES
  INTERFACE_LINK_LIBRARIES "EXReader::exr_render"
)
'''

DEPENDENCIES = '''
add_library(EXReader::vendor_file_miniz STATIC IMPORTED)
set_target_properties(EXReader::vendor_file_miniz PROPERTIES
  IMPORTED_LOCATION "${PACKAGE_PREFIX_DIR}/lib/exreader/libexr_vendor_miniz.a"
  INTERFACE_LINK_LIBRARIES "Threads::Threads;m;dl"
)
add_library(EXReader::vendor_file_freetype STATIC IMPORTED)
set_target_properties(EXReader::vendor_file_freetype PROPERTIES
  IMPORTED_LOCATION "${PACKAGE_PREFIX_DIR}/lib/exreader/libexr_vendor_freetype.a"
)
'''


@case('link-order')
def link_order():
    order = contract.link_order(TARGETS)
    assert order == ['exr_pdf', 'exr_render', 'exr_text', 'exr_base'], order
    cycle = TARGETS.replace('"EXReader::exr_base;EXReader::vendor_text"',
                            '"EXReader::exr_render;EXReader::vendor_text"')
    expect_error(lambda: contract.link_order(cycle), 'cycle')


@case('vendor-and-system')
def vendor_and_system():
    names = contract.vendor_archives(DEPENDENCIES)
    assert names == ['libexr_vendor_miniz.a', 'libexr_vendor_freetype.a'], names
    system = contract.system_libraries(DEPENDENCIES)
    assert system == ['-pthread', '-lm', '-ldl'], system
    assert contract.archive_flag('libexr_vendor_miniz.a') == '-lexr_vendor_miniz'


@case('pkgconfig-round-trip')
def pkgconfig_round_trip():
    text = contract.render_pc('3.40.0', 'EXReader test unit',
                              ['libexr_pdf.a', 'libexr_render.a'],
                              ['libexr_vendor_miniz.a'],
                              ['-pthread', '-lm'])
    fields, problems = contract.pc_contract(text, '3.40.0',
                                            ['libexr_pdf.a', 'libexr_render.a'],
                                            ['libexr_vendor_miniz.a'],
                                            ['-pthread', '-lm'])
    assert not problems, problems
    assert fields['prefix'] == '${pcfiledir}/../..', fields['prefix']


@case('pkgconfig-rejects-absolute-prefix')
def pkgconfig_absolute():
    text = contract.render_pc('3.40.0', 'unit', ['libexr_pdf.a'],
                              ['libexr_vendor_miniz.a'], ['-pthread', '-lm'])
    broken = text.replace('prefix=${pcfiledir}/../..', 'prefix=/home/runner/work/EXReader/stage')
    _, problems = contract.pc_contract(broken, '3.40.0', ['libexr_pdf.a'],
                                       ['libexr_vendor_miniz.a'], ['-pthread', '-lm'])
    assert any('prefix' in problem for problem in problems), problems


@case('pkgconfig-rejects-absolute-library')
def pkgconfig_absolute_library():
    text = contract.render_pc('3.40.0', 'unit', ['libexr_pdf.a'],
                              ['libexr_vendor_miniz.a'], ['-pthread', '-lm'])
    broken = text.replace('Libs: -L${libdir}', 'Libs: -L/opt/build/lib')
    _, problems = contract.pc_contract(broken, '3.40.0', ['libexr_pdf.a'],
                                       ['libexr_vendor_miniz.a'], ['-pthread', '-lm'])
    assert any('absolute install path' in problem for problem in problems), problems


@case('pkgconfig-requires-every-archive')
def pkgconfig_coverage():
    text = contract.render_pc('3.40.0', 'unit', ['libexr_pdf.a'],
                              ['libexr_vendor_miniz.a'], ['-pthread', '-lm'])
    _, problems = contract.pc_contract(text, '3.40.0', ['libexr_pdf.a', 'libexr_render.a'],
                                       ['libexr_vendor_miniz.a'], ['-pthread', '-lm'])
    assert problems, 'missing component archive was accepted'


@case('dedupe-plan')
def dedupe_plan():
    records = [
        {'path': 'LICENSE', 'bytes': 4, 'sha256': 'aa'},
        {'path': 'share/exreader/LICENSE', 'bytes': 4, 'sha256': 'aa'},
        {'path': 'lib/libexr_render.a', 'bytes': 4, 'sha256': 'bb'},
        {'path': 'lib/libexr_pdf.a', 'bytes': 4, 'sha256': 'bb'},
        {'path': 'include/exr/base.h', 'bytes': 4, 'sha256': 'cc'},
        {'path': 'include/exr/core.h', 'bytes': 4, 'sha256': 'cc'},
        {'path': 'docs/one.md', 'bytes': 4, 'sha256': 'dd'},
        {'path': 'docs/two.md', 'bytes': 4, 'sha256': 'ee'},
    ]
    plan = contract.dedupe_plan(records)
    assert plan == [{'primary': 'LICENSE', 'duplicate': 'share/exreader/LICENSE',
                     'bytes': 4, 'sha256': 'aa'}], plan


@case('tree-scan')
def tree_scan():
    root = Path(tempfile.mkdtemp(prefix='j24-selfcheck-'))
    try:
        (root / 'docs').mkdir()
        (root / 'lib/pkgconfig').mkdir(parents=True)
        (root / 'docs/note.md').write_text('built in /tmp/j24-workspace/build/sdk\n', encoding='utf-8')
        (root / 'lib/pkgconfig/exreader.pc').write_text('prefix=${pcfiledir}/../..\n', encoding='utf-8')
        (root / 'lib/libexr_base.a').write_bytes(b'\x7fELF not really\n')
        records = contract.walk(root)
        assert {record['path'] for record in records} == {
            'docs/note.md', 'lib/pkgconfig/exreader.pc', 'lib/libexr_base.a'}
        hits = contract.scan_tokens(root, ['/tmp/j24-workspace'])
        assert hits == [{'path': 'docs/note.md', 'token': '/tmp/j24-workspace', 'count': 1}], hits
        (root / 'docs/note.md').write_text('clean\n', encoding='utf-8')
        problems = contract.tree_problems(root, records)
        assert any('docs/note.md' in problem for problem in problems), problems
    finally:
        shutil.rmtree(root)


@case('path-safety')
def path_safety():
    assert contract.safe_relative('docs/a.md') == 'docs/a.md'
    for bad in ('../escape', '/absolute', 'docs/../escape', 'C:/drive', 'docs\\win'):
        expect_error(lambda value=bad: contract.safe_relative(value), '')


@case('seal-extract-hardlink')
def seal_extract():
    root = Path(tempfile.mkdtemp(prefix='j24-seal-'))
    try:
        prefix = root / 'prefix'
        (prefix / 'docs').mkdir(parents=True)
        (prefix / 'share').mkdir(parents=True)
        (prefix / 'lib').mkdir(parents=True)
        (prefix / 'LICENSE').write_text('license text\n', encoding='utf-8')
        os.link(prefix / 'LICENSE', prefix / 'docs' / 'LICENSE')
        (prefix / 'lib/libexr_base.a').write_bytes(b'archive\n')
        manifest = contract.seal(prefix, root / 'out', 'EXReader-test.tar.gz', 1700000000,
                                 {'source_sha': 'x'})
        assert manifest['duplicate_members'] == 1, manifest['duplicate_members']
        assert len(manifest['files']) == 3, manifest['files']
        report = contract.extract(root / 'out/EXReader-test.tar.gz', root / 'extracted', manifest)
        assert report['accepted'], report['problems']
        first = (root / 'extracted/LICENSE').stat().st_ino
        second = (root / 'extracted/docs/LICENSE').stat().st_ino
        assert first == second, 'hardlink was not restored'
        bad = json.loads(json.dumps(manifest))
        bad['files'][0]['sha256'] = '0' * 64
        tampered = contract.extract(root / 'out/EXReader-test.tar.gz', root / 'tampered', bad)
        assert not tampered['accepted'], 'tampered manifest was accepted'
    finally:
        shutil.rmtree(root)


def main():
    failures = 0
    for name, function in CASES:
        try:
            function()
            print('pass %s' % name)
        except Exception as error:  # noqa: BLE001 - a self-check must name every failure
            failures += 1
            print('fail %s: %s' % (name, error))
    print(json.dumps({'cases': len(CASES), 'failures': failures}))
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
