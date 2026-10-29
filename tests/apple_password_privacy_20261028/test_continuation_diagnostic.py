#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only boundary controls for pinned continuation failure diagnosis."""
import os
import json
import copy
import base64
import hashlib
from pathlib import Path
import tempfile
import subprocess
import struct
import unittest
import plistlib
import zipfile
from unittest.mock import patch
from contract import ROOT, sha
import inspect_continuation_failure as inspector
from inspect_continuation_failure import ARTIFACTS, BUNDLE, CASE, DIAGNOSTIC_STAGES, REFUSAL_CODES, RUN, SOURCE, SOURCE_FILE, SOURCE_LAST_LINE, SOURCE_PATH, SOURCE_SHA, activity_timing, attachment_summary, diagnostic_stage, locations, member_integrity, member_role, network_summary, refusal_report, safe_progress, sealed_lifecycle, xcresult_issues
from privacy_scan import needles
import authenticate_continuation as authenticator
import continuation_contract as current_contract
from continuation_contract import ENTITLEMENT_FILE, admission_app_identity, signature_summary, verify_admission_transition, appledouble_content
from continuation_lifecycle import seal_files


def diagnostic_control_macho(section):
    """Bounded protocol fixture, not executable/signature acceptance evidence."""
    size, offset = len(section), 208
    return (struct.pack('<IiiIIIII', 0xfeedfacf, 0x0100000c, 0, 2, 2, 176, 0, 0) +
        struct.pack('<IIIIII', 0x32, 24, 7, 0, 0, 0) +
        struct.pack('<II16sQQQQiiII', 0x19, 152, b'__TEXT', 0, offset + size, 0, offset + size, 5, 5, 1, 0) +
        struct.pack('<16s16sQQIIIIIIII', b'__entitlements', b'__TEXT', offset, size, offset, 0, 0, 0, 0, 0, 0, 0) + section)


def diagnostic_appledouble(attributes=None, resource=b''):
    """Actions-only synthetic wire-format fixture, not actual metadata proof."""
    finder = bytes(32)
    if attributes is not None:
        start = 120 + sum((12 + len(name) + 3) & ~3 for name, value in attributes)
        entries, payload = bytearray(), bytearray()
        for name, value in attributes:
            name = name + b'\x00'
            entry = struct.pack('>IIHB', start + len(payload), len(value), 0, len(name)) + name
            entries.extend(entry + bytes((-len(entry)) % 4)); payload.extend(value)
        total = start + len(payload)
        finder += bytes(2) + struct.pack('>8I2H', 0x41545452, 0, total, start, len(payload), 0, 0, 0, 0, len(attributes))
        finder += bytes(entries) + bytes(payload)
    return (struct.pack('>II16sH', 0x00051607, 0x00020000, b'Mac OS X        ', 2) +
            struct.pack('>6I', 9, 50, len(finder), 2, 50 + len(finder), len(resource)) + finder + resource)


def attachment_bundle(root, form='png'):
    """Actions-only original-parser fixture; not a real image/native proof."""
    directory = root / 'attachments'; directory.mkdir()
    profile = '12345678-1234-1234-1234-123456789abc'
    document = {'stages': list(inspector.STAGES), 'profile': profile, 'diagnostic_continuation': True,
                'operation': 'real Remember off and Update; not a dedicated Forget action'}
    (directory / 'metadata.json').write_text(json.dumps(document))
    entries = [{'exportedFileName': 'metadata.json', 'suggestedHumanReadableName': 'privacy-stages.json'}]
    for index, stage in enumerate(inspector.STAGES):
        name = 'privacy-' + stage + ('.png' if form == 'png' else '_opaque' if form == 'underscore' else '')
        filename = 'image' + str(index) + '.bin'; (directory / filename).write_bytes(b'\x89PNG\r\n\x1a\nfixture-not-real-image')
        entries.append({'exportedFileName': filename, 'suggestedHumanReadableName': name})
    (directory / 'manifest.json').write_text(json.dumps([{'testIdentifier': CASE, 'attachments': entries}]))
    result = {'commands': [{'role': 'attachments', 'exit': 0}],
        'checkpoints': {stage: {'profile_id': profile} for stage in inspector.STAGES},
        'files': {'attachments/' + name: item for name, item in seal_files(directory).items()}}
    return result


def candidate_bundle(root, name='privacy-stages_0_12345678-1234-1234-1234-123456789ABC.json'):
    result = attachment_bundle(root, 'underscore'); directory = root / 'attachments'
    groups = json.loads((directory / 'manifest.json').read_text())
    groups[0]['unknownMetadata'] = {'nested': [True, 1, 1.0, -0.0, {'keep': 'private-unknown-operand'}]}
    groups[0]['attachments'][0]['suggestedHumanReadableName'] = name
    (directory / 'manifest.json').write_text(json.dumps(groups))
    result['files'] = {'attachments/' + path: item for path, item in seal_files(directory).items()}
    return result


def run_candidate(root, result):
    report = {}
    inspector.replay_original_attachments(root, result, report)
    outcome = inspector.attachment_identity_trial(root, result, report)
    return outcome, report


def native_order_control(test, root, *, changed_member=False, sealed=True, bad_scan=False,
                         native_present=True, parser_failure=None, retained_bare_export=False,
                         retained_candidate_export=False, valid_later_evidence=False):
    """Actions-only synthetic archive through the REAL admission/native helper."""
    receipt = {'admission_closed': True, 'active_handlers': 0, 'admitted_handlers': 533,
        'rejected_handlers': 0, 'serving_stopped': True, 'drained': True, 'failed': False,
        'cleanup': {'certificate': 'completed', 'simulator-shutdown': 'not-required', 'simulator-erase': 'not-required'},
        'outer_limit_seconds': 4800, 'drain_limit_seconds': 90}
    members = {'native.log': (SOURCE_PATH + ':245: error: XCTAssertNil failed private-operand\n').encode(),
               'fixture-failures.json': b'["private-unknown-fixture-operand"]'}
    if native_present: members['privacy.xcresult/Info.plist'] = b'synthetic protocol fixture, not actual xcresult'
    if bad_scan: members['remember_closed-privacy-scan.json'] = b'{"private-unknown-root":{"accepted":false}}'
    if valid_later_evidence: members.update({'fixture-failures.json': b'[]', 'requests.json': b'[]'})
    fixture_result = None
    if retained_bare_export or retained_candidate_export:
        fixture = root / 'fixture-export'; fixture.mkdir()
        fixture_result = candidate_bundle(fixture) if retained_candidate_export else attachment_bundle(fixture, 'bare')
        for path in (fixture / 'attachments').iterdir(): members['attachments/' + path.name] = path.read_bytes()
    result = {'source_sha': SOURCE, 'run_id': RUN, 'attempt': '1', 'platform': 'macos',
        'accepted': False, 'diagnostic_only': True, 'full_f10_accepted': False, 'sequence_complete': False,
        'evidence_sealed': sealed, 'lifecycle': receipt, 'failure': 'RuntimeError',
        'commands': [{'role': 'native', 'exit': 65}],
        'strict_privacy_checks': dict.fromkeys(inspector.STAGES, False),
        'checkpoints': dict.fromkeys(inspector.STAGES, {}),
        'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in members.items()}}
    if retained_candidate_export: result['checkpoints'] = fixture_result['checkpoints']
    if valid_later_evidence:
        result['root'] = 'https://127.0.0.1:443/privacy-' + 'a' * 24 + '/'
        for checkpoint in result['checkpoints'].values(): checkpoint['network_requests'] = 0
    archive = root / 'control.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        for name, data in members.items():
            zipped.writestr(name, data + b'changed' if changed_member and name == 'native.log' else data)
        zipped.writestr('result.json', json.dumps(result))
    payload = archive.read_bytes(); digest = hashlib.sha256(payload).hexdigest()
    metadata = {'id': 123, 'name': 'password-continuation-native-macos-' + RUN + '-1',
        'workflow_run': {'id': int(RUN), 'head_sha': SOURCE}, 'size_in_bytes': len(payload),
        'digest': 'sha256:' + digest, 'expired': False}
    issue = {'_type': {'_name': 'TestFailureIssueSummary'},
        'message': {'_value': 'XCTAssertNil failed private-operand'}, 'testCaseName': {'_value': CASE},
        'documentLocationInCreatingWorkspace': {'url': {'_value': 'file://' + SOURCE_PATH + '#StartingLineNumber=245'}}}
    calls, stages = [], []
    original_run = subprocess.run
    real_stage = inspector.diagnostic_stage
    def stage(name): stages.append(name); real_stage(name)
    def command(argv, **kwargs):
        if argv[:2] == ['git', 'show']: return original_run(argv, **kwargs)
        if argv[:2] == ['gh', 'api']:
            test.assertTrue(argv[2].endswith('/actions/artifacts/123/zip'))
            kwargs['stdout'].write(payload)
            return subprocess.CompletedProcess(argv, 0)
        test.assertEqual(argv[:2], ['xcrun', 'xcresulttool'])
        test.assertTrue(kwargs['capture_output']); test.assertEqual(kwargs['timeout'], 120)
        calls.append(argv[2])
        if argv[2] == 'get':
            return subprocess.CompletedProcess(argv, 1 if parser_failure == 'exit' else 0,
                b'not-json private-operand' if parser_failure == 'json' else json.dumps([issue]).encode(), b'private-stderr-operand')
        test.assertEqual(argv[2:4], ['export', 'attachments'])
        exported = Path(argv[-1]); exported.mkdir(); (exported / 'manifest.json').write_text('[]')
        return subprocess.CompletedProcess(argv, 0, b'private-stdout-operand', b'private-stderr-operand')
    out = root / 'out'; out.mkdir()
    with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'NoGod3524/EXReader'}), \
            patch.object(inspector.subprocess, 'check_output', return_value=json.dumps(metadata).encode()), \
            patch.object(inspector.subprocess, 'run', side_effect=command), \
            patch.object(inspector, 'diagnostic_stage', side_effect=stage), \
            patch.object(inspector, 'CURRENT_SAFE_REPORT', None), patch.object(inspector, 'CURRENT_MEMBER_INTEGRITY', None), \
            patch.object(inspector, 'CURRENT_PLATFORM', None), \
            patch.object(inspector, 'inspect_native_result', wraps=inspector.inspect_native_result) as native:
        try: inspector.diagnose_platform(out, 'macos', 123, len(payload), digest)
        except Exception as error: refusal = inspector.current_refusal(error)
        else: test.fail('later refusal unexpectedly accepted')
        entered = native.call_count
    inspector.diagnostic_stage('entry')
    return refusal, calls, stages, entered


def current_result(platform='iphone'):
    stages = inspector.STAGES if platform == 'macos' else inspector.STAGES[:2]
    checkpoints = {stage: {'profile_id': '12345678-1234-1234-1234-123456789abc',
        'network_requests': 0, 'scans': {}, 'strict_privacy_passed': False, 'absent_mac_roots': [],
        'archive': stage + '-product.zip', 'archive_sha256': 'a' * 64,
        'sdk_original_sha256': 'b' * 64, 'original_bytes': 1} for stage in stages}
    commands = [{'role': role, 'exit': 0} for role in
        ('fixtures', 'project', 'build-for-testing', 'native', 'attachments', 'program-archive')]
    if platform != 'macos': commands = [{'role': 'native', 'exit': 65}, {'role': 'admission-installed-archive', 'exit': 0}]
    return {'source_sha': inspector.CURRENT_CASE_SOURCE, 'run_id': inspector.CURRENT_CASE_RUN,
        'attempt': '1', 'platform': platform, 'accepted': False, 'diagnostic_only': True,
        'full_f10_accepted': False, 'sequence_complete': platform == 'macos',
        'failure': None if platform == 'macos' else 'RuntimeError', 'commands': commands,
        'strict_privacy_checks': dict.fromkeys(stages, False), 'checkpoints': checkpoints,
        'root': 'https://127.0.0.1:443/privacy-' + 'a' * 24 + '/'}


def current_order_control(test, root, *, platform='iphone', changed_member=False,
                          sealed=True, bad_scan=False, wrong_api=False, wrong_identity=False,
                          mutate_after_native=None, admission_refusal=False):
    """REAL current entry, admission, finite UI replay and disposable native helper."""
    result = current_result(platform)
    receipt = {'admission_closed': True, 'active_handlers': 0, 'admitted_handlers': 533,
        'rejected_handlers': 0, 'serving_stopped': True, 'drained': True, 'failed': False,
        'cleanup': {'certificate': 'completed', 'simulator-shutdown': 'not-required' if platform == 'macos' else 'completed',
                    'simulator-erase': 'not-required' if platform == 'macos' else 'completed'},
        'outer_limit_seconds': 4800, 'drain_limit_seconds': 90}
    ui = ('EXR_PRIVACY_UI_SAVE elapsed_ms=10 status=saved\n'
        'EXR_PRIVACY_UI_STATE seq=1 elapsed_ms=20 phase=remembered snapshot=1 '
        'label=finished value=empty value_kind=none missing_label=0 missing_value=0\n')
    source_log = root / 'source-native.log'; source_log.write_text(ui)
    result['ui_state_observations'] = inspector.parse_ui_observations(source_log)
    members = {'native.log': ui.encode(), 'fixture-failures.json': b'[]', 'requests.json': b'[]',
        'privacy.xcresult/Info.plist': b'synthetic-not-xcresult'}
    for stage in result['checkpoints']: members[stage + '-product.zip'] = b'synthetic-not-product-zip'
    if platform == 'macos': members['program.zip'] = b'synthetic-not-program-zip'
    if bad_scan: members['remember_closed-privacy-scan.json'] = b'{"private-operand":{"accepted":false}}'
    result.update(evidence_sealed=sealed, lifecycle=receipt,
        files={name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in members.items()})
    if wrong_identity: result['source_sha'] = SOURCE
    archive = root / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        for name, data in members.items():
            zipped.writestr(name, data + b'changed' if changed_member and name == 'native.log' else data)
        zipped.writestr('result.json', json.dumps(result))
    payload = archive.read_bytes(); digest = hashlib.sha256(payload).hexdigest()
    metadata = {'id': 456, 'name': 'password-continuation-native-' + platform + '-' + inspector.CURRENT_CASE_RUN + '-1',
        'workflow_run': {'id': int(inspector.CURRENT_CASE_RUN), 'head_sha': SOURCE if wrong_api else inspector.CURRENT_CASE_SOURCE},
        'size_in_bytes': len(payload), 'digest': 'sha256:' + digest, 'expired': False}
    issue = {'_type': {'_name': 'TestFailureIssueSummary'},
        'message': {'_value': 'Test exceeded execution time allowance of 240 seconds private-operand'},
        'testCaseName': {'_value': CASE}}
    calls, stages = [], []
    out = root / 'out'; out.mkdir()
    real_stage = inspector.diagnostic_stage
    def stage(name): stages.append(name); real_stage(name)
    def command(argv, **kwargs):
        if argv[:2] == ['gh', 'api']:
            test.assertTrue(argv[2].endswith('/actions/artifacts/456/zip'))
            kwargs['stdout'].write(payload); return subprocess.CompletedProcess(argv, 0)
        test.assertEqual(argv[:2], ['xcrun', 'xcresulttool']); calls.append(argv[2])
        test.assertTrue(kwargs['capture_output']); test.assertEqual(kwargs['timeout'], 120)
        test.assertNotEqual(Path(argv[argv.index('--path') + 1]), out / platform / 'privacy.xcresult')
        if argv[2] == 'get': return subprocess.CompletedProcess(argv, 0, json.dumps([issue]).encode(), b'private-stderr')
        exported = Path(argv[-1]); exported.mkdir(); (exported / 'manifest.json').write_text('[]')
        if mutate_after_native == 'file': (out / platform / 'native.log').write_text('mutation')
        if mutate_after_native == 'directory': (out / platform / 'unexpected-empty').mkdir()
        return subprocess.CompletedProcess(argv, 0, b'private-stdout', b'private-stderr')
    def admission(folder, source, record, *, require_program):
        test.assertEqual(source, inspector.CURRENT_CASE_SOURCE); test.assertFalse(require_program)
        if admission_refusal: raise RuntimeError('unexpected admission archive namespace')
        return {'diagnostic_control_only': True}
    with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'NoGod3524/EXReader'}), \
            patch.object(inspector.subprocess, 'check_output', return_value=json.dumps(metadata).encode()), \
            patch.object(inspector.subprocess, 'run', side_effect=command), \
            patch.object(inspector, 'diagnostic_stage', side_effect=stage), \
            patch.object(inspector, 'admission_namespaces', return_value={}), \
            patch.object(inspector, 'admission_metadata', return_value={}), \
            patch.object(inspector, 'verify_ios_admission', side_effect=admission), \
            patch.object(inspector, 'CURRENT_SAFE_REPORT', None), patch.object(inspector, 'CURRENT_MEMBER_INTEGRITY', None), \
            patch.object(inspector, 'CURRENT_PLATFORM', None), \
            patch.object(inspector, 'inspect_native_result', wraps=inspector.inspect_native_result) as native, \
            patch.object(inspector, 'replay_original_attachments') as historical:
        try: report = inspector.diagnose_current_platform(out, platform, 456, len(payload), digest)
        except Exception as error: report = inspector.current_refusal(error)
        entered = native.call_count; historical.assert_not_called()
    inspector.diagnostic_stage('entry')
    return report, calls, stages, entered


class ContinuationDiagnosticControls(unittest.TestCase):
    def test_current_oracle_parameters_preserve_historical_default_and_shape(self):
        oracle = {'synthetic_only': True, 'source_sha': inspector.CURRENT_CASE_SOURCE,
            'run_id': inspector.CURRENT_CASE_RUN, 'attempt': '1', 'user': 'privacy-user-' + 'a' * 32,
            'passwords': {'remembered': 'Privacy-' + 'b' * 64 + '!%:+', 'session': 'Privacy-' + 'c' * 64 + '!%:+'}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root / 'synthetic-oracle-input.json'; path.write_text(json.dumps(oracle))
            proof = inspector.metadata_variants(root, source=inspector.CURRENT_CASE_SOURCE, run=inspector.CURRENT_CASE_RUN)
            self.assertTrue(proof)
            with self.assertRaises(RuntimeError): inspector.metadata_variants(root)
            for key, value in (('attempt', True), ('synthetic_only', 1), ('user', 'private-operand'), ('run_id', RUN)):
                path.write_text(json.dumps(dict(oracle, **{key: value})))
                with self.assertRaises(RuntimeError): inspector.metadata_variants(root,
                    source=inspector.CURRENT_CASE_SOURCE, run=inspector.CURRENT_CASE_RUN)
            path.write_text(json.dumps(dict(oracle, source_sha=SOURCE, run_id=RUN)))
            self.assertEqual(inspector.metadata_variants(root), proof)
            folder = root / 'ios-admission'; folder.mkdir()
            (folder / 'manifest.json').write_text(json.dumps(dict.fromkeys(('pre-sign', 'post-sign', 'installed'), {})))
            with patch.object(inspector, 'metadata_variants', side_effect=RuntimeError('control-stop')) as variants:
                with self.assertRaisesRegex(RuntimeError, '^control-stop$'):
                    inspector.admission_metadata(root, source=inspector.CURRENT_CASE_SOURCE, run=inspector.CURRENT_CASE_RUN)
                variants.assert_called_once_with(root, source=inspector.CURRENT_CASE_SOURCE, run=inspector.CURRENT_CASE_RUN)

    def test_current_case_pins_and_historical_profile_are_separate(self):
        self.assertEqual(inspector.CURRENT_CASE_SOURCE, '2e8ef281dc1c790427ee4a5c60cae3d880750d3a')
        self.assertEqual(inspector.CURRENT_CASE_RUN, '40877286914')
        self.assertEqual(inspector.CURRENT_CASE_ARTIFACTS, {
            'macos': (12898598312, 104208231, 'a42f6c78ea576042c54eb12951c4e608aa641f2a1fc5c6148ac8eabc5be96ae8'),
            'iphone': (12899507875, 176407990, '5232cee7ddf98f6bc1cba6d16dec705956cb666e898af516e7ecd832518f277f'),
            'ipad': (12900935511, 187645675, 'b043a78b1adee48a1b1b92fa8f5956898c6fdc1dabbf0d9ce519dea25229af37')})
        self.assertEqual((SOURCE, RUN), ('6803602e5791eafa69a6e61bc5499d36cd31d92e', '40858915090'))
        self.assertEqual(inspector.ATTACHMENT_SOURCE_HASHES['continuation_contract.py'],
                         '03a72ae6666b59f829ddd3427067dd2963a3664235f1e5d168041b28cee4e7d1')
        self.assertEqual(inspector.PROFILE_RUN, '40839064448')
        source = Path(inspector.__file__).read_text()
        self.assertIn('if not current_main(): raise SystemExit(1)', source)
        self.assertIn("sys.argv[1:] == ['--capture-profile']", source)

    def test_current_main_actual_routing_and_immutable_ui_source(self):
        ui = (ROOT / SOURCE_FILE).read_bytes()
        record = {'type': 'file', 'path': SOURCE_FILE, 'encoding': 'base64', 'size': len(ui), 'content': base64.b64encode(ui).decode()}
        with tempfile.TemporaryDirectory() as temporary, patch.object(inspector, 'ROOT', Path(temporary)), \
                patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'NoGod3524/EXReader'}), \
                patch.object(inspector, 'guard'), patch.object(inspector.subprocess, 'check_output', return_value=json.dumps(record).encode()) as fetch, \
                patch.object(inspector, 'run_current_platforms', return_value=False) as current, \
                patch.object(inspector, 'run_platforms') as historical, patch.object(inspector, 'capture_profile_main') as profile:
            self.assertFalse(inspector.current_main())
            self.assertTrue(fetch.call_args.args[0][-1].endswith('?ref=' + inspector.CURRENT_CASE_SOURCE))
            current.assert_called_once(); historical.assert_not_called(); profile.assert_not_called()

    def test_current_progress_distinguishes_success_scope_and_native_failure(self):
        for platform in ('macos', 'iphone', 'ipad'):
            value = current_result(platform)
            files = {stage + '-product.zip' for stage in value['checkpoints']} | {'program.zip'}
            proof = inspector.current_progress(value, files, platform)
            self.assertEqual(proof['native_command_exit'], 0 if platform == 'macos' else 65)
            self.assertFalse(proof['full_validate_executed']); self.assertFalse(proof['full_program_signature_credit'])
            self.assertFalse(proof['accepted']); self.assertFalse(proof['full_f10_accepted'])
            if platform == 'macos':
                self.assertEqual(proof['scope'], 'producer-completion-only')
                with self.assertRaises(RuntimeError): safe_progress(value, files)
            else:
                self.assertEqual(proof['nonzero_command_exits'], [{'role': 'native', 'exit': 65}])
                value['commands'] = [{'role': 'admission-installed-archive', 'exit': 0}]
                absent = inspector.current_progress(value, files, platform)
                self.assertIsNone(absent['native_command_exit']); self.assertFalse(absent['native_command_observed'])

    def test_current_progress_rejects_overclaims_identity_and_checkpoint_shapes(self):
        changes = [('accepted', True), ('full_f10_accepted', True), ('sequence_complete', True),
            ('source_sha', SOURCE), ('run_id', RUN), ('attempt', True), ('failure', 'private-operand'),
            ('strict_privacy_checks', {'remember_closed': 0}), ('checkpoints', {'private-operand': {}})]
        for key, change in changes:
            value = current_result(); value[key] = change
            with self.assertRaises(RuntimeError): inspector.current_progress(value,
                {stage + '-product.zip' for stage in inspector.STAGES}, 'iphone')
        for key, change in (('network_requests', True), ('original_bytes', -1), ('strict_privacy_passed', 0),
                            ('archive', 'private-operand'), ('profile_id', 'private-operand'), ('unexpected', True)):
            value = current_result(); value['checkpoints']['remember_closed'][key] = change
            with self.assertRaises(RuntimeError): inspector.current_progress(value,
                {stage + '-product.zip' for stage in inspector.STAGES}, 'iphone')
        for change in (False, None, 'private-operand'):
            value = current_result('macos'); value['sequence_complete'] = change
            with self.assertRaises(RuntimeError): inspector.current_progress(value,
                {stage + '-product.zip' for stage in inspector.STAGES} | {'program.zip'}, 'macos')

    def test_current_progress_rejects_duplicate_and_illtyped_commands(self):
        for commands in ([{'role': 'native', 'exit': True}], [{'role': 'native', 'exit': '65'}],
            [{'role': 'native', 'exit': 65}, {'role': 'native', 'exit': 0}],
            [{'role': 'private-operand', 'exit': 1}], [{'role': [], 'exit': 1}]):
            value = current_result(); value['commands'] = commands
            with self.assertRaises(RuntimeError): inspector.current_progress(value,
                {stage + '-product.zip' for stage in inspector.STAGES}, 'iphone')
        for role in ('native', 'attachments', 'program-archive'):
            value = current_result('macos'); value['commands'] = [row for row in value['commands'] if row['role'] != role]
            with self.assertRaises(RuntimeError): inspector.current_progress(value,
                {stage + '-product.zip' for stage in inspector.STAGES} | {'program.zip'}, 'macos')

    def test_current_ui_replay_rejects_mismatch_and_encoded_operands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root / 'native.log'
            path.write_text('EXR_PRIVACY_UI_SAVE elapsed_ms=10 status=saved\n')
            result = {'ui_state_observations': inspector.parse_ui_observations(path)}
            report = {}; inspector.replay_current_ui(root, result, report)
            self.assertTrue(report['ui_observations_match_producer'])
            changed = copy.deepcopy(result); changed['ui_state_observations']['initial_save'][0]['elapsed_ms'] = 10.0
            with self.assertRaises(RuntimeError): inspector.replay_current_ui(root, changed, {})
            for operand in list(needles({'secret': b'Privacy-' + b'a' * 40}).values()) + [b'Privacy-aaa...']:
                path.write_bytes(b'EXR_PRIVACY_UI_SAVE elapsed_ms=10 status=' + operand + b'\n')
                with self.assertRaises(RuntimeError): inspector.replay_current_ui(root, result, {})

    def test_current_actual_native_precedes_scan_refusal_and_partial_survives(self):
        with tempfile.TemporaryDirectory() as temporary:
            proof, calls, stages, count = current_order_control(self, Path(temporary), bad_scan=True)
        self.assertEqual(calls, ['get', 'export']); self.assertEqual(count, 1)
        self.assertLess(stages.index('xcresult-issues'), stages.index('scan-summaries'))
        partial = proof['validated_partial_report']
        self.assertTrue(partial['original_namespace_and_bytes_preserved'])
        self.assertTrue(partial['ui_observations_match_producer']); self.assertEqual(partial['native_command_exit'], 65)
        self.assertEqual(partial['xcresult']['issues'][0]['known_time_allowance'], [240])
        self.assertTrue(proof['diagnostic_refused']); self.assertNotIn('private-operand', json.dumps(proof))

    def test_current_bad_api_identity_member_or_lifecycle_blocks_native(self):
        for option in ('wrong_api', 'wrong_identity', 'changed_member', 'sealed'):
            with tempfile.TemporaryDirectory() as temporary:
                proof, calls, stages, count = current_order_control(self, Path(temporary), **{option: option != 'sealed'})
            self.assertTrue(proof['diagnostic_refused']); self.assertEqual(count, 0); self.assertEqual(calls, [])
            self.assertIsNone(proof['validated_partial_report'])

    def test_current_macos_map_and_ios_fatal_namespace_keep_distinct_credit(self):
        with tempfile.TemporaryDirectory() as temporary:
            proof, calls, stages, count = current_order_control(self, Path(temporary), platform='macos')
        self.assertTrue(proof['sequence_complete']); self.assertEqual(proof['scope'], 'producer-completion-only')
        self.assertTrue(proof['program_archive_present']); self.assertFalse(proof['full_validate_executed'])
        self.assertFalse(proof['full_program_signature_credit']); self.assertTrue(proof['original_namespace_and_bytes_preserved'])
        with tempfile.TemporaryDirectory() as temporary:
            proof, calls, stages, count = current_order_control(self, Path(temporary), admission_refusal=True)
        self.assertEqual(proof['stage'], 'admission-replay'); self.assertTrue(proof['diagnostic_refused'])
        self.assertEqual(proof['validated_partial_report']['native_command_exit'], 65)
        self.assertIn('xcresult', proof['validated_partial_report'])

    def test_current_original_file_or_empty_directory_mutation_refuses(self):
        for mutation in ('file', 'directory'):
            with tempfile.TemporaryDirectory() as temporary:
                proof, calls, stages, count = current_order_control(self, Path(temporary), mutate_after_native=mutation)
            self.assertEqual(proof['refusal_code'], 'current-original-changed')
            self.assertFalse(proof['validated_partial_report']['original_namespace_and_bytes_preserved'])
            self.assertIn('xcresult', proof['validated_partial_report'])

    def test_current_all_platforms_attempted_without_changing_historical_pins(self):
        seen = []
        def diagnose(out, platform, identifier, size, digest):
            seen.append((platform, identifier, size, digest))
            if platform == 'iphone': raise RuntimeError('current UI replay differs')
            return {'platform': platform, 'accepted': False}
        with tempfile.TemporaryDirectory() as temporary, patch.object(inspector, 'COMPLETED_REPORTS', []):
            self.assertFalse(inspector.run_current_platforms(Path(temporary), diagnoser=diagnose))
            self.assertEqual(len(inspector.COMPLETED_REPORTS), 3)
            self.assertTrue(inspector.COMPLETED_REPORTS[1]['diagnostic_refused'])
        self.assertEqual(seen, [(platform, *row) for platform, row in inspector.CURRENT_CASE_ARTIFACTS.items()])
        self.assertEqual(ARTIFACTS['macos'][0], 12890808734)

    def test_current_shared_helper_accepts_original_bytes_and_matches_counterfactual(self):
        for name in ('privacy-stages.json', 'privacy-stages_0_12345678-1234-1234-1234-123456789ABC.json'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root, name); report, compared = {}, {}
                directory = root / 'attachments'; before = seal_files(directory); manifest = (directory / 'manifest.json').read_bytes()
                inspector.replay_original_attachments(root, result, report)
                self.assertTrue(inspector.attachment_identity_trial(root, result, report, compared))
                self.assertTrue(inspector.replay_current_attachments(root, result, report, compared))
                proof = report['current_attachment_helper']
                self.assertTrue(proof['current_helper_verified']); self.assertEqual(proof['helper_outcome'], 'passed')
                self.assertIs(proof['next_profile_predicate'], True)
                self.assertTrue(all(proof[field] for field in ('matches_original_payload', 'matches_pinned_counterfactual',
                    'matches_original_screenshots', 'original_bytes_preserved', 'original_namespace_preserved', 'source_rechecked')))
                self.assertEqual(seal_files(directory), before); self.assertEqual((directory / 'manifest.json').read_bytes(), manifest)
                self.assertFalse(proof['accepted']); self.assertFalse(proof['native_acceptance']); self.assertFalse(proof['full_f10_accepted'])
                self.assertNotIn('private-unknown-operand', json.dumps(report))

    def test_current_helper_old_caller_bytes_and_external_profile_gates_unchanged(self):
        package = ROOT / 'tests/apple_password_privacy_20261028'
        self.assertEqual(sha(package / 'continuation_run.py'), '430cc3ea71ca7982982026305a8bdc8067a47d11eb4118e69db3820770da10b2')
        self.assertEqual(sha(package / 'authenticate_continuation.py'), '4e0127c553d22a765cfcbf9274aa6f476b55afaed5f25f6eda22ded5209ac54b')
        self.assertEqual(sha(package / 'continuation_contract.py'), inspector.CURRENT_ATTACHMENT_SOURCE_SHA)
        self.assertNotEqual(inspector.CURRENT_ATTACHMENT_SOURCE_SHA, inspector.ATTACHMENT_SOURCE_HASHES['continuation_contract.py'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); result = candidate_bundle(root)
            stages, unused = current_contract.attachments(root / 'attachments')
            runner = (package / 'continuation_run.py').read_text()
            expression = "all(value['profile_id'] == result['native_stages']['profile'] for value in result['checkpoints'].values())"
            self.assertIn('require(' + expression + ", 'UI/storage profile mismatch')", runner)
            result['native_stages'] = stages
            self.assertTrue(eval(expression, {'result': result}))
            result['checkpoints'][inspector.STAGES[0]]['profile_id'] = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
            self.assertFalse(eval(expression, {'result': result}))
            auth = (package / 'authenticate_continuation.py').read_text()
            self.assertIn("require(checkpoint['profile_id'] == stages['profile'], 'UI/profile identity differs')", auth)
            for checkpoint in result['checkpoints'].values():
                self.assertEqual(eval("checkpoint['profile_id'] == stages['profile']", {'checkpoint': checkpoint, 'stages': stages}),
                                 checkpoint['profile_id'] == stages['profile'])

    def test_current_helper_exact_document_names_refuse_extension_or_prefix_shortcuts(self):
        uuid = '12345678-1234-1234-1234-123456789ABC'
        for name in ('privacy-stages.json.extra', 'privacy-stages.json/private-operand', 'private-operand.json',
                'privacy-stages_00_' + uuid + '.json', 'privacy-stages_1000000_' + uuid + '.json',
                'privacy-stages_0_12345678-1234-1234-1234-123456789AbC.json',
                'privacy-stages_0_' + uuid + '.JSON', 'privacy-stages_１_' + uuid + '.json',
                'privacy-stages_0_UHJpdmFjeS0=.json', 'privacy-stages_0_Privacy-aaaa...json'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); candidate_bundle(root, name); directory = root / 'attachments'; before = seal_files(directory)
                with self.assertRaises(RuntimeError): current_contract.attachments(directory)
                self.assertEqual(seal_files(directory), before)

    def test_current_helper_manifest_identity_uniqueness_and_complete_inventory(self):
        for change in ('case', 'conflict', 'bool', 'list', 'empty', 'duplicate-document', 'duplicate-file', 'alias', 'extra', 'missing', 'unsafe', 'duplicate-json', 'numeric-loss'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); candidate_bundle(root); directory = root / 'attachments'
                groups = json.loads((directory / 'manifest.json').read_text())
                if change == 'case': groups[0]['testIdentifier'] = 'testForeign'
                elif change == 'conflict': groups[0]['testName'] = 'testForeign'
                elif change in ('bool', 'list', 'empty'):
                    groups[0]['testIdentifier'] = {'bool': False, 'list': [], 'empty': ''}[change]; groups[0]['testName'] = CASE
                elif change == 'duplicate-document':
                    (directory / 'second.json').write_bytes((directory / 'metadata.json').read_bytes())
                    groups[0]['attachments'].append(dict(groups[0]['attachments'][0], exportedFileName='second.json'))
                elif change == 'duplicate-file': groups[0]['attachments'].append(dict(groups[0]['attachments'][0]))
                elif change == 'alias':
                    (directory / 'METADATA.json').write_bytes((directory / 'metadata.json').read_bytes())
                    groups[0]['attachments'].append(dict(groups[0]['attachments'][0], exportedFileName='METADATA.json'))
                elif change == 'extra': (directory / 'extra').write_bytes(b'extra')
                elif change == 'missing': groups[0]['attachments'][0]['exportedFileName'] = 'missing.json'
                elif change == 'unsafe': groups[0]['attachments'][0]['exportedFileName'] = '../private-operand'
                text = json.dumps(groups)
                if change == 'duplicate-json': text = text.replace('"testIdentifier":', '"testIdentifier":"testForeign","testIdentifier":', 1)
                elif change == 'numeric-loss': text = text.replace('"unknownMetadata":', '"precision":1.00000000000000001,"unknownMetadata":', 1)
                (directory / 'manifest.json').write_text(text); before = seal_files(directory)
                with self.assertRaises(RuntimeError): current_contract.attachments(directory)
                self.assertEqual(seal_files(directory), before)

    def test_current_helper_canonical_payload_and_screenshots_do_not_relax(self):
        for change in ('extra', 'missing', 'order', 'incomplete', 'operation', 'flag', 'uuid', 'duplicate-key',
                       'invalid-json', 'invalid-utf8', 'oversize', 'image-duplicate', 'image-missing', 'image-magic', 'image-bare'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); candidate_bundle(root); directory = root / 'attachments'
                groups = json.loads((directory / 'manifest.json').read_text()); document = json.loads((directory / 'metadata.json').read_text())
                if change == 'extra': document['extra'] = 'private-operand'
                elif change == 'missing': del document['operation']
                elif change == 'order': document['stages'].reverse()
                elif change == 'incomplete': document['stages'].pop()
                elif change == 'operation': document['operation'] = 'private-operand'
                elif change == 'flag': document['diagnostic_continuation'] = 1
                elif change == 'uuid': document['profile'] = 'Privacy-aaaa...'
                elif change == 'image-duplicate': groups[0]['attachments'].append(dict(groups[0]['attachments'][1]))
                elif change == 'image-missing': groups[0]['attachments'][1]['suggestedHumanReadableName'] = 'not-a-screenshot'
                elif change == 'image-magic': (directory / 'image0.bin').write_bytes(b'not-png')
                elif change == 'image-bare': groups[0]['attachments'][1]['suggestedHumanReadableName'] = 'privacy-' + inspector.STAGES[0]
                data = json.dumps(document).encode()
                if change == 'duplicate-key': data = data[:-1] + b',"profile":"private-operand"}'
                elif change == 'invalid-json': data = b'private-operand not-json'
                elif change == 'invalid-utf8': data = b'\xffprivate-operand'
                elif change == 'oversize': data += b' ' * (1024 * 1024)
                (directory / 'metadata.json').write_bytes(data); (directory / 'manifest.json').write_text(json.dumps(groups))
                before = seal_files(directory)
                with self.assertRaises((RuntimeError, UnicodeDecodeError, json.JSONDecodeError)): current_contract.attachments(directory)
                self.assertEqual(seal_files(directory), before)

    def test_current_helper_mutation_empty_directory_and_special_entries_refuse(self):
        actual = current_contract._attachment_json
        for change in ('earlier-file', 'empty-directory'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); candidate_bundle(root); directory = root / 'attachments'; calls = []
                def mutate(data):
                    value = actual(data); calls.append(True)
                    if len(calls) == 2:
                        if change == 'earlier-file': (directory / 'image0.bin').write_bytes(b'changed')
                        else: (directory / 'empty-late').mkdir()
                    return value
                with patch.object(current_contract, '_attachment_json', side_effect=mutate), self.assertRaises(RuntimeError):
                    current_contract.attachments(directory)
        actual_read = current_contract._attachment_read
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); candidate_bundle(root); directory = root / 'attachments'; read_names = []
            def mutate_after_later_read(path, *args, **kwargs):
                data = actual_read(path, *args, **kwargs); read_names.append(path.name)
                if path.name == 'image3.bin':
                    self.assertIn('image0.bin', read_names)
                    with (directory / 'image0.bin').open('r+b') as file: file.write(b'changed!')
                return data
            with patch.object(current_contract, '_attachment_read', side_effect=mutate_after_later_read), self.assertRaises(RuntimeError):
                current_contract.attachments(directory)
        for change in ('symlink', 'fifo', 'hardlink'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); candidate_bundle(root); directory = root / 'attachments'
                if change == 'symlink': (directory / 'linked').symlink_to(directory / 'image0.bin')
                elif change == 'fifo': os.mkfifo(directory / 'pipe')
                else: os.link(directory / 'image0.bin', directory / 'hardlinked')
                with self.assertRaises(RuntimeError): current_contract.attachments(directory)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); candidate_bundle(root); directory = root / 'attachments'
            (directory / 'Empty').mkdir(); (directory / 'empty').mkdir()
            with self.assertRaisesRegex(RuntimeError, '^current attachment namespace changed$'): current_contract.attachments(directory)

    def test_current_helper_fd_swap_refuses_nonblocking(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); candidate_bundle(root); directory = root / 'attachments'; records = seal_files(directory)
            actual_open = os.open
            def swapped(path, flags, *args, **kwargs):
                self.assertTrue(flags & os.O_NONBLOCK)
                Path(path).unlink(); os.mkfifo(path)
                return actual_open(path, flags, *args, **kwargs)
            with patch.object(current_contract.os, 'open', side_effect=swapped), self.assertRaises(RuntimeError):
                current_contract._attachment_read(directory / 'metadata.json', records['metadata.json'], maximum=1024 * 1024)

    def test_current_replay_latches_actual_result_before_later_refusal(self):
        for final in (False, True):
            with tempfile.TemporaryDirectory() as temporary:
                refusal, calls, stages, unused = native_order_control(self, Path(temporary),
                    retained_candidate_export=True, valid_later_evidence=final)
                self.assertEqual(refusal['refusal_code'], 'attachment-contract-refused' if final else 'fixture-failure-shape')
                report = refusal['validated_partial_report']; proof = report['current_attachment_helper']
                self.assertTrue(proof['current_helper_verified']); self.assertFalse(proof['accepted'])
                self.assertTrue(report['original_attachment_contract']['fatal_refusal']); self.assertFalse(report['accepted'])
                self.assertLess(stages.index('attachment-current-replay'), stages.index('xcresult-copy'))
                self.assertEqual(calls, ['get', 'export']); self.assertNotIn('private-unknown-operand', json.dumps(refusal))

    def test_current_replay_binds_actual_source_and_full_counterfactual_values(self):
        for change in ('source', 'document', 'image'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root); report, compared = {}, {}
                inspector.replay_original_attachments(root, result, report)
                self.assertTrue(inspector.attachment_identity_trial(root, result, report, compared))
                if change == 'document': compared['stages']['operation'] = 'private-operand'
                elif change == 'image': compared['images'][inspector.STAGES[0]]['sha256'] = '0' * 64
                with patch.object(inspector, 'CURRENT_ATTACHMENT_SOURCE_SHA', '0' * 64 if change == 'source' else inspector.CURRENT_ATTACHMENT_SOURCE_SHA):
                    self.assertFalse(inspector.replay_current_attachments(root, result, report, compared))
                proof = report['current_attachment_helper']; self.assertFalse(proof['current_helper_verified'])
                self.assertEqual(proof['helper_outcome'], 'unavailable' if change == 'source' else 'passed')
                self.assertNotIn('private-operand', json.dumps(proof))

    def test_current_helper_unavailable_not_inferred_from_regenerated_export(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(current_contract, 'attachments') as current:
            root = Path(temporary); regenerated = root / 'regenerated'; regenerated.mkdir(); candidate_bundle(regenerated)
            report = {}; result = {'files': {}, 'commands': []}
            inspector.replay_original_attachments(root, result, report)
            self.assertTrue(inspector.attachment_identity_trial(root, result, report))
            self.assertTrue(inspector.replay_current_attachments(root, result, report, {}))
            self.assertEqual(report['current_attachment_helper']['status'], 'unavailable')
            self.assertFalse(report['current_attachment_helper']['current_helper_verified']); current.assert_not_called()

    def test_candidate_exact_names_call_original_helper_on_only_metadata_copy(self):
        for name, changed in [('privacy-stages.json', 0),
                ('privacy-stages_0_12345678-1234-1234-1234-123456789ABC.json', 1),
                ('privacy-stages_999999_12345678-1234-1234-1234-123456789abc.json', 1)]:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root, name); before = seal_files(root / 'attachments')
                outcome, report = run_candidate(root, result); proof = report['attachment_identity_candidate']
                self.assertTrue(outcome); self.assertTrue(proof['candidate_qualified'])
                self.assertEqual(proof['candidate_helper_outcome'], 'passed'); self.assertIs(proof['next_profile_predicate'], True)
                self.assertEqual(proof['allowed_changed_field_count'], changed)
                self.assertTrue(proof['original_bytes_preserved']); self.assertTrue(proof['copy_nonmanifest_bytes_preserved'])
                self.assertTrue(proof['copy_namespace_preserved'])
                self.assertTrue(proof['source_and_import_rechecked']); self.assertEqual(seal_files(root / 'attachments'), before)
                original = report['original_attachment_contract']
                self.assertEqual(original['original_helper_outcome'], 'refused' if changed else 'passed')
                self.assertIs(original['next_profile_predicate'], None if changed else True)
                self.assertEqual(original['fatal_refusal'], bool(changed))
                self.assertFalse(proof['accepted']); self.assertFalse(proof['native_acceptance']); self.assertFalse(proof['full_f10_accepted'])
                self.assertNotIn('private-unknown-operand', json.dumps(report))

    def test_candidate_name_grammar_refuses_unknown_and_extension_only_identity(self):
        uuid = '12345678-1234-1234-1234-123456789ABC'
        for name in ['private-operand.json', 'prefix-privacy-stages_0_' + uuid + '.json',
                'privacy-stages_00_' + uuid + '.json', 'privacy-stages_1000000_' + uuid + '.json',
                'privacy-stages_1_12345678-1234-1234-1234-123456789AbC.json',
                'privacy-stages_1_private-operand.json', 'privacy-stages_1_' + uuid + '.json.extra',
                'privacy-stages_1_' + uuid + '.JSON', 'privacy-stages.json/private-operand',
                'privacy-stages_１_' + uuid + '.json', 'privacy-stages_%31_' + uuid + '.json',
                'privacy-stages_1_UHJpdmFjeS0=.json', 'privacy-stages_1_Privacy-aaaa...json']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root, name)
                outcome, report = run_candidate(root, result); proof = report['attachment_identity_candidate']
                self.assertFalse(outcome); self.assertFalse(proof['candidate_qualified'])
                self.assertEqual(proof['candidate_helper_outcome'], 'unavailable'); self.assertIsNone(proof['next_profile_predicate'])
                for operand in ('private-operand', 'UHJpdmFjeS0=', 'Privacy-aaaa...'): self.assertNotIn(operand, json.dumps(proof))

    def test_candidate_manifest_selection_is_unique_complete_and_case_bound(self):
        for change in ('duplicate-candidate', 'duplicate-file', 'aliased-file', 'foreign-case',
                'conflicting-name', 'bool-fallback', 'list-fallback', 'empty-fallback', 'invalid-name-type',
                'extra-file', 'missing-reference', 'unsafe'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root); directory = root / 'attachments'
                groups = json.loads((directory / 'manifest.json').read_text())
                if change == 'duplicate-candidate':
                    (directory / 'other.json').write_bytes((directory / 'metadata.json').read_bytes())
                    groups[0]['attachments'].append(dict(groups[0]['attachments'][0], exportedFileName='other.json'))
                elif change == 'duplicate-file': groups[0]['attachments'].append(dict(groups[0]['attachments'][0]))
                elif change == 'aliased-file':
                    (directory / 'METADATA.json').write_bytes((directory / 'metadata.json').read_bytes())
                    groups[0]['attachments'].append(dict(groups[0]['attachments'][0], exportedFileName='METADATA.json'))
                elif change == 'foreign-case': groups[0]['testIdentifier'] = 'testForeignCase'
                elif change == 'conflicting-name': groups[0]['testName'] = 'testForeignCase'
                elif change in ('bool-fallback', 'list-fallback', 'empty-fallback'):
                    groups[0]['testIdentifier'] = {'bool-fallback': False, 'list-fallback': [], 'empty-fallback': ''}[change]
                    groups[0]['testName'] = CASE
                elif change == 'invalid-name-type': groups[0]['testName'] = [CASE]
                elif change == 'extra-file': (directory / 'extra.json').write_text('{}')
                elif change == 'missing-reference': groups[0]['attachments'][0]['exportedFileName'] = 'missing.json'
                else: groups[0]['attachments'][0]['exportedFileName'] = '../private-operand'
                (directory / 'manifest.json').write_text(json.dumps(groups))
                result['files'] = {'attachments/' + name: item for name, item in seal_files(directory).items()}
                outcome, report = run_candidate(root, result)
                self.assertFalse(outcome); self.assertFalse(report['attachment_identity_candidate']['candidate_qualified'])
                self.assertIsNone(report['attachment_identity_candidate']['next_profile_predicate'])

    def test_candidate_payload_exact_shape_and_checkpoint_identity(self):
        for change in ('extra', 'missing', 'order', 'incomplete', 'operation', 'flag', 'uuid', 'profile', 'duplicate', 'invalid-json', 'invalid-utf8', 'oversize'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root); directory = root / 'attachments'
                document = json.loads((directory / 'metadata.json').read_text())
                if change == 'extra': document['private-operand'] = 'private-operand'
                elif change == 'missing': del document['operation']
                elif change == 'order': document['stages'].reverse()
                elif change == 'incomplete': document['stages'].pop()
                elif change == 'operation': document['operation'] = 'UHJpdmFjeS0='
                elif change == 'flag': document['diagnostic_continuation'] = 1
                elif change == 'uuid': document['profile'] = 'Privacy-aaaa...'
                elif change == 'profile': result['checkpoints'][inspector.STAGES[0]]['profile_id'] = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
                data = json.dumps(document).encode()
                if change == 'duplicate': data = data[:-1] + b',"profile":"private-operand"}'
                elif change == 'invalid-json': data = b'private-operand not-json'
                elif change == 'invalid-utf8': data = b'\xffprivate-operand'
                elif change == 'oversize': data += b' ' * (1024 * 1024)
                (directory / 'metadata.json').write_bytes(data)
                result['files'] = {'attachments/' + name: item for name, item in seal_files(directory).items()}
                outcome, report = run_candidate(root, result); proof = report['attachment_identity_candidate']
                self.assertFalse(outcome); self.assertFalse(proof['candidate_qualified'])
                self.assertEqual(proof['candidate_helper_outcome'], 'unavailable'); self.assertIsNone(proof['next_profile_predicate'])
                for operand in ('private-operand', 'UHJpdmFjeS0=', 'Privacy-aaaa...'): self.assertNotIn(operand, json.dumps(proof))

    def test_candidate_duplicate_and_nonfinite_manifest_values_refuse(self):
        for data in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}', b'{"a":1e999}'):
            with self.assertRaises(RuntimeError): inspector.attachment_json(data)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); result = candidate_bundle(root); directory = root / 'attachments'
            raw = (directory / 'manifest.json').read_bytes().replace(b'"testIdentifier":', b'"testIdentifier":"testForeign", "testIdentifier":', 1)
            (directory / 'manifest.json').write_bytes(raw)
            result['files'] = {'attachments/' + name: item for name, item in seal_files(directory).items()}
            outcome, report = run_candidate(root, result)
            self.assertFalse(outcome); self.assertEqual(report['attachment_identity_candidate']['refusal']['refusal_code'], 'attachment-candidate-json-duplicate')

    def test_candidate_unknown_numeric_metadata_requires_exact_decimal_roundtrip(self):
        for token in ('1.00000000000000001', '0.100000000000000001', '1e-999', '-1e-999'):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root); directory = root / 'attachments'
                raw = (directory / 'manifest.json').read_text().replace('"unknownMetadata":', '"exactNumber":' + token + ',"unknownMetadata":', 1)
                (directory / 'manifest.json').write_text(raw)
                result['files'] = {'attachments/' + name: item for name, item in seal_files(directory).items()}
                outcome, report = run_candidate(root, result); proof = report['attachment_identity_candidate']
                self.assertFalse(outcome); self.assertFalse(proof['candidate_qualified'])
                self.assertEqual(proof['refusal']['refusal_code'], 'attachment-candidate-json-number')
                self.assertEqual(proof['candidate_helper_outcome'], 'unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); result = candidate_bundle(root); directory = root / 'attachments'
            raw = (directory / 'manifest.json').read_text().replace('"unknownMetadata":', '"exactNumbers":[0.1,1.0,-0.0,1e2],"unknownMetadata":', 1)
            (directory / 'manifest.json').write_text(raw)
            result['files'] = {'attachments/' + name: item for name, item in seal_files(directory).items()}
            outcome, report = run_candidate(root, result)
            self.assertTrue(outcome); self.assertTrue(report['attachment_identity_candidate']['candidate_qualified'])

    def test_candidate_single_field_comparison_is_type_exact_for_unknown_metadata(self):
        for left, right in [(True, 1), (1, 1.0), (0.0, -0.0), ({'a': [True]}, {'a': [1]}),
                            ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}), ([1, 2], [2, 1])]:
            self.assertFalse(inspector.attachment_same_value(left, right))
        actual = inspector.attachment_copy_proof
        for change in ('bool-int', 'int-float', 'nested-value', 'drop', 'entry-order', 'extra-field',
                       'document', 'screenshot', 'original-prefix', 'namespace', 'empty-directory'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root)
                def mutate(original, copied, expected, groups, position):
                    model = json.loads((copied / 'manifest.json').read_text())
                    if change == 'bool-int': model[0]['unknownMetadata']['nested'][0] = 1
                    elif change == 'int-float': model[0]['unknownMetadata']['nested'][1] = 1.0
                    elif change == 'nested-value': model[0]['unknownMetadata']['nested'][-1]['keep'] = 'replacement-private-operand'
                    elif change == 'drop': del model[0]['unknownMetadata']
                    elif change == 'entry-order': model[0]['attachments'].reverse()
                    elif change == 'extra-field': model[0]['attachments'][0]['extra'] = 'private-operand'
                    elif change == 'document': (copied / 'metadata.json').write_text('{}')
                    elif change == 'screenshot': (copied / 'image0.bin').write_bytes(b'changed')
                    elif change == 'original-prefix':
                        with (original / 'image0.bin').open('r+b') as file: file.write(b'changed!')
                    elif change == 'empty-directory': (copied / 'empty-extra').mkdir()
                    else: (copied / 'late').write_bytes(b'private-operand')
                    (copied / 'manifest.json').write_text(json.dumps(model))
                    return actual(original, copied, expected, groups, position)
                with patch.object(inspector, 'attachment_copy_proof', side_effect=mutate): outcome, report = run_candidate(root, result)
                proof = report['attachment_identity_candidate']; self.assertFalse(outcome); self.assertFalse(proof['candidate_qualified'])
                self.assertEqual(proof['candidate_helper_outcome'], 'unavailable'); self.assertIsNone(proof['next_profile_predicate'])
                self.assertNotIn('replacement-private-operand', json.dumps(proof))

    def test_candidate_post_helper_mutation_preserves_observed_but_not_qualified_outcome(self):
        actual = inspector.attachment_copy_proof
        for change in ('original', 'source'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = candidate_bundle(root); calls = []
                def late(original, copied, expected, groups, position):
                    calls.append(True)
                    if len(calls) == 2:
                        if change == 'original': (original / 'metadata.json').write_text('{}')
                        else: (copied.parent / 'source' / 'continuation_contract.py').write_text('foreign source')
                    return actual(original, copied, expected, groups, position)
                with patch.object(inspector, 'attachment_copy_proof', side_effect=late): outcome, report = run_candidate(root, result)
                proof = report['attachment_identity_candidate']; self.assertFalse(outcome)
                self.assertEqual(proof['candidate_helper_outcome'], 'passed'); self.assertIs(proof['next_profile_predicate'], True)
                self.assertFalse(proof['candidate_qualified']); self.assertFalse(proof['original_bytes_preserved'])

    def test_candidate_actual_helper_failure_keeps_next_profile_unexecuted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); result = candidate_bundle(root); directory = root / 'attachments'
            groups = json.loads((directory / 'manifest.json').read_text())
            for stage, entry in zip(inspector.STAGES, groups[0]['attachments'][1:]):
                entry['suggestedHumanReadableName'] = 'privacy-' + stage
            (directory / 'manifest.json').write_text(json.dumps(groups))
            result['files'] = {'attachments/' + name: item for name, item in seal_files(directory).items()}
            outcome, report = run_candidate(root, result); proof = report['attachment_identity_candidate']
            self.assertFalse(outcome); self.assertEqual(proof['candidate_helper_outcome'], 'refused')
            self.assertIsNone(proof['next_profile_predicate']); self.assertFalse(proof['candidate_qualified'])
            self.assertEqual(proof['refusal']['refusal_code'], 'attachment-original-incomplete')

    def test_candidate_source_substitution_and_absent_original_do_not_execute(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); result = candidate_bundle(root); report = {}
            inspector.replay_original_attachments(root, result, report)
            with patch.object(inspector.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'foreign source', b'private-operand')):
                self.assertFalse(inspector.attachment_identity_trial(root, result, report))
            self.assertEqual(report['attachment_identity_candidate']['candidate_helper_outcome'], 'unavailable')
            self.assertEqual(report['attachment_identity_candidate']['refusal']['refusal_code'], 'attachment-source')
        with tempfile.TemporaryDirectory() as temporary, patch.object(inspector, 'attachment_reference') as reference:
            root = Path(temporary); regenerated = root / 'regenerated'; regenerated.mkdir(); candidate_bundle(regenerated)
            report = {}; result = {'files': {}, 'commands': []}
            inspector.replay_original_attachments(root, result, report)
            self.assertTrue(inspector.attachment_identity_trial(root, result, report))
            self.assertEqual(report['attachment_identity_candidate']['status'], 'unavailable')
            self.assertFalse(report['attachment_identity_candidate']['candidate_qualified']); reference.assert_not_called()

    def test_candidate_qualified_report_survives_later_fatal_without_replacing_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            refusal, calls, stages, unused = native_order_control(self, Path(temporary), retained_candidate_export=True)
            self.assertEqual(refusal['refusal_code'], 'fixture-failure-shape')
            report = refusal['validated_partial_report']; original = report['original_attachment_contract']
            self.assertEqual(original['original_helper_outcome'], 'refused'); self.assertTrue(original['fatal_refusal'])
            self.assertTrue(report['attachment_identity_candidate']['candidate_qualified'])
            self.assertFalse(report['attachment_identity_candidate']['accepted']); self.assertFalse(report['accepted'])
            self.assertEqual(calls, ['get', 'export'])
            self.assertLess(stages.index('attachment-identity-candidate'), stages.index('xcresult-copy'))
            self.assertNotIn('private-unknown-operand', json.dumps(refusal))

    def test_candidate_success_does_not_bypass_actual_original_final_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            refusal, calls, stages, unused = native_order_control(self, Path(temporary),
                retained_candidate_export=True, valid_later_evidence=True)
            self.assertEqual(refusal['refusal_code'], 'attachment-contract-refused')
            self.assertEqual(refusal['stage'], 'attachment-contract-final')
            report = refusal['validated_partial_report']
            self.assertTrue(report['attachment_identity_candidate']['candidate_qualified'])
            self.assertTrue(report['original_attachment_contract']['fatal_refusal'])
            self.assertFalse(report['accepted']); self.assertFalse(report['full_f10_accepted'])
            self.assertEqual(calls, ['get', 'export'])

    def test_candidate_cleanup_failure_never_reports_qualification(self):
        actual = tempfile.TemporaryDirectory
        class FailedCleanup:
            def __init__(self, **kwargs): self.owned = actual(**kwargs)
            def __enter__(self): return self.owned.__enter__()
            def __exit__(self, *args):
                self.owned.__exit__(*args)
                raise RuntimeError('private-operand cleanup')
        with actual() as temporary:
            root = Path(temporary); result = candidate_bundle(root); report = {}
            inspector.replay_original_attachments(root, result, report)
            with patch.object(inspector.tempfile, 'TemporaryDirectory', FailedCleanup):
                self.assertFalse(inspector.attachment_identity_trial(root, result, report))
            proof = report['attachment_identity_candidate']
            self.assertEqual(proof['candidate_helper_outcome'], 'passed'); self.assertFalse(proof['candidate_qualified'])
            self.assertEqual(proof['status'], 'refused'); self.assertNotIn('private-operand', json.dumps(proof))

    def test_actual_original_attachment_helper_accepts_only_original_name_forms(self):
        for form in ('png', 'underscore', 'bare'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = attachment_bundle(root, form); report = {}
                outcome = inspector.replay_original_attachments(root, result, report)
                proof = report['original_attachment_contract']
                self.assertEqual(outcome, form != 'bare')
                self.assertEqual(proof['original_helper_outcome'], 'refused' if form == 'bare' else 'passed')
                self.assertIs(proof['next_profile_predicate'], None if form == 'bare' else True)
                self.assertTrue(proof['original_export_replayed']); self.assertTrue(proof['source_and_import_rechecked'])
                self.assertEqual(proof['predicates']['model_helper_accepts'], form != 'bare')
                self.assertIs(proof['predicates']['independent_document_profile_relation'], True)
                self.assertFalse(proof['predicates']['relation_is_original_next_predicate_execution'])
                if form == 'bare':
                    self.assertEqual(proof['original_helper_refusal']['refusal_code'], 'attachment-original-incomplete')
                    self.assertTrue(all(row['bare_role'] == 1 and row['eligible'] == 0
                                        for row in proof['predicates']['screenshot_name_forms'].values()))

    def test_original_attachment_source_import_pins_precede_execution(self):
        self.assertEqual(inspector.ATTACHMENT_SOURCE_HASHES, {
            'continuation_contract.py': '03a72ae6666b59f829ddd3427067dd2963a3664235f1e5d168041b28cee4e7d1',
            'contract.py': '3bbc7fca067c77b91ad5d4e3fa96a4e98e1d7ade6bfc5c90dd329b56f7eae3af'})
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(inspector.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'foreign source', b'private operand')), \
                patch.object(inspector.importlib.util, 'spec_from_file_location') as loader:
            with self.assertRaisesRegex(RuntimeError, '^original attachment source differs$'):
                inspector.attachment_reference(temporary)
            loader.assert_not_called()
        import contract
        actual_sha = inspector.sha
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(inspector, 'sha', side_effect=lambda path: 'f' * 64 if Path(path) == Path(contract.__file__) else actual_sha(path)), \
                patch.object(inspector.importlib.util, 'spec_from_file_location') as loader:
            with self.assertRaisesRegex(RuntimeError, '^original attachment import differs$'):
                inspector.attachment_reference(temporary)
            loader.assert_not_called()

    def test_original_attachment_profile_mismatch_and_absence_are_not_helper_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); result = attachment_bundle(root); report = {}
            result['checkpoints'][inspector.STAGES[0]]['profile_id'] = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
            self.assertFalse(inspector.replay_original_attachments(root, result, report))
            proof = report['original_attachment_contract']
            self.assertEqual(proof['original_helper_outcome'], 'passed'); self.assertIsNone(proof['original_helper_refusal'])
            self.assertIs(proof['next_profile_predicate'], False); self.assertTrue(proof['fatal_refusal'])
            self.assertIs(proof['predicates']['independent_document_profile_relation'], False)
        with tempfile.TemporaryDirectory() as temporary, patch.object(inspector, 'attachment_reference') as reference:
            report = {}; root = Path(temporary)
            # A fresh xcresult export in another directory is NOT the original.
            regenerated = root / 'regenerated'; regenerated.mkdir(); attachment_bundle(regenerated)
            self.assertTrue(inspector.replay_original_attachments(root, {'files': {}, 'commands': []}, report))
            proof = report['original_attachment_contract']
            self.assertEqual(proof['original_export_status'], 'absent')
            self.assertEqual(proof['original_helper_outcome'], 'unavailable'); self.assertIsNone(proof['next_profile_predicate'])
            reference.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, '^original attachment export missing$'):
                inspector.replay_original_attachments(root, {'files': {}, 'commands': [{'role': 'attachments', 'exit': 0}]}, {})

    def test_original_attachment_invalid_predicates_and_encoded_values_remain_private(self):
        for change in ('duplicate-image', 'duplicate-stages', 'unsafe', 'foreign-case', 'order', 'operation', 'uuid', 'flag', 'malformed-json'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = attachment_bundle(root); directory = root / 'attachments'
                groups = json.loads((directory / 'manifest.json').read_text())
                document = json.loads((directory / 'metadata.json').read_text())
                if change == 'duplicate-image': groups[0]['attachments'].append(dict(groups[0]['attachments'][1]))
                elif change == 'duplicate-stages': groups[0]['attachments'].append(dict(groups[0]['attachments'][0]))
                elif change == 'unsafe': groups[0]['attachments'][1]['exportedFileName'] = '../private-operand'
                elif change == 'foreign-case': groups[0]['testIdentifier'] = 'private-operand'
                elif change == 'order': document['stages'].reverse()
                elif change == 'operation': document['operation'] = 'UHJpdmFjeS0= private-operand'
                elif change == 'uuid': document['profile'] = 'Privacy-aaaa... private-operand'
                elif change == 'flag': document['diagnostic_continuation'] = 1
                (directory / 'manifest.json').write_text(json.dumps(groups))
                (directory / 'metadata.json').write_text('private-operand not JSON' if change == 'malformed-json' else json.dumps(document))
                result['files'] = {'attachments/' + name: item for name, item in seal_files(directory).items()}
                report = {}
                if change == 'malformed-json':
                    with self.assertRaises(json.JSONDecodeError): inspector.replay_original_attachments(root, result, report)
                else: self.assertFalse(inspector.replay_original_attachments(root, result, report))
                proof = report['original_attachment_contract']
                self.assertEqual(proof['original_helper_outcome'], 'refused'); self.assertIsNone(proof['next_profile_predicate'])
                for operand in ('private-operand', 'UHJpdmFjeS0=', 'Privacy-aaaa...'):
                    self.assertNotIn(operand, json.dumps(proof))

    def test_original_attachment_replay_rejects_mutation_and_contradictory_model(self):
        actual = inspector.attachment_predicates
        for change in ('prefix', 'namespace', 'contradiction'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); result = attachment_bundle(root); report = {}
                def observe(directory, checkpoints=None):
                    proof = actual(directory, checkpoints)
                    if change == 'prefix':
                        with (directory / 'image0.bin').open('r+b') as file: file.write(b'changed!')
                    elif change == 'namespace': (directory / 'late-file').write_bytes(b'private-operand')
                    else: proof['model_helper_accepts'] = False
                    return proof
                with patch.object(inspector, 'attachment_predicates', side_effect=observe), self.assertRaises(RuntimeError):
                    inspector.replay_original_attachments(root, result, report)
                proof = report['original_attachment_contract']
                self.assertEqual(proof['original_helper_outcome'], 'passed')
                self.assertFalse(proof['original_export_replayed'])

    def test_original_attachment_outcome_latches_before_later_fatal_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            refusal, calls, stages, unused = native_order_control(self, Path(temporary), retained_bare_export=True)
            self.assertEqual(refusal['refusal_code'], 'fixture-failure-shape')
            proof = refusal['validated_partial_report']['original_attachment_contract']
            self.assertEqual(proof['original_helper_outcome'], 'refused')
            self.assertEqual(proof['original_helper_refusal']['refusal_code'], 'attachment-original-incomplete')
            self.assertTrue(proof['fatal_refusal']); self.assertTrue(proof['original_export_replayed'])
            self.assertEqual(calls, ['get', 'export'])
            self.assertLess(stages.index('attachment-contract-replay'), stages.index('xcresult-copy'))
            self.assertNotIn('private-', json.dumps(refusal))

    def test_current_failure_pins_and_actual_profile_dispatch_are_separate(self):
        self.assertEqual(RUN, '40858915090')
        self.assertEqual(SOURCE, '6803602e5791eafa69a6e61bc5499d36cd31d92e')
        self.assertEqual(ARTIFACTS, {
            'macos': (12890808734, 73495841, 'dbe04fd8546e3f287e7255e7cee01532479a0c24ca3c55ac5ddbb1d49fa984f2'),
            'iphone': (12891029288, 201548440, '737c604cde22560e045c5b5edebc6ed5a7a8cbfea9423b1b991550eb2161a60c'),
            'ipad': (12892140802, 204032016, '792bc99aeda70476c54e040dce57c326f8833edb1ad99c01eb723253c5c9053d')})
        self.assertIsNot(ARTIFACTS, inspector.PROFILE_ARTIFACTS)
        with patch('continuation_log_capture.retained_profile', return_value={
                'profile_complete': True, 'performance_gate': True, 'profile_refused': False}) as profile, patch('builtins.print'):
            self.assertTrue(inspector.capture_profile_main())
            profile.assert_called_once_with(ROOT / 'build/apple-password-capture-profile',
                inspector.PROFILE_ARTIFACTS, inspector.PROFILE_SOURCE, inspector.PROFILE_RUN)

    def test_actual_native_helper_requires_member_and_lifecycle_admission(self):
        for options, code in [({'changed_member': True}, 'member-bytes'), ({'sealed': False}, 'unsealed-evidence')]:
            with tempfile.TemporaryDirectory() as temporary:
                refusal, calls, stages, entered = native_order_control(self, Path(temporary), **options)
                self.assertEqual(refusal['refusal_code'], code); self.assertEqual(calls, []); self.assertEqual(entered, 0)
                self.assertNotIn('xcresult-parser', stages); self.assertTrue(refusal['diagnostic_refused'])
        with tempfile.TemporaryDirectory() as temporary:
            refusal, calls, stages, entered = native_order_control(self, Path(temporary), native_present=False)
            self.assertEqual(refusal['refusal_code'], 'required-evidence-absent')
            self.assertEqual(refusal['stage'], 'xcresult-copy'); self.assertEqual(calls, []); self.assertEqual(entered, 1)

    def test_native_partial_evidence_survives_fatal_scan_or_fixture_refusal(self):
        for bad_scan, code, stage in [(False, 'fixture-failure-shape', 'fixture-failures'), (True, 'scan-root', 'scan-summaries')]:
            with tempfile.TemporaryDirectory() as temporary:
                refusal, calls, stages, entered = native_order_control(self, Path(temporary), bad_scan=bad_scan)
                self.assertEqual(calls, ['get', 'export']); self.assertEqual(entered, 1)
                self.assertLess(stages.index('lifecycle-receipt'), stages.index('xcresult-copy'))
                self.assertLess(stages.index('attachment-summary'), stages.index('scan-summaries'))
                self.assertEqual((refusal['stage'], refusal['refusal_code']), (stage, code))
                self.assertTrue(refusal['diagnostic_refused']); self.assertFalse(refusal['accepted'])
                report = refusal['validated_partial_report']
                self.assertEqual(report['xcresult']['issues'][0]['source_line'], 245)
                self.assertEqual(report['completed_checkpoints'], inspector.STAGES)
                self.assertEqual(report['strict_privacy_checks'], dict.fromkeys(inspector.STAGES, False))
                self.assertFalse(report['full_f10_accepted']); self.assertFalse(report['sequence_complete'])
                self.assertNotIn('private-', json.dumps(refusal))

    def test_actual_native_parser_failure_is_finite_not_an_empty_issue_result(self):
        for failure, stage, code in [('exit', 'xcresult-parser', 'xcresult-tool'), ('json', 'xcresult-issues', 'unclassified')]:
            with tempfile.TemporaryDirectory() as temporary:
                refusal, calls, stages, entered = native_order_control(self, Path(temporary), parser_failure=failure)
                self.assertEqual((refusal['stage'], refusal['refusal_code']), (stage, code))
                self.assertEqual(calls, ['get']); self.assertEqual(entered, 1)
                self.assertNotIn('xcresult', refusal['validated_partial_report'])
                self.assertTrue(refusal['diagnostic_refused']); self.assertNotIn('private-', json.dumps(refusal))

    def test_appledouble_structure_is_not_content_or_namespace_acceptance(self):
        plain = appledouble_content(diagnostic_appledouble(resource=b'opaque executable payload'))
        self.assertEqual(plain['attribute_layout'], 'absent')
        self.assertFalse(plain['namespace_accepted']); self.assertFalse(plain['content_semantics_verified'])
        self.assertFalse(plain['resource_fork']['all_zero'])
        attributes = [(b'com.apple.provenance', bytes(8)), (b'private-name-operand', b'private-value-operand')]
        proof = appledouble_content(diagnostic_appledouble(attributes))
        self.assertEqual([row['name_kind'] for row in proof['attributes']], ['provenance', 'other'])
        self.assertEqual([row['all_zero'] for row in proof['attributes']], [True, False])
        self.assertNotIn('private-name-operand', json.dumps(proof))
        self.assertNotIn('private-value-operand', json.dumps(proof))

    def test_appledouble_rejects_header_datafork_alias_trailer_and_truncation(self):
        original = diagnostic_appledouble()
        changes = [(0, '>I', 0x00051600), (4, '>I', 0x00010000), (24, '>H', 1),
            (26, '>I', 1), (38, '>I', 9), (30, '>I', 49), (34, '>I', 33),
            (42, '>I', 81), (46, '>I', 0xffffffff)]
        for offset, encoding, value in changes:
            changed = bytearray(original); struct.pack_into(encoding, changed, offset, value)
            with self.assertRaises(RuntimeError): appledouble_content(bytes(changed))
        for changed in (original[:81], original + b'undeclared bytes', b'not metadata' * 10):
            with self.assertRaises(RuntimeError): appledouble_content(changed)

    def test_appledouble_attribute_ranges_duplicates_names_and_padding_refuse(self):
        original = diagnostic_appledouble([(b'a', b'one'), (b'b', b'two')])
        # Entries start120 and136; data begins152.
        for offset, encoding, value in [(84, '>I', 0), (92, '>I', 0xffffffff),
                (96, '>I', 119), (100, '>I', 1), (104, '>I', 1), (116, '>H', 1),
                (118, '>H', 4097), (120, '>I', 151), (124, '>I', 0xffffffff),
                (128, '>H', 1), (130, '>B', 0), (136, '>I', 153), (144, '>H', 1),
                (147, '>B', ord('a')), (131, '>B', 0xff), (132, '>B', 1), (133, '>B', 1)]:
            changed = bytearray(original); struct.pack_into(encoding, changed, offset, value)
            with self.assertRaises(RuntimeError): appledouble_content(bytes(changed))

    def test_metadata_pairing_is_exact_and_all_unknown_roots_stay_unaccepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'EXReaderHost.app').mkdir()
            (root / 'EXReaderHost.app/EXReaderHost').write_bytes(b'actual executable fixture')
            (root / '__MACOSX/EXReaderHost.app').mkdir(parents=True)
            (root / '__MACOSX/empty').mkdir()
            for name in ('._EXReaderHost.app', 'EXReaderHost.app/._EXReaderHost',
                         'EXReaderHost.app/._missing', '._Foreign.app', 'arbitrary-file'):
                (root / '__MACOSX' / name).write_bytes(diagnostic_appledouble())
            (root / 'other-root').write_bytes(b'not ignored')
            proof = inspector.classify_metadata_tree(root, needles({'user': b'only-test-canary-123456'}))
            self.assertEqual(proof['all_file_count'], 7)
            self.assertEqual(sum(row['paired_host'] for row in proof['metadata_members']), 2)
            self.assertEqual({row['target_kind'] for row in proof['metadata_members']}, {'app-root', 'executable', 'unpaired'})
            self.assertEqual(proof['unpaired_metadata_directory_count'], 1)
            self.assertEqual(proof['other_root_count'], 1)
            self.assertFalse(proof['namespace_accepted']); self.assertFalse(proof['signature_replay_credited'])
            self.assertNotIn('arbitrary-file', json.dumps(proof))

    def test_metadata_and_executable_and_unknown_data_all_scan_encoded_variants(self):
        secret = b'only-test-canary-123456'; variants = needles({'user': secret})
        payload = b'\x00'.join(variants.values())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'EXReaderHost.app').mkdir(); (root / '__MACOSX').mkdir()
            (root / 'EXReaderHost.app/EXReaderHost').write_bytes(payload)
            (root / 'unknown-data').write_bytes(payload)
            (root / '__MACOSX/._EXReaderHost.app').write_bytes(
                diagnostic_appledouble([(b'private-operand', payload)], resource=payload))
            proof = inspector.classify_metadata_tree(root, variants)
            self.assertEqual(proof['hit_variant_labels'], sorted(variants))
            self.assertEqual(proof['metadata_members'][0]['hit_variant_labels'], sorted(variants))
            self.assertEqual(proof['all_file_count'], 3); self.assertEqual(proof['size_skips'], 0)
            self.assertFalse(proof['content_semantics_verified'])
            for value in (secret.decode(), base64.b64encode(secret).decode(), secret.hex(), 'private-operand'):
                self.assertNotIn(value, json.dumps(proof))

    def test_metadata_over_64mib_scans_boundary_and_tail_before_parser_size_refusal(self):
        secret = b'only-test-canary-123456'; variants = needles({'user': secret})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'EXReaderHost.app').mkdir(); (root / '__MACOSX').mkdir()
            path = root / '__MACOSX/._EXReaderHost.app'
            with path.open('wb') as file:
                file.seek(65 * 1024 * 1024 - 7); file.write(secret)
                file.seek(66 * 1024 * 1024); file.write(variants['user:utf16le'])
            proof = inspector.classify_metadata_tree(root, variants)
            row = proof['metadata_members'][0]
            self.assertGreater(row['bytes'], 64 * 1024 * 1024)
            self.assertIn('user:raw', row['hit_variant_labels']); self.assertIn('user:utf16le', row['hit_variant_labels'])
            self.assertEqual(row['classification'], 'unsupported-size-after-complete-scan')
            self.assertEqual(proof['all_bytes'], path.stat().st_size); self.assertEqual(proof['size_skips'], 0)

    def test_metadata_replay_refuses_late_earlier_file_and_prefix_mutation(self):
        variants = needles({'user': b'only-test-canary-123456'})
        for mutation in ('earlier-file', 'prefix', 'after-parse'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); (root / 'EXReaderHost.app').mkdir(); (root / '__MACOSX').mkdir()
                earlier = root / 'EXReaderHost.app/EXReaderHost'; earlier.write_bytes(b'original')
                (root / '__MACOSX/._EXReaderHost.app').write_bytes(diagnostic_appledouble())
                real_scan = inspector.scan_file
                def changed(path, supplied):
                    proof = real_scan(path, supplied)
                    if path.name == '._EXReaderHost.app' and mutation != 'after-parse':
                        if mutation == 'earlier-file': earlier.write_bytes(b'modified')
                        else: (root / 'EXReaderHost.app/late-file').write_bytes(b'late')
                    return proof
                def parsed(data):
                    proof = appledouble_content(data)
                    if mutation == 'after-parse': earlier.write_bytes(b'modified')
                    return proof
                with patch.object(inspector, 'scan_file', changed), \
                        patch.object(inspector, 'appledouble_content', parsed), self.assertRaises(RuntimeError):
                    inspector.classify_metadata_tree(root, variants)

    def test_metadata_oracle_identity_and_old_admission_guard_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); folder = root / 'ios-admission'; folder.mkdir()
            oracle = {'synthetic_only': True, 'source_sha': SOURCE, 'run_id': RUN, 'attempt': '1',
                'user': 'privacy-user-' + 'a' * 32,
                'passwords': {'remembered': 'Privacy-' + 'b' * 64 + '!%:+', 'session': 'Privacy-' + 'c' * 64 + '!%:+'}}
            (root / 'synthetic-oracle-input.json').write_text(json.dumps(oracle))
            manifest = {}
            for phase in ('pre-sign', 'post-sign', 'installed'):
                archive = folder / (phase + '.zip')
                with zipfile.ZipFile(archive, 'w') as zipped:
                    zipped.writestr('EXReaderHost.app/EXReaderHost', b'fixed executable fixture')
                    zipped.writestr('__MACOSX/._EXReaderHost.app', diagnostic_appledouble())
                manifest[phase] = {'archive_bytes': archive.stat().st_size, 'archive_sha256': sha(archive),
                    'files': {'EXReaderHost': {'bytes': len(b'fixed executable fixture'),
                                             'sha256': hashlib.sha256(b'fixed executable fixture').hexdigest()}}}
            (folder / 'manifest.json').write_text(json.dumps(manifest))
            rows = inspector.admission_metadata(root)
            self.assertEqual([row['phase'] for row in rows], ['pre-sign', 'post-sign', 'installed'])
            self.assertTrue(all(row['all_file_count'] == 2 and not row['namespace_accepted'] for row in rows))
            with self.assertRaisesRegex(RuntimeError, '^admission archive namespace differs$'):
                authenticator.verify_ios_admission(root, SOURCE, {}, require_program=False)
            for field in ('host-files', 'archive-hash'):
                changed = copy.deepcopy(manifest)
                if field == 'host-files': changed['installed']['files']['EXReaderHost']['sha256'] = 'f' * 64
                else: changed['installed']['archive_sha256'] = 'f' * 64
                (folder / 'manifest.json').write_text(json.dumps(changed))
                with self.assertRaisesRegex(RuntimeError, '^admission (archive members|original archive) differ(?:s)?$'):
                    inspector.admission_metadata(root)
            (folder / 'manifest.json').write_text(json.dumps(manifest))
            for changed in (dict(oracle, synthetic_only=1), dict(oracle, attempt=1), dict(oracle, source_sha='f' * 40),
                    dict(oracle, user='private-operand'), dict(oracle, passwords={'remembered': 'private-operand'})):
                (root / 'synthetic-oracle-input.json').write_text(json.dumps(changed))
                with self.assertRaises(RuntimeError): inspector.metadata_variants(root)

    def test_original_source_bytes_are_bound_to_pin_not_current_checkout(self):
        data = b'fixed source\nsecond line\n'
        record = {'type': 'file', 'path': SOURCE_FILE, 'encoding': 'base64',
                  'size': len(data), 'content': base64.b64encode(data).decode()}
        digest = hashlib.sha256(data).hexdigest()
        proof = inspector.verify_frozen_ui_source(record, digest, 2)
        self.assertTrue(proof['immutable_source_bytes_verified'])
        for changed in (dict(record, path='foreign.swift'), dict(record, size=True),
                dict(record, size=len(data) + 1), dict(record, encoding='other'),
                dict(record, content=base64.b64encode(b'changed source').decode())):
            with self.assertRaises(RuntimeError): inspector.verify_frozen_ui_source(changed, digest, 2)
        with self.assertRaises(RuntimeError): inspector.verify_frozen_ui_source(record, 'f' * 64, 2)
        with self.assertRaises(RuntimeError): inspector.verify_frozen_ui_source(record, digest, 3)

    def test_namespace_categories_observe_but_never_waive_extra_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); folder = root / 'ios-admission'; folder.mkdir()
            manifest = {}
            for phase in ('pre-sign', 'post-sign', 'installed'):
                archive = folder / (phase + '.zip')
                with zipfile.ZipFile(archive, 'w') as zipped:
                    zipped.writestr('EXReaderHost.app/Info.plist', b'fixed fixture')
                    zipped.writestr('__MACOSX/._EXReaderHost.app', b'fixed metadata fixture')
                    zipped.writestr('private-operand/root', b'fixed unknown fixture')
                manifest[phase] = {'archive_bytes': archive.stat().st_size, 'archive_sha256': sha(archive)}
            (folder / 'manifest.json').write_text(json.dumps(manifest))
            rows = inspector.admission_namespaces(root)
            self.assertEqual([row['phase'] for row in rows], ['pre-sign', 'post-sign', 'installed'])
            for row in rows:
                self.assertEqual(row['root_categories'], {role: {'directories': 1, 'files': 0}
                    for role in ('host-app', 'metadata-named', 'other')})
                self.assertEqual(row['all_member_count'], 3); self.assertFalse(row['namespace_accepted'])
            self.assertNotIn('private-operand', json.dumps(rows))
            with self.assertRaisesRegex(RuntimeError, '^admission archive namespace differs$'):
                authenticator.verify_ios_admission(root, 'a' * 40, {}, require_program=False)

    def test_each_platform_is_attempted_and_each_refusal_stays_fatal(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(inspector, 'COMPLETED_REPORTS', []), \
                patch.object(inspector, 'CURRENT_PLATFORM', None), patch.object(inspector, 'CURRENT_MEMBER_INTEGRITY', None), \
                patch.object(inspector, 'CURRENT_SAFE_REPORT', None), patch('builtins.print'):
            attempted = []
            def diagnostic(out, platform, identifier, size, digest):
                attempted.append(platform)
                partial = {'accepted': False, 'platform': platform, 'full_f10_accepted': False}
                if platform == 'iphone':
                    inspector.CURRENT_SAFE_REPORT = partial
                    inspector.diagnostic_stage('admission-replay')
                    raise RuntimeError('admission archive namespace differs')
                return partial
            self.assertFalse(inspector.run_platforms(Path(temporary), diagnostic))
            self.assertEqual(attempted, ['macos', 'iphone', 'ipad'])
            reports = json.loads((Path(temporary) / 'diagnostic.json').read_text())
            self.assertEqual(len(reports), 3)
            self.assertTrue(reports[1]['diagnostic_refused'])
            self.assertEqual(reports[1]['refusal_code'], 'admission-namespace')
            self.assertIsNone(reports[1]['member_integrity'])
            self.assertFalse(reports[1]['validated_partial_report']['accepted'])
            self.assertEqual(reports[2]['platform'], 'ipad')
            self.assertTrue(all(row['accepted'] is False for row in reports))
        inspector.diagnostic_stage('entry')

    def test_failed_native_admission_replay_cannot_disable_default_program_binding(self):
        # Synthetic protocol app, not a runnable binary/native signature proof.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); folder = root / 'ios-admission'; folder.mkdir()
            app = root / 'EXReaderHost.app'; app.mkdir(); (app / 'Frameworks').mkdir()
            (app / 'EXReaderHost').write_bytes(diagnostic_control_macho(ENTITLEMENT_FILE.read_bytes()))
            (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': BUNDLE,
                'CFBundleExecutable': 'EXReaderHost', 'EXRSourceSHA': 'a' * 40,
                'EXRSDKVersion': '3.42.0', 'EXRPageThemeEnabled': True}))
            (app / 'Frameworks/libexreader.3.42.0.dylib').write_bytes(b'protocol-only SDK')
            files = seal_files(app); identity = admission_app_identity(app, 'a' * 40, files)
            display = ('Identifier=' + BUNDLE + '\nSignature=adhoc\nTeamIdentifier=not set\n').encode()
            identity['signature'] = signature_summary(display, 0)
            manifest = {}
            for phase in ('pre-sign', 'post-sign', 'installed'):
                archive = folder / (phase + '.zip')
                with zipfile.ZipFile(archive, 'w') as zipped:
                    for name in files: zipped.write(app / name, 'EXReaderHost.app/' + name)
                manifest[phase] = dict(copy.deepcopy(identity), archive_sha256=sha(archive),
                    archive_bytes=archive.stat().st_size, signature_display_exit=0, signature_verify_exit=0)
                (folder / (phase + '-display.stdout')).write_bytes(b'')
                (folder / (phase + '-display.stderr')).write_bytes(display)
            (folder / 'manifest.json').write_text(json.dumps(manifest))
            result = {'ios_admission_summary': dict(verify_admission_transition(identity, identity, identity), status='verified-comparison'),
                'commands': [{'role': role, 'exit': 65 if role == 'native' else 0} for role in [
                    'build-for-testing', 'admission-pre-sign-archive', 'admission-host-sign',
                    'admission-post-sign-display', 'admission-post-sign-verify', 'admission-post-sign-archive',
                    'native', 'admission-installed-path', 'admission-installed-display', 'admission-installed-verify',
                    'admission-installed-archive']]}
            with patch.object(authenticator.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'', display)):
                report = authenticator.verify_ios_admission(root, 'a' * 40, result, require_program=False)
                self.assertTrue(report['built_and_installed_verified'])
                self.assertFalse(report['complete_program_binding_checked'])
                self.assertFalse(report['native_sequence_acceptance']); self.assertFalse(report['full_f10_accepted'])
                with self.assertRaises(KeyError): authenticator.verify_ios_admission(root, 'a' * 40, result)
                result['program'] = {'sha256': identity['binary']['sha256'],
                    'runtime_sha256': identity['libraries']['Frameworks/libexreader.3.42.0.dylib']['sha256']}
                self.assertTrue(authenticator.verify_ios_admission(root, 'a' * 40, result)['complete_program_binding_checked'])
                result['program']['sha256'] = 'f' * 64
                with self.assertRaisesRegex(RuntimeError, '^admission program binding differs$'):
                    authenticator.verify_ios_admission(root, 'a' * 40, result)
                with self.assertRaises(RuntimeError): authenticator.verify_ios_admission(root, 'a' * 40, result, require_program=0)
                (folder / 'installed.zip').write_bytes(b'altered archive')
                with self.assertRaisesRegex(RuntimeError, '^admission original archive differs$'):
                    authenticator.verify_ios_admission(root, 'a' * 40, result, require_program=False)

    def test_admission_command_roles_are_exact_finite_tokens(self):
        base = {'accepted': False, 'diagnostic_only': True, 'full_f10_accepted': False,
                'sequence_complete': False, 'strict_privacy_checks': {}, 'checkpoints': {}, 'failure': 'RuntimeError'}
        for role in inspector.ADMISSION_COMMAND_ROLES:
            result = dict(base, commands=[{'role': role, 'exit': 0}])
            self.assertEqual(safe_progress(result, set())['commands'], result['commands'])
            for operand in ('private-operand', 'Privacy-aaa...', 'UHJpdmFjeS0='):
                altered = dict(base, commands=[{'role': role + operand, 'exit': 0}])
                with self.assertRaisesRegex(RuntimeError, '^unexpected command shape$'): safe_progress(altered, set())

    def test_sealed_lifecycle_receipt_refuses_missing_false_or_arbitrary_fields(self):
        receipt = {'admission_closed': True, 'active_handlers': 0, 'admitted_handlers': 532,
            'rejected_handlers': 0, 'serving_stopped': True, 'drained': True, 'failed': False,
            'cleanup': {'certificate': 'completed', 'simulator-shutdown': 'not-required', 'simulator-erase': 'not-required'},
            'outer_limit_seconds': 4800, 'drain_limit_seconds': 90}
        result = {'evidence_sealed': True, 'lifecycle': receipt}
        self.assertEqual(sealed_lifecycle(result, 'macos'), receipt)
        for value in ({}, {'evidence_sealed': False, 'lifecycle': receipt},
                dict(result, lifecycle=dict(receipt, active_handlers=1)),
                dict(result, lifecycle=dict(receipt, failed=True)),
                dict(result, lifecycle=dict(receipt, extra='private operand'))):
            with self.assertRaises(RuntimeError): sealed_lifecycle(value, 'macos')
        for raw in list(needles({'secret': b'Privacy-' + b'f' * 64 + b'!%:+'}).values()) + [b'Privacy-fff...']:
            altered = dict(receipt, cleanup=dict(receipt['cleanup'], certificate=raw.decode('utf-8', errors='replace')))
            with self.assertRaisesRegex(RuntimeError, '^lifecycle cleanup incomplete$'):
                sealed_lifecycle(dict(result, lifecycle=altered), 'macos')

    def test_member_integrity_checks_all_and_keeps_size_and_hash_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            payloads = {'native.log': b'old', 'privacy.xcresult/Info.plist': b'plist',
                        'privacy.xcresult/Data/data.private-operand': b'data', 'private-operand.txt': b'other'}
            manifest = {}
            for name, data in payloads.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
                manifest[name] = {'bytes': len(data), 'sha256': sha(path)}
            self.assertEqual(member_integrity(root, manifest)['mismatch_count'], 0)
            (root / 'native.log').write_bytes(b'longer')
            (root / 'privacy.xcresult/Info.plist').write_bytes(b'PLIST')
            manifest['private-operand.txt']['bytes'] += 1
            report = member_integrity(root, manifest)
            self.assertTrue(report['complete']); self.assertEqual(report['member_count'], 4)
            self.assertEqual(report['mismatch_count'], 3)
            self.assertEqual(report['mismatch_groups'], [
                {'role': 'native-log', 'size_matches': False, 'hash_matches': False, 'count': 1},
                {'role': 'other', 'size_matches': False, 'hash_matches': True, 'count': 1},
                {'role': 'xcresult-info', 'size_matches': True, 'hash_matches': False, 'count': 1}])
            self.assertFalse(report['acceptance'])
            self.assertNotIn('private-operand', str(report))

    def test_member_role_never_echoes_encoded_truncated_or_spoofed_names(self):
        self.assertEqual(member_role('native.log'), 'native-log')
        self.assertEqual(member_role('sensitive-synthetic-product-logs/remember_closed/host-unified.json'), 'product-log')
        for raw in list(needles({'secret': b'Privacy-' + b'e' * 64 + b'!%:+'}).values()) + [b'Privacy-eee...']:
            operand = raw.decode('utf-8', errors='replace')
            for name, expected in ((operand, 'other'), ('native.log' + operand, 'other'),
                    ('privacy.xcresult/Data/' + operand, 'xcresult-data'), ('adapter/' + operand, 'adapter')):
                self.assertEqual(member_role(name), expected)
                self.assertNotIn(operand, member_role(name))

    def test_member_metadata_refuses_unknown_types_without_operand_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / 'native.log'; path.write_bytes(b'known')
            valid = {'bytes': path.stat().st_size, 'sha256': sha(path)}
            for item in ({'bytes': True, 'sha256': valid['sha256']}, {'bytes': -1, 'sha256': valid['sha256']},
                    dict(valid, sha256='private-operand'), dict(valid, extra='private-operand'), 'private-operand'):
                with self.assertRaisesRegex(RuntimeError, '^unexpected member metadata$'):
                    member_integrity(root, {'native.log': item})

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

    def test_historical_profile_artifacts_and_source_extent_remain_exact(self):
        self.assertEqual(inspector.PROFILE_RUN, '40839064448')
        self.assertEqual(inspector.PROFILE_SOURCE, 'abd16571fda41b5bc936fcbcfb9a125554992c2e')
        self.assertEqual(inspector.PROFILE_ARTIFACTS, {
            'macos': (12882218229, 165944812, '8e57858429168377b890a533de823b66dd215fe5279a402c4fd103fbda196987'),
            'iphone': (12882548477, 215120884, '3375a7fbbd91697532c6447b3f336715a8512039c6f89efad736342a60a3133b'),
            'ipad': (12883131501, 160391222, '001a9b42d19044057fcc5ecf580cffa60050a837b1d9a6a38f46d49277365dda')})
        self.assertEqual(SOURCE_SHA, '92629443887d6218722d65b9c4a545f90341fa65167ff8cdd73bde52921cca5f')
        self.assertEqual(SOURCE_LAST_LINE, 301)

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

    def test_absent_first_checkpoint_is_not_an_observed_zero_boundary(self):
        root = 'https://127.0.0.1:12345/privacy-' + 'a' * 24 + '/'
        absent = {'root': root, 'checkpoints': {}}
        row = {'credential': 'remembered', 'method': 'GET', 'path': '/privacy-' + 'a' * 24 + '/fixed'}
        for rows in ([], [row]):
            proof = network_summary(absent, rows)
            self.assertFalse(proof['first_checkpoint_observed']); self.assertEqual(proof['total_requests'], len(rows))
            for key in ('before_first_checkpoint', 'after_first_checkpoint', 'credential_method_counts_after_first',
                        'distinct_revision_shards_after_first'): self.assertIsNone(proof[key])
        observed = network_summary({'root': root, 'checkpoints': {'remember_closed': {'network_requests': 0}}}, [])
        self.assertTrue(observed['first_checkpoint_observed']); self.assertEqual(observed['after_first_checkpoint'], 0)
        self.assertEqual(observed['distinct_revision_shards_after_first']['remembered'], 0)
        for boundary in (True, -1, 1, None, 'private-operand'):
            with self.assertRaises(RuntimeError): network_summary({'root': root,
                'checkpoints': {'remember_closed': {'network_requests': boundary}}}, [])
        with self.assertRaises(RuntimeError): network_summary({'root': root,
            'checkpoints': {'remember_reopened': {'network_requests': 0}}}, [])
        with self.assertRaises(RuntimeError): network_summary(absent, [dict(row, path='/private-operand')])

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
