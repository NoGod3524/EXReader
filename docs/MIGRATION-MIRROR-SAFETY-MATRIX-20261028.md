# Frozen-v2 safety matrix and unchanged full-gate companion plan

Status: first Actions run retained as failed; narrow CI repair prepared below.
No local build/test/fixture/artifact parsing. Initial product code was copied from
the reviewed pre-COMMIT v2 package; the successor transparently fixes its owned
mirror helper's OS-specific owner/ACL behavior. Matrix additions are:

- `tests/migration/mirror_safety_matrix_20261028.py`
- `.github/workflows/migration-mirror-safety-matrix-20261028.yml`
- `.github/workflows/migration-matrix-full-companion-20261028.yml`
- this document

Workspace: `/workspace/shared/exreader-mirror-safety-matrix-20261028`.
Branch: `codex/migration-mirror-safety-matrix-20261028`.
Independent resumed review/fix copy:
`/workspace/shared/exreader-matrix-review-resume-20261028`.
Local base is `2249fa4a06370153423d27acb5fc3ea4f01a24ea` plus the ten inherited
precommit-package paths. The initial matrix review edited no inherited source;
the observed CI failures now justify only the `lm_mirror.c` changes below.

## Same-source identity

Both workflow preflight and probe require the reviewed product SHA-256 values:

| Source | SHA-256 |
|---|---|
| migration CMake | `b3ce74a1ad235859cf2656ea99c09a2d8447fc365484a20bedd77eeba5df4ab9` |
| `lm_main.c` | `2c36cb0d8c4102b35e11f45419820de5154ec98f5819694567ca3e239814b5ff` |
| `lm_mirror.c` | `3275bafb28e3767921ca1756f612abbd2192ac80651a887952767791db5d976a` |
| `lm_mirror.h` | `dccc5374b27f6614a7872cc584a952c11acf767200a8aa68ae1cc24f5c7b6be3` |

The exact changed-path allowlist against `e771f3c5d1567412f26184ad304730b7c640235d`
freezes SDK, original tests, original workflows and budgets. Evidence includes
full Actions source SHA/run/attempt, product source hashes and executable hashes.
No hash is used to infer whether a historical database COMMIT occurred.

Real schema-6 input is built **inside Actions** using actual SDK 3.40 source
`c2d23c29a3b2096c2236fdb414dcd1e66d3243b4` and its original migrator. The probe checks
both old executable version and actual `PRAGMA user_version=6`; it never changes
the schema header to fake a legacy fixture. Schema-7 seeds use the reviewed tool.

## New focused coverage

The Linux/Windows/macOS matrix source contains fifteen independently recorded cases;
one case failure does not erase later case evidence:

1. Four combinations of actual schema 6/7 and DELETE/WAL journals: explicit
   precommit publication-failure rollback, hard crash after mirror publication,
   cancellation before/after mirror publication, active-owner exclusion of ordinary
   writers, post-COMMIT ordinary writer preservation, busy fresh recovery owner and
   subsequent retry.
2. Both directions of the common migration lock: actual old migrator owner versus
   v2 contender, and v2 owner versus old contender. Never break a live owner's lock.
3. Foreign schema-6 target identity is rejected before the CREATE/upgrade-capable
   SDK opens it; an absent original-existing target is never recreated.
4. Legacy external-only recovery refuses an inaccessible preimage: POSIX symlink
   or real Windows read-deny ACL. Foreign bytes remain untouched; restored access
   allows exact baseline recovery without persisting a schema upgrade.
5. Non-regular mirror paths: POSIX FIFO and Windows directory junction. All
   migrate/verify/dump commands must refuse without blocking or touching the target.
6. Real intent-unlink failure after the recovery owner has finished(0) and owned
   preimage artifacts are already retired. POSIX directory permission refusal or
   Windows no-delete-share handle must report bytes-converged/cleanup-pending, not a DB
   rollback or failed historical COMMIT. An ordinary row write after owner
   release must survive both that failure and the retry after restoring access.
7. New-target v1 and existing-target v2 interrupted post-COMMIT acknowledgements:
   retain the legacy `failed / review-hook-timeout / exit 3` result while asserting
   `target_commit=committed`, correct separate private-stage knowledge, no claimed
   rollback, and exact current-state recovery. POSIX uses cooperative SIGTERM;
   Windows uses the real acknowledgement timeout, not a claimed graceful cancel.
   New-target precommit cancellation separately asserts no authoritative target,
   `target_commit=not-attempted`, and `private_stage_commit=not-committed`.
8. Foreign new target created at `writer-pause`: the v2 pre-COMMIT refusal is
   `target-changed / exit 3`, with both commit fields `not-attempted`. Foreign
   bytes and file identity survive; no mirror/intent is published. This is not
   the older, later publication-conflict expectation described below.
9. A real DELETE-journal reader blocks COMMIT: the failed call reports `unknown`,
   never a historical rollback inferred from cleanup or later recovery. A separate
   current-state read and recovery verify this particular rollback's data.
10. Equal ledger-before/after hashes with actual deleted-note restoration at COMMIT:
    recovery preserves the restored note and never treats equal bytes as evidence
    that COMMIT did not occur.

The early `publish-cancel` hook retains its historical `rolled_back=false` field;
the additive `target_commit=not-committed` records successful explicit rollback.
The later v2 `precommit-cancel` path additionally reports `rolled_back=true` after
its explicit rollback and exact mirror restoration. Tests preserve that distinction,
including actual schema-6 upgrade rollback and live WAL, rather than editing the
frozen product to make the two legacy fields identical.

WAL assertions compare authoritative logical rows/schema/ledger with a live WAL
connection, not the raw main-DB hash as proof of committed state. A committed
ordinary row write must survive recovery. Repeated hard-crash rendezvous remove
only their own stale test marker before starting the next process, so an old
marker cannot falsely prove a new process reached COMMIT.

The host coordination/stable namespace/process-crash-only boundary of v2 remains
unchanged. This is not power-loss atomicity, arbitrary noncooperating pathname CAS,
or proof of untested Windows file-symlink variants. The Windows special-path case
is explicitly a directory junction. Windows preimage read denial is a real ACL
fixture calibrated with an ordinary denied file read. Windows cleanup refusal is
a real kernel sharing fixture calibrated by a denied DELETE-access open before
resuming the tool; it is not mislabeled as the ineffective prior delete-ACL test.

## Historical probes remain retained, not silently passed

All inherited test/workflow/doc paths remain byte-for-byte unchanged by this
matrix review. Their branch-specific workflows do not run on the matrix branch.
In particular, `commit_outcome_evidence.py`'s
`private-stage-publication-conflict` case creates a foreign target at
`writer-pause` and asserts `publish-failed`, `private_stage_commit=committed`,
and `target_commit=unknown`. Frozen v2 now detects that target before COMMIT and
returns `target-changed`, with both commit fields `not-attempted`. That exact
historical assertion is retained, not reclassified as a pass or rewritten. No
new runtime failure is claimed: it has not been run against this candidate.
The new `foreign-new-target-before-commit` case records the actual v2 boundary
and the unchanged safety invariant that foreign bytes/identity must survive.
The inherited `mirror_recovery.py` also retains its historical post-COMMIT
existing-target `sidecar-fail` expectation; it is not v2 acceptance. Existing
failure artifacts remain untouched. The new matrix's commit/cancellation cases
provide explicit same-SHA coverage; merely retaining historical source files
does not count as executing those probes.

## Consolidated publication scope (17 unique paths in CI successor)

The publication baseline is the published full SHA
`e771f3c5d1567412f26184ad304730b7c640235d`, not local unpublished commit
`2249fa4a06370153423d27acb5fc3ea4f01a24ea`. The latter's four paths are included
below. Commit-outcome has four paths against the published baseline; mirror,
precommit and matrix have respectively 7, 10 and 13 paths against local
`2249fa4`. They overlap at `lm_main.c`; the consolidated diff is exactly these
16 initially published paths plus one additive companion workflow:

| Path | Change against published baseline | Origin |
|---|---|---|
| `.github/workflows/migration-commit-outcome-evidence.yml` | add | unpublished commit-outcome |
| `docs/MIGRATION-COMMIT-OUTCOME-EVIDENCE.md` | add | unpublished commit-outcome |
| `tests/migration/commit_outcome_evidence.py` | add | unpublished commit-outcome |
| `extras/migration/src/lm_main.c` | modify | commit-outcome + mirror + precommit; frozen in matrix |
| `extras/migration/CMakeLists.txt` | modify | inherited mirror; frozen in matrix |
| `extras/migration/src/lm_mirror.c` | add | mirror + precommit; narrow OS owner/ACL CI repair |
| `extras/migration/src/lm_mirror.h` | add | mirror + precommit; frozen in matrix |
| `.github/workflows/migration-mirror-recovery.yml` | add | inherited mirror |
| `docs/MIGRATION-MIRROR-RECOVERY.md` | add | inherited mirror |
| `tests/migration/mirror_recovery.py` | add | inherited mirror |
| `.github/workflows/migration-precommit-mirror.yml` | add | inherited precommit |
| `docs/MIGRATION-PRECOMMIT-MIRROR.md` | add | inherited precommit |
| `tests/migration/precommit_mirror.py` | add | inherited precommit |
| `.github/workflows/migration-mirror-safety-matrix-20261028.yml` | add | new matrix, reviewed here |
| `docs/MIGRATION-MIRROR-SAFETY-MATRIX-20261028.md` | add | new matrix, reviewed here |
| `tests/migration/mirror_safety_matrix_20261028.py` | add | new matrix, reviewed here |
| `.github/workflows/migration-matrix-full-companion-20261028.yml` | add | CI successor, original jobs unchanged |

Actions preflight requires exact set equality, not merely an allowed subset,
records all 17 source SHA-256 digests and rejects any SDK/old-test/old-workflow
drift outside that set. The four product hashes above remain mandatory.
The first review changed only its three matrix-owned paths; the CI successor also
adds the companion and repairs the existing owned mirror helper. No local
build/test, fixture creation or artifact parsing is permitted or performed.

## Required unchanged full companion run on the same SHA

A focused matrix pass is **not** 65/31/17 acceptance. Original dispatch was blocked
by absent authenticated CLI/browser dispatch capability; neither original feature
ref was moved. The additive `migration-matrix-full-companion-20261028.yml` copies
the original `migration-transaction-candidate.yml` unchanged from `concurrency:`
through the end, including every job/step/assertion/budget. Only workflow name and
`on` trigger differ: push on the matrix feature branch, with original path filters
plus the two owned workflow paths; no manual dispatch. A successor push launches
the focused and full companions together. Verify exactly one run per workflow
and that both `head_sha` values equal the new approved full source SHA.
Do not edit the original workflow or any test to accommodate the remaining four
old semantic failures. Its original source contains all three transaction-candidate
companions:

- `run_cases.py`: all original 65 scenarios and assertions;
- `review_cases.py`: all original 31 review checks;
- `tests/migration/e2e/check_e2e.py`: original 17-check real browser chain, using
  legacy reader input `24a3e04b6fc456fa3fa68fa7bd6d9cc3b5c4e383` and shipped exporter.

Source-only comparison against published `e771f3c5` confirms exact unchanged
bytes for these full-companion inputs (SHA-256, not runtime results):

| Source | SHA-256 |
|---|---|
| `tests/migration/run_cases.py` | `28c1401cdfac08475232a5b234748b379aca2ef8a9bf0760cd32310db83b215a` |
| `tests/migration/review_cases.py` | `3912538b2eb56f6b41a5b8a1ed4fdc85536a30c510c956af025b6a0ce18244a4` |
| `tests/migration/e2e/check_e2e.py` | `18dd994656ba58a3d7a1497bf449306e33b17a51a9a99aeb2d0befc3262d3b39` |
| `.github/workflows/migration-transaction-candidate.yml` | `c506e4166704a442cad4cdbdc5cd3cd4fb2a92e2a4324c20bb70b3bbaf7be373` |
| `tools/check_legacy_migration.py` | `a1b9d01d00d1f1d31eb37fb1a12d15450edda088f89d7df7e5ed25e546a44275` |

The original workflow also retains its unchanged aggregate gate, performance
budgets, raw logs/artifact identities and final failure propagation. Preserve its
failed outcome and exact failing case names; do not summarize only a pass count.
The existing established result is still 53/65 from run 40667133471. The source
expectation of seven mirror fixes plus one precommit rollback fix is not a measured
61/65 result, and no old case has been reclassified or waived.
The four currently identified unresolved original semantic assertions remain:
`ledger_loss_does_not_duplicate`, `existing_target_content_is_preserved`,
`write_failure_after_partial_writes_keeps_target`, and
`failed_rollback_is_reported_and_pre_image_kept`. This is not a prediction that a
new run can fail only those four; preserve and report every actual failure.

This plan requires **two distinct approved workflow scopes**: the new focused
three-OS matrix and one same-SHA original full companion run. They exercise different
coverage, not a duplicate rerun of the same workflow/source bundle. Before either
launch, read remote SHA/runs for deduplication and record the full SHA. No workflow
is dispatched by this source document. The new matrix's 60-minute job timeout is
the same ceiling used by the original full workflow, not a performance-budget
change or completion ETA. No credible CI finish ETA exists before approval/queue
admission/build observation.

## Resumed review disposition

Two source-review passes found and corrected a same-SHA coverage gap only in the
new matrix-owned paths: inherited focused workflows are not selected by this
branch, and the full companion has no `atomicity.transaction` assertions. The
new fifteen-case probe now covers the missing cancellation/commit-knowledge and
earlier foreign-target-refusal boundaries. Workflow preflight also rejects a
missing path from the consolidated sixteen-path bundle. A second independent
source review found no further concrete assertion/control-flow issue in those
edits. This is not compilation, OS-fixture or runtime clearance.

At the initial source-only checkpoint, product sources and all ten inherited precommit-package paths compared exactly
with `/workspace/shared/exreader-migration-precommit-mirror-20261028`; the only
differences from the starting matrix copy are this document, its new probe and
its new workflow. Pinned old SDK source was read through the read-only GitHub
connector: its original migrator has the real schema-6 header requirement,
common `.migrate-lock`, and `publish-pause` rendezvous used by the matrix.

The user explicitly approved the consolidated sixteen-path publication and two
same-SHA workflow scopes on 2026-10-28 at 21:28:14 UTC, in response to the exact
scope request sent at 21:27:21 UTC. This materially new approval covers publication
to `refs/heads/codex/migration-mirror-safety-matrix-20261028`, its push-triggered
three-OS matrix, and a separate unchanged `migration-transaction-candidate.yml`
dispatch on that frozen feature-branch SHA. Before publication, the branch/ref
and automatic runs are checked for absent or uncertain previous effects; never
start duplicate same-source runs. This is not an older four/seven/ten-path approval
or a saved permanent permission rule. No PR, main update, tag or release is in
scope. That initial publication is now retained as failed, not retrospectively
changed into a pass.

## First Actions run and justified CI successor

Published source `62b93cadc04483ea5d4917a090c94f815bf769bd`, tree
`f1d85e23dde71cd5540967ab97151bd5ff4f1f78`, ran focused matrix
[40772784064](https://github.com/NoGod3524/EXReader/actions/runs/40772784064), attempt 1.
The remote tree exactly matched local reviewed commit `a389a7c`; Git push lacked
shell credentials, so the authorized connected GitHub API published identical
tree bytes. No old feature ref, main, tag or PR was changed.

- macOS failed tool compilation: `O_NOFOLLOW` was undeclared in `lm_mirror.c`.
  The narrow fix defines `_DARWIN_C_SOURCE` before includes, as existing tool
  files already do; it does not remove `O_NOFOLLOW`. Artifact `12852812875`
  preserves that failure.
- Linux completed 13/15 focused cases. `schema6-delete` and `schema7-delete`
  failed because an ordinary writer committed while the migration owner should
  have excluded it. POSIX identity-only snapshots opened and closed the target
  DB, releasing the process's SQLite advisory locks. The repair uses `lstat`
  for non-content identity snapshots, rejects symlink/special files, and never
  opens/closes the DB merely to identify it. SDK open still checks access rights;
  stable namespace coordination remains required. Byte reads retain guarded
  `O_NOFOLLOW` opens. This mechanism is documented by
  [SQLite's advisory-lock guidance](https://www.sqlite.org/howtocorrupt.html#posix_advisory_locks_canceled_by_a_separate_thread_doing_close_).
- Windows completed 13/15 focused cases. `preimage-access-refusal` unexpectedly
  succeeded; the renamed preimage retained its deny-read ACL, fixture cleanup
  looked only at the old pathname, and artifact ZIP upload failed with EPERM.
  Raw Actions logs retain this failure; do not claim a complete Windows artifact.
  The helper removes unnecessary `FILE_FLAG_BACKUP_SEMANTICS`, which can enable
  privileged ACL bypass, while retaining `FILE_FLAG_OPEN_REPARSE_POINT` and
  directory/reparse rejection. The ACL probe now calibrates actual read denial
  and restores either preimage or renamed mirror access even when its assertion
  fails, preserving the failure rather than suppressing it.
- Windows `real-intent-cleanup-failure` also failed: its delete ACL did not force
  the intended unlink error. The successor transparently uses a no-delete-share
  handle with an independently observed sharing violation (Win32 error 32), not
  a claimed ACL refusal. It still requires the same cleanup-pending report,
  released DB owner, preserved ordinary write, and successful retry after release.

No original assertion or failed evidence is rewritten. The original full gate
did not run at this initial SHA. The additive companion avoids unauthorized
dispatch capability changes and existing-ref moves; both suites must run against
the successor SHA. Current source repairs have no runtime result until Actions
build and exercise them. Full 65/31/17 acceptance remains unestablished.

Independent source review cleared the complete successor helper and Windows
fixture cleanup on 2026-10-28 at 21:44 UTC. Reviewed probe SHA-256:
`a4b87be2ea851cd9fe419eca7abdd0f7f12a9d969b32dc62dd606c5c08093fb0`;
additive companion SHA-256:
`e3bb07eadd436f1d0ceaa53bad754f8e8e6abba6f80bdb8ac46868cae40813d3`.
The initial Linux artifact is `12853436430`, ZIP digest
`6b45fd4dbc62218d9ae72d674aa9e6f743d3ea2bf04f9a1501d2acfaf0676466`;
the initial macOS artifact ZIP digest is
`a98df1e29580f5b42806b6aee82690ab2ffcc32463d032399e343d6e7c709e30`.
These identities were read from Actions metadata; no artifact was parsed locally.
