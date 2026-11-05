#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only controls: no arbitrary/encoded/truncated input can be printed."""
import os
from pathlib import Path
import tempfile
import unittest
from inspect_native import SOURCE_PATH, log_locations, variant_labels
from privacy_scan import needles


class DiagnosticControls(unittest.TestCase):
    def test_variant_labels_only_not_operands(self):
        proof = {'files': [{'hits': ['user:raw', 'remembered:json', 'user:raw'], 'path_hits': []}], 'directories': []}
        self.assertEqual(variant_labels(proof), ['remembered:json', 'user:raw'])
        for value in ('user:raw arbitrary operand', 'Privacy-aaaa...', 'unknown:raw', 1):
            proof['files'][0]['hits'] = [value]
            with self.assertRaises(RuntimeError): variant_labels(proof)

    def test_all_encoded_operands_removed(self):
        secret = b'Privacy-' + b'a' * 64 + b'!%:+'
        expected = [{'file': 'PasswordPrivacyUITests.swift', 'line': 103, 'assertion': 'XCTAssertEqual',
                     'static_messages': [], 'static_controls': []}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            for value in needles({'secret': secret}).values():
                path.write_bytes(SOURCE_PATH.encode() + b':103: error: XCTAssertEqual failed (' + value + b')\n')
                self.assertEqual(log_locations(path), expected)

    def test_partial_operands_removed_and_static_source_tokens_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            path.write_text(SOURCE_PATH + ':42: error: XCTAssertTrue failed - '
                            'Unavailable control: account.remember operand=Privacy-aaaa...\n')
            self.assertEqual(log_locations(path), [{'file': 'PasswordPrivacyUITests.swift', 'line': 42,
                'assertion': 'XCTAssertTrue', 'static_messages': ['Unavailable control:'],
                'static_controls': ['account.remember']}])

    def test_unlocated_arbitrary_output_is_not_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            path.write_text('Type private arbitrary input into field\nerror: framework arbitrary message\n')
            self.assertEqual(log_locations(path), [])

    def test_spoofed_embedded_or_out_of_range_locations_are_not_printed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            for content in ('operand=' + SOURCE_PATH + ':42: error: XCTAssertTrue failed',
                            SOURCE_PATH + ':12345678901234567890: error: XCTAssertTrue failed',
                            SOURCE_PATH + ':999: error: XCTAssertTrue failed',
                            SOURCE_PATH + ':0: error: XCTAssertTrue failed',
                            'PasswordPrivacyUITests.swift:42: error: XCTAssertTrue failed'):
                path.write_text(content + '\n')
                self.assertEqual(log_locations(path), [])


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise RuntimeError('Actions only')
    unittest.main()
