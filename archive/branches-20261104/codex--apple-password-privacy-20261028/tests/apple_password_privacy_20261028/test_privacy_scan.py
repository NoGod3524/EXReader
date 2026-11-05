# SPDX-License-Identifier: MIT
"""Actions-only tests of the oracle; these never count as product acceptance."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import privacy_scan as scanner
import archive_contract


class PrivacyScanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='privacy-oracle-')
        self.root = Path(self.temporary.name)
        self.token = b'Actions-only-privacy-canary-83b21df0!%:+'
        self.variants = scanner.needles({'password': self.token})

    def tearDown(self):
        self.temporary.cleanup()

    def test_every_encoded_variant_across_chunk_boundary(self):
        for label, value in self.variants.items():
            with self.subTest(label=label):
                path = self.root / 'bytes.bin'
                path.write_bytes(b'x' * 30 + value + b'y' * 70)
                proof = scanner.scan_file(path, self.variants, 31)
                self.assertIn(label, proof['hits'])
                self.assertEqual(proof['bytes'], path.stat().st_size)

    def test_more_than_64mib_is_read_and_late_boundary_hit_detected(self):
        path = self.root / 'large.bin'
        offset = 65 * 1024 * 1024 - 7
        with path.open('wb') as file:
            file.seek(offset); file.write(self.token + b'end')
        proof = scanner.scan_tree(self.root, self.variants)
        self.assertFalse(proof['accepted'])
        self.assertEqual(proof['size_skips'], 0)
        self.assertEqual(proof['bytes'], offset + len(self.token) + 3)
        self.assertGreater(proof['files'][0]['chunks'], 64)
        self.assertIn('password:raw', proof['files'][0]['hits'])

    def test_clean_large_file_has_no_size_skip(self):
        path = self.root / 'clean.bin'
        with path.open('wb') as file:
            file.truncate(65 * 1024 * 1024 + 19)
        proof = scanner.scan_tree(self.root, self.variants)
        self.assertTrue(proof['accepted'])
        self.assertEqual(proof['bytes'], path.stat().st_size)
        self.assertEqual(proof['size_skips'], 0)

    def test_linked_file_and_directory_refused(self):
        outside = self.root.parent / (self.root.name + '-outside')
        outside.mkdir()
        try:
            (outside / 'target').write_bytes(b'not private')
            link = self.root / 'link'
            link.symlink_to(outside / 'target')
            with self.assertRaises(RuntimeError): scanner.scan_tree(self.root, self.variants)
            link.unlink(); link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RuntimeError): scanner.scan_tree(self.root, self.variants)
        finally:
            (outside / 'target').unlink(); outside.rmdir()

    def test_file_mutation_is_not_silently_accepted(self):
        path = self.root / 'changing'
        path.write_bytes(b'x' * 128)
        read, changed = scanner.os.read, [False]
        def mutate(fd, count):
            data = read(fd, count)
            if data and not changed[0]:
                changed[0] = True
                with path.open('ab') as file: file.write(b'z')
            return data
        with patch.object(scanner.os, 'read', mutate):
            with self.assertRaises(RuntimeError): scanner.scan_file(path, self.variants, 31)

    def test_empty_tree_and_unreadable_file_not_accepted(self):
        with self.assertRaises(RuntimeError): scanner.scan_tree(self.root, self.variants)
        path = self.root / 'private'; path.write_bytes(b'x')
        with patch.object(scanner.os, 'open', side_effect=PermissionError('private')):
            with self.assertRaises(PermissionError): scanner.scan_tree(self.root, self.variants)

    def test_earlier_file_changed_during_later_file_read_is_rejected(self):
        first, second = self.root / 'a', self.root / 'b'
        first.write_bytes(b'x' * 128); second.write_bytes(b'y' * 128)
        original = scanner.scan_file
        def mutate(path, variants, chunk_size):
            result = original(path, variants, chunk_size)
            if path == second:
                with first.open('ab') as file: file.write(self.token)
            return result
        with patch.object(scanner, 'scan_file', mutate):
            with self.assertRaises(RuntimeError): scanner.scan_tree(self.root, self.variants)

    def test_already_scanned_prefix_overwritten_without_growth_is_rejected(self):
        path = self.root / 'changing'
        path.write_bytes(b'x' * 4096)
        read, count = scanner.os.read, [0]
        def mutate(fd, size):
            data = read(fd, size)
            count[0] += 1
            if count[0] == 3:
                with path.open('r+b') as file:
                    file.write(self.token)
                # Deterministic metadata change even on coarse timestamp filesystems.
                os.utime(path, ns=(1, 1))
            return data
        with patch.object(scanner.os, 'read', mutate):
            with self.assertRaises(RuntimeError): scanner.scan_file(path, self.variants, 128)

    def test_earlier_root_mutated_during_later_root_scan_is_rejected(self):
        first, second = self.root / 'a', self.root / 'b'
        first.mkdir(); second.mkdir()
        (first / 'one').write_bytes(b'x'); (second / 'two').write_bytes(b'y')
        original = scanner.scan_tree
        def mutate(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == second:
                (first / 'one').write_bytes(self.token)
            return result
        with patch.object(scanner, 'scan_tree', mutate):
            with self.assertRaises(RuntimeError): scanner.scan_roots({'first': first, 'second': second}, self.variants)

    def test_file_added_in_already_scanned_directory_prefix_is_rejected(self):
        first, second = self.root / 'a', self.root / 'b'
        first.mkdir(); second.mkdir()
        (first / 'one').write_bytes(b'x'); (second / 'two').write_bytes(b'y')
        original = scanner.scan_file
        def mutate(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == second / 'two': (first / 'late').write_bytes(self.token)
            return result
        with patch.object(scanner, 'scan_file', mutate):
            with self.assertRaises(RuntimeError): scanner.scan_tree(self.root, self.variants)

    def test_reports_never_contain_canary_bytes(self):
        (self.root / 'sample').write_bytes(base64.b64encode(self.token))
        report = json.dumps(scanner.scan_tree(self.root, self.variants)).encode()
        self.assertNotIn(self.token, report)
        self.assertNotIn(base64.b64encode(self.token), report)

    def test_filename_canary_is_found_but_not_echoed(self):
        (self.root / self.token.decode()).write_bytes(b'clean contents')
        proof = scanner.scan_tree(self.root, self.variants)
        self.assertFalse(proof['accepted'])
        self.assertIn('password:raw', proof['files'][0]['path_hits'])
        self.assertEqual(proof['files'][0]['path'], '<canary-in-path>')
        self.assertNotIn(self.token, json.dumps(proof).encode())

    def test_empty_directory_name_canary_is_found_but_not_echoed(self):
        (self.root / 'ordinary').write_bytes(b'clean contents')
        (self.root / self.token.decode()).mkdir()
        proof = scanner.scan_tree(self.root, self.variants)
        self.assertFalse(proof['accepted'])
        self.assertIn('password:raw', proof['directories'][0]['path_hits'])
        self.assertNotIn(self.token, json.dumps(proof).encode())

    def test_late_creation_of_absent_optional_root_is_rejected(self):
        paths = {'preferences': self.root / 'absent'}
        before = scanner.optional_entries(paths)
        self.assertEqual(before, {'preferences': None})
        paths['preferences'].write_bytes(self.token)
        with self.assertRaises(RuntimeError): scanner.verify_optional_entries(paths, before)

    def test_dangling_optional_root_is_not_classified_as_absent(self):
        path = self.root / 'dangling'
        path.symlink_to(self.root / 'nonexistent')
        with self.assertRaises(RuntimeError): scanner.optional_entries({'preferences': path})

    def test_archive_case_unicode_parent_aliases_and_file_directory_collisions_refuse(self):
        collisions = [('File', 'file'), ('Parent/a', 'parent/b'), ('caf\u00e9/a', 'cafe\u0301/b'),
                      ('parent/child', 'parent'), ('parent', 'parent/child'), ('Name/', 'name/child'),
                      ('root//', 'root/'), ('.', 'ordinary')]
        for index, names in enumerate(collisions):
            with self.subTest(names=names):
                path, target = self.root / ('input-' + str(index) + '.zip'), self.root / ('target-' + str(index))
                with zipfile.ZipFile(path, 'w') as archive:
                    for name in names: archive.writestr(name, b'' if name.endswith('/') else b'payload')
                with self.assertRaises(RuntimeError): archive_contract.safe_extract(path, target)
                self.assertFalse(target.exists(), 'invalid archive wrote bytes before rejection')

    def test_archive_ordinary_explicit_and_implicit_directories_are_preserved(self):
        path, target = self.root / 'ordinary.zip', self.root / 'target'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('root/empty/', b'')
            archive.writestr('root/other/file', b'payload')
            archive.writestr('root/', b'')
        archive_contract.safe_extract(path, target)
        self.assertTrue((target / 'root/empty').is_dir())
        self.assertEqual((target / 'root/other/file').read_bytes(), b'payload')

    def test_archive_resource_bounds_refuse_instead_of_skipping(self):
        path, target = self.root / 'bounded.zip', self.root / 'target'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('one', b'abcdef'); archive.writestr('two', b'ghijkl')
        with patch.object(archive_contract, 'MAX_MEMBER_BYTES', 5):
            with self.assertRaises(RuntimeError): archive_contract.safe_extract(path, target)
        with patch.object(archive_contract, 'MAX_TOTAL_BYTES', 10):
            with self.assertRaises(RuntimeError): archive_contract.safe_extract(path, target)
        self.assertFalse(target.exists())


if __name__ == '__main__':
    scanner.require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only: no local fixtures or tests')
    unittest.main()
