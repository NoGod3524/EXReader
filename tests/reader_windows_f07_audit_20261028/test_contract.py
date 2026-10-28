"""Actions-only source protocol fixtures. Never substitute for captured evidence."""
import os
import struct
import unittest
import wf07_contract as C
from wf07_coff import read_symbols, member_defines

class Contract(unittest.TestCase):
    def test_coff_weak_and_cpp_are_dependencies(self):
        table = C.coff_symbols('COFF SYMBOL TABLE\n001 00000000 UNDEF notype () External | ?private@@YAXXZ\n002 00000000 UNDEF notype WeakExternal | weak_helper\n003 00000001 UNDEF notype External | common\n004 00000000 SECT2 notype () External | public_api\n')
        self.assertEqual(table['undefined'], ['?private@@YAXXZ', 'weak_helper'])
        self.assertEqual(table['defined'], ['common', 'public_api'])
        self.assertEqual(table['weak'], ['weak_helper'])

    def test_empty_and_unparsed_coff_rejected(self):
        for text in ('LTCG no symbols', 'COFF SYMBOL TABLE\nabc External | x'):
            with self.assertRaises(ValueError): C.coff_symbols(text)

    def test_hex_coff_section_label_not_a_parser_skip(self):
        self.assertEqual(C.coff_symbols('COFF SYMBOL TABLE\n01 00000000 SECT1A notype () External | public_api\n')['defined'], ['public_api'])

    def test_exact_exports_with_inline_and_indented_properties(self):
        prefix = 'build/f06/windows-build/raw-stage'
        configs = {prefix + '/lib/cmake/P/PTargets.cmake': 'add_library(P::a STATIC IMPORTED)\nset_target_properties(P::a PROPERTIES\n INTERFACE_LINK_LIBRARIES "Q::q"\n )',
            prefix + '/lib/cmake/P/PTargets-release.cmake': 'set_target_properties(P::a PROPERTIES IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/a.lib")'}
        owners, targets, deps = C.installed_exports(configs, {prefix + '/lib/a.lib'})
        self.assertEqual(owners, {prefix + '/lib/a.lib': 'P'})
        self.assertEqual(targets, {prefix + '/lib/a.lib': 'a'})
        self.assertEqual(deps, {'P': {'Q'}})

    def test_unowned_installed_library_refused(self):
        with self.assertRaises(ValueError): C.installed_exports({}, {'stage/lib/hidden.lib'})

    def test_owner_declaration_dependency_all_required(self):
        tables = {'a': dict(defined=['own'], undefined=['reader_public', '?helper@@', 'weak_helper']),
                  'b': dict(defined=['reader_public', '?helper@@', 'weak_helper'], undefined=[])}
        owners = dict(a='A', b='B')
        findings, _ = C.private_imports(tables, owners, {'B': {'reader_public'}}, {'A': {'B'}}, set())
        self.assertEqual([r['symbol'] for r in findings['a']], ['?helper@@', 'weak_helper'])
        findings, _ = C.private_imports(tables, owners, {'B': {'reader_public'}}, {}, set())
        self.assertEqual(len(findings['a']), 3)

    def test_same_package_helper_allowed_not_neighbor(self):
        tables = {'a': dict(defined=[], undefined=['helper']), 'b': dict(defined=['helper'], undefined=[])}
        self.assertFalse(C.private_imports(tables, dict(a='A', b='A'), {}, {}, set())[0]['a'])
        self.assertTrue(C.private_imports(tables, dict(a='A', b='B'), {}, {}, set())[0]['a'])

    def test_dynamic_exact_import_does_not_hide_proprietary_provider(self):
        tables = {'a': dict(defined=[], undefined=['helper', '__imp_ReadFile']), 'b': dict(defined=['helper'], undefined=[])}
        findings, _ = C.private_imports(tables, dict(a='A', b='B'), {}, {}, {'helper', '__imp_ReadFile'})
        self.assertEqual({r['symbol'] for r in findings['a']}, {'helper', '__imp_ReadFile'})
        self.assertEqual(findings['a'][0]['reason'], 'observed-pe-import-but-original-dll-provider-unverified')

    def test_unknown_and_duplicate_public_owners_fail(self):
        tables = {name: dict(defined=['reader_public'], undefined=['unknown']) for name in ('a', 'b')}
        findings, conflicts = C.private_imports(tables, dict(a='A', b='B'), {'A': {'reader_public'}}, {}, set())
        self.assertTrue(findings['a']); self.assertEqual(conflicts['reader_public']['defined_by'], ['A', 'B'])

    def test_generic_public_api_not_inline_calls_or_callbacks(self):
        text = 'extern "C" {\nint rfl_open(const char *path);\nvoid roe_close(void *p);\ntypedef void (*reader_callback)(void *p);\nstatic inline void wrapper(void) { reader_private(); }\nEXR_API const char *exr_version(void);\n}'
        self.assertEqual(C.public_entries(text), {'rfl_open', 'roe_close', 'exr_version'})
        self.assertEqual(C.public_entries(text, sdk=True), {'exr_version'})

    def test_public_declarations_ignore_quoted_and_local_extern_spoofs(self):
        text = 'const char *example = "int private_api(void); /* not comment */";\nstatic inline int wrapper(void) { extern int local_private(void); return local_private(); }\nint roe_real(void);'
        self.assertEqual(C.public_entries(text), {'roe_real'})
        with self.assertRaises(ValueError): C.public_entries('}\nint made_up(void);')

    def test_actual_private_header_dependency_not_hidden_by_inline_code(self):
        header = 'build/raw-stage/include/reader_selector_bytes_detail.h'
        text = 'CMakeFiles/codec.dir/src/codec.cpp.obj: #deps 2, deps mtime 123 (VALID)\n    D:/a/repo/src/codec.cpp\n    D:/a/repo/' + header + '\n'
        obj = 'CMakeFiles/codec.dir/src/codec.cpp.obj'
        uses, covered = C.private_header_dependencies(text, {obj: 'Consumer'}, {header: ['Owner']}, 'D:/a/repo', 'raw-codec')
        self.assertEqual(covered, {obj}); self.assertEqual(uses[0]['owners'], ['Owner'])
        self.assertFalse(C.private_header_dependencies(text, {obj: 'Owner'}, {header: ['Owner']}, 'D:/a/repo', 'raw-codec')[0])

    def test_missing_second_archive_object_is_not_complete_coverage(self):
        graph = 'build codec.lib: CXX_STATIC_LIBRARY_LINKER__codec_Release CMakeFiles/codec.dir/a.cpp.obj CMakeFiles/codec.dir/b.cpp.obj || helper\n'
        expected = C.archive_objects(graph, 'codec')
        text = 'CMakeFiles/codec.dir/a.cpp.obj: #deps 1, deps mtime 0 (STALE)\n    D:/a/repo/a.cpp\n'
        _, observed = C.private_header_dependencies(text, dict.fromkeys(expected, 'Owner'), {}, 'D:/a/repo', 'raw-codec')
        self.assertEqual(expected - observed, {'CMakeFiles/codec.dir/b.cpp.obj'})
        with self.assertRaises(ValueError):
            C.private_header_dependencies(text.replace('#deps 1', '#deps 20'), dict.fromkeys(expected, 'Owner'), {}, 'D:/a/repo', 'raw-codec')

    def test_private_source_include_and_unknown_owner_not_public(self):
        rows = [dict(consumer='Catalog', path='apps/export/src/sha256.inc', object='catalog.obj', build='product'),
                dict(consumer='Catalog', path='extras/unowned/helper.inc', object='catalog.obj', build='product')]
        findings, unknown = C.source_include_boundaries(rows, {'apps/export': {'Export'}}, set())
        self.assertEqual(findings[0]['owners'], ['Export'])
        self.assertEqual(unknown[0]['path'], 'extras/unowned/helper.inc')

    def test_parent_include_alias_is_bound_or_explicitly_unknown(self):
        obj = 'CMakeFiles/catalog.dir/a.cpp.obj'
        text = obj + ': #deps 2, deps mtime 0 (STALE)\n    D:/repo/apps/catalog/../export/src/sha256.inc\n    D:/repo/../../escape/private.h\n'
        records = []
        C.private_header_dependencies(text, {obj: 'Catalog'}, {}, 'D:/repo', 'product', records)
        findings, unknown = C.source_include_boundaries(records, {'apps/export': {'Export'}}, set())
        self.assertEqual(findings[0]['path'], 'apps/export/src/sha256.inc')
        self.assertTrue(unknown[0]['unclassified'])

    def test_map_ownership_needs_exact_final_input(self):
        rows = C.map_rows('Preferred load address is 140000000\n Address Publics by Value Rva+Base Lib:Object\n 0001:00000000 exr_version 0000000140001000 f exr_core:version.c.obj\n entry point at 0001:00000000\n')
        self.assertEqual(rows[0]['symbol'], 'exr_version')
        self.assertEqual(C.map_origin(rows[0]['origin'], {'sdk/lib/exr_core.lib'}), 'sdk/lib/exr_core.lib')
        self.assertIsNone(C.map_origin(rows[0]['origin'], {'other.lib'}))

    def test_duplicate_link_basename_refused(self):
        with self.assertRaises(ValueError): C.map_origin('x:a.obj', {'sdk/x.lib', 'product/x.lib'})

    def test_explicit_map_path_cannot_borrow_another_basename(self):
        self.assertIsNone(C.map_origin('D:/repo/wrong/x.lib:a.obj', {'sdk/x.lib'}, 'D:/repo'))

    def test_binary_coff_member_and_weak_fallback_identity(self):
        def symbol(name, section, storage=2, aux=0):
            return name.encode().ljust(8, b'\0') + struct.pack('<IhHBB', 0, section, 0, storage, aux)
        records = symbol('public', 1) + symbol('weak', 0, 105, 1) + struct.pack('<II', 0, 3).ljust(18, b'\0')
        obj = struct.pack('<HHIIIHH', 0x8664, 1, 0, 20, 3, 0, 0) + records + struct.pack('<I', 4)
        result = read_symbols(obj, 'actual.obj')
        self.assertTrue(member_defines(result, 'actual.obj', 'public'))
        self.assertFalse(member_defines(result, 'different.obj', 'public'))
        self.assertEqual(result['rows'][1]['fallback'], 'public')
        self.assertEqual(result['rows'][1]['search'], 3)
        duplicate = dict(result, members=['actual.obj', 'actual.obj'])
        self.assertFalse(member_defines(duplicate, 'actual.obj', 'public'))
        self.assertFalse(member_defines(result, 'wrong/path/actual.obj', 'public'))
        bad = bytearray(obj); struct.pack_into('<I', bad, 20 + 36, 99)
        with self.assertRaises(ValueError): read_symbols(bytes(bad), 'actual.obj')

    def test_unknown_ordinal_pe_import_refused(self):
        with self.assertRaises(ValueError): C.pe_imports('  unknown.dll\n   80000001 Ordinal 1\n')

    def test_original_paths_and_rsp_quotes(self):
        self.assertEqual(C.exact_path('D:/a/EXReader/build/x.lib', 'D:\\a\\EXReader'), 'build/x.lib')
        for path in ('D:/other/x.lib', 'D:/a/EXReader/../x.lib'):
            with self.assertRaises(ValueError): C.exact_path(path, 'D:/a/EXReader')
        self.assertEqual(C.tokens('"D:\\a path\\x.lib" kernel32.lib'), ['D:\\a path\\x.lib', 'kernel32.lib'])

    def test_scope_cannot_award_original_system_or_full_f07(self):
        self.assertTrue(C.GAPS)
        self.assertEqual(C.PINS['capture'][0], 12854809371)
        self.assertEqual(C.SOURCE, '739089d782c2d76f2708446175ccd24fce3b2e3b')

if __name__ == '__main__':
    C.require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions tests only')
    unittest.main()
