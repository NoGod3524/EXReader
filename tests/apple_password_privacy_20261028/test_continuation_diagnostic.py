#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only boundary controls for pinned continuation failure diagnosis."""
import os
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from contract import ROOT, sha
import inspect_continuation_failure as inspector
from inspect_continuation_failure import ARTIFACTS, BUNDLE, CASE, DIAGNOSTIC_STAGES, REFUSAL_CODES, RUN, SOURCE, SOURCE_FILE, SOURCE_LAST_LINE, SOURCE_PATH, SOURCE_SHA, activity_timing, attachment_summary, diagnostic_stage, locations, network_summary, refusal_report, safe_progress, xcresult_issues
from privacy_scan import needles


class ContinuationDiagnosticControls(unittest.TestCase):
    def test_refusal_codes_require_exact_owned_message_and_keep_false_verdict(self):
        for message, code in REFUSAL_CODES.items():
            report = refusal_report(RuntimeError(message), 'archive-extract')
            self.assertEqual(report['refusal_code'], code)
            self.assertEqual(report['exception_class'], 'runtime')
            self.assertTrue(report['diagnostic_refused'])
            self.assertFalse(report['accepted']); self.assertFalse(report['full_f10_accepted'])
            self.assertFalse(report['arbitrary_error_details_printed'])
            for value in ('operand ' + message, message + ' private-operand'):
                self.assertEqual(refusal_report(RuntimeError(value), 'archive-extract')['refusal_code'], 'unclassified')
        self.assertEqual(refusal_report(RuntimeError('prior continuation member differs', 'private-operand'),
            'member-bytes')['refusal_code'], 'unclassified')

    def test_refusal_never_formats_encoded_truncated_exception_operands(self):
        class OperandError(RuntimeError):
            def __str__(self):
                raise AssertionError('exception text must never be formatted')
        for raw in list(needles({'secret': b'Privacy-' + b'a' * 64 + b'!%:+'}).values()) + [b'Privacy-aaa...']:
            operand = raw.decode('utf-8', errors='replace')
            errors = [RuntimeError(operand), KeyError(operand), OSError(operand), OperandError(operand),
                subprocess.CalledProcessError(1, [operand], output=raw, stderr=raw),
                subprocess.TimeoutExpired([operand], 120, output=raw, stderr=raw)]
            for error in errors:
                report = refusal_report(error, operand)
                self.assertEqual(report['stage'], 'unknown')
                self.assertEqual(report['refusal_code'], 'unclassified')
                self.assertNotIn(operand, json.dumps(report, ensure_ascii=False))
                self.assertNotIn('OperandError', str(report))
        self.assertEqual(refusal_report(OperandError('prior continuation member differs'), 'member-bytes')
            ['exception_class'], 'other')

    def test_stage_transition_is_finite_and_invalid_value_does_not_replace_it(self):
        try:
            for stage in DIAGNOSTIC_STAGES:
                diagnostic_stage(stage)
                self.assertEqual(inspector.CURRENT_DIAGNOSTIC_STAGE, stage)
            for stage in ('archive-extract private-operand', 'unknown', ''):
                with self.assertRaisesRegex(RuntimeError, '^invalid diagnostic stage$'):
                    diagnostic_stage(stage)
                self.assertEqual(inspector.CURRENT_DIAGNOSTIC_STAGE, 'safe-report')
        finally:
            diagnostic_stage('entry')

    def test_current_macos_artifact_and_source_extent_are_exact(self):
        self.assertEqual(RUN, '40813760224')
        self.assertEqual(SOURCE, 'a16304c989aa9c1b94ce6e9bb6644a075b3e326b')
        self.assertEqual(ARTIFACTS, {'macos': (12871319916, 169232203,
            '19cc7e4b40b3ba01a6c10bf0c143bc911e2772927d6e9742a1d973dbc5e7f3c9')})
        self.assertEqual(sha(ROOT / SOURCE_FILE), SOURCE_SHA)
        self.assertEqual(SOURCE_LAST_LINE, 267)
        self.assertEqual(len((ROOT / SOURCE_FILE).read_text().splitlines()), SOURCE_LAST_LINE)

    def test_current_source_last_line_is_bounded_in_both_extractors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            for number in (SOURCE_LAST_LINE, SOURCE_LAST_LINE + 1):
                path.write_text(SOURCE_PATH + ':' + str(number) + ': error: XCTAssertTrue failed private-operand\n')
                rows = locations(path)
                self.assertEqual([row['line'] for row in rows], [number] if number == SOURCE_LAST_LINE else [])
                url = 'file://' + SOURCE_PATH + '#StartingLineNumber=' + str(number)
                issue = {'_type': {'_name': 'TestFailureIssueSummary'},
                    'message': {'_value': 'XCTAssertTrue failed private-operand'},
                    'testCaseName': {'_value': CASE},
                    'documentLocationInCreatingWorkspace': {'url': {'_value': url}}}
                report = xcresult_issues([issue])
                self.assertEqual(report['issues'][0]['source_line'], number if number == SOURCE_LAST_LINE else None)
                self.assertNotIn('private-operand', str(rows) + str(report))

    def test_attachment_tokens_cross_chunk_without_raw_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'text.txt').write_bytes(b'x' * (1024 * 1024 - 3) + '同步失败 private-operand'.encode())
            (root / 'manifest.json').write_text(json.dumps([{'testIdentifier': CASE, 'attachments': [
                {'exportedFileName': 'text.txt', 'suggestedHumanReadableName': 'arbitrary-private-name'}]}]))
            report = attachment_summary(root)
            self.assertEqual(report['attachments'][0]['status_token_presence'], ['failed'])
            self.assertEqual(report['attachments'][0]['kind'], 'other')
            self.assertNotIn('private', str(report))
            self.assertFalse(report['token_presence_is_actual_ui_state_proof'])
            self.assertEqual(report['type_counts']['.txt'], 1)
            self.assertFalse(report['text_status_tokens_absent'])
            (root / 'manifest.json').write_text('[]')
            empty = attachment_summary(root)
            self.assertEqual(empty['text_attachment_count'], 0)
            self.assertIsNone(empty['text_status_tokens_absent'])

    def test_attachment_traversal_and_foreign_case_refuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for case, filename in ((CASE, '../private-operand'), ('testForeignCase', 'text.txt')):
                (root / 'manifest.json').write_text(json.dumps([{'testIdentifier': case, 'attachments': [
                    {'exportedFileName': filename, 'suggestedHumanReadableName': 'unknown'}]}]))
                with self.assertRaises(RuntimeError): attachment_summary(root)

    def test_activity_timing_only_known_markers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            path.write_text('    t =    12.00s Launch ' + BUNDLE + '\n'
                            '    t =    25.50s Terminate ' + BUNDLE + '\n'
                            '    t =    70.00s Launch ' + BUNDLE + '\n'
                            '    t =    72.00s Tap "同步" Button\n'
                            '    t =    73.00s Find the "account.sync.state" StaticText\n'
                            '    t =    74.00s arbitrary private operand\n')
            report = activity_timing(path)
            self.assertEqual(report['markers'], [{'seconds': 12.0, 'marker': 'launch'},
                {'seconds': 25.5, 'marker': 'terminate'}, {'seconds': 70.0, 'marker': 'launch'},
                {'seconds': 72.0, 'marker': 'tap-sync'}])
            self.assertEqual(report['state_query_count'], 1)
            self.assertNotIn('private', str(report))

    def test_activity_operand_and_unbounded_time_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.log'
            for content in ('operand t = 12.00s Launch ' + BUNDLE, 't = 9999.00s Launch ' + BUNDLE,
                            't = 12.00s Launch ' + BUNDLE + ' private-operand',
                            't = 12.00s Tap "Privacy-aaaa..." Button'):
                path.write_text(content + '\n'); self.assertEqual(activity_timing(path)['markers'], [])

    def test_network_roles_and_shards_only(self):
        root = 'https://127.0.0.1:12345/privacy-' + 'a' * 24 + '/'
        result = {'root': root, 'checkpoints': {'remember_closed': {'network_requests': 0}}}
        prefix = '/privacy-' + 'a' * 24 + '/exreader-sync-v1/revisions/'
        rows = [{'credential': 'remembered', 'method': 'PROPFIND', 'path': prefix + format(i, '02x') + '/'} for i in range(256)]
        report = network_summary(result, rows)
        self.assertEqual(report['distinct_revision_shards_after_first']['remembered'], 256)
        self.assertEqual(report['credential_method_counts_after_first']['remembered']['PROPFIND'], 256)
        self.assertNotIn('a' * 24, str(report))
        for change in ({'credential': 'arbitrary private operand'}, {'method': 'arbitrary private operand'},
                       {'path': '/foreign/private-operand'}):
            with self.assertRaises(RuntimeError): network_summary(result, [dict(rows[0], **change)])

    def test_xcresult_encoded_operands_removed_and_position_bound(self):
        def issue(message, url):
            return {'_type': {'_name': 'TestFailureIssueSummary'}, 'message': {'_value': message},
                    'testCaseName': {'_value': 'PasswordPrivacyContinuationUITests.' + CASE + '()'},
                    'documentLocationInCreatingWorkspace': {'url': {'_value': url}}}
        good = 'file://' + SOURCE_PATH + '#EndingLineNumber=95&StartingLineNumber=95'
        for raw in list(needles({'secret': b'Privacy-' + b'c' * 64 + b'!%:+'}).values()) + [b'Privacy-ccc...']:
            report = xcresult_issues({'issues': [issue('XCTAssertTrue failed operand=' + raw.decode('utf-8', errors='replace'), good)]})
            self.assertEqual(report['issues'], [{'case_matches': True, 'source_line': 95, 'assertion': 'XCTAssertTrue',
                'static_messages': [], 'static_controls': [], 'fixed_signatures': [], 'known_time_allowance': []}])
        for url in ('operand=' + good, 'file://' + SOURCE_PATH + '#StartingLineNumber=99999',
                    good + '&StartingLineNumber=94', good + '&operand=private'):
            self.assertIsNone(xcresult_issues([issue('XCTAssertTrue failed', url)])['issues'][0]['source_line'])
        self.assertEqual(xcresult_issues({'message': {'_value': 'arbitrary private operand'}})['failure_issue_count'], 0)
        self.assertEqual(xcresult_issues([issue('Test exceeded execution time allowance of 240 seconds private operand', good)])
                         ['issues'][0]['known_time_allowance'], [240])
        self.assertEqual(xcresult_issues([issue('Test exceeded execution time allowance of 999999 seconds', good)])
                         ['issues'][0]['known_time_allowance'], [])

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
                          SOURCE_PATH + ':' + str(SOURCE_LAST_LINE + 1) + ': error: XCTAssertNil', SOURCE_PATH + ':999999999: error: XCTAssertNil',
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
