"""Synthetic protocol cases for the final-image provider audit; Actions executes them."""
import copy
import unittest

import fp_core as C
import fp_maps as M

GNU = """Archive member included to satisfy reference by file (symbol)

LOAD build/host.o
LOAD /opt/prod/lib/libEXReaderProductCatalog.a
Linker script and memory map

.text           0x0000000000401000     0x2000
 .text          0x0000000000401000       0x40 /opt/prod/lib/libEXReaderProductCatalog.a(catalog.o)
 .text          0x0000000000401040       0x20 /opt/sdk/lib/libreader_sdk.a(entry.o)
 .text          0x0000000000401060        0x0 /opt/sdk/lib/libreader_sdk.a(empty.o)
 .text          0x0000000000401080       0x10 build/host.o
"""
APPLE = """# Path: /b/app
# Object files:
[  0] linker synthesized
[  1] /b/host.o
[  2] /opt/prod/lib/libEXReaderProductCatalog.a(catalog.o)
# Sections:
# Address\tSize\tSegment\tSection
# Symbols:
# Address\tSize\tFile  Name
0x1000\t0x20\t[  2] _sqlite3_open_v2
"""
MSVC = """ app

 Timestamp is 0

 Address         Publics by Value              Rva+Base               Lib:Object

 0001:00000000       main                       0000000140001000 f   host.obj
 0001:00000100       sqlite3_open_v2            0000000140001100 f   EXReaderProductCatalog.lib:catalog.obj
"""
LLD = """             VMA              LMA     Size Align Out     In      Symbol
          201000           201000       40     4 .text
          201000           201000       40     4         /opt/prod/lib/libEXReaderProductCatalog.a(catalog.o):(.text.open)
          201040           201040        0     4         /opt/sdk/lib/libsdk.a(empty.o):(.text)
"""
NM_PRODUCT = "/opt/prod/lib/libEXReaderProductCatalog.a:catalog.o:0000000000000000 T sqlite3_open_v2\n"
NM_SDK = ("/opt/sdk/lib/libreader_sdk.a:entry.o:0000000000000000 T reader_open\n"
          "/opt/sdk/lib/libreader_sdk.a:entry.o:                 U sqlite3_open_v2\n")
NM_HOST = "/opt/host/libhost.a:host.o:                 U reader_open\n"


def evidence():
    archives = {'/opt/prod/lib/libEXReaderProductCatalog.a': M.parse_nm_archive(NM_PRODUCT),
                '/opt/sdk/lib/libreader_sdk.a': M.parse_nm_archive(NM_SDK),
                '/opt/host/libhost.a': M.parse_nm_archive(NM_HOST)}
    return dict(roles=dict(sdk=['/opt/sdk/'], product=['/opt/prod/'], host=['/opt/host/']), archives=archives,
                selected=[['/opt/prod/lib/libEXReaderProductCatalog.a', 'catalog.o'],
                          ['/opt/sdk/lib/libreader_sdk.a', 'entry.o'], ['/opt/host/libhost.a', 'host.o']],
                product_catalog_archives=['libEXReaderProductCatalog.a'], dynamic_needed=['libc.so.6'])


def kinds(ev):
    return sorted(f['kind'] for f in M.audit(ev))


class MapParsers(unittest.TestCase):
    def test_gnu(self):
        r = M.parse_gnu_map(GNU)
        self.assertEqual(r['members'], [('/opt/prod/lib/libEXReaderProductCatalog.a', 'catalog.o'),
                                        ('/opt/sdk/lib/libreader_sdk.a', 'entry.o')])
        self.assertIn('/opt/prod/lib/libEXReaderProductCatalog.a', r['loads'])

    def test_apple(self):
        self.assertEqual(M.parse_apple_map(APPLE)['members'], [('/opt/prod/lib/libEXReaderProductCatalog.a', 'catalog.o')])

    def test_msvc(self):
        self.assertEqual(M.parse_msvc_map(MSVC)['members'], [('EXReaderProductCatalog.lib', 'catalog.obj')])

    def test_lld(self):
        self.assertEqual(M.parse_lld_map(LLD)['members'], [('/opt/prod/lib/libEXReaderProductCatalog.a', 'catalog.o')])

    def test_wrong_format_fails_closed(self):
        for parser, text in ((M.parse_gnu_map, APPLE), (M.parse_apple_map, GNU), (M.parse_msvc_map, GNU), (M.parse_lld_map, GNU)):
            with self.assertRaises(ValueError):
                parser(text)

    def test_nm_unknown_kind_and_garbage(self):
        with self.assertRaises(ValueError):
            M.parse_nm_archive('garbage line')
        table = M.parse_nm_archive(NM_SDK)
        self.assertEqual(table['entry.o']['undefined'], {'sqlite3_open_v2'})


class Audit(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(kinds(evidence()), [])

    def test_second_sqlite_provider(self):
        ev = evidence()
        ev['archives']['/opt/sdk/lib/libreader_sdk.a']['vendor.o'] = dict(defined={'sqlite3_open_v2'}, weak=set(), undefined=set())
        ev['selected'].append(['/opt/sdk/lib/libreader_sdk.a', 'vendor.o'])
        found = kinds(ev)
        self.assertIn('duplicate_provider', found)
        self.assertIn('sqlite_not_uniquely_product_catalog', found)
        self.assertIn('foreign_sqlite_provider', found)

    def test_sqlite_owned_by_wrong_archive(self):
        ev = evidence()
        ev['archives']['/opt/host/libhost.a']['host.o']['defined'].add('sqlite3_open_v2')
        ev['archives']['/opt/prod/lib/libEXReaderProductCatalog.a']['catalog.o']['defined'].clear()
        self.assertIn('sqlite_not_uniquely_product_catalog', kinds(ev))

    def test_system_sqlite_dependency(self):
        ev = evidence(); ev['dynamic_needed'].append('libsqlite3.so.0')
        self.assertEqual(kinds(ev), ['system_sqlite_dependency'])

    def test_unowned_input(self):
        ev = evidence(); ev['selected'].append(['/tmp/stray/libx.a', 'x.o'])
        self.assertIn('unowned_link_input', kinds(ev))

    def test_missing_native_table(self):
        ev = evidence(); ev['selected'].append(['/opt/host/libhost.a', 'ghost.o'])
        self.assertIn('selected_member_without_native_table', kinds(ev))

    def test_sdk_entry_not_selected_from_sdk(self):
        ev = evidence(); ev['selected'].remove(['/opt/sdk/lib/libreader_sdk.a', 'entry.o'])
        self.assertIn('sdk_entry_without_selected_sdk_owner', kinds(ev))

    def test_sqlite_reference_needs_product_definer(self):
        ev = evidence(); ev['selected'].remove(['/opt/prod/lib/libEXReaderProductCatalog.a', 'catalog.o'])
        self.assertIn('sqlite_reference_without_product_definer', kinds(ev))

    def test_unselected_sdk_vendor_sqlite_is_not_a_provider(self):
        ev = evidence()
        ev['archives']['/opt/sdk/lib/libreader_sdk.a']['vendor.o'] = dict(defined={'sqlite3_open_v2'}, weak=set(), undefined=set())
        self.assertEqual(kinds(ev), [])

    def test_selected_wrong_sdk_sqlite_provider_rejected(self):
        ev = evidence()
        ev['archives']['/opt/sdk/lib/libreader_sdk.a']['vendor.o'] = dict(defined={'sqlite3_open_v2'}, weak=set(), undefined=set())
        ev['selected'].remove(['/opt/prod/lib/libEXReaderProductCatalog.a', 'catalog.o'])
        ev['selected'].append(['/opt/sdk/lib/libreader_sdk.a', 'vendor.o'])
        found = kinds(ev)
        self.assertIn('sqlite_not_uniquely_product_catalog', found)
        self.assertIn('foreign_sqlite_provider', found)
        rows = M.sqlite_reference_rows(ev)
        self.assertTrue(rows and all(r['status'] == 'PROBLEM' for r in rows))

    def test_duplicate_real_provider_rejected(self):
        ev = evidence()
        ev['archives']['/opt/host/libhost.a']['dup.o'] = dict(defined={'reader_open'}, weak=set(), undefined=set())
        ev['selected'].append(['/opt/host/libhost.a', 'dup.o'])
        self.assertIn('duplicate_provider', kinds(ev))

    def test_unselected_whole_archive_accepted_and_classified(self):
        ev = evidence()
        ev['archives']['/opt/sdk/lib/libvendor_sqlite.a'] = {'sqlite3.o': dict(defined={'sqlite3_open_v2', 'sqlite3_step'}, weak=set(), undefined=set())}
        self.assertEqual(kinds(ev), [])
        rows = M.sqlite_reference_rows(ev)
        row = [r for r in rows if r['symbol'] == 'sqlite3_open_v2'][0]
        self.assertEqual(row['status'], 'resolved_by_selected_product')
        self.assertEqual(row['unselected_candidates'][0]['role'], 'sdk')

    def test_apple_underscore_canon(self):
        ev = evidence()
        row = ev['archives']['/opt/prod/lib/libEXReaderProductCatalog.a']['catalog.o']
        row['defined'] = {'_sqlite3_open_v2'}
        self.assertIn('sqlite_not_uniquely_product_catalog', kinds(copy.deepcopy(ev)))
        self.assertEqual([f for f in M.audit(ev, lambda s: s[1:] if s.startswith('_') else s)], [])


OBJ_NM = "/b/host/main.c.o:0000000000000000 T main\n/b/host/main.c.o:                 U reader_open\n"
DYN = """Symbol table '.dynsym' contains 4 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     1: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND malloc@GLIBC_2.2.5 (2)
     2: 0000000000000000     0 NOTYPE  WEAK   DEFAULT  UND __gmon_start__
     3: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND gtk_init
"""
VER = """Version symbols section '.gnu.version' contains 4 entries:
Version needs section '.gnu.version_r' contains 1 entry:
 Addr: 0x0000000000000500  Offset: 0x000500  Link: 7 (.dynstr)
  000000: Version: 1  File: libc.so.6  Cnt: 1
  0x0010:   Name: GLIBC_2.2.5  Flags: none  Version: 2
"""


class LooseObjectsAndVersions(unittest.TestCase):
    def loose(self, defined=(), path='/opt/host/main.c.o'):
        ev = evidence()
        ev['archives'][path] = {'main.c.o': dict(defined=set(defined), weak=set(), undefined={'reader_open'})}
        ev['selected'].append([path, 'main.c.o'])
        return ev

    def test_object_nm_parser(self):
        row = M.parse_nm_object(OBJ_NM)
        self.assertEqual((row['defined'], row['undefined']), ({'main'}, {'reader_open'}))
        with self.assertRaises(ValueError):
            M.parse_nm_object('not nm')

    def test_clean_loose_object_accepted(self):
        self.assertEqual(kinds(self.loose({'main'})), [])

    def test_loose_object_sqlite_provider_rejected(self):
        found = kinds(self.loose({'sqlite3_open_v2'}))
        self.assertIn('duplicate_provider', found)
        self.assertIn('foreign_sqlite_provider', found)

    def test_loose_object_duplicating_sdk_symbol_rejected(self):
        self.assertIn('duplicate_provider', kinds(self.loose({'reader_open'})))

    def test_unowned_loose_object_rejected(self):
        self.assertIn('unowned_link_input', kinds(self.loose({'main'}, '/tmp/stray/main.c.o')))

    def test_loose_object_without_native_table_rejected(self):
        ev = evidence()
        ev['selected'].append(['/opt/host/ghost.c.o', 'ghost.c.o'])
        self.assertIn('selected_member_without_native_table', kinds(ev))

    def dyn(self, text=DYN, ver=VER, needed=('libc.so.6',)):
        return M.audit_dynamic(dict(symbols=M.parse_dyn_syms(text), verneed=M.parse_verneed(ver), needed=list(needed)))

    def test_versions_accepted_and_weak_left_pending(self):
        findings, pending = self.dyn()
        self.assertEqual(findings, [])
        by_kind = {p['kind']: p for p in pending}
        self.assertEqual(by_kind['weak_undefined_imports_unproven']['symbols'], ['__gmon_start__'])
        self.assertEqual(by_kind['unversioned_imports_unproven_without_system_dso']['symbols'], ['gtk_init'])

    def test_dynamic_sqlite_symbol_rejected(self):
        text = DYN + '     4: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND sqlite3_open_v2\n'
        self.assertEqual([f['kind'] for f in self.dyn(text)[0]], ['dynamic_sqlite_symbol'])

    def test_version_not_in_verneed_rejected(self):
        text = DYN + '     4: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND memcpy@GLIBC_2.14 (3)\n'
        self.assertEqual([f['kind'] for f in self.dyn(text)[0]], ['dynamic_version_not_in_verneed'])

    def test_verneed_file_not_in_needed_rejected(self):
        self.assertEqual([f['kind'] for f in self.dyn(needed=())[0]], ['verneed_file_not_needed'])

    def test_verneed_parser_ignores_other_sections(self):
        self.assertEqual(M.parse_verneed(VER), {'libc.so.6': ['GLIBC_2.2.5']})
        with self.assertRaises(ValueError):
            M.parse_dyn_syms('nothing')


class Scope(unittest.TestCase):
    def test_additions_only(self):
        good = ['A\t' + C.OWNED + 'x.py', 'A\t' + C.WORKFLOW, 'A\t' + C.AUDITOR, 'A\t' + C.DOC]
        self.assertEqual(C.owned_paths(good), good)
        for bad in ('M\t' + C.OWNED + 'x.py', 'A\tsrc/x.c', 'A\tCMakeLists.txt', 'D\t' + C.DOC):
            with self.assertRaises(ValueError):
                C.owned_paths([bad])

    def test_unsafe_names(self):
        for name in ('/abs', '../x', 'a//b', 'a\\b', 'c:x'):
            with self.assertRaises(ValueError):
                C.safe_name(name)


class Aggregate(unittest.TestCase):
    def row(self, sha='a', run='1', attempt='1', passed=True):
        return dict(source_sha=sha, run_id=run, attempt=attempt, passed=passed)

    def test_never_accepts(self):
        full = {p: self.row() for p in C.PLATFORMS}
        record = C.bind_results(full)
        self.assertTrue(record['same_source_complete'])
        self.assertFalse(record['f07_accepted'] or record['full_six_platform_f07_accepted'])

    def test_mixed_source_and_missing(self):
        mixed = {p: self.row() for p in C.PLATFORMS}
        mixed['ipad'] = self.row(sha='b')
        self.assertTrue(C.bind_results(mixed)['mixed_source_or_run'])
        self.assertFalse(C.bind_results(mixed)['same_source_complete'])
        self.assertEqual(C.bind_results({'linux': self.row()})['missing'], ['windows', 'macos', 'iphone', 'ipad', 'android'])
        failed = {p: self.row() for p in C.PLATFORMS}; failed['android'] = self.row(passed=False)
        self.assertEqual(C.bind_results(failed)['failed'], ['android'])

    def test_unknown_platform(self):
        with self.assertRaises(ValueError):
            C.bind_results({'plan9': self.row()})


if __name__ == '__main__':
    unittest.main(verbosity=2)
