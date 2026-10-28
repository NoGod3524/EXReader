# SPDX-License-Identifier: MIT
"""Actions-only, pinned adapter for the authenticated GTK sync/account run."""
import hashlib
import io
import json
import os
import zipfile

from check_parallel_integration import fetch, pages, download_artifact_zip

RUN = 40629444286
SOURCE = '6b2e3a2d44e085c40fa20e07bbceef93706e8ff0'
ARCHIVE = (12790797986, 5185218, 'aea21c97eaa96a5aad9656b6419196e7581d18b098a1100ca2f3ea04de43c6fc')
IDENTITY = (12790822821, 426, '7a3e9f62c6f4f6d4cee35fb1eb4d74f355ef76d23d427d308f56f9b0c07f0fac')
PROGRAM = 'ab8c2b7497b72d1af1121ac2cece610420ffb5c84b543a8aecbf4e26ec5b56a8'
REPORT = 'c4a3e50a9e75a3a11c410c0af1ec73f01700ec51309d1c79be786120a7862184'
RETAINED = frozenset('''
real_more_menu_and_keyboard_open_masked_native_account_controls
explicit_remember_uses_real_secret_service_and_persists_only_uuid_and_exact_root
new_actual_process_loads_saved_credentials_with_the_same_stable_account_id
back_during_local_preparation_cancels_owner_work_before_network_start
main_window_close_during_preparation_retires_queued_owner_work_before_shutdown
default_scan_stages_all_52_exact_originals_in_50_row_owner_pages_and_preserves_edited_metadata
finished_ui_reports_record_scan_only_without_claiming_readable_remote_books
disconnect_polls_closed_before_destroy_and_only_then_reenables_credentials
status_syncing_capture_is_read_only
real_paused_tls_scan_leaves_gtk_responsive_and_cancel_is_nonblocking
status_cancelled_capture_is_read_only
explicit_retry_keeps_same_handle_and_remote_history_without_projecting_or_importing_it
status_failed_capture_is_read_only
server_failure_is_visible_and_only_explicit_retry_resumes_the_scan
status_sweep-complete_capture_is_read_only
verified_local_book_with_two_heads_stages_original_without_selecting_or_projecting_and_still_receives_remote_records
changing_exact_root_is_refused_without_network_or_rebinding
mismatching_existing_private_original_is_never_overwritten_and_prevents_network_start
back_waits_asynchronously_for_closed_and_reopening_loads_credentials
forget_deletes_real_system_record_and_restart_keeps_nonsecret_binding_only
durable_pending_metadata_refuses_staging_without_overwriting_the_journal
native_product_binding_rejects_a_different_uuid_before_any_http
locked_real_secret_service_reports_unavailable_and_does_not_claim_credentials_saved
explicit_session_only_choice_still_scans_with_secure_storage_unavailable
session_only_credentials_are_absent_after_actual_process_restart
application_close_defers_sdk_owner_shutdown_until_native_session_closed
credentials_and_authorization_are_absent_from_profiles_product_databases_wire_and_all_evidence
'''.split())
EXTRA = frozenset(('live_status_widget_is_noneditable_and_matches_capture',
                   'closed_session_retained_until_pending_capture_releases'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def artifact(pin, name):
    ident, size, sha = pin
    meta = fetch('actions/artifacts/' + str(ident))
    assert meta['id'] == ident and meta['name'] == name and meta['expired'] is False
    assert meta['workflow_run']['id'] == RUN and meta['workflow_run']['head_sha'] == SOURCE
    assert meta['size_in_bytes'] == size and meta['digest'] == 'sha256:' + sha
    raw = download_artifact_zip(ident)
    assert len(raw) == size and digest(raw) == sha
    return raw


def member(archive, suffix):
    found = [name for name in archive.namelist() if name.endswith(suffix)]
    assert len(found) == 1, (suffix, found)
    return archive.read(found[0])


def review(report, identity, program, report_bytes):
    assert report['accepted'] is True and report['source_sha'] == SOURCE
    assert str(report['run_id']) == str(RUN) and str(report['attempt']) == '1'
    assert report['program_sha256'] == PROGRAM == digest(program)
    assert digest(report_bytes) == REPORT
    checks, extra = report['checks'], report['extra_checks']
    assert len(RETAINED) == 27 and len(EXTRA) == 2
    assert isinstance(checks, list) and len(checks) == report['count'] == 27 and set(checks) == RETAINED
    assert isinstance(extra, list) and len(extra) == 2 and set(extra) == EXTRA
    assert report['live_widget']['editable'] is False
    pending = report['pending_capture']
    assert all(pending[key] is True for key in ('closed_while_pending', 'retained_until_release', 'reopened'))
    assert report['owner_page_limit'] == 50 and report['copy_chunk_limit'] == 65536 and report['original_limit'] == 134217728
    assert identity['verified'] is True and identity['source_sha'] == SOURCE
    assert str(identity['run_id']) == str(RUN) and str(identity['attempt']) == '1'
    assert identity['artifact_id'] == ARCHIVE[0] and identity['archive_sha256'] == ARCHIVE[2]
    assert identity['program_sha256'] == PROGRAM and identity['report_sha256'] == REPORT
    assert identity['retained_checks'] == 27 and identity['additional_checks'] == 2


def verify():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'artifact analysis is Actions-only'
    run = fetch('actions/runs/%d/attempts/1' % RUN)
    assert run['id'] == RUN and run['run_attempt'] == 1 and run['head_sha'] == SOURCE
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    jobs = pages('actions/runs/%d/attempts/1/jobs' % RUN, 'jobs')
    for name in ('combined', "Independently authenticate this run's focused evidence"):
        found = [job for job in jobs if job['name'] == name]
        assert len(found) == 1 and found[0]['status'] == 'completed' and found[0]['conclusion'] == 'success'
    with zipfile.ZipFile(io.BytesIO(artifact(ARCHIVE, 'gtk-sync-account-40629444286-1'))) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        report_bytes = member(archive, 'combined-account/result.json')
        report = json.loads(report_bytes)
        program = member(archive, 'EXReader-Linux/bin/exreader-linux')
    with zipfile.ZipFile(io.BytesIO(artifact(IDENTITY, 'gtk-sync-account-identity-40629444286-1'))) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        identity = json.loads(member(archive, 'identity.json'))
    review(report, identity, program, report_bytes)
    return {'source': SOURCE, 'run': RUN, 'attempt': 1, 'artifact': ARCHIVE[0],
            'identity_artifact': IDENTITY[0], 'zip_sha256': ARCHIVE[2],
            'identity_zip_sha256': IDENTITY[2], 'program_sha256': PROGRAM,
            'report_sha256': REPORT, 'passing_cases': sorted(RETAINED | EXTRA),
            'scope_basis': '29 named checks from pinned original report and authenticated same-run identity'}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
