# Migration candidate regression triage

Source: 8357eafa28423a7ab93ba08b823af80f01ad1505.
[Run 40636401201, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40636401201):
Linux and Windows each failed the unchanged candidate gate, 52/65 scenarios,
111/128 recorded assertions. macOS was still queued when this note was written.
The previous migrator separately passed its original 65 scenarios in those jobs.

## Eight cases interrupted while accessing the legacy sidecar

The Linux job log identifies the missing `.legacy-map.json` or a null result
from its reader at the point of failure:

- `note_ambiguous_quote_unlocated`
- `fixed_missing_quote_unlocated_and_rects_recorded`
- `unknown_fields_reported_and_kept`
- `orphan_note_preserved`
- `rerun_same_pack_is_stable`
- `ledger_loss_does_not_duplicate`
- `same_original_different_legacy_id_merges`
- `ledger_with_unknown_version_refused`

The candidate stores its authoritative ledger in the database and explicitly
exports JSON. The same-source transaction suite checks exported ambiguous
and orphan notes, fixed-note rectangles, unknown fields, repeated migration
and cross-identity deduplication. It also checks damaged internal ledger
rejection. These checks establish the behavior they actually exercise; they
do not establish automatic sidecar compatibility or make the original cases
pass. Decide and document the supported external contract, and retain the
unchanged run and original failures.

## Five other cases

- `existing_target_content_is_preserved`: content check passed; old
  backup-stage-and-replace assertion failed. Existing targets are modified
  transactionally by the candidate. Verify equivalent preservation through
  the actual public workflow, including failure and retry.
- `target_occupied_by_lock_file`: old busy and break-lock assertions
  failed. The new SQLite lock does not by itself coordinate the old
  replacement migrator. Establish a safe, explicit transition for old and
  new entry points; do not run them concurrently.
- `write_failure_after_partial_writes_keeps_target`: preservation assertions
  passed, but the old injected write-failure outcome did not. Check where the
  candidate injects the failure and demonstrate a real transactional rollback.
- `ledger_publish_failure_rolls_back_library`: old sidecar publication
  fault and rollback assertions failed. Validate the analogous failure before
  transaction commit with both book data and authoritative ledger unchanged.
- `failed_rollback_is_reported_and_pre_image_kept`: old replacement rollback
  failure and pre-image expectations failed. Establish the corresponding
  error and recovery contract for transaction or new-target publication
  failure; do not claim the old pre-image behavior.

The old review and browser chains also stop at the missing sidecar. Keep the
original runs and named checks and verify any revised contract independently.
Host lifecycle integration and a same-source multi-platform gate remain open.
