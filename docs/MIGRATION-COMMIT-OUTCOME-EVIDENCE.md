# Migration commit knowledge: narrow tools-only candidate

Base: `e771f3c5d1567412f26184ad304730b7c640235d` (product code
`e0e7aebda7b2f8d9e3b947b7f96823a05b219027`). This change does not fix or
supersede the original transaction candidate gate at
[40667133471](https://github.com/NoGod3524/EXReader/actions/runs/40667133471),
which retained 53/65 original scenarios and missing-sidecar review/browser
failures on all three operating systems. No old assertion, budget, SDK code,
exporter, ledger serialization, or original workflow is changed.

## Problem and limited correction

The transaction executable can commit its database and subsequently return
`failed / review-hook-timeout` when the post-commit acknowledgement rendezvous
is cancelled or times out. A failed command is therefore not proof that its
database writes were rolled back. The existing result, code, and exit status
are deliberately retained; additive evidence makes the distinction visible.

Only the transaction executable adds `atomicity.transaction`:

- `target_commit`: knowledge about the authoritative target transaction or,
  for a new target, publication of the already committed private stage.
- `private_stage_commit`: separate knowledge about a new private stage.

Values:

- `not-attempted`: this process has not attempted that commit/publication.
  It is **not** a verified rollback claim. Early failures that rely on close
  still retain this value; non-migration commands also have no such attempt.
- `not-committed`: an explicit rollback returned success before any commit
  attempt on that owner.
- `committed`: the commit call, or new-target publication, returned success.
  Later report/acknowledgement failure does not erase this fact.
- `unknown`: the commit/publication call was attempted without a confirmed
  successful return. Cleanup does not downgrade this to a rollback claim.

These are process-local observations, **not persisted receipts** and not a
power-loss durability guarantee. A killed process may produce no report.
No ledger hash is used to infer historical commit: the unchanged-ledger,
changed-database counterexample at
[40675005491](https://github.com/NoGod3524/EXReader/actions/runs/40675005491)
continues to apply. No automatic database restore or retry is introduced.

## Focused Actions evidence

The dedicated workflow builds the frozen SDK once and builds both the baseline
and candidate tools against that installation. The new Actions-only probe:

1. Retains a baseline post-commit failure report and independently reads the
   newly committed book from SQLite.
2. Checks new and existing target post-commit failures: on POSIX, cooperative
   SIGTERM; on Windows, the unchanged acknowledgement timeout (not simulated
   graceful Windows cancellation).
3. Checks explicit pre-commit cancellation for new and existing targets.
4. Creates a foreign destination at the new-target publication boundary;
   the foreign bytes remain unchanged, private-stage commit is confirmed,
   and target publication is conservatively unknown.
5. Holds a rollback-journal reader through COMMIT to produce an actual SDK
   commit error. The report remains unknown even when a separate subsequent
   read confirms this particular attempt was rolled back.

Raw stdout/stderr, fixture inputs, databases, and the Actions-generated summary
are retained for failures too. This focused evidence is not a substitute for
the original 65 scenarios, 31 review checks, 17 browser checks, or full
same-source integration gate. Initial publication has no claimed test result.

The retained failure identities from run 40667133471, Linux job 122744348256,
are listed here so a later full run cannot disguise a regression behind the
same 53/65 count:

```
note_ambiguous_quote_unlocated
fixed_missing_quote_unlocated_and_rects_recorded
unknown_fields_reported_and_kept
orphan_note_preserved
rerun_same_pack_is_stable
ledger_loss_does_not_duplicate
same_original_different_legacy_id_merges
ledger_with_unknown_version_refused
existing_target_content_is_preserved
write_failure_after_partial_writes_keeps_target
ledger_publish_failure_rolls_back_library
failed_rollback_is_reported_and_pre_image_kept
```

## Remaining work

Automatic sidecar maintenance still requires a real preparation/publication
path, a durable pending journal, and fail-closed recovery. Merely recognizing
the old `sidecar-fail` injection before COMMIT would not demonstrate a real
external publication failure and is not included. Old stage-replacement and
post-commit byte-rollback assertions remain unresolved. Exact historical
commit identification when ledger bytes repeat requires a separate atomic
SDK receipt contract, outside this frozen-SDK change. Noncooperating pathname
replacement remains a host/deployment coordination requirement.
