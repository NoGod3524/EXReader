# Existing-target pre-COMMIT mirror publication (source-only package)

This separate candidate starts from local commit `2249fa4` plus the frozen,
source-reviewed seven-path mirror package. It does not modify that other worktree.
No build, test, fixture generation, performance run or artifact parsing has run
locally; all validation belongs in GitHub Actions. No remote write is authorized
by this document.

## Narrow objective

Make the unchanged `ledger_publish_failure_rolls_back_library` case truthful for
an **existing target**: the real external mirror publication occurs before SDK
COMMIT. A publication error is followed by explicit `migration_finish(...,0)`;
only success establishes `rolled_back=true`. Restore the exact original external
mirror bytes or original absence, then remove only the invocation's validated
owned intent/stage/preimage. No DB file replacement or DB preimage is invented.

New targets retain the prior v1 protocol: COMMIT private stage, no-overwrite
publish target, then reconcile its mirror. They do not acquire a new orphan-mirror
prepublication window. This hybrid is deliberately smaller than a global reorder.

## Existing-target immutable v2 intent

Keep all v1 fields and add a validated artifact run token, planned mirror file ID
and size, and exact external-mirror preimage file ID. Planned hash is the existing
after hash. Preimage bytes/size are the recorded original mirror hash/size. Fixed
artifact paths are derived from target + safe token, never accepted from JSON.
The journal remains bounded and immutable; v1 recovery remains supported.

Before any publication: exclusively stage exact planned raw ledger bytes; copy
an existing external mirror into a real exclusive byte preimage; flush both;
record their regular-file identities and hashes; exclusive-create and flush the
v2 intent. The preimage is external JSON, NOT a database image. A partial intent
fails closed and retains its evidence.

POSIX preimage contents are written only after mode 0600 is established; restoring
that copy may intentionally tighten access rather than reproduce all metadata.
On supported modern Windows, exclusive `CopyFileW` preserves source security
attributes, then the owned copy is flushed and hash/identity-checked. The API's
security-attribute behavior starts with Windows 8/Server 2012; older Windows is
not a confidentiality guarantee of this protocol. See
[Microsoft CopyFileW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-copyfilew).
This is a byte-preimage contract, not a portable ACL/xattr/timestamp restoration
contract. An unconfirmed failed copy is retained, never deleted by filename alone.

Publish planned mirror only after baseline/owner/stage rechecks. COMMIT follows
only after a second cooperative cancellation check. A successful DB COMMIT means
the mirror already reflects planned bytes; current-state reconciliation still
reacquires a fresh owner and reads exact current ledger bytes before retiring the
intent. Ordinary row writers are preserved.

## Failure and recovery decisions

- Real precommit mirror publication failure or cooperative cancellation: explicit
  SDK rollback first. If confirmed, restore exact original mirror/absence using
  the recorded preimage or remove only the recorded planned file. Never delete a
  foreign same-content file just because a hash matches. Failed rollback or
  unexplained mirror identity leaves intent/evidence and reports inconsistency.
- COMMIT error: retain `unknown`, even if cleanup later rolls back. Do not claim a
  historical outcome. Restart reads current internal ledger and converges bytes;
  ledger-before==ledger-after is not COMMIT proof.
- Existing target with current ledger before/after: export exact current raw bytes
  when mirror is original, recorded planned publication, or absent. Equal-current
  mirror is a no-op.
- Existing target with no internal ledger and before_found=false: use the recorded
  external preimage/absence, but only replace/remove the recorded planned file.
  A restored preimage file ID is recognized on retry after its rename.
- Original-new target recovery stays v1 and never publishes its private stage.

Retire owned artifact files only after mirror disposition is verified and the
fresh recovery owner has explicitly finished(0). Then remove the exact intent.
A crash during cleanup remains recoverable: a converged mirror does not require
an already-removed preimage. Missing preimage while restoration is still required
fails closed. Cleanup failure leaves pending and does not deny a confirmed DB
rollback/commit. No recursive or filename-only deletion of abandoned artifacts.

## Contract boundary and remaining work

The guarantee remains process-crash recovery, not cross-platform power-loss
atomicity. Flushed payload/intent files alone do not prove directory-entry
persistence. Stable target/sidecar/pending/private-artifact paths, no external sidecar editor during the
operation, and common-lock coordination by all internal-ledger writers remain
required. Arbitrary historical/noncooperating file replacers are not fenced by
SQLite or hash-before-rename checks. Stop in place if that lifecycle cannot be
established; do not turn this limitation into a fake green claim.

Expected old failure mapping: seven missing-mirror cases addressed by the prior
package, plus this one real publication-failure rollback case. This is not an
observed 61/65 result. Adoption-event, two replacement-stage-report assertions,
and failed DB-preimage rollback semantics remain separate. SDK/old tests/old
assertions/budgets stay unchanged. Exact full failure identities remain in the
prior mirror protocol document.

Planned new Actions evidence must run the original targeted case unchanged plus
real filesystem publication failures, before/after mirror-publication crashes,
confirmed rollback restoring original existence/bytes, legacy external-only
preimages, unknown COMMIT outcomes, preimage loss/foreign IDs, cleanup interruption,
and unchanged new-target v1 behavior. Independent source review is required before
any publication request; the prior seven-path review does not clear this reorder.

## Prepared source evidence (not executed)

`tests/migration/precommit_mirror.py` and
`.github/workflows/migration-precommit-mirror.yml` now exist. The branch-specific
workflow builds unchanged SDK + both tool executables, runs the new focused probe,
and independently invokes unchanged `run_cases.py --only
ledger_publish_failure_rolls_back_library`. That old case still runs if the focused
probe fails after a successful build; its original failed status/assertions are
not rewritten. Logs, fixtures, raw output and summaries are uploaded always.
All three OS jobs have a 30-minute resource ceiling, not a finish-time promise.

The POSIX real-filesystem fault removes parent-directory write permission at the
actual publication boundary. That can also prevent SQLite DELETE-journal cleanup.
The probe therefore distinguishes a confirmed SDK rollback from a real unconfirmed
rollback (`inconsistent`, `rolled_back=false`, no COMMIT attempted), retains pending
evidence, restores fixture permissions, and only then tests recovery/data bytes.
It does not manufacture a confirmed rollback from that shared-directory failure.
Windows uses a scoped deny-delete ACL fixture and restores it in a finally block.

The probe also source-covers internal-ledger and legacy external-only crash
recovery, cleanup interrupted after preimage retirement, cooperative POSIX cancel
versus Windows hard kill, explicit post-publication cancellation restoring original
mirror absence, same-content foreign stage/preimage/mirror identity refusal,
COMMIT-busy unknown evidence, equal-hash actual DB changes, and new-target v1.
Schema-6/WAL, full 65/31/17 and original performance budgets remain later unchanged
Actions obligations. There is no runtime result or green claim yet.

The inherited `mirror_recovery.py` and its old-branch workflow are unchanged
historical sources for the frozen seven-path package. Their existing-target
sidecar-fail expectation was post-COMMIT and intentionally is not v2 acceptance;
this candidate does not edit that probe to make it green. The new workflow selects
the new protocol probe and the untouched original rollback case explicitly.

Relative to the frozen seven-path worktree, this package changes only
`lm_main.c`, `lm_mirror.c`, `lm_mirror.h`, and adds the three precommit doc/probe/
workflow paths above. Relative to local base `2249fa4`, it contains ten owned paths
including the inherited seven. Workspace:
`/workspace/shared/exreader-migration-precommit-mirror-20261028`; branch:
`codex/migration-precommit-mirror-20261028`. Bounded independent source review
cleared the code/probe/workflow checkpoint on 2026-10-28 at 20:52 UTC. No
commit/push/CI has been attempted for this package; separate specific approval
is required, not reuse of the four-file or seven-file package approval.

Reviewed source SHA-256 values (not build results or commit IDs):

| File | SHA-256 |
|---|---|
| `lm_main.c` | `2c36cb0d8c4102b35e11f45419820de5154ec98f5819694567ca3e239814b5ff` |
| `lm_mirror.c` | `efa530a6303c6c55d4c6237d6589e645f98347dfb65787dec6167bb7d4216316` |
| `lm_mirror.h` | `dccc5374b27f6614a7872cc584a952c11acf767200a8aa68ae1cc24f5c7b6be3` |
| `precommit_mirror.py` | `3566e83e8604d6b98343b944dcc1762005c3a0f0007bb23847107545794919e8` |
| `migration-precommit-mirror.yml` | `f924868fd029e63d6b9c4be09ca9496a73316d780d47fd226c6848c0430d092a` |

Review limits: the real-OS fixture may observe rollback failure as well as mirror
publication failure. Its success alone cannot be advertised as confirmed rollback
under a real OS refusal; retain the recorded distinction. No source review proves
compilation, platform behavior, full old-gate acceptance or performance.
