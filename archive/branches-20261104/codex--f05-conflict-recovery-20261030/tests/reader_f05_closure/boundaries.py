# SPDX-License-Identifier: MIT
"""Named fault boundaries for this package, shared by the fixture, the
per-platform acceptance and the cross-platform aggregate.

NEW_CHECKS is the exact ordered set each platform must produce. Anything a
platform cannot reach is refused by the aggregate instead of being reported as
a pass. UNCOVERED_LIMITS names sub-windows this package explicitly does not
claim; they are recorded verbatim by every platform so the aggregate can refuse
a report that silently drops one.

ORIGINAL_SESSION_CHECKS is the unchanged 20-item acceptance of the pre-existing
account-session suite at the fixed implementation start. This package keeps that
suite and reports it from the same source/run/attempt; it does not replace,
weaken or re-implement those assertions.
"""

NEW_CHECKS = [
    'put_committed_before_ack_response_withheld_then_kill_preserves_remote_bytes_and_outbox',
    'kill_during_original_upload_before_remote_commit_leaves_no_partial_remote_object',
    'replay_of_an_already_committed_immutable_revision_is_412_and_never_rewritten',
    'kill_during_verification_get_before_hash_keeps_remote_bytes_and_outbox',
    'truncated_verification_get_is_refused_without_acknowledgement',
    'kill_while_acknowledging_after_verified_get_never_duplicates_or_loses_work',
    'abrupt_process_exit_after_outbox_commit_keeps_one_remote_object_and_no_pending_row',
    'kill_during_original_download_leaves_no_published_cache_identity',
    'original_download_timeout_removes_private_temp_and_keeps_pending_identity',
    'cached_original_identity_is_reverified_before_reuse',
    'remote_original_with_wrong_bytes_is_never_published_as_local_identity',
    'real_401_is_reported_without_acknowledgement_or_implicit_retry',
    'real_403_is_reported_without_acknowledgement_or_implicit_retry',
    'real_429_retry_after_is_not_followed_by_implicit_replay',
    'real_503_during_publication_retains_outbox_and_republishes_on_explicit_retry',
    'mid_sweep_503_keeps_completed_shards_and_resumes_at_the_failed_shard',
    'connection_reset_during_put_body_resolves_by_get_and_keeps_outbox',
    'bounded_publication_timeout_leaves_no_remote_object_and_keeps_outbox',
    'existing_immutable_object_with_foreign_bytes_is_not_overwritten_or_acked',
    'same_account_reopen_after_forced_kill_resumes_without_rebinding',
    'different_account_after_forced_kill_is_refused_before_any_request',
]

ORIGINAL_SESSION_CHECKS = [
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

UNCOVERED_LIMITS = [
    'atomic_rename_to_revision_receive_single_instruction_window',
    'fixture_store_durability_before_response_flush',
    'sqlite_page_torn_write_under_sigkill',
    'host_ui_projection_and_other_platform_hosts',
    'third_party_server_retry_and_backoff_policy',
]

NEW_CHECKS += ["f05_two_offline_peers_publish_their_own_wire","f05_partial_peer_revision_cancel_keeps_atomic_history","f05_peer_conflict_survives_hard_kill_and_idempotent_rescan","f05_peer_tombstone_crosses_wire_without_history_loss"]
UNCOVERED_LIMITS += ['six_host_ui_same_source_closure', 'host_receive_import_cancel_and_crash', 'concurrent_delete_put_explicit_restore_over_wire']
