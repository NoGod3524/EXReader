# F08 retained causal failure audit

Status: the single audit attempt failed during Python parsing, before any diagnostic logic ran. Formal progress stays 95/108; F08 is not accepted.

## Scope and immutable producer

The audit branch is `codex/dot-f08-causal-failure-audit-20261031`, based on `aa070c9032ae114650d1dcc1e4a1f8c002ec961d`.
Only this document, `tests/reader_f08_causal_failure_audit_20261031/audit.py`, and `.github/workflows/dot-f08-causal-failure-audit-20261031.yml` are added.
No product, SDK, original sampler, previous causal driver/probe/verifier, source lock, timeout or other workflow is changed.

The producer is [run 41169786301, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41169786301),
source `878a3f67a2bcfad51d49c67292548e5892185f3d`.
[Artifact 13030394230](https://github.com/NoGod3524/EXReader/actions/runs/41169786301/artifacts/13030394230)
has name `f08-causal-41169786301-1`, size 4,422,645 bytes and SHA-256
`d20d1b690625b914f16dadc958c7cbb1409c17681db96896190678d350d0c189`.
Actions metadata was read back and matches these pins. The diagnostic did not download or parse the ZIP; its inner records remain unexamined.

The original cohort remains 44 launches / 760 samples / 2 positive + 24 negative controls.
The new producer planned 6 launches / 18 actions / 2 positive + 8 negative controls.
It attempted ten actions: page/font launches 0, 1, 3 and 4 failed after one action each;
shelf launches 2 and 5 each completed three driver actions. Producer accepted=false remains intact.
Its new controls, causal verifier and dependent artifact authentication were not completed.

## One execution

One Ubuntu 22.04 job, at most 20 minutes, one attempt, no automatic repair or rerun.
The workflow only triggers on its exact branch and audit source/workflow paths.
Concurrency serializes this audit; the script checks attempt 1, a single run for this workflow/branch,
the exact parent commit and exactly three added paths. A later documentation-only result commit uses [skip ci].
No product run, compilation, installation, new sampling or execution of retained binaries is included.
All diagnostic execution and ZIP parsing occur inside Actions; no local syntax checks or tests are run.

The standard-library audit first checks the producer's run/attempt/source and artifact metadata,
then streams at most the pinned ZIP length with a 90-second download timeout and verifies its full digest.
It rejects absolute/traversal/ambiguous names, duplicate normalized or case-folded names,
file/parent collisions, encrypted entries, symlinks, special entries and excessive counts/sizes.
Limits are 1,000 ZIP entries, 64 MiB per member, 256 MiB total expansion.
Members are read in memory; retained binaries are never extracted or executed.
The original ZIP, metadata, actual complete inventory and per-member hashes are preserved as audit evidence.

The actual inventory must bind all six launch/PID records to the top driver and the producer source.
The retained host and causal module are rehashed, including the known original host digest.
Missing producer bundle/summary is reported explicitly; an authenticated failed artifact is not a completed producer bundle.

## Predicate reconstruction and limits

For every action, the audit prints its saved numeric baseline, target, same-book identity,
input type/code/timing and every recorded numeric state, including pre-action and post-deadline rows.
It reports effect, painted generation, same book, busy/saving settled, shelf_loading and shelf_restoring
as true/false/unknown. Numeric -1 stays unavailable, never a successful effect.
Successful writes and newer sequences are separately required for causal candidates.

Input propagation rows are retained and grouped by GDK timestamp/type/code/hardware code.
Page/font candidates require the same process, input clock, target GtkImage draw, frame counter,
same-book effect and newer generation inside that frame. Every raw frame and counter interval stays,
including long gaps, counter gaps, mixed and unknown windows.
Shelf draws remain unknown temporal candidates; event_to_matching_paint_us stays null.
A driver's quiet window does not establish application idleness.

Static source inspection found evidence limits that this audit must preserve:
the producer does not save Watch.events or predicate evaluation records, failed wait start/end timestamps,
input focus or reader_visible in the probe. Its failed action has no done/effect_at.
The audit marks inject_end + 180 seconds as a nominal boundary only, retains the full raw trace,
and does not assert that state publication equals watcher delivery.
A linked state with only shelf_restoring failing supports the candidate condition;
it does not by itself prove the exact failed watcher evaluation or that the shelf was hidden.
Contrary states satisfying the entire original predicate are explicitly reported.

GDK presentation 0 remains null; predicted time never replaces presentation.
Xvfb frame activity is not physical display presentation or a 60fps result.

## Deterministic controls

The planned, unexecuted positive control establishes a linked restoring-only state while retaining a one-second interval
and a frame-counter gap. It still does not confirm a hidden-shelf root cause.

The twelve planned, unexecuted negatives cover:

1. Wrong producer source identity.
2. Wrong ZIP digest with the correct byte length.
3. Missing launch.
4. Duplicate launch.
5. Unavailable effect field.
6. Missing input.
7. Unmet target effect.
8. Wrong book.
9. No newer painted generation.
10. Busy/saving not settled.
11. Missing draw/frame association.
12. Shelf loading still true, preventing attribution solely to shelf restoring.

These are diagnostic audit controls, separate from the producer's unexecuted 2+8 controls.
A completed diagnostic cannot promote F08 or revise the failed producer's result.

## Actual single attempt: failed before execution

- Audit source: [6725cbd3e496dd8daba81136240e79f70f28f5f3](https://github.com/NoGod3524/EXReader/commit/6725cbd3e496dd8daba81136240e79f70f28f5f3).
- [Run 41174980081, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41174980081), push event, created 2026-10-31 06:02:51 UTC.
- [Job 124460551080](https://github.com/NoGod3524/EXReader/actions/runs/41174980081/job/124460551080) used Ubuntu 22.04 with the 20-minute cap. Checkout succeeded at the exact audit source.
- At 06:02:59 UTC, Python reported `SyntaxError: '[' was never closed` at audit.py line 373. The baseline list comprehension at lines 373-374 lacks its closing square bracket. This is an error in the audit implementation, not evidence about the producer's timeout or product performance.
- No audit source guard, synthetic control, producer API call, ZIP download, ZIP hash check, inventory parsing, retained-binary check or per-launch analysis executed.
- Artifact upload then failed because `build/f08-causal-failure-audit/` did not exist. The Actions artifact query returned an empty list. The decoded job log is the failure evidence; there is no generated audit bundle or diagnostic receipt.
- The one-run budget is consumed. No repair, rerun, product execution or resampling followed. The failed source and run remain intact.
- The source branch was read back at the exact audit SHA. The commit-scoped Actions query found one run, attempt 1, with failure.
- The hidden-shelf condition remains an unverified static candidate. No new causal result, physical-presentation result or F08 acceptance evidence was obtained.

This result is published as a separate documentation-only commit with [skip ci]. The audit source file remains the exact failed version for traceability.
