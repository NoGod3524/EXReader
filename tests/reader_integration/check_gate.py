# SPDX-License-Identifier: MIT
"""Cloud rejection regression for the product preintegration evidence boundary."""
import copy
import io
import json
import os
from pathlib import Path
import stat
import sys
import unittest
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_reader_product_integration import (JOBS, WORKFLOW, checks, identity, report_bytes,
                                               validate_archive, verify_metadata, verify_reports)

SOURCE, RUN, ATTEMPT = 'a' * 40, 123, 2


def fixture():
    run = {'id': RUN, 'head_sha': SOURCE, 'run_attempt': ATTEMPT, 'path': WORKFLOW, 'event': 'push',
           'status': 'in_progress', 'conclusion': None}
    jobs = [{'id': i + 1, 'name': name, 'run_id': RUN, 'head_sha': SOURCE, 'run_attempt': ATTEMPT,
             'status': 'completed', 'conclusion': 'success'}
            for i, name in enumerate(JOBS)]
    jobs.append({**jobs[0], 'id': 5, 'name': 'strict preintegration summary',
                 'status': 'in_progress', 'conclusion': None})
    artifacts = [{'id': i + 1, 'name': f'{prefix}-{platform}-{RUN}-{ATTEMPT}', 'expired': False,
                  'size_in_bytes': 100, 'digest': 'sha256:' + 'b' * 64,
                  'workflow_run': {'id': RUN, 'head_sha': SOURCE}}
                 for i, (prefix, platform) in enumerate(JOBS.values())]
    return run, jobs, artifacts


class Gate(unittest.TestCase):
    def test_current_running_summary_with_four_completed_upstreams_is_valid(self):
        verify_metadata(*fixture(), SOURCE, RUN, ATTEMPT)

    def test_prior_attempt_records_retained_without_taking_their_evidence(self):
        run, jobs, artifacts = fixture()
        previous = {**artifacts[0], 'id': 99, 'name': f'reader-desktop-sdk-Linux-{RUN}-1', 'expired': True}
        self.assertEqual(len(verify_metadata(run, jobs, artifacts + [previous], SOURCE, RUN, ATTEMPT)), 4)
        with self.assertRaises(ValueError):
            verify_metadata(run, jobs, artifacts[1:] + [previous], SOURCE, RUN, ATTEMPT)

    def test_metadata_substitutions_are_rejected(self):
        mutations = [
            ('caller-source', lambda r, j, a: r.update(head_sha='c' * 40)),
            ('caller-attempt', lambda r, j, a: r.update(run_attempt=1)),
            ('caller-workflow', lambda r, j, a: r.update(path='.github/workflows/reader-commands.yml')),
            ('pull-request-source', lambda r, j, a: r.update(event='pull_request')),
            ('missing-job', lambda r, j, a: j.pop(0)),
            ('duplicate-job-id', lambda r, j, a: j[0].update(id=j[1]['id'])),
            ('unexpected-job', lambda r, j, a: j[0].update(name='old workflow')),
            ('foreign-job-source', lambda r, j, a: j[0].update(head_sha='c' * 40)),
            ('foreign-job-run', lambda r, j, a: j[0].update(run_id=1)),
            ('partial-rerun-old-job', lambda r, j, a: j[0].update(run_attempt=1)),
            ('failed-job', lambda r, j, a: j[0].update(conclusion='failure')),
            ('skipped-job', lambda r, j, a: j[0].update(conclusion='skipped')),
            ('cancelled-job', lambda r, j, a: j[0].update(conclusion='cancelled')),
            ('running-job', lambda r, j, a: j[0].update(status='in_progress')),
            ('missing-artifact', lambda r, j, a: a.pop()),
            ('duplicate-artifact-id', lambda r, j, a: a[0].update(id=a[1]['id'])),
            ('old-attempt-artifact', lambda r, j, a: a[0].update(name='reader-commands-Linux-123-1')),
            ('expired-artifact', lambda r, j, a: a[0].update(expired=True)),
            ('empty-artifact', lambda r, j, a: a[0].update(size_in_bytes=0)),
            ('missing-digest', lambda r, j, a: a[0].pop('digest')),
            ('foreign-artifact-run', lambda r, j, a: a[0]['workflow_run'].update(id=1)),
            ('foreign-artifact-source', lambda r, j, a: a[0]['workflow_run'].update(head_sha='c' * 40)),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                run, jobs, artifacts = fixture()
                mutate(run, jobs, artifacts)
                with self.assertRaises(ValueError):
                    verify_metadata(run, jobs, artifacts, SOURCE, RUN, ATTEMPT)

    def test_report_identity_and_unique_non_skipped_checks(self):
        original = {'source_sha': SOURCE, 'run_id': str(RUN), 'attempt': str(ATTEMPT)}
        identity(original, SOURCE, RUN, ATTEMPT)
        for field, value in [('source_sha', 'b' * 40), ('run_id', '1'), ('attempt', '1'),
                             ('complete_product', True), ('problems', ['refused'])]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                identity({**original, field: value}, SOURCE, RUN, ATTEMPT)
        checks([{'id': 'one', 'pass': True}, {'id': 'two', 'pass': True}], 2, flag='pass')
        for rows in ([{'id': 'one', 'pass': True}], [{'id': 'one', 'pass': True}] * 2,
                     [{'id': 'one', 'pass': True}, {'id': 'two', 'pass': False}],
                     [{'id': 'one', 'pass': True}, {'id': 'two', 'pass': 'skipped'}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                checks(rows, 2, flag='pass')

    def test_native_module_scope_contract(self):
        reports = {}
        for folder, count in [('sync-source-evidence', 77), ('sync-protocol-evidence', 59),
                              ('sync-evidence', 33), ('projection-evidence', 32), ('commands-evidence', 33), ('metadata-evidence', 29)]:
            reports[folder + '/result.json'] = {
                'accepted': True, 'source_sha': SOURCE, 'run_id': str(RUN), 'attempt': str(ATTEMPT),
                'count': count, 'platform': 'linux', 'checks': [{'id': str(i), 'pass': True} for i in range(count)],
                'complete_product': False}
        reports['sync-evidence/result.json'].update(shards=256, entries_per_shard_ceiling=2000, full_library_complete=False)
        reports['projection-evidence/result.json'].update(metadata_history_outbox_same_product_transaction=True, sdk_database_writes=False)
        reports['commands-evidence/result.json'].update(native_only_wire_producer=True, schema1_changed=False,
                                                       sdk_database_writes=False, mobile_accepted=False)
        reports['metadata-evidence/result.json'].update(
            checks=[str(i) for i in range(29)], native_adapter_only=True, sdk_database_writes=False,
            schema1_changed=False, wire_changed=False, desktop_ui_accepted=False,
            sdk_source_verification_accepted=False, consumer_sha256='b' * 64)

        def verify(values):
            return verify_reports('reader-commands', 'Linux', lambda n: json.dumps(values[n]).encode(), SOURCE, RUN, ATTEMPT)

        self.assertEqual(len(verify(reports)), 6)
        for name, field, value in [('sync-evidence', 'full_library_complete', True),
                                   ('sync-evidence', 'shards', 1),
                                   ('projection-evidence', 'metadata_history_outbox_same_product_transaction', False),
                                   ('commands-evidence', 'native_only_wire_producer', False),
                                   ('commands-evidence', 'sdk_database_writes', True),
                                   ('commands-evidence', 'mobile_accepted', True),
                                   ('commands-evidence', 'schema1_changed', True),
                                   ('commands-evidence', 'accepted', False),
                                   ('commands-evidence', 'attempt', '1'),
                                   ('metadata-evidence', 'desktop_ui_accepted', True),
                                   ('metadata-evidence', 'schema1_changed', True),
                                   ('metadata-evidence', 'consumer_sha256', 'invalid')]:
            with self.subTest(name=name, field=field), self.assertRaises(ValueError):
                changed = copy.deepcopy(reports)
                changed[name + '/result.json'][field] = value
                verify(changed)
        with self.assertRaises(KeyError):
            verify({k: v for k, v in reports.items() if k != 'commands-evidence/result.json'})

    def test_archive_rejects_unsafe_duplicate_and_symlink_members(self):
        for names in (['../result.json'], ['/result.json'], ['C:/result.json'], ['x\\result.json'],
                      ['result.json', 'result.json']):
            with self.subTest(names=names):
                stream = io.BytesIO()
                with warnings.catch_warnings(), zipfile.ZipFile(stream, 'w') as archive:
                    warnings.simplefilter('ignore', UserWarning)
                    for name in names:
                        archive.writestr(name, '{}')
                stream.seek(0)
                with zipfile.ZipFile(stream) as archive, self.assertRaises(ValueError):
                    validate_archive(archive)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            link = zipfile.ZipInfo('link.json')
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, 'target')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive, self.assertRaises(ValueError):
            validate_archive(archive)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('result.json', '{}')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            validate_archive(archive)
            self.assertEqual(report_bytes(archive, 'result.json'), b'{}')


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run rejection regression only in GitHub Actions')
    unittest.main(verbosity=2)
