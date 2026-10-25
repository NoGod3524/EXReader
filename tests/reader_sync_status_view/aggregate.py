# SPDX-License-Identifier: MIT
"""Actions-only strict same-run artifact aggregation for the status view.

Downloads each platform artifact archive from the same run/attempt, recomputes
its SHA-256, compares it with the GitHub API digest, and re-verifies every
report identity (source, run, attempt, platform, named checks, consumer bytes)
from inside the archive. Rejects missing, extra, cross-source, cross-attempt or
tampered artifacts instead of summing what happens to be present.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

REQUIRED = {
    'installed_c_and_cpp_consumers_bind_the_public_package',
    'idle_session_only_capture_is_read_only_and_requests_nothing',
    'empty_snapshot_paging_and_argument_paths',
    'running_capture_reports_syncing_phase_before_any_step_completes',
    'cancelled_snapshot_keeps_cursor_and_partial_history_resumable',
    'one_completed_256_shard_sweep_is_not_a_complete_library',
    'outbox_page_counts_distinct_records_and_pages_inside_the_snapshot',
    'conflict_probe_is_opt_in_and_marks_only_listed_records',
    'retried_records_and_fixed_reason_come_from_module_tokens',
    'rows_expose_only_closed_tokens_and_ids',
    'repeated_captures_leave_product_storage_byte_identical',
    'row_limit_hard_bounds_and_default_are_enforced',
    'revisions_owner_violation_fails_closed_without_a_snapshot',
    'revisions_free_capture_is_safe_from_many_threads',
    'bounded_page_records_are_published_and_acknowledged_by_the_real_session',
    'pending_original_is_surfaced_and_never_acknowledged',
    'metadata_wait_observations_mirror_the_session_counter',
    'credential_failure_maps_to_one_fixed_safe_reason',
    'unreachable_native_transport_is_reported_as_offline',
    'closing_and_closed_phases_stay_observable',
    'snapshot_outlives_session_and_revisions_and_releases_once',
    'evidence_contains_no_credentials_server_body_or_origin_text',
}
PLATFORMS = {'Linux': 'linux', 'Windows': 'win32', 'macOS': 'darwin'}
CONSUMERS = ('status-view-consumer', 'status-view-consumer.exe')
WORKFLOW = '.github/workflows/reader-sync-status-view.yml'
PRODUCERS = {'installed read-only status view (' + runner + ')'
             for runner in ('ubuntu-22.04', 'windows-2022', 'macos-14')}


def authenticate_producers(metadata, jobs, source, run, attempt):
    if (str(metadata.get('id')), metadata.get('head_sha'), str(metadata.get('run_attempt')),
        metadata.get('path', '').split('@')[0]) != (run, source, attempt, WORKFLOW):
        raise ValueError('run source/attempt/workflow differs')
    producers = [job for job in jobs if job.get('name') != 'strict same-run artifact aggregation']
    if len(producers) != 3 or {job.get('name') for job in producers} != PRODUCERS:
        raise ValueError('missing, duplicate or foreign producer')
    if any((job.get('head_sha'), str(job.get('run_attempt')), job.get('status'), job.get('conclusion')) !=
           (source, attempt, 'completed', 'success') for job in producers):
        raise ValueError('producer not completed/success on this source and attempt')


def payload_members(names):
    if len(names) != len(set(names)):
        raise ValueError('duplicate ZIP members')
    reports = [name for name in names if name.endswith('/result.json')]
    binaries = [name for name in names if name.rsplit('/', 1)[-1] in CONSUMERS]
    if len(reports) != 1 or len(binaries) != 1:
        raise ValueError('exactly one status report and one consumer binary are required')
    return reports[0], binaries[0]


def protocol_selftest():
    metadata = dict(id=7, head_sha='source', run_attempt=1, path=WORKFLOW)
    jobs = [dict(name=name, head_sha='source', run_attempt=1, status='completed', conclusion='success')
            for name in sorted(PRODUCERS)]
    authenticate_producers(metadata, jobs, 'source', '7', '1')
    rejected = 0
    for key, value in (('id', 8), ('head_sha', 'foreign'), ('run_attempt', 2), ('path', 'foreign.yml')):
        bad = dict(metadata);bad[key] = value
        try: authenticate_producers(bad, jobs, 'source', '7', '1')
        except ValueError: rejected += 1
        else: raise AssertionError('foreign ' + key + ' accepted')
    bad_jobs = [jobs[:-1], jobs + [jobs[0]]]
    for key, value in (('head_sha', 'foreign'), ('run_attempt', 2), ('status', 'in_progress'),
                       ('conclusion', 'failure'), ('conclusion', 'skipped'), ('name', jobs[1]['name'])):
        bad = copy.deepcopy(jobs);bad[0][key] = value;bad_jobs.append(bad)
    for bad in bad_jobs:
        try: authenticate_producers(metadata, bad, 'source', '7', '1')
        except ValueError: rejected += 1
        else: raise AssertionError('invalid producers accepted')
    names = ['status-view-evidence/result.json', 'bin/status-view-consumer']
    payload_members(names)
    for bad in (names + [names[0]], names + ['other/result.json'],
                names + ['other/status-view-consumer.exe'], names[:1], names[1:]):
        try: payload_members(bad)
        except ValueError: rejected += 1
        else: raise AssertionError('ambiguous or missing payload accepted')
    print(json.dumps(dict(protocol_negative_cases=rejected, accepted=True)))


def gh(*arguments, capture=True):
    result = subprocess.run(['gh', *arguments], check=True, capture_output=capture)
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = options.output.resolve()
    folder.mkdir(parents=True)
    listing = json.loads(gh('api', 'repos/%s/actions/runs/%s/artifacts?per_page=100'
                            % (options.repository, options.run_id)))
    metadata = json.loads(gh('api', 'repos/%s/actions/runs/%s' % (options.repository, options.run_id)))
    jobs = json.loads(gh('api', 'repos/%s/actions/runs/%s/attempts/%s/jobs?per_page=100'
                         % (options.repository, options.run_id, options.attempt)))['jobs']
    authenticate_producers(metadata, jobs, options.source, options.run_id, options.attempt)
    expected = {value: 'reader-sync-status-view-%s-%s-%s' % (value, options.run_id, options.attempt)
                for value in PLATFORMS}
    observed = {}
    problems = []
    for artifact in listing['artifacts']:
        for value, name in expected.items():
            if artifact['name'] == name:
                if value in observed:
                    raise ValueError('duplicate platform artifact ' + name)
                observed[value] = artifact
    for value, name in expected.items():
        if value not in observed:
            problems.append('missing artifact ' + name)
    if len(observed) != 3:
        problems.append('artifact set is not exactly the three platforms')
    evidence = []
    signatures = set()
    for value, artifact in sorted(observed.items()):
        name = artifact['name']
        if artifact.get('expired'):
            problems.append(name + ' is expired')
        expires = datetime.strptime(artifact['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            problems.append(name + ' expires in the past')
        archive = folder / (name + '.zip')
        with archive.open('wb') as handle:
            subprocess.run(['gh', 'api', 'repos/%s/actions/artifacts/%s/zip'
                            % (options.repository, artifact['id'])], check=True, stdout=handle)
        data = archive.read_bytes()
        digest = 'sha256:' + hashlib.sha256(data).hexdigest()
        if digest != artifact['digest']:
            problems.append(name + ' digest differs from the API record')
        if len(data) != artifact['size_in_bytes'] or not data:
            problems.append(name + ' byte count differs from the API record or is empty')
        report = None
        consumer = None
        with zipfile.ZipFile(archive) as bundle:
            report_name, consumer_name = payload_members(bundle.namelist())
            report = json.loads(bundle.read(report_name))
            consumer = hashlib.sha256(bundle.read(consumer_name)).hexdigest()
        if report is None:
            problems.append(name + ' has no report')
            continue
        if consumer is None:
            problems.append(name + ' has no installed consumer binary')
        elif consumer != report['consumer_sha256']:
            problems.append(name + ' consumer bytes differ from the report')
        if report.get('source_sha') != options.source:
            problems.append(name + ' report source differs from GITHUB_SHA')
        if str(report.get('run_id')) != options.run_id or str(report.get('attempt')) != options.attempt:
            problems.append(name + ' report run/attempt differs from this run')
        if report.get('platform') != PLATFORMS[value]:
            problems.append(name + ' report platform differs from its runner')
        checks = report.get('checks') or []
        if len(checks) != len(set(checks)) or report.get('count') != len(checks):
            problems.append(name + ' check list is duplicated or miscounted')
        if not REQUIRED.issubset(set(checks)):
            problems.append(name + ' is missing named checks: %s' % sorted(REQUIRED - set(checks)))
        if report.get('accepted') is not True:
            problems.append(name + ' is not accepted')
        signatures.add(tuple(checks))
        evidence.append({
            'platform': PLATFORMS[value], 'runner': value, 'artifact': {
                'id': artifact['id'], 'name': name, 'size_in_bytes': artifact['size_in_bytes'],
                'digest': digest, 'api_digest': artifact['digest'], 'expired': artifact['expired'],
                'expires_at': artifact['expires_at'], 'archive_sha256': hashlib.sha256(data).hexdigest()},
            'report': report, 'consumer_sha256': consumer})
    if len(signatures) != 1:
        problems.append('platform check lists differ')
    aggregate = {
        'schema': 'reader-sync-status-view-aggregate-v1',
        'accepted': not problems, 'source_sha': options.source, 'run_id': options.run_id,
        'attempt': options.attempt, 'artifacts': evidence, 'problems': problems,
        'jobs': [{'id': entry['id'], 'name': entry['name'], 'conclusion': entry['conclusion'],
                  'runner': entry.get('runner_name')} for entry in jobs if entry['name'].startswith('installed read-only')]}
    (folder / 'aggregate.json').write_text(json.dumps(aggregate, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': aggregate['accepted'], 'problems': problems,
                      'platforms': [entry['platform'] for entry in evidence]}, indent=2))
    if problems:
        sys.exit(1)


if __name__ == '__main__':
    if sys.argv[1:] == ['--protocol-selftest']:
        protocol_selftest()
    else:
        main()
