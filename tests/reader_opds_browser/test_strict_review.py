#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only negative regression tests for strict evidence authentication."""
import copy
import hashlib
import io
import json
import os
import unittest
import zipfile
from check_artifacts import (REQUIRED_CASES, validate_cases, validate_job, validate_members,
                             validate_artifact, unique_object, validate_consumers, validate_report)


def archive_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, payload in entries.items():
            archive.writestr('opds-consumer/' + name, payload)
    return stream.getvalue()


def consumer_report(entries):
    return {'consumers': [{'name': name, 'bytes': len(payload),
                           'sha256': hashlib.sha256(payload).hexdigest()}
                          for name, payload in entries.items()]}


class StrictReview(unittest.TestCase):
    def test_consumer_binary_binding(self):
        for platform in ('linux', 'macos', 'windows'):
            suffix = '.exe' if platform == 'windows' else ''
            entries = {'opds-consumer' + suffix: b'network executable',
                       'opds-import-consumer' + suffix: b'import executable'}
            good = consumer_report(entries)
            with zipfile.ZipFile(io.BytesIO(archive_bytes(entries))) as archive:
                self.assertEqual(len(validate_consumers(archive, good, platform)), 2)
                for field, value in [('bytes', 1), ('sha256', '0' * 64),
                                     ('name', 'unrelated-consumer')]:
                    bad = copy.deepcopy(good)
                    bad['consumers'][0][field] = value
                    with self.subTest(platform=platform, field=field), self.assertRaises(ValueError):
                        validate_consumers(archive, bad, platform)
                bad = copy.deepcopy(good)
                bad['consumers'][1] = copy.deepcopy(bad['consumers'][0])
                with self.subTest(platform=platform, defect='duplicate report'), self.assertRaises(ValueError):
                    validate_consumers(archive, bad, platform)
                with self.subTest(platform=platform, defect='missing receipt'), self.assertRaises(ValueError):
                    validate_consumers(archive, {'consumers': good['consumers'][:1]}, platform)
                wrong_platform = 'linux' if platform == 'windows' else 'windows'
                with self.subTest(platform=platform, defect='wrong platform'), self.assertRaises(ValueError):
                    validate_consumers(archive, good, wrong_platform)
            binary_name = 'opds-consumer' + suffix
            altered = dict(entries, **{binary_name: b'X' + entries[binary_name][1:]})
            with zipfile.ZipFile(io.BytesIO(archive_bytes(altered))) as archive:
                with self.subTest(platform=platform, defect='same-size binary tamper'), self.assertRaises(ValueError):
                    validate_consumers(archive, good, platform)
            empty = dict(entries, **{binary_name: b''})
            with zipfile.ZipFile(io.BytesIO(archive_bytes(empty))) as archive:
                with self.subTest(platform=platform, defect='empty binary'), self.assertRaises(ValueError):
                    validate_consumers(archive, consumer_report(empty), platform)
            missing = {'opds-import-consumer' + suffix: entries['opds-import-consumer' + suffix]}
            with zipfile.ZipFile(io.BytesIO(archive_bytes(missing))) as archive:
                with self.subTest(platform=platform, defect='missing binary'), self.assertRaises(ValueError):
                    validate_consumers(archive, good, platform)

    def test_report_identity(self):
        good = dict(accepted=True, package='EXReaderOpdsBrowser 0.1.0', source_sha='source',
                    run_id=12, attempt=2, platform='linux', sdk_changed=False, schema_changed=False,
                    checks=len(REQUIRED_CASES), cases=[{'id': i, 'ok': True} for i in sorted(REQUIRED_CASES)],
                    origin_isolation=dict(plain_requests_with_authorization=0, tls_requests=2))
        self.assertEqual(len(validate_report(good, 'source', 12, 2, 'linux')), len(REQUIRED_CASES))
        for field, value in [('accepted', False), ('accepted', 'true'), ('package', 'other'),
                             ('source_sha', 'other'), ('run_id', 13), ('attempt', 1),
                             ('platform', 'windows'), ('sdk_changed', True), ('schema_changed', True),
                             ('origin_isolation', dict(plain_requests_with_authorization=1, tls_requests=2)),
                             ('origin_isolation', dict(plain_requests_with_authorization=0, tls_requests=0))]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_report(dict(good, **{field: value}), 'source', 12, 2, 'linux')

    def test_artifact_authentication(self):
        data = b'authenticated ZIP bytes'
        good = dict(id=17, expired=False, size_in_bytes=len(data),
                    expires_at='2999-01-01T00:00:00Z',
                    workflow_run=dict(id=12, head_sha='source'),
                    digest='sha256:' + hashlib.sha256(data).hexdigest())
        validate_artifact(good, data, 'source', 12)
        for field, value in [('id', 0), ('expired', True), ('size_in_bytes', 1),
                             ('expires_at', '2000-01-01T00:00:00Z'),
                             ('digest', 'sha256:' + '0' * 64),
                             ('workflow_run', dict(id=13, head_sha='source')),
                             ('workflow_run', dict(id=12, head_sha='other'))]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_artifact(dict(good, **{field: value}), data, 'source', 12)
        with self.assertRaises(ValueError):
            validate_artifact(good, b'tampered ZIP bytes', 'source', 12)
        with self.assertRaises(ValueError):
            json.loads('{"accepted": false, "accepted": true}', object_pairs_hook=unique_object)

    def test_job_identity(self):
        good = dict(head_sha='source', run_id=12, run_attempt=2,
                    status='completed', conclusion='success')
        validate_job(good, 'source', 12, 2)
        for field, value in [('head_sha', 'other'), ('run_id', 13), ('run_attempt', 1),
                             ('status', 'in_progress'), ('conclusion', 'failure')]:
            with self.subTest(field=field):
                bad = dict(good, **{field: value})
                with self.assertRaises(ValueError):
                    validate_job(bad, 'source', 12, 2)

    def test_members(self):
        good = ['opds-evidence/result.json', 'opds-consumer/opds-consumer']
        validate_members(good)
        for extra in ['opds-evidence/result.json', 'other/result.json', '../escape',
                      '/absolute', 'foo\\bar', 'foo/../bar', 'foo//bar', 'C:/absolute']:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_members(good + [extra])
        with self.assertRaises(ValueError):
            validate_members(['opds-consumer/opds-consumer'])

    def test_cases(self):
        good = {'checks': len(REQUIRED_CASES), 'cases': [{'id': i, 'ok': True} for i in sorted(REQUIRED_CASES)]}
        self.assertEqual(len(validate_cases(good)), len(REQUIRED_CASES))
        for value in [False, 'true', 1, None]:
            bad = copy.deepcopy(good)
            bad['cases'][0]['ok'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_cases(bad)
        bad = copy.deepcopy(good)
        bad['cases'][0]['id'] = bad['cases'][1]['id']
        with self.assertRaises(ValueError):
            validate_cases(bad)
        bad = copy.deepcopy(good)
        bad['checks'] = len(REQUIRED_CASES) - 1
        with self.assertRaises(ValueError):
            validate_cases(bad)
        bad = copy.deepcopy(good)
        bad['cases'][0]['id'] = 'fabricated_replacement'
        with self.assertRaises(ValueError):
            validate_cases(bad)
        with self.assertRaises(ValueError):
            validate_cases({'checks': 59, 'cases': good['cases'][:59]})

if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Actions only: no local tests')
    unittest.main()
