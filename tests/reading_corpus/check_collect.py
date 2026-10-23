#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline collector protocol; invoked only by Actions before real collection."""
from contextlib import contextmanager, redirect_stdout
from email.utils import formatdate
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/reading_corpus'))
import collect
import frozen

URL = 'https://publisher.invalid/original.pdf'
NOW = 1800000000


def response(data=b'original', url=URL):
    result = io.BytesIO(data)
    result.url = url
    return result


def error(code=429, retry_after=None, url=URL):
    headers = {} if retry_after is None else {'Retry-After': retry_after}
    return urllib.error.HTTPError(url, code, 'test response', headers, io.BytesIO())


@contextmanager
def network(results):
    elapsed = [0]

    def sleep(seconds):
        elapsed[0] += seconds

    with patch.object(collect.urllib.request, 'urlopen', side_effect=results) as opened, \
            patch.object(collect.time, 'monotonic', side_effect=lambda: elapsed[0]), \
            patch.object(collect.time, 'time', side_effect=lambda: NOW + elapsed[0]), \
            patch.object(collect.time, 'sleep', side_effect=sleep) as slept:
        yield opened, slept


class CollectorProtocol(unittest.TestCase):
    def test_429_then_success_honors_retry_after_seconds(self):
        with network([error(retry_after='3'), response()]) as (opened, slept):
            self.assertEqual(collect.fetch(URL, 8), (b'original', URL))
            self.assertEqual(opened.call_count, 2)
            slept.assert_called_once_with(3)

    def test_retry_after_http_date(self):
        date = formatdate(NOW + 7, usegmt=True)
        with network([error(retry_after=date), response()]) as (opened, slept):
            self.assertEqual(collect.fetch(URL, 8)[0], b'original')
            slept.assert_called_once_with(7)

    def test_429_exhaustion_fails_after_four_requests(self):
        with network([error() for _ in range(4)]) as (opened, slept):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                collect.fetch(URL, 8)
            self.assertEqual(raised.exception.code, 429)
            self.assertEqual(opened.call_count, 4)
            self.assertEqual([call.args[0] for call in slept.call_args_list], [2, 4, 8])

    def test_retry_after_exceeding_total_window_fails_without_shortening(self):
        for value in ('180', '9' * 5000, formatdate(NOW + 181, usegmt=True)):
            with self.subTest(value=value[:50]), network([error(retry_after=value)]) as (opened, slept):
                with self.assertRaises(urllib.error.HTTPError):
                    collect.fetch(URL, 8)
                self.assertEqual(opened.call_count, 1)
                slept.assert_not_called()
        with network([error(retry_after='100'), error(retry_after='100')]) as (opened, slept):
            with self.assertRaises(urllib.error.HTTPError):
                collect.fetch(URL, 8)
            self.assertEqual(opened.call_count, 2)
            slept.assert_called_once_with(100)

    def test_remaining_retry_window_bounds_the_next_request_timeout(self):
        with network([error(retry_after='150'), response()]) as (opened, slept):
            self.assertEqual(collect.fetch(URL, 8)[0], b'original')
            self.assertEqual([call.kwargs['timeout'] for call in opened.call_args_list], [60, 30])

    def test_invalid_retry_after_uses_bounded_fallback(self):
        with network([error(retry_after='invalid'), response()]) as (opened, slept):
            self.assertEqual(collect.fetch(URL, 8)[0], b'original')
            slept.assert_called_once_with(2)

    def test_other_errors_fail_immediately(self):
        for failure in (error(404), error(503), urllib.error.URLError('connection failed')):
            with self.subTest(error=type(failure).__name__), network([failure]) as (opened, slept):
                with self.assertRaises(type(failure)):
                    collect.fetch(URL, 8)
                self.assertEqual(opened.call_count, 1)
                slept.assert_not_called()

    def test_byte_bound_is_preserved(self):
        with network([response(b'original!')]) as (opened, slept):
            with self.assertRaisesRegex(ValueError, 'download bound'):
                collect.fetch(URL, 8)
            self.assertEqual(opened.call_count, 1)
            slept.assert_not_called()

    def test_https_requirement_is_preserved(self):
        with network([]) as (opened, slept):
            with self.assertRaisesRegex(ValueError, 'HTTPS required'):
                collect.fetch('http://publisher.invalid/book', 8)
            opened.assert_not_called()
        for result in (response(url='http://publisher.invalid/book'), error(url='http://publisher.invalid/book')):
            with self.subTest(result=type(result).__name__), network([result]) as (opened, slept):
                with self.assertRaisesRegex(ValueError, 'HTTPS redirect required'):
                    collect.fetch(URL, 8)
                self.assertEqual(opened.call_count, 1)
                slept.assert_not_called()


class FrozenInputProtocol(unittest.TestCase):
    def setUp(self):
        self.rights = b'Permission to copy'
        self.entries = [{'id': 'document-' + str(i), 'path': 'epub/book-' + str(i) + '.epub',
                         'format': 'EPUB', 'source_url': URL + '/' + str(i), 'license_url': URL + '/rights',
                         'license_required_terms': ['Permission to copy'],
                         'sha256': collect.sha(('fixed-' + str(i)).encode()), 'size': 7,
                         'limits': {'download_bytes': 100}} for i in range(8)]
        self.manifest = json.dumps({'files': self.entries}).encode()
        prior = [dict(entry, retrieved_url=entry['source_url'],
                      observed_license_sha256=collect.sha(self.rights)) for entry in self.entries]
        archived = {'files': prior, 'complete': True, 'engine_executed': False,
                    'original_manifest_sha256': collect.sha(self.manifest)}
        self.members = {'inputs/manifest.json': json.dumps(archived).encode()}
        for i, entry in enumerate(self.entries):
            self.members['inputs/assets/' + entry['path']] = ('fixed-' + str(i)).encode()
            self.members['inputs/licenses/' + entry['id'] + '.txt'] = self.rights
        self.registry = {'run_id': 1, 'run_attempt': 1, 'source_sha': 'a' * 40,
                         'workflow': '.github/workflows/reading-required.yml',
                         'artifact_id': 2, 'artifact_name': 'fixed',
                         'manifest_sha256': collect.sha(self.manifest)}
        self.run = {'id': 1, 'run_attempt': 1, 'head_sha': 'a' * 40,
                    'path': self.registry['workflow'], 'status': 'completed', 'conclusion': 'success'}
        self.raw = self.archive(self.members)
        self.artifact = {'id': 2, 'name': 'fixed', 'expired': False,
                         'digest': self.registry['artifact_digest'], 'size_in_bytes': len(self.raw),
                         'workflow_run': {'id': 1, 'head_sha': 'a' * 40}}

    def archive(self, members):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, raw in members.items():
                archive.writestr(name, raw)
        raw = stream.getvalue()
        self.registry.update(artifact_bytes=len(raw), artifact_digest='sha256:' + collect.sha(raw))
        return raw

    def test_registered_archive_restores_eight_exact_raw_inputs(self):
        frozen.verify_origin(self.registry, self.run, [self.artifact])
        inputs, origins = frozen.restore_archive(self.raw, self.manifest, self.registry)
        self.assertEqual(len(inputs), 8)
        for entry in self.entries:
            self.assertEqual(collect.sha(inputs[entry['path']]), entry['sha256'])
            self.assertEqual(origins[entry['path']]['archived_license_sha256'], collect.sha(self.rights))

    def test_changed_run_or_attempt_or_status_is_refused(self):
        for key, value in [('id', 3), ('head_sha', 'b' * 40), ('run_attempt', 2),
                           ('path', 'other.yml'), ('status', 'in_progress'), ('conclusion', 'failure')]:
            with self.subTest(key=key):
                run = dict(self.run, **{key: value})
                with self.assertRaises(ValueError):
                    frozen.verify_origin(self.registry, run, [self.artifact])

    def test_changed_expired_missing_or_duplicate_artifact_is_refused(self):
        for key, value in [('id', 3), ('name', 'other'), ('expired', True),
                           ('size_in_bytes', 1), ('digest', 'sha256:' + 'f' * 64),
                           ('workflow_run', {'id': 3, 'head_sha': 'a' * 40})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                frozen.verify_origin(self.registry, self.run, [dict(self.artifact, **{key: value})])
        for artifacts in ([], [self.artifact, self.artifact]):
            with self.assertRaises(ValueError):
                frozen.verify_origin(self.registry, self.run, artifacts)

    def test_zip_and_manifest_digest_changes_are_refused(self):
        for raw, manifest in ((self.raw + b'changed', self.manifest), (self.raw, self.manifest + b' ')):
            with self.assertRaises(ValueError):
                frozen.restore_archive(raw, manifest, self.registry)

    def test_missing_extra_unsafe_and_duplicate_document_members_are_refused(self):
        name = 'inputs/assets/' + self.entries[0]['path']
        missing = dict(self.members); missing.pop(name)
        for members in (missing, dict(self.members, **{'inputs/assets/extra.epub': b'other'}),
                        dict(self.members, **{'../escape': b'other'}),
                        dict(self.members, **{'C:/escape': b'other'})):
            with self.subTest(names=list(members)[-1]), self.assertRaises(ValueError):
                frozen.restore_archive(self.archive(members), self.manifest, self.registry)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(name, b'first')
            archive.writestr(name, b'second')
        raw = stream.getvalue()
        self.registry.update(artifact_bytes=len(raw), artifact_digest='sha256:' + collect.sha(raw))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            frozen.restore_archive(raw, self.manifest, self.registry)

    def test_document_content_extent_bound_and_license_tampering_are_refused(self):
        name = 'inputs/assets/' + self.entries[0]['path']
        for replacement in (b'wrong-0', b'too-long', b'x' * 101):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                frozen.restore_archive(self.archive(dict(self.members, **{name: replacement})), self.manifest, self.registry)
        license_name = 'inputs/licenses/' + self.entries[0]['id'] + '.txt'
        with self.assertRaisesRegex(ValueError, 'license'):
            frozen.restore_archive(self.archive(dict(self.members, **{license_name: b'changed'})), self.manifest, self.registry)

    def test_cached_collection_still_fetches_current_licenses_and_inspects_every_document(self):
        inputs, origins = frozen.restore_archive(self.raw, self.manifest, self.registry)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = root / 'manifest.json'; manifest.write_bytes(self.manifest)
            for rights, expected in ((self.rights, 0), (b'permission removed', 1)):
                output = root / str(expected)
                with patch.object(sys, 'argv', ['collect', 'cached', str(manifest), str(output)]), \
                        patch.object(frozen, 'recover', return_value=(inputs, origins, self.registry)), \
                        patch.object(collect, 'fetch', return_value=(rights, URL)) as fetched, \
                        patch.object(collect, 'structure', return_value={'inspected': True}) as inspected, \
                        patch.object(collect.time, 'sleep'), redirect_stdout(io.StringIO()):
                    self.assertEqual(collect.main(), expected)
                self.assertEqual(fetched.call_count, 8)
                self.assertTrue(all(call.args[0] == URL + '/rights' for call in fetched.call_args_list))
                self.assertEqual(inspected.call_count, 8 if expected == 0 else 0)
                report = json.loads((output / 'manifest.json').read_bytes())
                self.assertEqual(report['complete'], expected == 0)
                self.assertEqual(report['raw_input_archive'], self.registry)

    def test_direct_mismatch_retains_observed_identity_without_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = root / 'manifest.json'; manifest.write_bytes(self.manifest)
            output = root / 'output'
            with patch.object(sys, 'argv', ['collect', 'collect', str(manifest), str(output)]), \
                    patch.object(collect, 'fetch', return_value=(b'changed', URL + '/final')), \
                    patch.object(frozen, 'recover') as recovered, patch.object(collect.time, 'sleep'), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(collect.main(), 1)
            recovered.assert_not_called()
            report = json.loads((output / 'manifest.json').read_bytes())
            self.assertEqual(len(report['collection_failures']), 8)
            self.assertEqual(report['collection_failures'][0]['observed_source'],
                             {'sha256': collect.sha(b'changed'), 'size': 7, 'final_url': URL + '/final'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
