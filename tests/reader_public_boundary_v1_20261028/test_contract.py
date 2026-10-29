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

    def test_lld_exact_named_provider(self):
        text='100 100 20 4 /stage/lib/libreader_reading_state_codec.a(reading_state.cpp.o):(.text.reader_rs_encode_retained_raw_v1)\n100 100 20 1 reader_rs_encode_retained_raw_v1\n'
        self.assertEqual(C.lld_symbol_origin(text,'reader_rs_encode_retained_raw_v1'),('/stage/lib/libreader_reading_state_codec.a(reading_state.cpp.o)',0x100))

    def test_lld_standalone_contribution_never_borrows_archive(self):
        text='100 100 20 4 /stage/lib/owner.a(member.o):(.text.public)\n100 100 20 4 caller.o:(.text.public)\n100 100 20 1 public\n'
        self.assertEqual(C.lld_symbol_origin(text,'public')[0],'caller.o')

    def test_lld_new_section_without_provider_rejected(self):
        with self.assertRaises(AssertionError):C.lld_symbol_origin('100 100 20 4 owner.a(member.o):(.text.public)\n100 100 20 4 .other\n100 100 20 1 public\n','public')

    def test_lld_missing_duplicate_or_prefix_symbol_rejected(self):
        for text in ('100 100 20 4 owner.a(member.o):(.text.public)\n100 100 20 1 public_extra\n',
                     '100 100 20 4 owner.a(member.o):(.text.public)\n100 100 20 1 public\n104 104 20 1 public\n'):
            with self.assertRaises(AssertionError):C.lld_symbol_origin(text,'public')

    def test_lld_malformed_intervening_origin_rejected(self):
        with self.assertRaises(AssertionError):C.lld_symbol_origin('100 100 20 4 owner.a(member.o):(.text.public)\nBAD_ROW other.o:(.text.public)\n100 100 20 1 public\n','public')

    def test_lld_out_of_range_symbol_rejected(self):
        with self.assertRaises(AssertionError):C.lld_symbol_origin('100 100 20 4 owner.a(member.o):(.text.public)\n120 120 20 1 public\n','public')

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
            command=str(driver)+' --target=x86_64-none-linux-android26 --sysroot='+str(sysroot)+' -shared -o image.so'
            self.assertEqual(C.ndk_driver_binding(command,cache,before)['target'],'x86_64-none-linux-android26')
            for bad in (command.replace('android26','android27'),command.replace(str(sysroot),'/other/sysroot'),command.replace(str(driver),'/other/clang++')):
                with self.assertRaises(AssertionError):C.ndk_driver_binding(bad,cache,before)
            for override in (' -target arm64-linux-android26',' --target arm64-linux-android26',' --sysroot /other',' -isysroot /other',' -target=arm64-linux-android26',' -isysroot=/other',' -Xclang -triple'):
                with self.assertRaises(AssertionError):C.ndk_driver_binding(command+override,cache,before)
            with self.assertRaises(AssertionError):C.ndk_driver_binding(command,cache.replace(str(driver),'/other/clang++'),before)
            driver.write_bytes(b'changed driver')
            with self.assertRaises(AssertionError):C.ndk_driver_binding(command,cache,before)

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
