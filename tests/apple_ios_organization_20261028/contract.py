# SPDX-License-Identifier: MIT
"""Exact case/step contract; no local test or artifact execution."""
BASE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
PACKAGE = 'tests/apple_ios_organization_20261028/'
WORKFLOW = '.github/workflows/apple-ios-organization-20261028.yml'
LIFECYCLE = ['created', 'member_added', 'member_restart', 'member_removed',
             'member_tombstone_restart', 'member_restored', 'renamed', 'group_removed',
             'removed_filter_on', 'group_tombstone_restart', 'group_restored', 'final_restart']
CASES = {
    'testShelfLifecycleMembershipAndRestart': LIFECYCLE,
    'testTagLifecycleMembershipAndRestart': LIFECYCLE,
    'testSeriesLifecycleMembershipAndRestart': LIFECYCLE,
    'testNestedShelfIdentityAndParentNavigation': ['nested_created', 'parent_navigation', 'nested_restart'],
    'testStagedIntentTerminationRetryIsIdempotent': ['staged', 'pending_restart', 'retried_once', 'single_identity_restart'],
    'testStaleSnapshotRejectsIndependentWriterAndSurvivesRestart': ['independent_writer_committed', 'stale_refused',
        'stale_pending_restart', 'stale_retry_refused', 'competitor_preserved', 'competitor_restart'],
}
