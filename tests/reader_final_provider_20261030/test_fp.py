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

    def test_apple_underscore_canon(self):
        ev = evidence()
        row = ev['archives']['/opt/prod/lib/libEXReaderProductCatalog.a']['catalog.o']
        row['defined'] = {'_sqlite3_open_v2'}
        self.assertIn('sqlite_not_uniquely_product_catalog', kinds(copy.deepcopy(ev)))
        self.assertEqual([f for f in M.audit(ev, lambda s: s[1:] if s.startswith('_') else s)], [])


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
