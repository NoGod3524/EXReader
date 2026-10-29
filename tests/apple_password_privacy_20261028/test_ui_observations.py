#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only finite output and unchanged native assertion/budget controls."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from contract import ROOT
from privacy_scan import needles
from ui_observations import parse_ui_observations

SOURCE = '0533fadf8d5cc41959a7ae81ef1dbd294c7d096e'
SWIFT = 'tests/apple_password_privacy_20261028/continuation_ui/PasswordPrivacyContinuationUITests.swift'
FROZEN_SHA = '01f9eeeafa9a5f1102d933cea31d51f55179af8053a4949f84b4f13c40a56b8f'


def line(sequence=1, elapsed=10, label='failed', value='other', missing=1):
    return ('EXR_PRIVACY_UI_STATE seq=' + str(sequence) + ' elapsed_ms=' + str(elapsed) +
            ' phase=remembered snapshot=1 label=' + label + ' value=' + value +
            ' value_kind=string missing_label=0 missing_value=' + str(missing) + '\n')


class UIObservationControls(unittest.TestCase):
    def test_finite_actual_state_and_missing_indicator(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'; path.write_text(line() + line(8, 5100))
            report = parse_ui_observations(path)
            self.assertTrue(report['observed']); self.assertFalse(report['privacy_acceptance'])
            self.assertEqual(report['records'][0]['label_code'], 'failed')
            self.assertTrue(report['records'][0]['value_missing_credential'])
            self.assertFalse(report['raw_ui_text_printed'])

    def test_encoded_truncated_and_unknown_operands_refused_without_echo(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            for raw in list(needles({'secret': b'Privacy-' + b'd' * 64 + b'!%:+'}).values()) + [b'Privacy-ddd...']:
                path.write_bytes(line(label=raw.decode('utf-8', errors='replace')).encode())
                with self.assertRaisesRegex(RuntimeError, '^invalid finite UI observation record$'):
                    parse_ui_observations(path)

    def test_absence_and_out_of_order_or_unbounded_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'; path.write_text('unrelated private native activity\n')
            self.assertFalse(parse_ui_observations(path)['observed'])
            for text in (line(1, 10) + line(1, 11), line(2, 10) + line(3, 9), line(100001), line(1, 4800001)):
                path.write_text(text)
                with self.assertRaises(RuntimeError): parse_ui_observations(path)

    def test_native_assertions_keys_sequence_and_timeouts_byte_preserved(self):
        original = subprocess.check_output(['git', 'show', SOURCE + ':' + SWIFT], cwd=ROOT)
        self.assertEqual(hashlib.sha256(original).hexdigest(), FROZEN_SHA)
        current = (ROOT / SWIFT).read_text()
        stripped, count = re.subn(r'    // DIAGNOSTIC_UI_BEGIN\n.*?    // DIAGNOSTIC_UI_END\n', '', current, flags=re.S)
        self.assertEqual(count, 1)
        anchor = 'guard let item = observedSnapshot(id) else { return "" }'
        self.assertEqual(stripped.count(anchor), 1)
        stripped = stripped.replace(anchor, 'guard let item = try? node(id).snapshot() else { return "" }', 1)
        self.assertTrue(stripped.encode() == original, 'native logic outside observation wrapper changed')


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise RuntimeError('Actions only')
    unittest.main()
