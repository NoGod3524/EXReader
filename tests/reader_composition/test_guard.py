# SPDX-License-Identifier: MIT
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'guard', Path(__file__).resolve().parents[2] / 'tools/reader_composition/guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class AdmissionTests(unittest.TestCase):
    def test_exact_adoption(self):
        self.assertEqual([], guard.differences({'a': 'old'}, {'a': 'new'}, [('one', {'a': 'new'})]))

    def test_content_or_mode_tamper(self):
        for value in ('100644 blob bad', '100755 blob good'):
            with self.subTest(value=value):
                self.assertTrue(guard.differences({}, {'a': value}, [('one', {'a': '100644 blob good'})]))

    def test_deleted_and_added_unowned_files(self):
        self.assertEqual(2, len(guard.differences({'old': 'x'}, {'new': 'y'}, [])))

    def test_ownership_overlap(self):
        self.assertTrue(guard.differences({}, {'a': 'x'}, [('one', {'a': 'x'}), ('two', {'a': 'x'})]))

    def test_missing_input_cannot_match_missing_output(self):
        self.assertTrue(guard.differences({}, {}, [('one', {'a': None})]))

    def test_root_path_cannot_be_claimed_by_input(self):
        path = guard.MANIFEST
        self.assertTrue(guard.differences({}, {path: 'x'}, [('one', {path: 'x'})]))


if __name__ == '__main__':
    unittest.main()
