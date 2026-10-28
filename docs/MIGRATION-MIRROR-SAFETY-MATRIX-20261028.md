# Frozen-v2 safety matrix and unchanged full-gate companion plan

Status: tested source `9e6f9a9d6dd46f1ac087d52bf04d832751dc765f` passes the
focused 15-case matrix on all three OS; the unchanged full companion remains
red at 61/65 candidate scenarios per OS. Exact terminal evidence and the unresolved
historical acceptance-contract decision are below. The newly authorized additive
candidate tests are prepared, not yet executed. Full P0 / original 65/65 is not accepted.
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

The first Linux/Windows/macOS matrix contained fifteen independently recorded cases;
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
At the pre-run checkpoint the established result was 53/65 from run 40667133471.
The then-source expectation of seven mirror fixes plus one precommit rollback fix
was not a measured 61/65 result. The terminal successor result is now recorded
below; no old case has been reclassified or waived.
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
the successor SHA. At that repair-review checkpoint the source had no runtime
result until Actions built and exercised it. Full 65/31/17 acceptance remains
unestablished after the successor results below.

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

## Terminal same-SHA Actions evidence

Tested commit: `9e6f9a9d6dd46f1ac087d52bf04d832751dc765f`; tree:
`fc5267b11f4f360d97d6d43cf51e890c0fc812dc`. Both runs are attempt 1 and
completed; neither the failed first run nor these runs were cancelled or rerun.
This evidence seal changes this document only, not the tested product, SDK,
fixtures, tests, workflows or budgets. Both workflow path filters exclude a
docs-only change, so the seal does not request another validation run. Claims
refer to the tested commit above, not to a later documentation commit.

| Actions run | Linux | macOS | Windows | Overall |
|---|---|---|---|---|
| [Focused matrix 40774524902](https://github.com/NoGod3524/EXReader/actions/runs/40774524902) | 15/15 | 15/15 | 15/15 | success |
| [Unchanged full companion 40774524965](https://github.com/NoGod3524/EXReader/actions/runs/40774524965) | candidate 61/65, review 31/31, E2E 17/17 | candidate 61/65, review 31/31, E2E 17/17 | candidate 61/65, review 31/31, E2E 17/17 | failure |

The full companion's noncandidate executable separately passed 65/65 scenarios
(135/135 assertions), review 31/31 and E2E 17/17 on each OS. The transaction
candidate recorded 130/135 assertions on each OS, not 135/135. Its same four
failed scenarios and five failed assertions are listed below. The aggregate
`record` job also failed with `required migration jobs did not all succeed`;
its incomplete/mismatched-evidence review step was skipped because the gate was
already failed. That skipped step is not claimed as passed.

Actions job logs, not local artifact parsing, establish these results:
focused [Linux](https://github.com/NoGod3524/EXReader/actions/runs/40774524902/job/123120193549),
[macOS](https://github.com/NoGod3524/EXReader/actions/runs/40774524902/job/123120193096),
[Windows](https://github.com/NoGod3524/EXReader/actions/runs/40774524902/job/123120193975);
full [Linux](https://github.com/NoGod3524/EXReader/actions/runs/40774524965/job/123120197615),
[macOS](https://github.com/NoGod3524/EXReader/actions/runs/40774524965/job/123120197902),
[Windows](https://github.com/NoGod3524/EXReader/actions/runs/40774524965/job/123120198171),
[aggregate](https://github.com/NoGod3524/EXReader/actions/runs/40774524965/job/123123785185).
All 15 named focused cases explicitly logged `passed: true` per OS. In particular,
Windows now records the calibrated read ACL, directory junction and no-delete-share
cleanup fixtures, with a successfully uploaded artifact. This does not erase the
first Windows upload failure or claim untested file-symlink/power-loss behavior.

### Four retained failures: exact contract mapping

Source references in this section are frozen at the tested commit. No old tests
or expected outcomes were changed. Independent source review agrees that merely
relabeling the new implementation cannot truthfully satisfy these old mechanisms.

1. **`ledger_loss_does_not_duplicate`: 2/3.**
   [`run_cases.py:428-436`](https://github.com/NoGod3524/EXReader/blob/9e6f9a9d6dd46f1ac087d52bf04d832751dc765f/tests/migration/run_cases.py#L428-L436)
   deletes the external mirror, not the authoritative internal ledger, and requires
   an `adopted-existing` entry. `lm_main.c:1988-1998` reloads the surviving internal
   lineage; `:727` and `:821` therefore emit `already-migrated`. The no-new-books/notes
   and unchanged logical-content checks passed. Rewriting known lineage as a new
   adoption solely to satisfy this assertion would misdescribe the operation.
2. **`existing_target_content_is_preserved`: 1/2.**
   [`run_cases.py:478-487`](https://github.com/NoGod3524/EXReader/blob/9e6f9a9d6dd46f1ac087d52bf04d832751dc765f/tests/migration/run_cases.py#L478-L487)
   passes the existing book/notes/IDs preservation check, but demands
   `atomicity.stage=published` as evidence of backup/replacement.
   `lm_main.c:1982` opens the existing target for an in-place transaction; only a
   new target publishes a private DB stage at `:2218-2224`. No existing-target DB
   stage was published, so that report must not be fabricated.
3. **`write_failure_after_partial_writes_keeps_target`: 3/4.**
   [`run_cases.py:673-679`](https://github.com/NoGod3524/EXReader/blob/9e6f9a9d6dd46f1ac087d52bf04d832751dc765f/tests/migration/run_cases.py#L673-L679)
   combines exit/code with a DB-stage value of `removed` or `built-from-backup`.
   The source injects the write error at `lm_main.c:805`, but an existing-target
   transaction creates no DB stage. Actions records that combined assertion failed;
   it does not independently expose the truth of each short-circuited predicate.
   The subsequent byte-equality, no-residue and logical-content checks did run
   and pass: [`Ctx.check:68-70`](https://github.com/NoGod3524/EXReader/blob/9e6f9a9d6dd46f1ac087d52bf04d832751dc765f/tests/migration/run_cases.py#L68-L70)
   appends/returns a boolean, does not raise, and its caller does not return early.
   [`unchanged:577-580`](https://github.com/NoGod3524/EXReader/blob/9e6f9a9d6dd46f1ac087d52bf04d832751dc765f/tests/migration/run_cases.py#L577-L580)
   supplies two checks, followed by the logical-content check. Each OS log explicitly
   reports 3/4 with only the first composite assertion failed. A review suggestion
   that these later checks were skipped was checked against source and corrected.
4. **`failed_rollback_is_reported_and_pre_image_kept`: 0/2.**
   [`run_cases.py:711-717`](https://github.com/NoGod3524/EXReader/blob/9e6f9a9d6dd46f1ac087d52bf04d832751dc765f/tests/migration/run_cases.py#L711-L717)
   requires `inconsistent / exit 6` and a retained raw database `.pre-*` file.
   The v2 alias at `lm_main.c:1632` instead refuses mirror publication before
   COMMIT and `:1651-1663` attempts SDK rollback/restores external mirror bytes.
   Successful rollback cannot truthfully be called failed; a mirror preimage is
   not a raw database preimage. The genuine SDK rollback-error branch at `:1651-1653`
   exists but is **not exercised by this historical alias**. A calibrated real
   rollback-error/retained-evidence test is still a coverage gap; the 45/45 focused
   result does not grant that missing coverage.

### 封存时的最小验收决策（后续授权见下一节）

需要决定：**P0 是否允许现有目标采用“原位事务 + 内部权威账本”，并以新增、
架构一致的验收测试证明同等安全性，同时永久保留旧完整门禁的四项失败？**
若允许，下一步只新增验收覆盖，分别证明账本镜像丢失后的真实来源/无重复、
现有内容保护、部分写入失败的独立退出码与回滚证据，以及真正的回滚错误/
证据保留；不修改旧 65 项断言、不把 61/65 改称 65/65。
若仍要求旧的备份数据库替换、`adopted-existing` 事件、数据库 stage 和 `.pre-*`
语义全部成立，则需要重新设计迁移实现；不能靠改报告标签完成。这是验收契约/
架构选择，不是再批准一次相同 CI。当前完整 P0 仍未通过。

### Retained artifact identities

These are GitHub Actions metadata/ZIP digests, not a claim that artifacts were
downloaded or parsed locally. The full companion's aggregate parsed its inputs
inside Actions and preserved its failed summary. All artifacts below belong to
the tested full SHA and attempt 1.

| Scope / OS | Artifact ID | Bytes | ZIP SHA-256 |
|---|---|---:|---|
| focused / Linux | `12854710822` | 182325 | `10c2f5e9713caae7c88534b99e2a45ab644129a774caca6d763723d318918959` |
| focused / macOS | `12853778797` | 182537 | `f2f3b1c1cc3080f3577bb1cbe704b6e27910fc1e8973f1dcf3a9015fa9b71c3c` |
| focused / Windows | `12853872312` | 184219 | `9690a5ed92676c05bab770b9bbaacdf9cb7c64a8b8e33a96b830286fe47a6757` |
| full / Linux | `12854820663` | 310255 | `c2cba4d46c79328701e8d0bdfd96ca9867d4d2f9f10192516cdd820325adb90c` |
| full / macOS | `12854586419` | 303554 | `e04569f12bd0ff9971168b2efaa65e76539b6076d8213d82b9c5e8640b26351d` |
| full / Windows | `12854881283` | 304882 | `3644193a2c5bb6a51ac734322b3dbebdd09af96a4a48416db5bcfcbc995e8de0` |
| full / failed aggregate | `12853364688` | 1156 | `11edd78114815d9c813880142a48d9ecf8cd45bf8196eaed992aa545c77e8bbe` |

## Authorized additive transaction-candidate acceptance (source prepared)

At 21:59:11 UTC the user reaffirmed delegated approval in response to the exact
recommendation to continue the transaction candidate, add the four safety groups,
retain the original failures, and publish the feature-branch evidence. The
previously denied docs-only seal was retried once with that new evidence and
published as `e3597313e250d627920224a16e1224271fb6efad`; its tree exactly matches
`8ecb736d8e6cd55d84262d0dbb6788480bd068e1`. Ref readback succeeded and no Actions
run was created for that docs-only SHA. This does not retrospectively approve an
untested behavior or grant original 65/65 acceptance.

The following paragraph records the **frozen 22:10 proposal**, not the corrected
current test design. Its rollback-return assumption is superseded by the
source finding and explicit five-path successor below. The exact original
two-file payload remains preserved at `02e26205024c24f49c2140354a08100b7397ac45`.

That proposed delta adds tests in the existing owned matrix probe and updates this
document only. Product sources, SDK, inherited probes, all original 65/31/17
checks, original full jobs, thresholds and publication-path set are unchanged.
The original 15 matrix cases remain intact. Four additive groups contribute
14 independently recorded cases, making a required 29 per OS:

1. **Truthful lineage after mirror loss (4).** Real old SDK schema-6 seeds have
   no internal ledger; after removing their external ledger, content matching
   must report `adopted-existing`. Candidate schema-7 seeds retain their internal
   ledger; removing only the external mirror must report `already-migrated`,
   not invent adoption. Both variants run under DELETE and live WAL, preserve
   every original book/note column and file identity, create no duplicate books
   or notes, and rebuild the exact current mirror.
2. **Existing-library in-place preservation (4).** Actual schema 6/7 × DELETE/WAL
   preserve every original book/note column and file identity, independently
   verify writer exclusion, report a real committed transaction with no DB
   stage, and preserve a later ordinary write through idempotent recovery.
3. **Partial-write failure (4).** Two distinct new originals ensure one actual
   import succeeds before `write-fail@1` refuses the second. Each schema/journal
   combination separately checks exit 3, `failed`, `injected-write-fail`, and
   the correct absence of a DB stage. Fresh current-state observations establish
   preserved schema/rows/internal ledger, exact external mirror, same file
   identity and no owned residue. DELETE additionally checks raw DB bytes; WAL
   does not pretend a main-file hash captures live committed state. Close-time
   rollback is not relabeled as explicit process-local rollback acknowledgement.
4. **Real SDK rollback error (2, DELETE only).** At the existing post-mirror,
   pre-COMMIT rendezvous, require a real nonempty SQLite journal and calibrate
   actual OS deletion refusal before letting the SDK call `ROLLBACK`: POSIX
   removes parent-directory write permission and confirms a disposable owned
   file cannot be unlinked; Windows holds the exact journal without delete
   sharing and confirms Win32 error 32. POSIX uses cooperative SIGTERM; Windows
   lets the existing acknowledgement hook time out. No fake SDK return or old
   `rollback-fail` alias supplies the result. A case passes only for actual
   `inconsistent / rollback-failed / exit 6`, no claimed confirmed rollback,
   and exact retained intent, published mirror and mirror-preimage bytes.
   Journal size/header observations are recorded but never used to infer the
   rollback outcome. After releasing the OS fault, a fresh product recovery
   owner must restore original logical state/mirror, pass SQLite integrity
   checking and preserve a subsequent ordinary write on a repeated recovery.

The deletion fixture is deliberately **not** called WAL rollback-error coverage:
WAL rollback does not finalize a DELETE journal. WAL rollback-error behavior,
power-loss guarantees and unrestricted pathname replacement remain unproved.
This scoped fault tests an actual error return and retained recovery evidence,
not a claim that all row bytes remained changed after a failed acknowledgement.
SQLite may have restored data before journal finalization fails. The fixture
requires both the error report and independent successful later recovery.
The mechanism follows SQLite's documented
[journal lifecycle](https://www.sqlite.org/tempfiles.html) and
[SQLite 3.54.0 pager rollback/finalization implementation](https://github.com/sqlite/sqlite/blob/version-3.54.0/src/pager.c)
and [Windows journal deletion implementation](https://github.com/sqlite/sqlite/blob/version-3.54.0/src/os_win.c);
those references inform source review, not proof of the installed SDK's runtime
behavior. Only the next Actions result can establish these new cases.

The original written contract in `docs/WP12-LEGACY-MIGRATION.md:113-126` expressly
requires backup stages, database replacement and retained raw DB preimages; these
are not merely incidental test labels. The candidate contract intentionally
differs: keep internal lineage and database writes in one transaction, never
replace an existing DB, and retain accurately named mirror/recovery evidence.
This avoids restoring stale whole-DB bytes over later ordinary writes under the
documented stable-path/host-coordination contract. It does not prove integrated
host lifecycle or make the four original failures disappear. Candidate safety
acceptance and legacy full-gate compatibility must remain separate conclusions.

Independent source review cleared this additive 29-case design at 22:10 UTC,
after requiring cleanup operations and evidence writes to be attempted even
when permission/handle restoration fails. Probe SHA-256:
`119bfc40357f2f5f8a77d12f5496c00c41a9c62c616a8432faf8ee75e1f76c67`.
This is clearance to validate in Actions, not a measured rollback-error outcome.

## 22:41 correction: real I/O error observation is not SDK error-return proof

**Source-review clearance of the preceding mandatory exit-6 assumption is
superseded.** `src/library.c:247-252` returns the result of SQL `ROLLBACK` and
clears its transaction flag on OK. Pinned SQLite 3.54.0's
[`OP_AutoCommit`](https://github.com/sqlite/sqlite/blob/version-3.54.0/src/vdbe.c#L3997-L4045)
calls the void
[`sqlite3RollbackAll`](https://github.com/sqlite/sqlite/blob/version-3.54.0/src/main.c#L1437-L1477),
which discards the Btree rollback return. The Btree can return a pager I/O error
while ending/downgrading its transaction; later cleanup does not automatically
surface that dropped error. This is a confirmed source-level observability
limitation, not a measured corruption or data-loss event.

Consequently, neither actual journal-deletion refusal nor a real WAL read error
guarantees `exr_library_migration_finish(...,0,...) != EXR_OK`. The former test
was strict rather than fabricated, but its desired exit-6 outcome was not
justified by the complete call chain. The original payload and its source-review
history remain preserved, not silently rewritten into successful evidence.

The corrected package has five explicit paths relative to the held proposal:

1. `tests/migration/mirror_safety_matrix_20261028.py`
2. `docs/MIGRATION-MIRROR-SAFETY-MATRIX-20261028.md`
3. new `tests/migration/rollback_observe_20261028/CMakeLists.txt`
4. new `tests/migration/rollback_observe_20261028/observe.c`
5. `.github/workflows/migration-mirror-safety-matrix-20261028.yml`

The consolidated source manifest is now 19 paths relative to `e771f3c5`, with
the two new consumer files explicitly admitted by the existing source guard.
No helper source is hidden inside a generated Python string. The workflow builds
the consumer in Actions and passes its executable to the probe. Product sources,
the frozen SDK/SQLite implementation, the original 15 cases and other 12
candidate cases, all old 65/31/17 assertions/budgets, and the unchanged companion
jobs remain untouched. The test/doc/workflow delta triggers both existing
workflows on one successor SHA; no redundant dispatch is planned.

### Corrected group four: two independently recorded observation groups

The matrix still requires 29 top-level cases per OS. Each new schema-6/schema-7
observation group records its sub-observations independently; one failure does
not silently prevent the remaining observations from running:

- **Uninstrumented product DELETE refusal:** preserve the real journal and OS
  refusal controls, capture actual exit/result/rollback reporting, and record
  exact intent, mirror and preimage disposition. If the product reports
  `rollback-failed`, its strict retained-evidence assertions still apply. Other
  actual results are not relabeled as SDK errors or retained evidence. Fresh
  recovery must preserve original rows/identity and a later ordinary write.
- **Diagnostic DELETE negative control and actual refusal on all three OSes:**
  a separate consumer links the unchanged installed SDK and its matching public
  SQLite header. SQLite's public startup error callback observes the actual
  SDK process, without a replacement VFS, fake return, private-structure access
  or second SQLite implementation. Require a real `SQLITE_IOERR_DELETE` event
  for the exact owned journal during the actual SDK finish window. Record the
  literal SDK status/message, including OK if returned; SDK OK plus an internal
  I/O event is an observability limitation, **not** a passed failed-rollback
  branch. [SQLite's public error logger](https://www.sqlite.org/errlog.html).
- **Exact attribution control:** parse the pinned OS logger's filename field,
  require normalized filename equality and the expected OS operation, and run
  positive plus sibling-prefix negative parser controls in Actions. A log for
  `library.sqlite-wal` or `library.sqlite-other` must not count as a main-DB read
  fault merely because its message contains `library.sqlite`. These synthetic
  parser checks are labeled separately from actual fault calibration.
- **Windows-only WAL negative control and read refusal:** a checkpointed live
  WAL baseline locates committed page 1 in the main DB. Real schema-6 upgrade or
  schema-7 creation of the previously absent internal ledger dirties page 1.
  An exclusive native byte-range lock is calibrated by a separate `ReadFile`
  returning error 33, then held through SDK finish. A genuine SQLite read-error
  log for that exact path during finish is mandatory; a successful control lock
  alone is insufficient. The consumer explicitly disables SQLite mmap through
  its public configuration API, because native byte locks do not constrain
  mapped reads. This is a disclosed diagnostic configuration, not every host
  application's configuration. [Microsoft's byte-lock contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex).

The diagnostic consumer registers logging before SDK initialization, checks the
linked SQLite version and source ID against the pinned header, and writes its
actual finish result before a separate fault-release/close phase. No-fault
controls require SDK OK with no finish I/O event. Fault cases require actual
I/O attribution but do not prejudge the SDK result. A fresh actual SDK migration
owner first recovers/reopens, reads the expected absent ledger and explicitly
rolls back its transaction (including any temporary schema-6 upgrade).
Independent fixture SQL then checks integrity, every table/column/row, persisted
schema and ledger; a later ordinary write must remain readable. Its SQLite
version is recorded separately. These are fixture observations, not a production
SDK integrity API.

### Remaining acceptance and coverage gaps

The SDK-only API lacks this internal error logger and a whole-library integrity
operation. Diagnostic SQLite instrumentation must not be described as SDK-only
coverage. Linux/macOS WAL physical-I/O error coverage remains absent; their
ordinary permissions do not calibrate refusal on already-open WAL/DB handles.
Actual calibration of all new cases is still unmeasured until Actions executes
this successor. No runtime pass is claimed here.

`lm_main.c:1655-1665` currently treats SDK OK as sufficient to report rollback
and retire mirror evidence. `mirror_reconcile:1702-1707,1744-1749` checks only a
fresh ledger and then trusts another rollback result; it is not independent
whole-library proof. A conservative future tool-only mitigation could retain
evidence and report recovery-unverified until adequate verification, but must
persist that state and not silently auto-clear it through ledger equality.
No such product mitigation is included in this test package. Its impact on
normal rollback, schema-6 upgrade, later writers and restart needs independent
review and scope approval before implementation.

Thus an observation matrix pass would establish measured mechanisms and fixture
recovery, **not full candidate/P0 acceptance**. The original 61/65 candidate
results, four historical contract conflicts, original failure records and the
real error-return branch gap remain visible. No original 65/65 claim is made.
