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
        self.assertEqual(len(set((*C.OWNERS,*C.ADDED))),24)
        self.assertTrue(all(p.startswith('apps/reader/') for p in C.OWNERS))
        self.assertEqual(len(C.NEW_OWNER),3)

    def test_no_sdk_or_old_tests_in_scope(self):
        for p in (*C.OWNERS,*C.ADDED):
            self.assertFalse(p.startswith(('src/','include/','cmake/','tests/reader_selector_bytes/','tests/reader_f06_packages/')))

    def test_old_private_call_absent(self):
        for p in ('apps/reader/reading-commands/src/reading_commands.cpp','apps/reader/reading-state/src/reading_state.cpp'):
            self.assertNotIn('reader_rs_encode_retained_raw_v3',(C.ROOT/p).read_text())

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

    def test_no_full_f07_scope_claim(self):
        source=(Path(__file__).with_name('run.py')).read_text()
        self.assertIn('final_whole_image_f07_audit=False',source)
        self.assertIn('full_six_f07_accepted=False',source)


if __name__=='__main__':
    C.actions();unittest.main()
