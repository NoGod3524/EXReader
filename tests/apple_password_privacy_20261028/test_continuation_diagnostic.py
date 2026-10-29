#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only boundary controls for pinned continuation failure diagnosis."""
import os
from pathlib import Path
import tempfile
import unittest
from inspect_continuation_failure import SOURCE_PATH, locations, safe_progress
from privacy_scan import needles


class ContinuationDiagnosticControls(unittest.TestCase):
    def test_all_encoded_and_truncated_operands_removed(self):
        expected = [{'file': 'PasswordPrivacyContinuationUITests.swift', 'line': 104,
                     'assertion': 'XCTAssertNil', 'static_messages': [], 'static_controls': [], 'fixed_signatures': []}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            for value in list(needles({'secret': b'Privacy-' + b'b' * 64 + b'!%:+'}).values()) + [b'Privacy-bbb...']:
                path.write_bytes(SOURCE_PATH.encode() + b':104: error: XCTAssertNil failed (' + value + b')\n')
                self.assertEqual(locations(path), expected)

    def test_fixed_timeout_signature_does_not_print_arbitrary_description(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            path.write_text(SOURCE_PATH + ':104: error: XCTAssertNil failed - NSURLErrorDomain Code=-1001 '
                            'Loopback observation failed private url and arbitrary operand\n')
            self.assertEqual(locations(path), [{'file': 'PasswordPrivacyContinuationUITests.swift', 'line': 104,
                'assertion': 'XCTAssertNil', 'static_messages': ['Loopback observation failed'],
                'static_controls': [], 'fixed_signatures': ['url-request-timeout']}])

    def test_spoofed_or_unbounded_locations_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            for value in ('operand=' + SOURCE_PATH + ':104: error: XCTAssertNil',
                          SOURCE_PATH + ':161: error: XCTAssertNil', SOURCE_PATH + ':999999999: error: XCTAssertNil',
                          SOURCE_PATH + ':0: error: XCTAssertNil', 'unlocated arbitrary test failure'):
                path.write_text(value + '\n'); self.assertEqual(locations(path), [])

    def test_progress_keeps_strict_failure_and_rejects_arbitrary_fields(self):
        value = {'accepted': False, 'diagnostic_only': True, 'full_f10_accepted': False, 'sequence_complete': False,
                 'strict_privacy_checks': {'remember_closed': False}, 'checkpoints': {},
                 'commands': [{'role': 'native', 'exit': 65}], 'failure': 'RuntimeError'}
        self.assertFalse(safe_progress(value, set())['strict_privacy_checks']['remember_closed'])
        for field, replacement in [('accepted', True), ('sequence_complete', True), ('failure', 'arbitrary private operand'),
                                   ('strict_privacy_checks', {'arbitrary operand': False}),
                                   ('strict_privacy_checks', {'remember_closed': 0}),
                                   ('commands', [{'role': 'native', 'exit': 999999999}]),
                                   ('commands', [{'role': 'arbitrary operand', 'exit': 1}])]:
            with self.assertRaises(RuntimeError): safe_progress(dict(value, **{field: replacement}), set())


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise RuntimeError('Actions only')
    unittest.main()
