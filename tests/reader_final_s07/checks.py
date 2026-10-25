# SPDX-License-Identifier: MIT
"""Named acceptance items of S07 (raw synchronisation multi-peer faults).

CHECKS is the exact ordered set the three-peer fixture must produce. The driver
refuses to write a report when an item is missing, and the same-source
aggregate job refuses a report whose names, order or count drift.

EXPECTED records the invariant that each item asserts; it is copied into the
report so a reader can see what was claimed next to what was measured.

GAPS records sub-windows this package explicitly does not claim. None of them
is silently treated as a pass.
"""

CHECKS = [
    'real_capture_graph_and_original_identity_bootstrap',
    'network_reset_before_commit_then_explicit_retry_publishes_exactly_once',
    'response_lost_newer_head_then_old_request_retry_keeps_head_and_outbox',
    'out_of_order_parent_graph_child_before_parent_then_complete',
    'duplicate_wire_receive_is_idempotent_for_both_receivers',
    'unknown_anchor_version_refused_over_network_and_direct_receive',
    'legacy_max2_consumers_coexist_without_corruption',
    'exact_wire_ids_parents_and_original_hash_after_cross_process_reopen',
]

EXPECTED = {
    'real_capture_graph_and_original_identity_bootstrap':
        'The sender bootstraps only genuine public-SDK capture wire; the exported graph has '
        'exactly the capture revisions plus the two typed metadata revisions, and the private '
        'original is the real 8845-byte PDF with SHA-256 '
        '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc.',
    'network_reset_before_commit_then_explicit_retry_publishes_exactly_once':
        'A connection reset before the remote commit leaves no remote object and the whole '
        'outbox retained; the explicit retry from a new process publishes every immutable '
        'revision exactly once, verifies each by GET and empties the outbox.',
    'response_lost_newer_head_then_old_request_retry_keeps_head_and_outbox':
        'After a committed PUT whose response and verification GET are lost, the sender '
        'receives a newer head and then retries the old request: the retry is answered 412, '
        'verified by GET, acknowledged exactly once, and the newer head, the history size and '
        'the outbox are unchanged.',
    'out_of_order_parent_graph_child_before_parent_then_complete':
        'A receiver that is served a child revision before its parent retains the exact child '
        'bytes with a missing parent and no safe projection, and completes the graph with the '
        'same bytes once the parent arrives.',
    'duplicate_wire_receive_is_idempotent_for_both_receivers':
        'Re-delivering the same wire to the same receiver and to the second receiver adds no '
        'head, no history row, no outbox row and no remote object, and never rewrites bytes.',
    'unknown_anchor_version_refused_over_network_and_direct_receive':
        'An unknown anchor version served by the real server is refused by the raw receiver '
        'with the format status before any write, refused again on direct receive, and refused '
        'by the old MAX2 consumer together with anchor version 3.',
    'legacy_max2_consumers_coexist_without_corruption':
        'Two old MAX2 consumers publish and receive their genuine legacy1/legacy2 wire on the '
        'same server root as the raw peers, keep exact bytes, and the raw3 refusal leaves their '
        'own history and outbox untouched.',
    'exact_wire_ids_parents_and_original_hash_after_cross_process_reopen':
        'Every wire that the three peers hold has identical bytes, revision ID and parent set on '
        'the sender and on both receivers, the immutable original hash is identical, and a fresh '
        'process reopens each store with an empty outbox and the retained capture graph.',
}

GAPS = [
    'real_third_party_webdav_service_and_real_account',
    'six_target_sdk_interop_and_host_ui',
    'concurrent_multi_writer_on_one_store',
    'sqlite_page_torn_write_under_power_loss',
    'server_side_retry_and_backoff_policy',
    'android_apple_windows_gtk_host_projection',
]
