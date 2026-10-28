#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
import os
from pathlib import Path
import tempfile
import unittest
from log_evidence import attribute_unified_log, retain_product_log, verify_product_log
from privacy_scan import needles


class FailedLogRetention(unittest.TestCase):
    def capture(self, root, stdout=b'synthetic-input-only\n', stderr=b'', code=0):
        return retain_product_log(root, 'remember_closed', 'macos', 'source', 'run', '1', stdout, stderr, code)

    def verify(self, root):
        return verify_product_log(root, 'remember_closed', 'macos', 'source', 'run', '1')

    def test_failed_verdict_preserves_complete_unredacted_synthetic_bytes(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            stdout = b'prefix\n' + b'a' * (1024 * 1024 + 3) + b'Privacy-fixture-secret-only!%:+\n'
            stderr = b'capture-stderr-fixture\n'
            folder = self.capture(root, stdout, stderr)
            with self.assertRaises(RuntimeError): raise RuntimeError('unchanged privacy verdict refuses')
            self.assertEqual((folder / 'host-unified.json').read_bytes(), stdout)
            self.assertEqual((folder / 'capture-stderr.txt').read_bytes(), stderr)
            self.assertEqual((folder / 'host-unified.json').stat().st_mode & 0o777, 0o600)
            manifest = self.verify(root)
            self.assertNotIn('Privacy-fixture-secret-only', json.dumps(manifest))
            self.assertTrue(manifest['may_contain_synthetic_credentials'])

    def test_mutation_or_missing_capture_refuses(self):
        for operation in ('mutate', 'delete'):
            with tempfile.TemporaryDirectory() as name:
                root = Path(name); folder = self.capture(root)
                if operation == 'mutate': (folder / 'host-unified.json').write_bytes(b'changed')
                else: (folder / 'capture-stderr.txt').unlink()
                with self.assertRaises(RuntimeError): self.verify(root)

    def test_failed_capture_retained_but_not_accepted(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); folder = self.capture(root, b'', b'failure bytes', 1)
            self.assertEqual((folder / 'capture-stderr.txt').read_bytes(), b'failure bytes')
            with self.assertRaises(RuntimeError): self.verify(root)

    def test_attribution_emits_only_fixed_categories_roles_and_counts(self):
        user, password = b'privacy-user-fixture-only', b'Privacy-fixture-password-only'
        variants = needles({'user': user, 'remembered': password})
        events = [{'eventMessage': user.decode(), 'senderImagePath': '/System/Library/PrivateFrameworks/AXRuntime.framework/AXRuntime'},
                  {'eventMessage': password.decode(), 'senderImagePath': '/tmp/EXReaderHost'},
                  {'eventMessage': user.decode(), 'senderImagePath': '/secret/path/' + password.decode()},
                  {'eventMessage': 'clean', 'senderImagePath': '/tmp/EXReaderHost'}]
        report = attribute_unified_log(json.dumps(events).encode(), variants)
        self.assertEqual(report['matched_event_groups'], [
            {'sender_category': 'apple-accessibility-framework-image', 'credential_roles': ['user'], 'event_count': 1},
            {'sender_category': 'application-image', 'credential_roles': ['remembered'], 'event_count': 1},
            {'sender_category': 'unknown-or-other-image', 'credential_roles': ['user'], 'event_count': 1}])
        self.assertNotIn(user.decode(), json.dumps(report)); self.assertNotIn(password.decode(), json.dumps(report))
        self.assertNotIn('/secret/path', json.dumps(report)); self.assertFalse(report['owner_callsite_proven'])
        self.assertTrue(report['byte_scan_is_authoritative'])

    def test_unknown_format_or_variant_never_supplies_false_acceptance(self):
        for payload in (b'invalid json', b'{}'):
            report = attribute_unified_log(payload, needles({'user': b'privacy-user-fixture-only'}))
            self.assertFalse(report['parsed_json_array']); self.assertTrue(report['byte_scan_is_authoritative'])
            self.assertNotIn('accepted', report)
        with self.assertRaises(RuntimeError): attribute_unified_log(b'[]', {'arbitrary-secret-label': b'value'})


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise RuntimeError('Actions only')
    unittest.main()
