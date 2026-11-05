# SPDX-License-Identifier: MIT
"""Fixed named-check identity shared by the Actions driver and the strict checker.

The list is written before any consumer reads a fixture: a missing, extra or
renamed check is a refusal, not an acceptable run.
"""

REQUIRED_CASES = [
    "preferences.seed_manifest",
    "wire.seed_manifest",
    "preferences.defaults",
    "preferences.roundtrip",
    "preferences.unknown_version_keeps_file",
    "preferences.limit_ceiling",
    "preferences.lower_limit",
    "preferences.nan_range",
    "preferences.truncated_format",
    "preferences.duplicate_key_format",
    "preferences.nul_string_format",
    "preferences.unknown_enum_format",
    "preferences.import_legacy_partial",
    "preferences.import_legacy_unknown_bits",
    "preferences.import_legacy_invalid_merge",
    "preferences.status_names",
    "preferences.unicode_path",
    "preferences.empty_path",
    "preferences.cross_process_reopen",
    "wire.seed_v1_progress_valid",
    "wire.seed_v2_epub_annotation_valid",
    "wire.unknown_field_format",
    "wire.duplicate_key_format",
    "wire.invalid_utf8_format",
    "wire.byte_limit",
    "wire.hash_mismatch",
    "wire.pending_intent_local_then_ack",
    "wire.receive_idempotent_without_queue",
    "wire.decode_v1_matches_seed",
    "wire.decode_not_reading_refused",
    "wire.validation_does_not_write",
    "encode.v1_annotation_valid",
    "encode.v2_point_valid",
    "encode.v1_chapter_scope_refused",
    "encode.v2_nul_refused",
    "encode.argument_refused",
    "cross_process.revisions_reopen",
    "c_abi.parity",
    "fuzz.preferences.invariants",
    "fuzz.wire-validate.invariants",
    "fuzz.wire-decode.invariants",
    "fuzz.wire-receive.invariants",
    "fuzz.wire-local.invariants",
    "determinism.preferences",
    "determinism.wire-validate",
    "determinism.wire-decode",
    "determinism.wire-receive",
    "determinism.wire-local",
]

FUZZ_TARGETS = ["preferences", "wire-validate", "wire-decode", "wire-receive", "wire-local"]

# Deterministic replay names only exist when a run actually produced a case.
REPLAY_CASES = ["replay." + target for target in FUZZ_TARGETS]
