"""Synthetic resolution, rejection and missing-evidence cases for system-library import resolution."""
import copy
import os
import tempfile
import unittest

import fp_core as C
import fp_maps as M
import fp_system as S


def sym(name, version=None, bind='GLOBAL', ndx='UND'):
    return dict(name=name, version=version, bind=bind, ndx=ndx, type='FUNC', vis='DEFAULT', default=True)


LIBC = dict(path='/lib/libc.so.6', basename='libc.so.6', soname='libc.so.6', sha256='a' * 64, needed=[],
            exports=[('malloc', 'GLIBC_2.2.5', True), ('__cxa_finalize', 'GLIBC_2.2.5', True),
                     ('memcpy', 'GLIBC_2.14', True), ('memcpy', 'GLIBC_2.2.5', False)])
GTK = dict(path='/lib/libgtk-3.so.0', basename='libgtk-3.so.0', soname='libgtk-3.so.0', sha256='b' * 64,
           needed=['libc.so.6'], exports=[('gtk_init', None, True)])
VERNEED = {'libc.so.6': ['GLIBC_2.2.5', 'GLIBC_2.14']}
NEEDED = ['libgtk-3.so.0']


def libs():
    return {'libc.so.6': copy.deepcopy(LIBC), 'libgtk-3.so.0': copy.deepcopy(GTK)}


def run(symbols, verneed=VERNEED, needed=NEEDED, table=None, runpath=()):
    return S.resolve_imports(symbols, verneed, needed, libs() if table is None else table, runpath)


def status(rows, label):
    return [r['status'] for r in rows if r['import_'] == label]


class Resolution(unittest.TestCase):
    def test_versioned_unversioned_and_weak_provided_are_resolved(self):
        rows, findings, pending = run([sym('malloc', 'GLIBC_2.2.5'), sym('gtk_init'),
                                       sym('__cxa_finalize', 'GLIBC_2.2.5', 'WEAK')])
        self.assertEqual([r['status'] for r in rows], ['resolved'] * 3)
        self.assertEqual((findings, pending), ([], []))
        self.assertEqual(rows[0]['providers'][0]['sha256'], 'a' * 64)

    def test_unprovided_weak_stays_pending_not_waived(self):
        rows, findings, pending = run([sym('__gmon_start__', None, 'WEAK'), sym('_ITM_registerTMCloneTable', None, 'WEAK')])
        self.assertEqual([r['status'] for r in rows], ['pending', 'pending'])
        self.assertEqual(findings, [])
        self.assertEqual(len(pending), 2)

    def test_versioned_import_absent_is_a_finding(self):
        rows, findings, _ = run([sym('malloc', 'GLIBC_2.99')])
        self.assertEqual(rows[0]['status'], 'FINDING')
        self.assertEqual(findings[0]['kind'], 'versioned_import_unprovided')

    def test_version_defined_by_library_outside_verneed_is_rejected(self):
        _, findings, _ = run([sym('malloc', 'GLIBC_2.2.5')], verneed={'libother.so.1': ['GLIBC_2.2.5']})
        self.assertEqual([f['kind'] for f in findings], ['versioned_import_unprovided'])

    def test_non_default_version_does_not_satisfy_unversioned_import(self):
        table = libs()
        table['libc.so.6']['exports'] = [('legacy', 'GLIBC_2.2.5', False)]
        rows, findings, _ = run([sym('legacy')], table=table)
        self.assertEqual(rows[0]['status'], 'FINDING')
        self.assertEqual(findings[0]['kind'], 'strong_import_unprovided')

    def test_strong_unprovided_with_complete_closure_is_a_finding(self):
        self.assertEqual([f['kind'] for f in run([sym('nowhere')])[1]], ['strong_import_unprovided'])

    def test_missing_library_evidence_keeps_everything_pending(self):
        table = libs()
        table['libgtk-3.so.0']['exports'] = None  # exports never recorded
        rows, findings, pending = run([sym('gtk_init'), sym('malloc', 'GLIBC_2.2.5')], table=table)
        self.assertEqual(findings, [])
        self.assertEqual(status(rows, 'gtk_init'), ['pending'])
        self.assertIn('needed_library_unrecorded', [p['kind'] for p in pending])
        missing = {}
        self.assertEqual(run([sym('gtk_init')], table=missing)[0][0]['status'], 'pending')

    def test_custom_runpath_resolves_nothing(self):
        rows, findings, pending = run([sym('gtk_init')], runpath=['/opt/x'])
        self.assertEqual(rows[0]['status'], 'pending')
        self.assertEqual(findings, [])
        self.assertIn('custom_runpath_not_resolved', [p['kind'] for p in pending])

    def test_system_sqlite_library_in_closure_rejected(self):
        table = libs()
        table['libgtk-3.so.0']['exports'].append(('sqlite3_open_v2', None, True))
        self.assertIn('system_sqlite_library_in_closure', [f['kind'] for f in run([sym('gtk_init')], table=table)[1]])

    def test_closure_follows_transitive_needed(self):
        order, missing = S.closure(NEEDED, libs())
        self.assertEqual((order, missing), (['libgtk-3.so.0', 'libc.so.6'], []))


class Identity(unittest.TestCase):
    def test_recorded_digest_must_match_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b'library bytes')
        try:
            table = {'libx.so': dict(path=handle.name, sha256=C.sha(b'library bytes'))}
            self.assertTrue(S.verify_recorded(table))
            table['libx.so']['sha256'] = C.sha(b'tampered')
            with self.assertRaises(ValueError):
                S.verify_recorded(table)
            with self.assertRaises(ValueError):
                S.verify_recorded({'libx.so': dict(path=handle.name, sha256='')})
        finally:
            os.unlink(handle.name)


class Parsers(unittest.TestCase):
    HEADER = """Dynamic section at offset 0x1 contains 3 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x000000000000000e (SONAME)             Library soname: [libx.so.1]
 0x000000000000001d (RUNPATH)            Library runpath: [/opt/lib]
"""
    SYMS = """Symbol table '.dynsym' contains 4 entries:
   Num:    Value          Size Type    Bind   Vis      Ndx Name
     1: 0000000000001000    10 FUNC    GLOBAL DEFAULT   12 memcpy@@GLIBC_2.14
     2: 0000000000001010    10 FUNC    GLOBAL DEFAULT   12 memcpy@GLIBC_2.2.5
     3: 0000000000001020    10 FUNC    GLOBAL HIDDEN    12 hidden_fn
     4: 0000000000001030    10 FUNC    GLOBAL DEFAULT   12 plain_fn
     5: 0000000000002000 0x1c19d90 OBJECT  GLOBAL DEFAULT   12 icudt70_dat
"""

    def test_dynamic_header(self):
        header = S.parse_dynamic_header(self.HEADER)
        self.assertEqual((header['soname'], header['needed'], header['runpath']), ('libx.so.1', ['libc.so.6'], ['/opt/lib']))
        with self.assertRaises(ValueError):
            S.parse_dynamic_header('garbage')

    def test_default_flag_and_hidden_excluded(self):
        exports = S.exports_of(M.parse_dyn_syms(self.SYMS))
        self.assertIn(('memcpy', 'GLIBC_2.14', True), exports)
        self.assertIn(('memcpy', 'GLIBC_2.2.5', False), exports)
        self.assertIn(('plain_fn', None, True), exports)
        self.assertNotIn('hidden_fn', [e[0] for e in exports])
        self.assertIn(('icudt70_dat', None, True), exports)  # hexadecimal size column


if __name__ == '__main__':
    unittest.main(verbosity=2)
