"""New protocol tests and negative source fixtures; Actions only."""
import io
import unittest
import zipfile

import af07_contract as C


class AuditContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls): C.actions_only()

    def test_nm_preserves_local_and_weak_unknown(self):
        table = C.symbols('object.o:\n00000000 t sqlite3_open_v2\n         w opds_sha_init\n')
        self.assertEqual(table['defined'], ['sqlite3_open_v2'])
        self.assertEqual(table['undefined'], ['opds_sha_init'])

    def test_nm_unparsed_lines_and_unknown_types_fail(self):
        for value in ('0000 T good\nunparsed line', '0000 ? mystery', '0000 Q mystery', 'garbage'):
            with self.subTest(value=value), self.assertRaises(ValueError): C.symbols(value)

    def test_actual_public_c_declarations_not_prefix_or_implementation(self):
        text = ('/* int bogus(void); */ int rfl_open(void); void roe_run(int);\n'
                'const char *roe_name(void); // int commented(void);\n'
                'static int reader_private(void); inline int reader_inline(void);\n'
                'typedef void (*callback)(void); inline int helper(int x) {return x;}\n'
                'int incomplete(')
        self.assertEqual(C.public_entries(text), {'rfl_open', 'roe_run', 'roe_name'})
        self.assertEqual(C.public_entries('EXR_API int exr_version(void); int exr_private(void);', sdk=True), {'exr_version'})

    def test_inline_body_calls_do_not_grant_public_imports(self):
        text = ('static inline int wrapper(void) { return exr_private(); }\n'
                'inline void throws(void) { throw reader_exception(); }\n'
                'inline void method(void) { object.reader_private(); object->reader_other(); }\n'
                'extern "C" { int real_public(void); }')
        self.assertEqual(C.public_entries(text), {'real_public'})

    def test_local_extern_and_quoted_text_are_not_public(self):
        text = ('static inline int wrapper(void) { extern int exr_private(void); return exr_private(); }\n'
                'const char *example = "text // ; int exr_fake(void); /* braces } */";\n'
                'extern "C" { int real_public(void); struct Opaque { int field; }; }')
        self.assertEqual(C.public_entries(text), {'real_public'})
        with self.assertRaises(ValueError): C.public_entries('extern "C" { int missing_close(void);')

    def imports(self, undefined, owner='Consumer', headers=None, deps=None, system=()):
        tables = {'consumer.a': dict(defined=['consumer_local'], undefined=undefined),
                  'helper.a': dict(defined=['opds_sha_init', 'reader_public'], undefined=[])}
        owners = {'consumer.a': owner, 'helper.a': 'Provider'}
        return C.private_imports(tables, owners, headers or {}, deps or {}, (), set(system))['consumer.a']

    def test_cross_package_helper_not_allowed(self):
        self.assertEqual(self.imports(['opds_sha_init'])[0]['symbol'], 'opds_sha_init')

    def test_same_package_helper_allowed(self):
        self.assertEqual(self.imports(['opds_sha_init'], owner='Provider'), [])

    def test_public_header_requires_allowed_owner(self):
        self.assertTrue(self.imports(['reader_public'], headers={'Provider': {'reader_public'}}))
        self.assertEqual(self.imports(['reader_public'], headers={'Provider': {'reader_public'}}, deps={'Consumer': {'Provider'}}), [])

    def test_unknown_name_without_prefix_fails(self):
        self.assertEqual(self.imports(['invisible_helper'])[0]['reason'], 'unknown-unresolved-import')

    def test_duplicate_public_defining_package_is_ambiguous(self):
        tables = {'consumer.a': dict(defined=[], undefined=['reader_public']),
                  'first.a': dict(defined=['reader_public'], undefined=[]),
                  'second.a': dict(defined=['reader_public'], undefined=[])}
        result = C.private_imports(tables, {'consumer.a': 'Consumer', 'first.a': 'First', 'second.a': 'Second'},
                                  {'First': {'reader_public'}}, {'Consumer': {'First'}}, set(), set())
        self.assertEqual(result['consumer.a'][0]['observed_providers'], ['First', 'Second'])

    def test_exact_system_symbol_not_blanket_prefix(self):
        self.assertEqual(self.imports(['malloc'], system={'malloc'}), [])
        self.assertTrue(self.imports(['_ZNSt_unknown_private'], system={'malloc'}))

    def test_public_declaration_without_provider_definition_fails(self):
        self.assertTrue(self.imports(['reader_missing'], headers={'Provider': {'reader_missing'}}, deps={'Consumer': {'Provider'}}))

    def test_archive_alias_rejected(self):
        for names in (['../x'], ['A/x', 'a/y'], ['x', 'x/y'], ['x', 'x']):
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as archive:
                for name in names: archive.writestr(name, b'x')
            data.seek(0)
            with zipfile.ZipFile(data) as archive, self.assertRaises(ValueError): C.members(archive)

    def test_wrong_root_cannot_borrow_installed_prefix(self):
        good = '/original/build/wave3/stage/lib/libx.a'
        self.assertEqual(C.exact_workspace_path(good, '/original', C.MODULES), C.MODULES + '/lib/libx.a')
        for path in ('/wrong' + good, '/original/alias/../build/wave3/stage/lib/libx.a', '/original/build/wave3/stage//lib/libx.a'):
            with self.subTest(path=path), self.assertRaises(ValueError): C.exact_workspace_path(path, '/original', C.MODULES)

    def test_sqlite_owner_resets_at_standalone_object(self):
        prefix = '0 0 10 1 '
        good = prefix + '/original/libreader_catalog_sqlite.a(sqlite3.c.o):(.text.sqlite3_open_v2)\n' + prefix + 'sqlite3_open_v2\n'
        self.assertEqual(C.sqlite_map_owner(good), '/original/libreader_catalog_sqlite.a(sqlite3.c.o)')
        changed = good.replace(prefix + 'sqlite3_open_v2', prefix + 'host.o:(.text.sqlite3_open_v2)\n' + prefix + 'sqlite3_open_v2')
        self.assertEqual(C.sqlite_map_owner(changed), 'host.o')
        with self.assertRaises(ValueError): C.sqlite_map_owner(good.replace(prefix + 'sqlite3_open_v2', prefix + '.text\n' + prefix + 'sqlite3_open_v2'))

    def test_hidden_sdk_image_import_and_unneeded_stub_rejected(self):
        records = {
            'host': dict(full=dict(defined=[], undefined=['exr_hidden', 'malloc', 'unused_only']),
                         dynamic=dict(defined=[], undefined=[]), needed=['sdk', 'libc.so']),
            'sdk': dict(full=dict(defined=['exr_hidden', 'exr_version'], undefined=[]),
                        dynamic=dict(defined=['exr_hidden', 'exr_version'], undefined=[]), needed=[]),
        }
        reached, allowed = C.system_scope('host', records, {'sdk': 'sdk'},
                                         {'libc.so': {'malloc'}, 'unused.so': {'unused_only'}}, {'malloc', 'unused_only'})
        self.assertEqual(C.image_imports('host', records, reached, allowed, ['sdk'], {'exr_version'}), ['exr_hidden', 'unused_only'])

    def test_hidden_runtime_in_other_image_cannot_resolve_import(self):
        records = {
            'host': dict(full=dict(defined=[], undefined=['__cxa_hidden']),
                         dynamic=dict(defined=[], undefined=['dynsym_only']), needed=['sdk']),
            'sdk': dict(full=dict(defined=['__cxa_hidden'], undefined=[]),
                        dynamic=dict(defined=[], undefined=[]), needed=[]),
        }
        reached, allowed = C.system_scope('host', records, {'sdk': 'sdk'}, {}, {'__cxa_hidden'})
        self.assertEqual(C.image_imports('host', records, reached, allowed, ['sdk'], set()), ['__cxa_hidden', 'dynsym_only'])
        records['sdk']['dynamic']['defined'] = ['__cxa_hidden']
        reached, allowed = C.system_scope('host', records, {'sdk': 'sdk'}, {}, {'__cxa_hidden'})
        self.assertEqual(C.image_imports('host', records, reached, allowed, ['sdk'], set()), ['dynsym_only'])

    def test_duplicate_manifest_or_header_owner_rejected(self):
        mapping = {}
        C.assign_unique(mapping, 'header.h', 'First')
        with self.assertRaises(ValueError): C.assign_unique(mapping, 'header.h', 'Second')
        manifests = {}
        C.assign_unique(manifests, 'Package', {})
        with self.assertRaises(ValueError): C.assign_unique(manifests, 'Package', {})

    def test_generated_cmake_indented_close(self):
        text = ('set_target_properties(Owner::lib PROPERTIES\n'
                '  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/libowner.a"\n  )\n')
        self.assertEqual([(name, body.strip()) for name, body in C.target_properties(text)],
                         [('Owner::lib', 'IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/libowner.a"')])
        self.assertEqual(C.target_properties('set_target_properties(Owner::lib PROPERTIES incomplete'), [])

    def test_complete_installed_include_ownership(self):
        C.require_header_coverage(C.header_coverage({'include/public.h'}, {'include/public.h': 'Owner'}))
        for installed, owners in (({'include/public.h', 'include/private.ipp'}, {'include/public.h': 'Owner'}),
                                  ({'include/public.h'}, {'include/public.h': 'Owner', 'include/absent.h': 'Other'}),
                                  (set(), {})):
            with self.subTest(installed=installed, owners=owners), self.assertRaises(ValueError):
                C.require_header_coverage(C.header_coverage(installed, owners))

    def test_ndk_script_rejects_unhandled_directives_and_paths(self):
        import af07_ndk_inputs as N
        self.assertEqual(N.input_tokens(b'INPUT(-lc++_shared)'), ['-lc++_shared'])
        for payload in (b'GROUP(-lc)', b'INPUT(/outside/lib.so)', b'INPUT(../lib.so)',
                        b'INPUT(-l../escape)', b'INPUT(-lc) SEARCH_DIR(/outside)', b'INPUT()', b'INPUT(-l:libc.so)'):
            with self.assertRaises(ValueError): N.input_tokens(payload)

    def test_ndk_script_resolution_exact_search_and_no_runtime_grant(self):
        import af07_ndk_inputs as N
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); api = root / '26'; api.mkdir()
            script = api / 'libc++.so'; script.write_bytes(b'INPUT(-lc++_shared)')
            target = root / 'libc++_shared.so'; target.write_bytes(b'\x7fELFfixture')
            report = N.resolve(script, root, (api, root))
            self.assertEqual(report['kind'], 'INPUT-script')
            self.assertEqual(report['children'][0]['path'], 'libc++_shared.so')
            self.assertEqual(N.system_names({'libc.so': 1, 'libfuture.so': 35}, 26), {'libc.so'})
            self.assertNotIn('libc++.so', N.system_names({'libc.so': 1}, 26))
            target.unlink()
            with self.assertRaises(ValueError): N.resolve(script, root, (api, root))

    def test_ndk_script_cycles_and_link_aliases_fail(self):
        import af07_ndk_inputs as N
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); script = root / 'libcycle.so'
            script.write_bytes(b'INPUT(-lcycle)')
            with self.assertRaises(ValueError): N.resolve(script, root, (root,))
            target = root / 'libtarget.so'; target.write_bytes(b'\x7fELFfixture')
            alias = root / 'libalias.so'; alias.symlink_to(target)
            with self.assertRaises(ValueError): N.resolve(alias, root, (root,))
            with self.assertRaises(ValueError): N.resolve(target, root, (root.parent,))

    def test_ndk_manifest_not_extension_grants_runtime_name(self):
        import af07_ndk_inputs as N
        self.assertEqual(N.system_names({'libc.so': '21', 'libfuture.so': '35'}, 26), {'libc.so'})
        for metadata in ({}, {'libc.so': True}, {'../libc.so': 1}, {'libc.so': '0'},
                         {'libc.so': ' 21'}, {'libc.so': '021'}, {'libc.so': '21.0'},
                         {'libc.so': '-1'}, {'libc.so': 'current'}, {'libc.so': None}):
            with self.assertRaises(ValueError): N.system_names(metadata, 26)
        records = {'host': dict(needed=['libc++.so'], full=dict(defined=[]), dynamic=dict(defined=[]))}
        with self.assertRaises(ValueError): C.system_scope('host', records, {}, {'libc.so': set()}, set())

    def test_ndk_script_probe_requires_exact_observed_bytes(self):
        from af07_ndk_probe import verify_script
        self.assertEqual(verify_script(b'INPUT(-lc++_shared)'), ['-lc++_shared'])
        for payload in (b'INPUT(-lc++_shared)\n', b'INPUT(-lother)', b'GROUP(-lc++_shared)', b'\x7fELF'):
            with self.assertRaises(ValueError): verify_script(payload)

    def test_diagnostic_requires_exact_failure_identity_and_output_hash(self):
        import af07_diagnostic as D
        summary = dict(audit_sha=D.PRIOR_SHA, audit_run=str(D.PRIOR_RUN), audit_attempt='1',
                       original_capture_replayed=True, android_static_closure_accepted=False,
                       full_six_platform_f07_accepted=False)
        prefix = '/sdk/ndk/27.0.12077973/toolchains/llvm/prebuilt/linux-x86_64/'
        row = dict(label='system-008', exit=1,
                   argv=[prefix + 'bin/llvm-nm', '-D', '-g', '--defined-only', prefix + 'sysroot/usr/lib/x86_64-linux-android/26/libtest.so'],
                   stdout_sha256=C.sha(b''), stderr_sha256=C.sha(b'not ELF'))
        report = D.selected_failure(summary, [row], b'', b'not ELF')
        self.assertTrue(report['diagnostic_only'])
        self.assertFalse(report['include_dependency_coverage_complete'])
        with self.assertRaises(ValueError): D.selected_failure(summary, [row], b'', b'changed')
        with self.assertRaises(ValueError): D.selected_failure(dict(summary, audit_sha='wrong'), [row], b'', b'not ELF')
        row['argv'][-1] = '/captured/product.so'
        with self.assertRaises(ValueError): D.selected_failure(summary, [row], b'', b'not ELF')


if __name__ == '__main__':
    C.actions_only()
    unittest.main()
