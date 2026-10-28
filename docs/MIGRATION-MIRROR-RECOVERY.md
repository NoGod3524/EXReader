# Tools-only external mirror and pending recovery

Status: source-only incremental candidate; not built or tested. The separate
commit-outcome branch remains unchanged. Internal SQLite data and its raw ledger
are authoritative. The external `.legacy-map.json` is a mirror, not a commit
receipt. Equal before/after ledger bytes cannot identify whether COMMIT happened.

## Scope and safety boundary

No frozen SDK, old test, assertion, budget, exporter byte contract, or production
owner change. No DB pre-image replacement or automatic replay. An unpublished
private stage is never published by recovery. The guarantee is process-crash
recovery on a stable local filesystem, NOT power-loss durability. File contents
are flushed; cross-platform parent-directory persistence is not yet proven.

The host must exclude noncooperating target/sidecar pathname replacement and
external sidecar editors while the common `.migrate-lock` is held. That lock
coordinates the two tools, not arbitrary editors or historical binaries. All
writers of the opaque internal migration ledger must also honor that lock.
Ordinary SDK row/metadata writers may run in the COMMIT/reacquire gaps and their
writes are preserved. A noncooperating ledger-set caller after recovery releases
its owner cannot be fenced by these tools; automatic mirror convergence is not
promised for that unsupported lifecycle. A hash
check followed by rename is not compare-and-swap. File IDs detect substitutions
but do not close SDK open-by-path races. `--break-lock` requires every old owner
to be stopped; its use is not evidence of that fact. If these ownership conditions
cannot be established, do not migrate or recover in place; export separately.

## Immutable pending intent

`TARGET.migration-pending.json` is exclusively created and flushed before COMMIT.
Its bounded, strict version-1 format records owner file ID (existing target or
private stage), a validated hex/hyphen private-stage token, original-target
existence, internal ledger before/after hashes,
and original mirror existence/file ID/hash/size. It accepts no artifact paths.
It is an intent, not a signed authenticity token or a commit receipt. A partial,
unknown-version, unreadable, or malformed intent blocks writes and is retained.

An export stage contains real raw `migration_ledger_get` bytes; it is not a DB
pre-image. Recovery never calls the normal serializer (`sidecar_text`) because
that appends the current pack and can invent/drop information. Fresh export
stages are exclusive-created. Only the live process's owned temp can be removed;
crashed temps and private stages are retained, not glob-cleaned.

## Ordered state machine

1. Acquire common migration lock. Inspect target/mirror/pending with strict
   absent/regular/error semantics; reject symlink/reparse/special/unreadable paths.
2. If pending exists, reconcile it before processing another pack. For an
   existing target, identity-check before SDK open, acquire fresh migration owner,
   and recheck identity. Never call CREATE-capable `migration_open` on a known
   missing target during recovery. Keep lock through explicit `finish(0)` and
   journal disposition. Do not persist schema upgrades from this reader.
   Exception: `migrate --dry-run` only validates pending intent and returns
   recovery-required; it never repairs a mirror or retires pending state.
3. Begin ordinary migration owner. If internal ledger exists, external mirror
   must be absent or byte-identical to it. A valid but divergent envelope is not
   an overwriteable baseline. Legacy external-only first import remains separate.
4. Process pack and verify using existing checks. Stage exact planned ledger bytes
   and persist immutable intent. Recheck mirror baseline and owner identity before
   COMMIT. Any precommit error explicitly rolls back; partial intent stays blocked.
5. Attempt COMMIT, preserving process-local unknown/committed reporting. For a
   new target publish the committed private stage with no-overwrite semantics.
6. Hold the common lock, close/reacquire a fresh migration owner, and fetch current
   raw internal ledger. This gap can admit ordinary writers; never restore planned
   DB metadata or stale stage bytes. Require current ledger hash to equal intent
   before or after. Equal before/after permits convergence, not commit inference.
7. If mirror already equals current ledger, preserve its file identity/metadata.
   Otherwise publish a fresh exact-current-byte stage only when mirror is absent
   or still the intent's original file+bytes. An unexplained third state conflicts.
8. Verify current mirror equality while owner is still held, explicitly `finish(0)`,
   then remove only the exact pending file snapshot, and release common lock. A
   cleanup failure reports mirror-converged plus cleanup-pending, never rollback
   or a failed DB commit. It blocks a new intent until revalidated cleanup succeeds.

Recovery of an original-new target still absent may retire the intent only if the
original mirror is unchanged and the retained stage has its recorded file ID.
This says only that no authoritative target is currently present, NOT that one
was never published. Retain the stage. Existing-target
absence or foreign target identity is conflict. With no current internal ledger,
only a before-absent intent plus unchanged original mirror can be retired. A
current ledger outside before/after needs separate export or a new reviewed
reconciliation intent; never reuse planned bytes blindly.

## Crash/retry/cancel obligations

| Interruption | Required next action |
|---|---|
| Before complete intent | DB transaction rolls back; incomplete pending fails closed |
| After intent, before/inside COMMIT | Fresh owner reads current DB; hash is not commit proof |
| New stage committed, target absent | Retain stage; never publish during recovery |
| Target committed, mirror stale | Export exact current ledger; do not restore DB |
| Mirror published, pending remains | No-op equality check then remove exact intent |
| Cleanup/remove fails | Pending remains; retry is idempotent, no recursive deletion |
| Cancellation before COMMIT | Explicit rollback when possible; do not claim it otherwise |
| Cancellation after COMMIT | Preserve committed/unknown evidence; mirror may remain pending |
| Another writer changes only DB rows | Preserve those writes; reconcile current raw ledger only |
| Another writer changes ledger to third state | Conflict; no overwritten mirror/DB |

Read-only verify/dump do not acquire or break stale migration locks merely because
valid pending exists. They validate current DB/ledger normally and separately
report mirror pending. A journal authorizes only its original mirror, planned
bytes, or current bytes; invalid journal/foreign target/unexplained divergence
fails closed. Mirror convergence is not full data verification.

## Incremental implementation and Actions-only validation

Milestone 1 adds strict file snapshots, immutable intent encode/read/remove,
preexisting-divergence rejection, and a pure recovery classifier in
`lm_mirror.[ch]`, registered only on the transaction executable. Independent
source review cleared this helper milestone; that is not runtime validation.

Milestone 2 now source-integrates prepare/publish/recover and owned-artifact
retention in `lm_main.c`, with focused `tests/migration/mirror_recovery.py` and
`.github/workflows/migration-mirror-recovery.yml`. The integration/probe/workflow
received final bounded independent source clearance on 2026-10-28 at 20:18 UTC
from the separate migration commit-reporting reviewer. No commit/push/run is authorized by this
document, and no runtime result is claimed. Separate immediate publication
approval is required; the earlier four-file commit-outcome package stays separate.

Actions must cover all three OSes: absent/regular/error and special paths; partial
and unknown-version intents; copied/foreign target identity; preexisting sidecar
divergence; crash before/after COMMIT, new-target publication, mirror publication,
and intent removal; cooperative cancellation versus Windows hard kill; read-only
verify/dump with pending; equal ledger bytes despite actual DB changes; ordinary
writer preservation; third-state ledger refusal; no-overwrite foreign new target;
missing-mirror reconstruction retaining unknown/orphan/unlocated history; stale
lock retry and retention of abandoned stages. Tests generate fixtures and parse
all artifacts only in Actions. Preserve raw failure evidence.

Run original 65/31/17 gates unchanged and compare exact failed-case identities,
not just counts. Real mirror support is expected to address seven of the first
eight currently failing transaction cases. `ledger_loss_does_not_duplicate`
also demands `adopted-existing` after deleting only the external mirror; retained
internal identity must not be erased or mislabeled just to pass that assertion.
The four replacement/pre-image-stage cases remain incompatible with in-place
SQLite ownership unless their real semantic safety can be satisfied; never fake
`published`, postcommit rollback, or a DB pre-image. No green claim until evidence.

### Historical 53/65 failure mapping (not a new result)

| Historical failing case | This candidate's intended effect |
|---|---|
| `note_ambiguous_quote_unlocated` | Real external mirror makes retained record observable |
| `fixed_missing_quote_unlocated_and_rects_recorded` | Same |
| `unknown_fields_reported_and_kept` | Same, exact raw ledger export |
| `orphan_note_preserved` | Same, no serializer reconstruction during recovery |
| `rerun_same_pack_is_stable` | Same bytes, and already-equal mirror is not replaced |
| `same_original_different_legacy_id_merges` | Real mirror exposes both mappings |
| `ledger_with_unknown_version_refused` | Real mirror exists; original envelope refusal preserved |
| `ledger_loss_does_not_duplicate` | No duplication and bytes rebuilt, but no false `adopted-existing` event |
| `existing_target_content_is_preserved` | No fake replacement-stage `published` report |
| `write_failure_after_partial_writes_keeps_target` | Existing rollback safety retained; stage-report mismatch unresolved |
| `ledger_publish_failure_rolls_back_library` | Real post-COMMIT failure reports committed + pending, never rollback |
| `failed_rollback_is_reported_and_pre_image_kept` | No invented DB pre-image or unsafe restore |

Seven fixes are a source-grounded expectation, not 60/65 runtime evidence. The
latest established original gate remains 53/65 at run 40667133471. The focused
workflow does not run or substitute for the 65/31/17 gates, schema-6/WAL coverage,
or performance budgets; those require subsequent unchanged Actions validation.

The publication-failure rollback case is not proof that SDK expansion is needed:
a later genuinely pre-COMMIT mirror publication could call `finish(0)` on real
publication failure. That different protocol requires an exact external-mirror
preimage, bound publication-file identity, and safe handling of a new target's
orphan mirror. It is intentionally not mixed into this reviewed post-COMMIT
convergence candidate. Historical exact-once commit receipts and identity-bound
no-create SDK opening remain unavailable in the frozen API; current-state mirror
reconciliation does not require either under the explicit host coordination.

Current seven owned paths, relative to local base `2249fa4a06370153423d27acb5fc3ea4f01a24ea`:
`extras/migration/CMakeLists.txt`, `extras/migration/src/lm_main.c`,
`extras/migration/src/lm_mirror.c`, `extras/migration/src/lm_mirror.h`,
`tests/migration/mirror_recovery.py`, `.github/workflows/migration-mirror-recovery.yml`,
and this document. No old tests, old workflows, SDK files, or budgets changed.

### Source-review manifest and next-run boundary

Workspace: `/workspace/shared/exreader-migration-mirror-recovery-20261028`.
Branch: `codex/migration-mirror-recovery-20261028`. The seven-path candidate is
uncommitted source on the base above; the separate commit-outcome checkout is
still clean at that base. Source review covered helper validation, main control
flow, probe assertions, workflow permissions/freeze guard, and protocol limits.
Review fixes include both pre-COMMIT and pre-mirror-publication cancellation
fences, dry-run non-mutation, strict legacy dump fallback, safe early target-race
refusal, and explicit ownership before temp cleanup.

The intended single new workflow is `migration-mirror-recovery.yml`: push-only
on this exact branch, one Linux/Windows/macOS matrix, contents-read permission,
per-SHA concurrency, 30-minute per-job timeout, unchanged installed SDK build,
transaction tool build, then `mirror_recovery.py`. It retains complete build
logs, generated fixtures/DBs, raw process output and JSON summary as artifacts.
No manual dispatch or automatic rerun is added. Before any approved push, verify
the exact remote SHA/runs to avoid duplicate same-source execution.

Focused assertions cover normal/idempotent/missing mirrors; preexisting valid
divergence; real mirror publication failure; dry-run with pending; ordinary row
writer preservation; intent/commit/mirror crash points; POSIX cooperative
cancellation versus explicitly labeled Windows hard kill; early/late foreign new
targets; missing private stage; equal ledger hashes despite DB note restoration;
third-state ledger, foreign target, malformed and unknown-version intent refusal.
They do NOT establish schema-6/WAL recovery, true cleanup-I/O failure, full special
file/ACL behavior, full browser/review/65-case acceptance, or performance budgets.
Those are unchanged subsequent Actions obligations, not passed coverage.

The workflow timeout is a resource ceiling, not a completion estimate. There is
no credible CI finish ETA before publication authorization, queue admission, and
the first build observation. Stop before commit/push/CI until this expanded
seven-path package receives specific approval; do not reuse the older four-path
commit-outcome approval for it.
