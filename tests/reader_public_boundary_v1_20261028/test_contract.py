"""Actions-only synthetic controls; never substitute for native producer evidence."""
import importlib.util
import os
from pathlib import Path
import unittest
import tempfile

spec=importlib.util.spec_from_file_location('public_boundary_validator',Path(__file__).with_name('run.py'))
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)


class BoundaryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        C.actions()

    def test_exact_scope(self):
        self.assertEqual(len(C.OWNERS),17);self.assertEqual(len(C.ADDED),7)
        self.assertEqual(C.HOSTS,('examples/android/app/src/main/cpp/wave3_product_jni.inc',))
        self.assertEqual(len(set((*C.OWNERS,*C.HOSTS,*C.ADDED))),25)
        self.assertTrue(all(p.startswith('apps/reader/') for p in C.OWNERS))
        self.assertEqual(len(C.NEW_OWNER),3)

    def test_no_sdk_or_old_tests_in_scope(self):
        for p in (*C.OWNERS,*C.HOSTS,*C.ADDED):
            self.assertFalse(p.startswith(('src/','include/','cmake/','tests/reader_selector_bytes/','tests/reader_f06_packages/')))

    def test_artifact_inventory_requires_hidden_dependencies(self):
        files={'build/module/.ninja_deps':{},'build/module/.ninja_log':{},'build/module/public.a':{}}
        self.assertEqual(C.file_inventory_difference([*files,'inventory.json'],files),dict(missing=[],unexpected=[]))
        diff=C.file_inventory_difference(['inventory.json','build/module/public.a'],files)
        self.assertEqual(diff['missing'],['build/module/.ninja_deps','build/module/.ninja_log'])
        self.assertEqual(diff['unexpected'],[])

    def test_artifact_inventory_never_ignores_extra_hidden_files(self):
        diff=C.file_inventory_difference(['inventory.json','build/.unexpected'],{})
        self.assertEqual(diff,dict(missing=[],unexpected=['build/.unexpected']))

    def test_hidden_upload_is_bounded_to_captured_evidence(self):
        text=(C.ROOT/'.github/workflows/reader-public-boundary-v1-20261028.yml').read_text()
        self.assertEqual(text.count('include-hidden-files: true'),4)
        self.assertEqual(text.count('path: build/public-boundary-v1/evidence/\n          include-hidden-files: true'),4)

    def test_original_selector_versions_uses_actual_legacy_sibling(self):
        data=Path('/owned/native-data')
        for entry in ('linux','windows','macos','iphone','ipad','android'):
            legacy,work=C.selector_phase_layout(data,entry)
            self.assertEqual(legacy,work.parent/'candidate-legacy')
            self.assertNotEqual(legacy,work)
            self.assertEqual(work,data/(entry+'-original')/'actual')
        self.assertNotEqual(C.selector_phase_layout(data,'iphone')[0],C.selector_phase_layout(data,'ipad')[0])

    def test_actual_ninja_supported_cache_types_and_exact_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            ninja=Path(tmp)/'ninja';ninja.write_bytes(b'synthetic tool, never executed')
            before={'ninja_tools':{str(ninja):{'sha256':C.digest(ninja),'resolved':str(ninja.resolve())}}}
            for kind in ('FILEPATH','STRING','UNINITIALIZED'):
                line='CMAKE_MAKE_PROGRAM:'+kind+'='+str(ninja)
                self.assertEqual(C.configured_ninja('// comment\n'+line+'\n',before),ninja)
            for text in ('','// CMAKE_MAKE_PROGRAM:FILEPATH='+str(ninja),
                         'CMAKE_MAKE_PROGRAM:FILEPATH='+str(ninja)+'\nCMAKE_MAKE_PROGRAM:STRING='+str(ninja),
                         'CMAKE_MAKE_PROGRAM:BOOL='+str(ninja),'CMAKE_MAKE_PROGRAM:STRING=',
                         'CMAKE_MAKE_PROGRAM:FILEPATH=ninja','CMAKE_MAKE_PROGRAM:FILEPATH='+str(ninja)+'-missing'):
                with self.assertRaises(AssertionError):C.configured_ninja(text,before)
            with self.assertRaises(AssertionError):C.configured_ninja(line,{'ninja_tools':{}})
            ninja.write_bytes(b'changed after producer')
            with self.assertRaises(AssertionError):C.configured_ninja(line,before)

    def test_guard_fixture_cannot_fall_back_to_second_raw_prefix(self):
        selected=Path('/owned/legacy-stage')
        raw=C.guard_fixture_source('EXReaderRevisions 0.4.0',selected)
        self.assertIn('EXReaderRevisions 0.4.0 EXACT CONFIG REQUIRED PATHS "/owned/legacy-stage/lib/cmake/EXReaderRevisions" NO_DEFAULT_PATH',raw)
        self.assertIn('NO_CMAKE_FIND_ROOT_PATH',raw)
        self.assertIn('file(REAL_PATH "${EXReaderRevisions_DIR}" _actual_config)',raw)
        self.assertIn('if(NOT _actual_config STREQUAL _expected_config)',raw)
        old=C.guard_fixture_source('EXReaderRevisions 0.3.0',selected,Path('/owned/legacy-api.c'))
        self.assertIn('EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED',old)
        self.assertIn('target_link_libraries(guard-compile PRIVATE EXReaderRevisions::reader_revisions)',old)
        public=C.guard_fixture_source('EXReaderRevisions 0.3.0',selected,C.HERE/'codec_v1.c',True)
        self.assertIn('codec_v1.c',public)
        self.assertIn('add_library(guard-compile OBJECT ',public)
        self.assertNotIn('target_include_directories',public)

    def test_public_header_compile_refusal_is_not_generic_link_or_build_failure(self):
        for text in ("fatal error C1083: Cannot open include file: 'reader_selector_bytes_v1.h': No such file or directory",
                     "fatal error: 'reader_selector_bytes_v1.h' file not found",
                     'fatal error: reader_selector_bytes_v1.h: No such file or directory'):
            self.assertTrue(C.missing_public_header_diagnostic(text))
        for text in ('reader_selector_bytes_v1.h: unrelated error','undefined reference to reader_selector_encode_v1',
                     "fatal error: 'other.h' file not found",'reader_selector_bytes_v1.h mentioned; linker failed'):
            self.assertFalse(C.missing_public_header_diagnostic(text))

    def test_snapshot_empty_directories_are_transferred_without_hiding_file_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();(source/'empty/nested').mkdir(parents=True)
            (source/'kept').write_bytes(b'actual file')
            inventory=C.snapshot(source);incoming=Path(tmp)/'incoming';incoming.mkdir()
            (incoming/'kept').write_bytes(b'actual file')
            self.assertNotEqual(C.snapshot(incoming),inventory)
            C.restore_snapshot_directories(incoming,inventory)
            self.assertEqual(C.snapshot(incoming),inventory)
            (incoming/'kept').unlink();C.restore_snapshot_directories(incoming,inventory)
            self.assertNotEqual(C.snapshot(incoming),inventory)
            for dirs in (['../escape'],['same','same'],['kept']):
                with self.assertRaises(AssertionError):C.snapshot_directories({'files':inventory['files'],'directories':dirs})

    def test_old_private_call_absent(self):
        for p in ('apps/reader/reading-commands/src/reading_commands.cpp','apps/reader/reading-state/src/reading_state.cpp',*C.HOSTS):
            self.assertNotIn('reader_rs_encode_retained_raw_v3',(C.ROOT/p).read_text())

    def test_android_caller_uses_installed_public_declaration(self):
        source=(C.ROOT/C.HOSTS[0]).read_text()
        self.assertIn('#include <reader_reading_state_retained_raw_v1.h>',source)
        self.assertEqual(source.count('reader_rs_encode_retained_raw_v1('),1)

    def test_private_header_clients_absent(self):
        for p in ('apps/reader/reading-state/src/reading_state.cpp','apps/reader/annotation-import/src/annotation_import.cpp','apps/reader/annotation-export/src/annotation_export.cpp'):
            self.assertNotIn('reader_selector_bytes_detail',(C.ROOT/p).read_text())

    def test_safe_members(self):
        self.assertTrue(C.safe_member('build/stage/include/public.h'))
        for name in ('','/a','../a','a/../b','a//b','a\\b','C:/a','a/./b'):
            self.assertFalse(C.safe_member(name),name)

    def test_elf_definition(self):
        self.assertTrue(C.symbol_present('a.a(m.o): 00000000 T reader_public_v1','reader_public_v1',True))

    def test_macho_definition(self):
        self.assertTrue(C.symbol_present('a.a(m.o): 00000000 T _reader_public_v1','reader_public_v1',True))

    def test_elf_import(self):
        self.assertTrue(C.symbol_present('a.a(m.o):          U reader_public_v1','reader_public_v1',False))

    def test_weak_not_strong_public_definition(self):
        self.assertFalse(C.symbol_present('a.a(m.o): 00000000 W reader_public_v1','reader_public_v1',True))

    def test_prefix_not_exact_symbol(self):
        self.assertFalse(C.symbol_present('a.a(m.o): 00000000 T reader_public_v1_private','reader_public_v1',True))

    def test_unknown_kind_not_definition(self):
        self.assertFalse(C.symbol_present('a.a(m.o): 00000000 Q reader_public_v1','reader_public_v1',True))

    def test_coff_definition(self):
        self.assertTrue(C.symbol_present('00A 00000000 SECT3 notype () External | reader_public_v1','reader_public_v1',True,True))

    def test_coff_import(self):
        self.assertTrue(C.symbol_present('00A 00000000 UNDEF notype () External | reader_public_v1','reader_public_v1',False,True))
        self.assertFalse(C.symbol_present('00A 00000000 UNDEF notype () External | reader_public_v1','reader_public_v1',True,True))

    def test_coff_local_not_public(self):
        self.assertFalse(C.symbol_present('00A 00000000 SECT3 notype () Static | reader_public_v1','reader_public_v1',True,True))

    def test_coff_data_not_function(self):
        self.assertFalse(C.symbol_present('00A 00000000 SECT3 notype External | reader_public_v1','reader_public_v1',True,True))

    def test_coff_common_not_import(self):
        self.assertFalse(C.symbol_present('00A 00000008 UNDEF notype () External | reader_public_v1','reader_public_v1',False,True))

    def test_coff_weak_not_import(self):
        self.assertFalse(C.symbol_present('00A 00000000 UNDEF notype () WeakExternal | reader_public_v1','reader_public_v1',False,True))

    def test_coff_high_hex_section(self):
        self.assertTrue(C.symbol_present('00A 00000000 SECT1AF notype () External | reader_public_v1','reader_public_v1',True,True))

    def group(self,source='reading_state.cpp',header='reader_selector_bytes_v1.h',status='VALID'):
        return C.ninja_dependency_groups('object.o: #deps 2, deps mtime 123 ('+status+')\n    '+source+'\n    '+header+'\n')

    def test_actual_dependency_positive(self):
        proof=C.owned_dependency_proof('reading_state.cpp',['object.o'],self.group(),C.ROOT,['reader_selector_bytes_v1.h'])
        self.assertTrue(proof['private_selector_header_absent'])

    def test_msvc_headers_bind_to_exact_compiler_input(self):
        inputs,outputs=C.ninja_explicit_inputs('object.obj:\n  input: CXX_COMPILER__reader_Release\n    reading_state.cpp\n    || order_target\n  outputs:\n    reader.lib\n','object.obj','CXX_COMPILER')
        self.assertEqual(inputs,['reading_state.cpp']);self.assertEqual(outputs,['reader.lib'])
        groups=C.ninja_dependency_groups('object.obj: #deps 1, deps mtime 123 (VALID)\n    reader_selector_bytes_v1.h\n')
        proof=C.owned_dependency_proof('reading_state.cpp',['object.obj'],groups,C.ROOT,['reader_selector_bytes_v1.h'],{'object.obj':inputs[0]})
        self.assertEqual(proof['source_binding'],'exact Ninja compiler input and archive object')

    def test_msvc_missing_graph_source_rejected(self):
        groups=C.ninja_dependency_groups('object.obj: #deps 1, deps mtime 123 (VALID)\n    reader_selector_bytes_v1.h\n')
        with self.assertRaises(AssertionError):C.owned_dependency_proof('reading_state.cpp',['object.obj'],groups,C.ROOT,['reader_selector_bytes_v1.h'])
        with self.assertRaises(AssertionError):C.owned_dependency_proof('reading_state.cpp',['object.obj'],groups,C.ROOT,['reader_selector_bytes_v1.h'],{})

    def test_wrong_graph_source_rejected_even_if_depfile_names_expected(self):
        with self.assertRaises(AssertionError):C.owned_dependency_proof('reading_state.cpp',['object.o'],self.group(),C.ROOT,[],{'object.o':'not_reading_state.cpp'})

    def test_compiler_query_wrong_node_or_rule_rejected(self):
        text='object.obj:\n  input: CXX_COMPILER__reader_Release\n    reading_state.cpp\n  outputs:\n    reader.lib\n'
        with self.assertRaises(AssertionError):C.ninja_explicit_inputs(text,'not_object.obj','CXX_COMPILER')
        with self.assertRaises(AssertionError):C.ninja_explicit_inputs(text,'object.obj','CXX_STATIC_LIBRARY_LINKER')

    def test_compiler_query_truncation_rejected(self):
        with self.assertRaises(AssertionError):C.ninja_explicit_inputs('object.obj:\n  input: CXX_COMPILER__reader_Release\n    reading_state.cpp\n','object.obj','CXX_COMPILER')

    def lld(self,value,kind='input',address=0x100,size=0x20):
        return f'{address:x} {address:x} {size:x} 1 '+{'output':'','input':' '*8,'symbol':' '*16}[kind]+value+'\n'

    def test_lld_exact_named_provider(self):
        text=self.lld('/stage/lib/libreader_reading_state_codec.a(reading_state.cpp.o):(.text.reader_rs_encode_retained_raw_v1)')+self.lld('reader_rs_encode_retained_raw_v1','symbol')
        self.assertEqual(C.lld_symbol_origin(text,'reader_rs_encode_retained_raw_v1'),('/stage/lib/libreader_reading_state_codec.a(reading_state.cpp.o)',0x100))

    def test_lld_standalone_contribution_never_borrows_archive(self):
        text=self.lld('/stage/lib/owner.a(member.o):(.text.public)')+self.lld('caller.o:(.text.public)')+self.lld('public','symbol')
        self.assertEqual(C.lld_symbol_origin(text,'public')[0],'caller.o')

    def test_lld_new_section_without_provider_rejected(self):
        with self.assertRaises(AssertionError):C.lld_symbol_origin(self.lld('owner.a(member.o):(.text.public)')+self.lld('.other','output')+self.lld('public','symbol'),'public')

    def test_lld_missing_duplicate_or_prefix_symbol_rejected(self):
        for text in (self.lld('owner.a(member.o):(.text.public)')+self.lld('public_extra','symbol'),
                     self.lld('owner.a(member.o):(.text.public)')+self.lld('public','symbol')+self.lld('public','symbol',0x104)):
            with self.assertRaises(AssertionError):C.lld_symbol_origin(text,'public')

    def test_lld_malformed_intervening_origin_rejected(self):
        with self.assertRaises(AssertionError):C.lld_symbol_origin(self.lld('owner.a(member.o):(.text.public)')+'BAD_ROW other.o:(.text.public)\n'+self.lld('public','symbol'),'public')

    def test_lld_out_of_range_symbol_rejected(self):
        with self.assertRaises(AssertionError):C.lld_symbol_origin(self.lld('owner.a(member.o):(.text.public)')+self.lld('public','symbol',0x120),'public')

    def test_lld_demangled_anonymous_namespace_is_symbol_not_input(self):
        observed='long std::__ndk1::(anonymous namespace)::as_integer_helper<long, std::__ndk1::basic_string<char, std::__ndk1::char_traits<char>, std::__ndk1::allocator<char>>, long (*)(char const*, char**, int)>(std::__ndk1::basic_string<char, std::__ndk1::char_traits<char>, std::__ndk1::allocator<char>> const&, std::__ndk1::basic_string<char, std::__ndk1::char_traits<char>, std::__ndk1::allocator<char>> const&, unsigned long*, int, long (*)(char const*, char**, int))'
        text=self.lld('/ndk/libc++_static.a(string.cpp.o):(.text.helper)')+self.lld(observed,'symbol')
        self.assertEqual([row[3] for row in C.lld_rows(text)],['input','symbol'])
        self.assertEqual(C.lld_symbol_origin(text,observed),('/ndk/libc++_static.a(string.cpp.o)',0x100))

    def test_lld_unknown_hierarchy_rejected(self):
        for indent in (1,7,9,15,17):
            with self.assertRaises(AssertionError):C.lld_rows('100 100 20 1 '+' '*indent+'owner.a(member.o):(.text.public)\n')
        with self.assertRaises(AssertionError):C.lld_rows('100 100 20 1 \towner.a(member.o):(.text.public)\n')

    def test_lld_unknown_input_cannot_borrow_prior_owner(self):
        text=self.lld('owner.a(member.o):(.text.public)')+self.lld('unknown-input-form')+self.lld('public','symbol')
        with self.assertRaises(AssertionError):C.lld_symbol_origin(text,'public')

    def test_lld_wanted_symbol_requires_actual_input_row(self):
        with self.assertRaises(AssertionError):C.lld_symbol_origin(self.lld('owner.a(member.o):(.text.public)','symbol')+self.lld('public','symbol'),'public')

    def test_android_actual_link_map_binding(self):
        root=Path('/workspace');image=root/'libproduct.so'
        mapping,_=C.android_link_binding(': && /ndk/clang++ -shared -Wl,-Map,actual.map -o libproduct.so caller.o && :\n',image,root)
        self.assertEqual(mapping,root/'actual.map')
        for command in ('clang++ -Wl,-Map,actual.map -o other.so caller.o',
                        'clang++ -o libproduct.so caller.o',
                        'clang++ -Wl,-Map,actual.map -o libproduct.so @link.rsp'):
            with self.assertRaises(AssertionError):C.android_link_binding(command,image,root)

    def test_selected_ndk_requires_exact_prebuild_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'lib.a';path.write_bytes(b'captured before build')
            record=C.ndk_file_record(root,path);before={'root':str(root),'inputs':{'lib.a':record}}
            self.assertEqual(C.selected_ndk_record(before,path),record)
            path.write_bytes(b'changed after build')
            with self.assertRaises(AssertionError):C.selected_ndk_record(before,path)

    def test_selected_ndk_missing_prebuild_record_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'lib.a';path.write_bytes(b'not selected before')
            with self.assertRaises(AssertionError):C.selected_ndk_record({'root':str(root),'inputs':{}},path)

    def test_ndk_wrong_root_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'ndk';root.mkdir();outside=Path(tmp)/'ndk-lookalike';outside.mkdir();(outside/'lib.a').write_bytes(b'wrong root')
            with self.assertRaises(AssertionError):C.ndk_file_record(root,outside/'lib.a')
            with self.assertRaises(AssertionError):C.ndk_file_record(root,root/'..'/'ndk-lookalike/lib.a')

    def test_ndk_escaping_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'ndk';root.mkdir();outside=Path(tmp)/'outside.a';outside.write_bytes(b'not NDK')
            alias=root/'lib.a';alias.symlink_to(outside)
            with self.assertRaises(AssertionError):C.ndk_file_record(root,alias)

    def test_runtime_bytes_require_notice_coverage_not_filename_only(self):
        relative='toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/libc++_static.a'
        record={'path':relative,'resolved':relative,'symlink':None}
        notices={'NOTICE':'retained distribution notices','NOTICE.toolchain':C.LLVM_LICENSE_BLOCK}
        self.assertTrue(C.llvm_runtime_notice_coverage(record,notices))
        self.assertFalse(C.llvm_runtime_notice_coverage(record,{}))
        self.assertFalse(C.llvm_runtime_notice_coverage(record,{'NOTICE':'x','NOTICE.toolchain':'Apache License LLVM END OF TERMS AND CONDITIONS LLVM Exceptions'}))
        self.assertFalse(C.llvm_runtime_notice_coverage(dict(record,path='unknown/libc++_static.a'),notices))
        self.assertFalse(C.llvm_runtime_notice_coverage(dict(record,resolved='unknown/in-root.a',symlink='unknown/in-root.a'),notices))
        truncated=dict(notices);truncated['NOTICE.toolchain']=C.LLVM_LICENSE_BLOCK.replace('You must give any other recipients','You MAY OMIT recipients')
        self.assertFalse(C.llvm_runtime_notice_coverage(record,truncated))

    def test_actual_ndk_driver_target_and_sysroot_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);driver=root/'toolchains/llvm/prebuilt/linux-x86_64/bin/clang++';driver.parent.mkdir(parents=True);driver.write_bytes(b'not executed')
            sysroot=root/'toolchains/llvm/prebuilt/linux-x86_64/sysroot';sysroot.mkdir()
            before={'root':str(root),'tools':{'clang++':C.ndk_file_record(root,driver)}}
            cache='CMAKE_CXX_COMPILER:FILEPATH='+str(driver)+'\n'
            records={'CXX':'set(CMAKE_CXX_COMPILER "'+str(driver)+'")\n'}
            command=str(driver)+' --target=x86_64-none-linux-android26 --sysroot='+str(sysroot)+' -shared -o image.so'
            self.assertEqual(C.ndk_driver_binding(command,cache,before,records)['target'],'x86_64-none-linux-android26')
            self.assertEqual(C.ndk_driver_binding(command,'',before,records)['target'],'x86_64-none-linux-android26')
            for wrong in ({},{'CXX':records['CXX']*2},{'CXX':records['CXX'].replace(str(driver),'/wrong/clang++')},{'CXX':'# '+records['CXX']}):
                with self.assertRaises(AssertionError):C.ndk_driver_binding(command,cache,before,wrong)
            for bad in (command.replace('android26','android27'),command.replace(str(sysroot),'/other/sysroot'),command.replace(str(driver),'/other/clang++')):
                with self.assertRaises(AssertionError):C.ndk_driver_binding(bad,cache,before,records)
            for override in (' -target arm64-linux-android26',' --target arm64-linux-android26',' --sysroot /other',' -isysroot /other',' -target=arm64-linux-android26',' -isysroot=/other',' -Xclang -triple'):
                with self.assertRaises(AssertionError):C.ndk_driver_binding(command+override,cache,before,records)
            for wrong in (cache*2,cache.replace(str(driver),'/other/clang++'),cache.replace('FILEPATH','BOOL')):
                with self.assertRaises(AssertionError):C.ndk_driver_binding(command,wrong,before,records)
            driver.write_bytes(b'changed driver')
            with self.assertRaises(AssertionError):C.ndk_driver_binding(command,cache,before,records)

    def test_ndk_prebuild_requires_same_source_run_attempt(self):
        before=dict(C.identity(),complete=True);C.require_prebuild_identity(before)
        for key in C.identity():
            bad=dict(before);bad[key]='different'
            with self.assertRaises(AssertionError):C.require_prebuild_identity(bad)

    def test_ordinary_archive_exact_member_positive(self):
        C.validate_archive_members(b'!<arch>\n',['one.o','two.o'],{'two.o'})

    def test_thin_duplicate_and_missing_archive_member_rejected(self):
        for magic,listing,selected in ((b'!<thin>\n',['one.o'],{'one.o'}),(b'!<arch>\n',['one.o','one.o'],{'one.o'}),
                                       (b'!<arch>\n',['one.o'],{'other.o'}),(b'!<arch>\n',['one.o'],{None})):
            with self.assertRaises(AssertionError):C.validate_archive_members(magic,listing,selected)

    def test_private_dependency_rejected(self):
        with self.assertRaises(AssertionError):C.owned_dependency_proof('reading_state.cpp',['object.o'],self.group(header='reader_selector_bytes_detail.h'),C.ROOT,[])

    def test_wrong_source_alias_rejected(self):
        with self.assertRaises(AssertionError):C.owned_dependency_proof('reading_state.cpp',['object.o'],self.group(source='not_reading_state.cpp'),C.ROOT,[])

    def test_unlinked_object_rejected(self):
        with self.assertRaises(AssertionError):C.owned_dependency_proof('reading_state.cpp',['other.o'],self.group(),C.ROOT,[])

    def test_stale_dependency_rejected(self):
        with self.assertRaises(AssertionError):C.owned_dependency_proof('reading_state.cpp',['object.o'],self.group(status='STALE'),C.ROOT,[])

    def test_truncated_ninja_group_rejected(self):
        with self.assertRaises(AssertionError):C.ninja_dependency_groups('object.o: #deps 2, deps mtime 123 (VALID)\n    reading_state.cpp\n')

    def test_no_dependency_group_rejected(self):
        with self.assertRaises(AssertionError):C.ninja_dependency_groups('reading_state.cpp')

    def test_make_complete_rule(self):
        groups=C.make_dependency_group('object.o: reading_state.cpp reader_selector_bytes_v1.h\n')
        self.assertTrue(C.owned_dependency_proof('reading_state.cpp',['object.o'],groups,C.ROOT,['reader_selector_bytes_v1.h']))

    def test_make_truncation_rejected(self):
        with self.assertRaises(AssertionError):C.make_dependency_group('object.o: reading_state.cpp')

    def test_required_public_header_missing(self):
        with self.assertRaises(AssertionError):C.owned_dependency_proof('reading_state.cpp',['object.o'],self.group(header='other.h'),C.ROOT,['reader_selector_bytes_v1.h'])

    def test_snapshot_replacement_preserves_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'device';destination=Path(tmp)/'host';source.mkdir();destination.mkdir()
            (source/'keep.jsonl').write_text('original');C.exact_copy(source,destination)
            self.assertTrue((destination/'keep.jsonl').exists())
            (source/'keep.jsonl').unlink();(destination/'stale-wal').write_text('stale')
            C.exact_copy(source,destination)
            self.assertFalse((destination/'keep.jsonl').exists());self.assertFalse((destination/'stale-wal').exists())
            self.assertEqual(C.snapshot(source),C.snapshot(destination))

    def test_wire_inventory_is_nonempty_six(self):
        self.assertEqual(len(C.EXPECTED_WIRES),6);self.assertNotEqual(set(),C.EXPECTED_WIRES)

    def test_ios_program_uses_actual_generated_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'probe.app').mkdir();(root/'probe.app/probe').write_text('synthetic not executed')
            self.assertEqual(C.built_program(root,'probe','iphone'),root/'probe.app/probe')
            self.assertEqual(C.built_program(root,'probe','ipad'),root/'probe.app/probe')
            with self.assertRaises(AssertionError):C.built_program(root,'probe','macos')

    def test_ios_program_never_accepts_stale_unbundled_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'probe').write_text('synthetic not executed')
            with self.assertRaises(AssertionError):C.built_program(root,'probe','iphone')

    def test_no_full_f07_scope_claim(self):
        source=(Path(__file__).with_name('run.py')).read_text()
        self.assertIn('final_whole_image_f07_audit=False',source)
        self.assertIn('full_six_f07_accepted=False',source)


if __name__=='__main__':
    C.actions();unittest.main()
