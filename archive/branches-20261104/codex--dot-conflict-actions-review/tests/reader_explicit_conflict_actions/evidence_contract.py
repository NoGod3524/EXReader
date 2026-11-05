# SPDX-License-Identifier: MIT
"""Fixed acceptance contract. Executed only by GitHub Actions."""
import hashlib
import json

EXPECTED_CHECKS = [
    'installed_consumer_uses_one_verified_product_sqlite_provider',
    'two_real_clients_expose_every_concurrent_head_with_exact_validated_wire',
    'prepare_never_chooses_a_head_or_writes_history_projection_or_outbox',
    'explicit_resolution_names_all_observed_heads_and_user_fields_not_clock_or_order',
    'resolution_preserves_original_histories_schema_and_adds_exactly_one_revision_and_outbox_row',
    'merge_revision_replicates_to_the_other_client_as_the_single_safe_head',
    'single_safe_head_refuses_conflict_action',
    'same_snapshot_retry_after_commit_is_exact_noop_without_requeue',
    'committed_revision_id_reused_with_a_fresh_snapshot_is_refused_and_writes_nothing',
    'revision_arriving_after_prepare_is_stale_and_the_command_writes_nothing',
    'stale_snapshot_is_refreshed_and_retried_once_with_the_same_stable_id',
    'missing_parent_heads_are_displayed_but_resolution_is_refused_without_writes',
    'late_parent_arrival_makes_the_same_entity_resolvable_after_a_new_prepare',
    'put_after_observed_tombstone_is_refused_before_any_write',
    'explicit_restore_names_the_delete_and_concurrent_heads_and_revives_the_group',
    'group_tombstone_resolution_does_not_cascade_to_membership_or_book_history',
    'single_tombstone_allows_only_explicit_restore_and_a_repeated_delete_is_refused',
    'restore_without_a_direct_delete_head_is_refused_and_explicit_delete_merges_all_heads',
    'book_tombstone_and_explicit_restore_are_resolved_independently',
    'membership_tombstone_and_restore_are_resolved_without_touching_book_or_group_history',
    'membership_without_retained_book_history_reports_needs_bootstrap_without_writes',
    'thirty_two_heads_merge_with_thirty_two_parents_and_thirty_three_are_refused',
    'progress_and_annotation_conflicts_show_exact_wire_and_are_never_resolved_or_navigated_here',
    'typed_command_identity_invalid_targets_and_missing_entities_are_refused_before_writing',
    'cancellation_is_observed_only_before_the_commit_boundary_and_leaves_no_partial_state',
    'native_transaction_failure_rolls_back_history_outbox_and_projection_then_retries_exactly_once',
    'foreign_worker_and_callback_reentry_are_rejected_without_state_change',
    'installed_c_header_prepares_inspects_and_applies_an_explicit_group_resolution',
    'no_sdk_database_notes_or_original_book_files_are_created_or_modified',
    'same_snapshot_stable_id_with_changed_fields_is_collision_without_duplicate_history_or_outbox',
    'snapshot_view_outlives_owner_close_and_is_released_on_another_worker',
    'membership_restore_waits_for_explicit_group_and_book_restores_without_partial_writes',
]
PLATFORMS = {'Linux': ('ubuntu-22.04', 'Linux'), 'Windows': ('windows-2022', 'Windows'), 'macOS': ('macos-14', 'Darwin')}


def package_sha256(assets):
    package = sorted((a for a in assets if a['role'] == 'installed'), key=lambda a: a['path'])
    return hashlib.sha256(json.dumps(package, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def required_assets(runner_os):
    suffix = '.exe' if runner_os == 'Windows' else ''
    library = 'reader_conflict_actions.lib' if runner_os == 'Windows' else 'libreader_conflict_actions.a'
    cmake = 'conflict-stage/lib/cmake/EXReaderConflictActions/'
    return {
        'consumer/conflict-consumer' + suffix: 'cxx_consumer',
        'consumer/conflict-c-consumer' + suffix: 'c_consumer',
        'conflict-stage/lib/' + library: 'installed',
        'conflict-stage/include/reader_conflict_actions.h': 'installed',
        **{cmake + name: 'installed' for name in (
            'EXReaderConflictActionsConfig.cmake', 'EXReaderConflictActionsConfigVersion.cmake',
            'EXReaderConflictActionsTargets.cmake', 'EXReaderConflictActionsTargets-release.cmake')},
    }
