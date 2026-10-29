#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only finite output, bounded accessor correction and old-logic controls."""
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

    def test_initial_save_and_separate_failed_detail_are_finite_not_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            path.write_text('EXR_PRIVACY_UI_SAVE elapsed_ms=5 status=remember-update-incomplete\n' + line() +
                            'EXR_PRIVACY_UI_DETAIL elapsed_ms=11 phase=remembered missing_credential=1\n')
            report = parse_ui_observations(path)
            self.assertEqual(report['initial_save'], [{'elapsed_ms': 5, 'status': 'remember-update-incomplete'}])
            self.assertTrue(report['failed_details'][0]['missing_credential_text_exists'])
            self.assertFalse(report['privacy_acceptance'])
            path.write_text(line())
            report = parse_ui_observations(path)
            self.assertEqual(report['initial_save'], [])
            self.assertEqual(report['failed_details'], [])

    def test_separate_detail_operands_spoofed_order_and_duplicates_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            save = 'EXR_PRIVACY_UI_SAVE elapsed_ms=5 status=saved\n'
            detail = 'EXR_PRIVACY_UI_DETAIL elapsed_ms=11 phase=remembered missing_credential=1\n'
            invalid = [save + save, detail, line(label='running') + detail, line() + detail + detail,
                       line() + detail.replace('elapsed_ms=11', 'elapsed_ms=9'), line() + save,
                       save.replace('elapsed_ms=5', 'elapsed_ms=500') + line(),
                       line() + detail.replace('elapsed_ms=11', 'elapsed_ms=100') + line(2, 20),
                       line(label='running', value='failed') + detail]
            for raw in list(needles({'secret': b'Privacy-' + b'f' * 64 + b'!%:+'}).values()) + [b'Privacy-fff...']:
                operand = raw.decode('utf-8', errors='replace')
                invalid.extend([save.replace('status=saved', 'status=' + operand),
                                line() + detail.replace('missing_credential=1', 'missing_credential=' + operand)])
            for value in invalid:
                path.write_text(value)
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
        # Exactly one evidence-justified accessor change; no assertion, expected
        # state, UI action, restart, key, wait or global budget is removed.
        accessor = 'if id == "account.sync.state" { return observedSyncState(item) }'
        self.assertEqual(stripped.count(accessor), 1)
        stripped = stripped.replace(accessor, 'if id == "account.sync.state" { return item.label }', 1)
        for call in ('        observeInitialSaveStatus()\n', '        assertStateAccessorControls()\n'):
            self.assertEqual(stripped.count(call), 1)
            stripped = stripped.replace(call, '', 1)
        self.assertTrue(stripped.encode() == original, 'native logic outside bounded accessor/observations changed')
        self.assertIn('if !label.isEmpty { return label }', current)
        self.assertIn('guard allowMacValue, let value = value as? String else { return "" }', current)
        self.assertIn('return states.contains(value) ? value : ""', current)
        self.assertIn('value: item.value, allowMacValue: false)', current)
        self.assertIn('XCTAssertEqual(exactSyncState(label: "正在同步", value: "本轮扫描完成", allowMacValue: true), "正在同步")', current)
        self.assertIn('XCTAssertEqual(exactSyncState(label: "同步失败", value: "本轮扫描完成", allowMacValue: true), "同步失败")', current)


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise RuntimeError('Actions only')
    unittest.main()
