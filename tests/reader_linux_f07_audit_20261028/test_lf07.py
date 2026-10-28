"""Synthetic protocol fixtures; authored here, executed only by Actions."""
import unittest
import lf07_contract as C


class Contract(unittest.TestCase):
    def test_nm_local_weak_unique_and_versions(self):
        t = C.symbols('unit.o:\n0001 T api\n0002 t hidden\n         U other@GLIBC_2.2.5\n         w weak_helper\n0003 u unique\n')
        self.assertEqual(t['global_defined'], ['api', 'unique'])
        self.assertEqual(t['undefined'], ['other', 'weak_helper'])
        self.assertIn('hidden', t['defined'])

    def test_nm_rejects_unknown_format(self):
        with self.assertRaises(ValueError): C.symbols('broken symbol table')
        with self.assertRaises(ValueError): C.symbols('0001 Q unknown_kind')
        with self.assertRaises(ValueError): C.symbols('')

    def test_public_declarations_not_prefix_or_inline(self):
        h = 'int rfl_open(void);\nvoid roe_run(int);\nstatic int private_helper(void);\ninline int helper(int x) {return x;}\ntypedef void (*callback)(void);'
        self.assertEqual(C.public_entries(h), {'rfl_open', 'roe_run'})

    def test_sdk_requires_actual_api_declaration(self):
        self.assertEqual(C.public_entries('EXR_API int exr_version(void);\nint exr_private(void);', sdk=True), {'exr_version'})

    def tables(self):
        return {'a': C.symbols('0001 T own\n U public_call\n'), 'b': C.symbols('0002 T public_call\n0003 T secret\n')}

    def test_declared_public_owner_positive(self):
        got = C.module_findings(self.tables(), {'a': 'A', 'b': 'B'}, {'B': {'public_call'}}, {'A': {'B'}}, set(), set())
        self.assertFalse(any(got.values()))

    def test_undeclared_public_owner_rejected(self):
        got = C.module_findings(self.tables(), {'a': 'A', 'b': 'B'}, {'B': {'public_call'}}, {}, set(), set())
        self.assertEqual(got['a'][0]['symbol'], 'public_call')

    def test_resolved_private_helper_not_accepted(self):
        tables = self.tables(); tables['a'] = C.symbols('0001 T own\n U secret\n w mangled_helper\n')
        got = C.module_findings(tables, {'a': 'A', 'b': 'B'}, {'B': {'public_call'}}, {'A': {'B'}}, set(), set())
        self.assertEqual({r['symbol'] for r in got['a']}, {'secret', 'mangled_helper'})

    def test_same_package_helper_positive(self):
        tables = self.tables(); tables['a'] = C.symbols('0001 T own\n U secret\n')
        self.assertFalse(any(C.module_findings(tables, {'a': 'A', 'b': 'A'}, {}, {}, set(), set()).values()))

    def test_wrong_owner_header_and_system_cannot_launder_helper(self):
        tables = self.tables(); tables['a'] = C.symbols('0001 T own\n U secret\n')
        got = C.module_findings(tables, {'a': 'A', 'b': 'B'}, {'A': {'secret'}}, {'A': {'B'}}, set(), {'secret'})
        self.assertEqual(got['a'][0]['symbol'], 'secret')

    def test_exact_observed_system_only(self):
        tables = {'a': C.symbols('0001 T own\n U free\n U missing_runtime\n')}
        got = C.module_findings(tables, {'a': 'A'}, {}, {}, set(), {'free'})
        self.assertEqual([r['symbol'] for r in got['a']], ['missing_runtime'])

    def test_map_ranges_ignore_discarded_and_debug(self):
        text = ('Discarded input sections\n .text 0x100 0x20 /wrong.a(x.o)\n'
                'Linker script and memory map\n .text\n  0x100 0x20 /sdk/libexr_base.a(core.c.o)\n'
                ' .debug_info 0x0 0x1000 /bad.a(debug.o)\n')
        ranges = C.map_ranges(text)
        row = C.symbols('00000100 T exr_version')['rows'][0]
        self.assertEqual(C.symbol_owner(row, ranges), '/sdk/libexr_base.a(core.c.o)')

    def test_map_missing_or_duplicate_ownership_rejected(self):
        row = C.symbols('00000100 T exr_version')['rows'][0]
        with self.assertRaises(ValueError): C.symbol_owner(row, [])
        with self.assertRaises(ValueError): C.symbol_owner(row, [dict(start=0x100, size=10, object='a'), dict(start=0x100, size=10, object='b')])

    def test_final_only_unknown_and_weak_imports_rejected(self):
        full = C.symbols('001 T own\n U unknown_final\n w weak_final')
        dynamic = C.symbols('001 T own\n U dynamic_only')
        findings = C.final_undefined_findings(full, dynamic, {}, [])
        self.assertEqual({r['symbol'] for r in findings}, {'unknown_final', 'weak_final', 'dynamic_only'})

    def test_final_version_and_project_private_provider(self):
        full = C.symbols('001 T own\n U free@GLIBC_2.2.5\n U secret\n U missing_version@VER_2')
        system = C.symbols('002 T free@@GLIBC_2.2.5\n003 T secret\n004 T missing_version@@VER_1')
        findings = C.final_undefined_findings(full, full, {'OtherPackage': {'secret'}}, system['rows'])
        self.assertEqual({r['symbol'] for r in findings}, {'secret', 'missing_version@VER_2'})

    def test_archive_sources_exclude_probe_targets(self):
        graph = ('build CMakeFiles/lib.dir/a.o: CXX_COMPILER__lib_Release /src/a.cpp\n'
                 'build CMakeFiles/probe.dir/p.o: CXX_COMPILER__probe_Release /tests/probe.cpp\n'
                 'build libowner.a: CXX_STATIC_LIBRARY_LINKER__lib_Release CMakeFiles/lib.dir/a.o || phony\n')
        self.assertEqual(C.archive_compile_sources(graph, ['libowner.a']), ['/src/a.cpp'])
        with self.assertRaises(ValueError): C.archive_compile_sources(graph, ['missing.a'])

    def test_original_contract_isolated_and_pinned(self):
        import sys
        before = sys.modules.get('contract')
        frozen = C.frozen_capture()
        self.assertEqual(frozen.identity(), C.package_identity())
        self.assertEqual(sys.modules.get('contract'), before)
        self.assertEqual(frozen.PROGRAM, 'build/gtk-raw-wave3/retained-host/gtk-host/exreader-linux')


if __name__ == '__main__':
    C.actions_only()
    unittest.main()
