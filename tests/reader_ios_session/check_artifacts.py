# SPDX-License-Identifier: MIT
"""Actions-only same-run iOS originals, lifecycle and process-recovery evidence."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_reading_v2'))
from check_sdk import EXPECTED

SESSION_CHECKS = [
    'c_abi_and_idle_creation_make_no_network_request',
    'premature_destroy_is_nonblocking_busy_and_preserves_handle',
    'background_worker_and_observation_remain_responsive_during_native_https',
    'overlapping_sweeps_are_refused',
    'cancelled_transfer_keeps_the_last_successful_cursor',
    'same_product_account_is_exclusively_locked_across_processes',
    'full_256_shards_and_100_record_continuation_are_actually_processed',
    'remote_history_is_retained_without_sdk_writes_or_implicit_projection',
    'a_new_sweep_discovers_insertions_preceding_an_old_cursor',
    'offline_outbox_is_published_verified_and_acked_on_the_worker',
    'wrong_staged_original_is_refused_without_acknowledging_the_outbox',
    'repaired_private_original_is_hash_verified_published_and_acknowledged',
    'another_independent_product_database_receives_the_same_history',
    'persistent_account_binding_contains_no_authorization',
    'account_or_root_changes_are_refused_before_network_and_preserve_history',
    'same_account_reopens_after_process_shutdown_without_rebinding',
    'network_failure_is_observed_without_an_automatic_retry_loop',
    'explicit_retry_resumes_and_preserves_durable_history',
    'invalid_account_identity_is_rejected_before_worker_creation',
    'all_native_requests_keep_credentials_at_the_selected_origin_and_leave_no_transfer_temp',
]
RECOVERY_CHECKS = [
    'native_put_commits_before_get_verification_without_premature_ack',
    'uikit_main_loop_and_nonblocking_controls_survive_a_blocked_native_request',
    'actual_uikit_process_sigkill_preserves_history_and_unacked_outbox',
    'same_account_new_process_retries_immutable_put_verifies_get_and_acks_once',
    'uikit_close_observes_closed_before_destroy_and_keeps_the_main_loop_live',
    'close_during_native_transfer_cancels_asynchronously_and_joins_only_after_closed',
    'process_recovery_never_persists_authorization_or_projects_remote_metadata',
]
APP = 'consumer/ReaderSessionProbe.app/ReaderSessionProbe'


def verify(read, source, run_id, attempt):
    def report(path):
        value = json.loads(read(path))
        require(value.get('accepted') is True and value['source_sha'] == source and
                int(value['run_id']) == run_id and int(value['attempt']) == attempt, 'report source/run/attempt or refusal: ' + path)
        return value
    main = report('result.json')
    reading = report('evidence/result.json')
    faults = report('faults/result.json')
    recovery = report('process-recovery/result.json')
    require(main['execution_platform'] == reading['execution_platform'] == faults['execution_platform'] == 'ios-simulator', 'execution platform')
    require(recovery['execution_platform'] == 'ios-simulator-uikit', 'UIKit execution platform')
    require(main['reading_cases'] == 18 and main['receiver_found'] == 17 and main['receiver_mislocated'] == 0 and
            main['originals_exported'] == 4 and main['session_sweeps'] == 38, 'SDK originals or real reading cases differ')
    require([c['id'] for c in reading['cases']] == EXPECTED and reading['receiver_mislocated'] == 0, 'reading case identity')
    require(all(c['state'] == ('AMBIGUOUS' if c['id'] == 'txt-ambiguous' else 'FOUND') for c in reading['cases']), 'reading navigation states')
    raw = json.loads(read('evidence/probe.json'))
    require(raw['failures'] == 0 and raw['checks'] and all(c['pass'] is True for c in raw['checks']), 'raw reading checks')
    sessions = json.loads(read('evidence/probe.json.sessions.json'))
    require(sessions['accepted'] is True and sessions['count'] == len(sessions['sessions']) == 38 and
            all(s['shards'] == 256 and s['sweeps'] == 1 and s['observations'] > 0 for s in sessions['sessions']), 'actual 38 account sweeps')
    lifecycle = json.loads(read('evidence/probe.json.lifecycle.json'))
    require(lifecycle['code'] == 0 and lifecycle['main_thread_ticks'] == main['main_thread_ticks'] > 0, 'main runloop observation')
    require(faults['checks'] == SESSION_CHECKS and faults['count'] == main['session_fault_checks'] == 20, 'original 20 fault checks')
    require(recovery['checks'] == RECOVERY_CHECKS and recovery['count'] == main['uikit_process_recovery_checks'] == 7, 'UIKit recovery checks')
    launches = [e['pid'] for e in recovery['events'] if e['event'] == 'launch']
    kills = [e['pid'] for e in recovery['events'] if e['event'] == 'SIGKILL']
    require(len(set(launches)) == recovery['native_processes'] == main['uikit_process_launches'] == 3 and kills == launches[:1], 'actual UIKit process identities')
    app_hash = hashlib.sha256(read(APP)).hexdigest()
    require(main['consumer_sha256'] == reading['consumer_sha256'] == recovery['consumer_sha256'] == app_hash, 'actual UIKit consumer hash')
    fault_hash = hashlib.sha256(read('consumer/ios-session-controls')).hexdigest()
    require(main['fault_consumer_sha256'] == faults['consumer_sha256'] == fault_hash, 'actual iOS fault consumer hash')
    require(main['revision_consumer_sha256'] == hashlib.sha256(read('consumer/ios-session-revisions')).hexdigest(), 'actual iOS revision consumer hash')
    require(len(main['sqlite_provider']) == 1 and 'reader_catalog_sqlite' in main['sqlite_provider'][0], 'single product SQLite provider')
    require(main['sdk_changed'] is False and main['schema_changed'] is False and main['host_ui_accepted'] is False and
            main['physical_device_execution'] is False and main['complete_product'] is False, 'declared scope drifted')
    return {'reading_cases': 18, 'session_sweeps': 38, 'session_fault_checks': 20, 'uikit_process_recovery_checks': 7,
            'consumer_sha256': app_hash, 'fault_consumer_sha256': fault_hash}


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id, attempt, source = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA']
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt, 'problems': [],
               'artifact': None, 'producer_job': None, 'negative_checks': [], 'execution_platform': 'ios-simulator',
               'physical_device_execution': False, 'host_ui_accepted': False, 'six_platform_accepted': False, 'complete_product': False}
    try:
        run = fetch(f'actions/runs/{run_id}')
        require(run['head_sha'] == source and run['run_attempt'] == attempt and run['path'] == '.github/workflows/reader-ios-session.yml', 'caller identity')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        producers = [j for j in jobs if j['name'] == 'installed iOS SDK and actual account roundtrip']
        require(len(producers) == 1 and producers[0]['conclusion'] == 'success' and producers[0]['head_sha'] == source and producers[0]['run_attempt'] == attempt, 'producer not successful on this source/attempt')
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        found = [a for a in artifacts if a['name'] == f'reader-ios-session-{run_id}-{attempt}']
        require(len(found) == 1, 'producer artifact missing/duplicated'); artifact = found[0]
        require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and artifact['workflow_run']['head_sha'] == source, 'artifact source/size/expiration')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(artifact['id'], stream); stream.seek(0); data = stream.read()
        require(len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'actual ZIP digest/size')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate ZIP paths')
            for path in archive.namelist():
                require(not path.startswith('/') and '\\' not in path and '..' not in path.split('/'), 'unsafe ZIP path')
            summary.update(verify(archive.read, source, run_id, attempt))
            mutations = [
                ('source', 'result.json', lambda v: v.__setitem__('source_sha', '0' * 40)),
                ('sweeps', 'result.json', lambda v: v.__setitem__('session_sweeps', 37)),
                ('fault_missing', 'faults/result.json', lambda v: v['checks'].pop()),
                ('recovery_refused', 'process-recovery/result.json', lambda v: v.__setitem__('accepted', False)),
                ('native_hash', 'result.json', lambda v: v.__setitem__('consumer_sha256', '0' * 64)),
            ]
            for name, path, mutate in mutations:
                changed = json.loads(archive.read(path)); mutate(changed); changed = json.dumps(changed).encode()
                try: verify(lambda p: changed if p == path else archive.read(p), source, run_id, attempt)
                except Exception: summary['negative_checks'].append(name)
                else: raise AssertionError('invalid evidence accepted: ' + name)
            try: verify(lambda p: b'changed binary' if p == APP else archive.read(p), source, run_id, attempt)
            except Exception: summary['negative_checks'].append('actual_binary')
            else: raise AssertionError('changed native executable accepted')
        summary['artifact'] = {k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
        summary['producer_job'] = {k: producers[0][k] for k in ('id', 'name', 'conclusion')}
        summary['accepted'] = True
    except Exception as error:
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__': main()
