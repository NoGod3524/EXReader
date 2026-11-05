# CLAUDE-H03: original-file retention on GTK Retry

Status: contract review only. Candidate evidence, no score change. The formal
acceptance baseline stays 95/108 (87.96%).

Input: `7f15fe49374cd9389e2106837351d4bbd5e56113`
(`codex/dot-f05-paging-evidence-20261030`). No build, syntax check, test,
fixture or benchmark was run for this package, locally or in Actions.

## Question

Does the formal contract require GTK **Retry** of a pending metadata intent to
re-verify the retained original file, as the first Restore does?

## Code as read (read-only)

`examples/linux/metadata.inc`:

- `metadata_bootstrap` proves the retained SDK original's format, SHA-256 and
  size (`reader_catalog_sdk_original_identity`) against the product record
  before staging a bootstrap.
- `metadata_save` repeats that proof for `READER_COMMAND_RESTORE` only, then
  stages and calls `reader_metadata_finish_pending`.
- The `READER_METADATA_RETRY` action calls `reader_metadata_finish_pending`
  directly. The GTK layer adds no original-identity check on that path.

## Contract as read

- `docs/READER-DESKTOP-METADATA.md`: `finish_pending` "precisely retries the
  same intent"; a restart "replays the original IDs, fields and heads". The
  original-source verification obligation is stated for **book bootstrap**
  ("The host verifies exact retained original format, SHA-256 and size through
  the public SDK"). Retry is not described as re-verifying anything.
- `docs/READER-GTK-COLLECTIONS.md`: a refused or interrupted transaction
  "retains those same bytes"; Retry "never binds the edit to newer heads".
  Original proof is described before a legacy book's first classification.
- No document reviewed states that a Restore, or its Retry, promises a
  parseable original. The text "Restore requires the exact retained original
  verified by the public SDK" exists only as a GTK message string at the
  initial Restore guard.

## Distinction

| Promise | Documented | Where |
|---|---|---|
| Restore metadata from retained history | yes | GTK-COLLECTIONS, DESKTOP-METADATA |
| Initial Restore/bootstrap requires verified original | yes (bootstrap); code-only (Restore) | DESKTOP-METADATA; `metadata.inc` |
| Retry re-verifies the original | **no** | none |
| Retry replays the identical intent and heads | yes | DESKTOP-METADATA, GTK-COLLECTIONS |

## Result

**Checked, no violation.** Retry matches its documented contract (exact replay
of the staged intent). The absence of an original check on Retry is therefore
not recorded as a defect, and no replaced/truncated/digest-mismatch comparison
test was written. This is a documentation judgement, not an execution result.

## Not proven

- Behaviour of Retry after the retained original is replaced, truncated or no
  longer matches its digest. It was neither run nor asserted.
- Whether the product intends the first-Restore guard to also bind Retry. If the
  owner decides it should, that is a new contract line first; only then would an
  Actions-only first-Restore-versus-Retry comparison be justified.
- No overlap with the GTK restore-recovery 10 cases was examined by execution.

## Delivery

- Branch: `codex/claude-h03-original-retry-20261030`
- Files: this document only. No `tests/claude_h03_*/`, no workflow, no run ID,
  no artifact.
- Re-check: `git show 7f15fe49374cd9389e2106837351d4bbd5e56113:examples/linux/metadata.inc`
  and the two documents named above.
