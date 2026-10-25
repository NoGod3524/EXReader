"""Actions-only same-attempt authenticated original ZIP comparison."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

JOB = 'installed dual-family status view ('
FROZEN_LEGACY_CHECKS = [
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
    'evidence_contains_no_credentials_server_body_or_origin_text']


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    repo, run, attempt, source = (os.environ[key] for key in
                                  ['GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'])

    def get(path, binary=False):
        data = subprocess.check_output(['gh', 'api', 'repos/' + repo + '/' + path], timeout=300)
        return data if binary else json.loads(data)

    record = get('actions/runs/' + run + '/attempts/' + attempt)
    assert record['head_sha'] == source and record['run_attempt'] == int(attempt)
    jobs = get('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    artifacts = get('actions/runs/' + run + '/attempts/' + attempt + '/artifacts?per_page=100')['artifacts']
    platforms, retained = [], []
    for platform, runner in [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022')]:
        job = [entry for entry in jobs if entry['name'] == JOB + runner + ')']
        assert len(job) == 1 and job[0]['conclusion'] == 'success', (runner, [entry['name'] for entry in jobs])
        assert job[0]['head_sha'] == source
        found = [entry for entry in artifacts
                 if entry['name'] == 'reader-next-s17-' + platform + '-' + run + '-' + attempt]
        assert len(found) == 1, [entry['name'] for entry in artifacts]
        artifact = found[0]
        assert not artifact['expired']
        assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        assert artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == int(run)
        raw = get('actions/artifacts/' + str(artifact['id']) + '/zip', True)
        assert len(raw) == artifact['size_in_bytes']
        assert 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names))
            for name in names:
                entry = PurePosixPath(name)
                assert not entry.is_absolute() and '..' not in entry.parts, name
                assert '\\' not in name and ':' not in name and not name.endswith('.key'), name
            assert 'result.json' in names and 'raw-acceptance/result.json' in names
            result = json.loads(archive.read('result.json'))
            assert result['accepted'] and not result['adopted'] and not result['actual_hosts']
            assert (result['source_sha'], result['run_id'], result['attempt']) == (source, run, attempt)
            assert result['default_family_unchanged'] and result['raw_symbols_absent_from_default']
            assert len(result['mixed_profiles_refused']) == 5, result['mixed_profiles_refused']
            assert set(result['programs']) == {'raw-view-consumer', 'raw-view-c-consumer', 'raw-revision'}
            raw_report = json.loads(archive.read('raw-acceptance/result.json'))
            assert raw_report['accepted'] and raw_report['family'] == 'raw'
            assert (raw_report['source_sha'], raw_report['run_id'], raw_report['attempt']) == (source, run, attempt)
            assert raw_report['count'] == len(raw_report['checks']) >= 15
            assert len(set(raw_report['checks'])) == raw_report['count']
            assert len(raw_report['mirrored_fields']) == 16, raw_report['mirrored_fields']
            assert raw_report['profile'] == {'view': '0.2.0', 'session': '0.2.0', 'sync': '0.2.0',
                                             'revisions': '0.4.0', 'raw': 1}
            frozen = json.loads(archive.read('frozen-legacy-acceptance/result.json'))
            assert frozen['accepted'] and frozen['count'] == len(frozen['checks'])
            assert frozen['checks'] == FROZEN_LEGACY_CHECKS, frozen['checks']
            assert frozen['metadata_wait_positive_covered'] is True
            assert frozen['sdk_changed'] is False and frozen['schema_changed'] is False
            assert frozen['wire_changed'] is False and frozen['anchor_changed'] is False
            assert frozen['product_wiring_accepted'] is False and frozen['host_ui_accepted'] is False
            retained.append({'checks': raw_report['checks'], 'frozen': frozen['checks'],
                             'profile': raw_report['profile']})
        platforms.append({'platform': platform, 'producer_job': job[0]['id'],
                          'artifact': {key: artifact[key] for key in
                                       ['id', 'name', 'digest', 'size_in_bytes', 'expires_at']},
                          'raw_checks': raw_report['count'], 'frozen_checks': frozen['count'],
                          'mixed_profiles_refused': result['mixed_profiles_refused']})
    assert retained[0] == retained[1], 'both platforms must report the identical named checks'
    result = {'accepted': True, 'adopted': False, 'source_sha': source, 'run_id': run, 'attempt': attempt,
              'platforms': platforms, 'cross_platform_checks_identical': True,
              'scope': 'explicit sync-status-view raw session0.2 install family only',
              'actual_hosts': False, 'physical_device': False, 'complete_product': False}
    output = Path('build/reader-next-s17-summary')
    output.mkdir(parents=True)
    (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
