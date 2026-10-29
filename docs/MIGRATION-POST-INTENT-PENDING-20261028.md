# Limited v3 post-intent recovery barrier

Source implementation only, 2026-10-28. No local execution. This is an explicitly
limited fail-closed intermediate candidate, **not full migration P0 acceptance**.
Automatic full recovery is not implemented. The previous exact tested source
was `d7529944ac88ab576d1519db45efa9aa165e929d` (tree
`e439bc4044df18b777aebb173b94fa721aac3e7b`); its observation matrix was 87/87 and
its unchanged full companion candidate was 61/65 on every OS. Those historical
results do not apply to this unexecuted successor.

## Exact seven-path source scope

1. `extras/migration/src/lm_main.c`
2. `extras/migration/src/lm_mirror.c`
3. `extras/migration/src/lm_mirror.h`
4. new `tests/migration/post_intent_pending_20261028.py`
5. `tests/migration/mirror_safety_matrix_20261028.py` — only three product hashes;
   all 29 existing assertions and their execution remain unchanged.
6. `.github/workflows/migration-mirror-safety-matrix-20261028.yml` — exact guard,
   old v2 consumer build and independent additive test invocation/artifact input.
7. this new document.

The frozen SDK/SQLite, old 65/31/17 tests, budgets, companion workflow/jobs and
diagnostic consumer are unchanged. The earlier denied docs-only seal at local
`77ccbbd88fda5e2f4f3f57aaa59184c13057edb0` is held separately: its payload is not
included or retried through this successor. The still earlier denied proposal
`02e26205024c24f49c2140354a08100b7397ac45` remains intact.

Actions admission additionally requires the exact seven name/status changes
against tested `d7529944...`, freezing every other predecessor path. It compares
the old 29-case probe byte-for-byte after only the three declared product-hash
substitutions; the broader historical 21-path allowlist is not the sole guard.

## User-visible behavior and reason

The previous Windows observations showed that the product restored the mirror
and retired its intent/preimage while the native journal-delete refusal remained
active. The separate SDK diagnostic measured internal I/O errors with SDK OK.
All tested fixtures recovered their data; this was not measured data loss.
SDK OK alone is nevertheless not independent complete recovery verification.

New **existing-target** intents use version 3, persisted before external mirror
publication. This version is a retirement policy, not a COMMIT receipt. On
abort, close-only interrupted completion, or restart, the candidate retains
intent, owned mirror bytes/preimage and its shared migration lock. It does not
restore the mirror by consuming the only preimage. A fresh `recover-mirror` or
migration reports `recovery-unverified` and does not open or modify the DB or
retire the evidence. The updated candidate's `--break-lock` cannot erase this
policy. If the barrier file is absent, it may reserve a new own lock before
reporting the retained requirement; an existing lock is untouched.

This can block a later migration after cancellation even when SQLite actually
rolled back correctly. That is the consciously accepted intermediate behavior,
not a hidden complete-recovery claim. Ordinary library reads/writes are not
blocked by this filesystem migration lock after the database owner closes. No
old database snapshot is written over a later ordinary writer.

The report keeps literal SDK acknowledgement and adds separate fields for
rollback requested/status, logical state, I/O observation and physical cleanup.
The limited rollback-request observation is null outside the instrumented
post-intent call, not false: pre-intent dry-run can actually request rollback
without this new observer. Additive early dry-run controls check this wording.
`io_observation` is **not-installed**, never no-error. `physical_cleanup` is
not-independently-verified; `full_recovery_accepted` is false. Existing
`rolled_back` continues to describe SDK acknowledgement, not independent proof.
Read/verify commands preserve an observed v3 policy flag, including a schema-6
read refusal; touched-item verification never reports that the barrier lifted.

## Narrow successful-COMMIT path

An existing-target v3 run already publishes the exact planned mirror before
COMMIT. If this same invocation actually receives `finish(commit=1)==EXR_OK`,
then closes its original SDK owner, it can clean up only after checking:

- in-memory committed outcome, original run token and target identity;
- exact same pending-intent file identity and bytes;
- exact owned published mirror, or unchanged original identity/bytes when those
  bytes already equal the planned after bytes;
- exact ownership/bytes of each artifact being retired.

The deliberate post-COMMIT pause is rechecked before artifact retirement. A
foreign equal-byte mirror does not qualify. A failed or unavailable check keeps
pending evidence. This is labelled `commit-planned-mirror-matched`, not verified
current whole-library state. An ordinary writer after owner close is permitted
and preserved; it is not assumed absent.

Unlike the prior route, this v3 completion does **not** reopen a fresh SDK
migration owner and call another opaque rollback. It introduces no SQLite
global callback, mmap changes, VFS, fake returns or private SDK access. SDK close
has no returned status; its physical cleanup is not independently verified.
The COMMIT exemption is never persisted or inferred on restart from equal
ledger hashes. New-target v1 and inherited v1/v2 recovery remain unchanged and
are not silently relabelled as verified v3 recovery.

## Shared lock ownership and old binaries

New lock creation flushes its run nonce and snapshots its file identity/bytes.
Normal cleanup removes only that exact owned lock, within the existing
stable-path contract; replacement/foreign locks are left untouched. Pending v3
retains the lock, with a fresh ownership check before reporting it as retained.
This is not an atomic filesystem compare-and-swap or a power-loss guarantee.
The old explicit v1/v2 stale-lock contract is not broadened by this patch.

The tested v2 candidate's parser accepts only versions 1 and 2 and exact field
counts. It rejects a real v3 intent. **Actual SDK 3.40's original migrator does
not recognize any pending-intent version.** It rejects schema 7 for schema
incompatibility, but on schema 6 the retained common `.migrate-lock` provides
default exclusion. Do not call this v3 format recognition. Running that old
binary with explicit `--break-lock` bypasses the barrier and is an unsupported
downgrade risk; old binaries/SDK are not modified here. Tests never weaken that
disclosure into universal backward safety.

## Planned Actions-only validation

The new suite independently records 25 cases per OS:

- Actual schema 6/7 × DELETE/live WAL: normal same-process COMMIT with an ordinary
  write before artifact cleanup; idempotent equal-byte mirror completion;
  post-publication cancellation; hard crash after intent and after mirror
  publication (16 cases total).
- Real DELETE journal deletion refusal for each schema (2): calibrated POSIX
  errno 13 or Windows sharing violation 32, actual product output and exact
  pending artifact/lock identity retention. This does not install a product I/O
  logger or infer a non-OK SDK result from the OS refusal.
- Foreign lock, equal-byte foreign intent, mirror and preimage at the cleanup
  rendezvous, plus foreign mirror/intent at the final retirement boundary (6).
- Malformed/partial v3 intent: refusal before SDK open and no foreign lock
  deletion even with `--break-lock` (1).

Pending cases independently check baseline rows, later ordinary writes, repeat
reopen/cancel/dry-run refusals and absence of DB overwrite. Actual SDK 3.40 default
shared-lock refusal is distinct from the old v2 candidate's format rejection;
the latter uses an isolated fixture so its legacy lock handling cannot consume
the original barrier. Schema-6 fixtures come from the real 3.40 build, not a
rewritten header. The old v2 consumer is rebuilt from exact tested `d7529944...`
against the unchanged installed SDK, only in Actions.

The existing 29-case matrix still runs after an additive-suite failure and keeps
its assertions. Some prior expectations of automatic post-abort recovery are
expected to conflict with the new pending policy. They must be reported red,
not rewritten to green. The original unchanged full companion runs on the same
source SHA, preserving all original four historical failures and any additional
observed conflicts. No full P0, original 65/65, old 29/29 or new 25/25 result is
claimed before actual terminal Actions evidence. The independent review found
the final retirement pause needed another exact target/mirror identity check;
those checks and additional attribution/retirement cases are included, not
waived under the stable-path caveat. Final intent/artifact ownership mismatches
are nonzero refusals, not mislabeled successful owned-unlink cleanup warnings.

## Explicit remaining gaps

Pre-intent failures, dry-run/cancel before intent, partial-write cleanup and
SDK-open/schema-upgrade error cleanup have no new durable verification barrier.
No complete baseline verifier or automatic release of v3 pending is provided.
SDK error-return observability, actual non-OK rollback coverage, non-Windows WAL
physical-fault coverage, general namespace attacks and power-loss guarantees
remain unresolved. Mirror preimages only preserve external-mirror evidence;
they do not repair lost database rows. A future full recovery implementation
must preserve normal rollback behavior and later ordinary writes while proving
more than ledger equality.

**结论：这是先保留证据、明确显示“恢复未验证”的有限安全改动。正常确认提交
继续完成；取消或重启后的迁移可能暂时被阻塞。不是已经完成自动恢复或迁移 P0。**
