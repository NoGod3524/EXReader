# F08 retained causal failure audit

Status: the corrected audit completed successfully. Its 1+12 controls passed; producer ZIP identity, all six launches and retained binary hashes were checked. Four reader failures have a recorded shelf_restoring blocker; both shelf traces lack target draws. Formal progress stays 95/108; F08 is not accepted.

## Scope and immutable producer

The audit branch is `codex/dot-f08-causal-failure-audit-20261031`, based on `aa070c9032ae114650d1dcc1e4a1f8c002ec961d`.
Only this document, `tests/reader_f08_causal_failure_audit_20261031/audit.py`, and `.github/workflows/dot-f08-causal-failure-audit-20261031.yml` are added.
No product, SDK, original sampler, previous causal driver/probe/verifier, source lock, timeout or other workflow is changed.

The producer is [run 41169786301, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41169786301),
source `878a3f67a2bcfad51d49c67292548e5892185f3d`.
[Artifact 13030394230](https://github.com/NoGod3524/EXReader/actions/runs/41169786301/artifacts/13030394230)
has name `f08-causal-41169786301-1`, size 4,422,645 bytes and SHA-256
`d20d1b690625b914f16dadc958c7cbb1409c17681db96896190678d350d0c189`.
The corrected audit authenticated and parsed this original ZIP inside Actions. The initial parsing failure remains retained below.

The original cohort remains 44 launches / 760 samples / 2 positive + 24 negative controls.
The new producer planned 6 launches / 18 actions / 2 positive + 8 negative controls.
It attempted ten actions: page/font launches 0, 1, 3 and 4 failed after one action each;
shelf launches 2 and 5 each completed three driver actions. Producer accepted=false remains intact.
Its new controls, causal verifier and dependent artifact authentication were not completed.

## Bounded executions

The initial single execution failed during parsing and is retained below.
This repair has one additional Ubuntu 22.04 job, at most 20 minutes, attempt 1, with no automatic rerun.
The workflow only triggers on its exact branch and audit source/workflow paths.
Concurrency serializes this audit. The repaired script requires the exact parent
`25a5d87f0b17a796dbd57dd2c2342893e36f4013` and changes to only the audit script and this document.
It admits exactly two workflow runs: retained failure 41174980081 at source
`6725cbd3e496dd8daba81136240e79f70f28f5f3`, and the current source's new attempt 1.
A later documentation-only result commit uses [skip ci].
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

The executed positive control establishes a linked restoring-only state while retaining a one-second interval
and a frame-counter gap. It still does not confirm a hidden-shelf root cause.

All twelve executed negatives passed:

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
- The initial one-run budget was consumed. No repair or rerun occurred under that budget. The failed source and run remain intact; the later corrected execution used its separate one-run allocation.
- The source branch was read back at the exact audit SHA. The commit-scoped Actions query found one run, attempt 1, with failure.
- At that point the hidden-shelf condition remained an unverified static candidate; the parsing failure produced no causal or physical-presentation evidence.

This result is published as a separate documentation-only commit with [skip ci]. The exact failed version remains at source commit 6725cbd3e496dd8daba81136240e79f70f28f5f3 for traceability.

## Corrected execution

The baseline list comprehension now has its missing closing square bracket.
The only other script changes bind admission to the retained result-document parent,
the two modified paths, and the known failed run plus this one additional execution.
The producer identity/hash pins, raw predicates and joins, all 1+12 audit controls,
20-minute workflow limit and original failed results are unchanged.

The corrected execution completed successfully:

- Source: [e8117f49ec1a5e9b5ad3ab56fafb856163aae175](https://github.com/NoGod3524/EXReader/commit/e8117f49ec1a5e9b5ad3ab56fafb856163aae175).
- [Run 41175713826, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41175713826), push event, created 2026-10-31 06:13:37 UTC.
- [Job 124462730256](https://github.com/NoGod3524/EXReader/actions/runs/41175713826/job/124462730256) succeeded with the unchanged 20-minute limit. Controls passed at 06:13:45 UTC; the diagnostic receipt was printed at 06:13:47 UTC; the output artifact finalized at 06:13:49 UTC.
- Exactly 1 positive and 12 negative audit controls passed. The producer's original new-cohort 2+8 controls remain unexecuted.
- The source guard admitted the exact repair parent/paths, the retained failed run and only this additional attempt. The commit-scoped run query returned one run for the repaired source.
- [Audit artifact 13033380160](https://github.com/NoGod3524/EXReader/actions/runs/41175713826/artifacts/13033380160), name `f08-causal-failure-audit-41175713826-1`, is 4,474,409 ZIP bytes. Actions reports SHA-256 `d2922091f660fc8efc0056a309f9778a72648b6367c6e2a607ac136e02f2c16d`. Upload reported 14 files, including the original ZIP and diagnostic outputs. The result was reviewed through decoded job logs and Actions metadata; the output ZIP was not downloaded or parsed outside Actions.

### Producer evidence authenticated inside Actions

The audit verified the pinned producer run/attempt/source, artifact identity, original outer ZIP length and full SHA-256 before parsing. Its actual inventory contains 17 files. All six launch/PID records matched the top driver and per-launch copies.

Retained binary digests:

- host.bin: `1bc210ccef0a9bd9bc4b365cc0386e3127e1f0a52152b3487d1bd94ff2cdeeab`.
- module.so, the new causal module: `9150f41a8a06f0e190f700c10667b0a5be65f272d982ce84a8b718ab848c4e97`.

The producer ZIP has neither bundle.json nor summary.json. This matches its verifier abort and is explicitly recorded as an incomplete producer bundle. No binary was executed.

### All six original launches

Counts below cover each whole raw process trace, including preparation, event propagation and shutdown; input-row counts are not counts of measured injections.

| Launch | Kind | PID | Original driver | Attempted actions | States | Inputs | Target draws | Frames |
|---|---|---:|---|---:|---:|---:|---:|---:|
| 0 | page | 11127 | failed | 1 | 17 | 5 | 2 | 23 |
| 1 | font | 11163 | failed | 1 | 36 | 5 | 2 | 42 |
| 2 | shelf | 11207 | passed | 3 | 41 | 178 | 0 | 258 |
| 3 | page | 11252 | failed | 1 | 35 | 5 | 2 | 41 |
| 4 | font | 11285 | failed | 1 | 35 | 5 | 2 | 41 |
| 5 | shelf | 11311 | passed | 3 | 41 | 178 | 0 | 258 |

All six hosts exited with code 0 and no reported watcher failure. The audit's probe-integrity checks found no overflow, hook, clock or frame-order issue. It retained all raw rows and frame intervals.

### Four reader failures: the recorded false term is established

Each failed action has exactly one matching input group and one same-clock, same-frame target-image draw/state join. Each matched state has book=1, painted_generation 1 -> 2, a newer state sequence, a successful write, busy=0, saving=0 and shelf_loading=0. In all four, shelf_restoring=1 is the only false term of the original driver changed predicate.

| Launch / action | Expected effect | Input keyval | Matched state sequence | Frame counter | Event to matching frame end, us |
|---|---|---:|---:|---:|---:|
| 0 / 00-0 | page 0 -> 1 | 65473 | 15 | 21 | 22,999 |
| 1 / 01-0 | font 24 -> 26 | 65474 | 34 | 40 | 18,651 |
| 3 / 03-0 | page 0 -> 1 | 65473 | 33 | 39 | 20,309 |
| 4 / 04-0 | font 24 -> 26 | 65474 | 33 | 39 | 18,818 |

These four intervals describe GDK frame-end associations in the failed cohort, not a performance distribution or physical presentation measurement.

For each failed action, all six raw states in the nominal wait window have known relevant fields, shelf_loading=0 and shelf_restoring=1. Busy/saving temporarily change during the action, then clear at the matched painted state. No recorded state in that window satisfies the entire original predicate. The two final raw states, approximately 180.06 seconds after injection, still have the completed effect/new generation and only shelf_restoring blocking the predicate.

There are no intervening recorded state writes between the early matched state and those final rows. That long gap is retained; absence of writes does not establish application idleness. Exact failed wait boundaries, watcher deliveries/predicate evaluations, reader visibility and focus were not captured. The audit therefore establishes the false term in the saved states and supports the hidden-shelf hypothesis, while keeping hidden_shelf_root_cause_confirmed=false.

### Shelf evidence gap

Both shelf processes contain zero target draw records despite having frame-clock records. Each of the six shelf actions has one matching input group and a state satisfying the original driver predicate, but zero draw/frame joins; all report `no_matching_draw_frame_state`.

This is a missing observation in the causal evidence. It does not prove that scrolling failed to paint. Driver success is not a passed shelf causal analysis, and even a preceding shelf draw would remain only an unknown temporal candidate under the existing publication timing.

### Result boundary

The diagnostic completed; the producer remains failed, with ten attempted actions rather than eighteen completed actions. The original 44 launches / 760 samples / 2+24 controls and all prior failures remain unchanged. The producer's new 2+8 controls were not retroactively executed. No resampling or product change occurred.

Both bounded audit executions are consumed. This result is recorded in a separate documentation-only [skip ci] commit. Formal progress remains 95/108, F08_accepted=false and physical_display_presented=false.
