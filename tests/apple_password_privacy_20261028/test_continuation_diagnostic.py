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


class ContinuationDiagnosticControls(unittest.TestCase):
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

    def test_current_three_artifacts_and_source_extent_are_exact(self):
        self.assertEqual(RUN, '40839064448')
        self.assertEqual(SOURCE, 'abd16571fda41b5bc936fcbcfb9a125554992c2e')
        self.assertEqual(ARTIFACTS, {
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
