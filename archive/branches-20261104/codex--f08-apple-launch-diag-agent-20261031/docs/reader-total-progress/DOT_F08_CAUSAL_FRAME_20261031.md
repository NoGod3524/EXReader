# F08 input / paint attribution candidate

Base cfdaf6a4531548be63b4dd0c2bccd6b050a93124; branch codex/dot-f08-causal-frame-20261031.
Exactly seven new files, no product/SDK/original sampler edits.
Authorized one Actions run, original sampling cap 90 minutes plus original artifact verification cap 20 minutes.
No automatic repair/retry, no local build/syntax/test/ZIP processing.

## Frozen evidence and additional workload

Original 44 launches / 760 samples and original 2 positive / 24 negative controls execute unchanged, using the original frame-clock module.
Original run 41155753132 and analysis run 41161801430 remain historical evidence, not overwritten.
New six launches use the same packaged host with the NEW test module: page/font/shelf, twice each, three actions each = 18.
They are a separate cohort, not replacements or additions to the old performance distribution.
The independent public seed still generates the fixed 2202-original synthetic corpus. No real user library or credential is used.
New controls: two positives (including a one-second active gap, and a quiet observation window), eight negatives:
foreign PID; missing input; ambiguous input; wrong generation; reverse counter; overflow; omitted long gap; invented presentation.

## Passive trace and attribution

A GTK emission hook observes event and draw. Returning TRUE from an emission hook keeps that hook installed; it does not consume a GTK event or alter a handler return.
No forced redraw, frame-clock begin_updating, timer, input injection from the module, AddRef changes to product objects, or product hook is added.
The original g_file_set_contents runs once with unchanged arguments/result. Bounded integer parsing reads only fixed numeric observation fields.
No book text, query strings, clipboard, passwords or arbitrary exception message is exported.
Buffers are bounded at 65536 rows per stream and 64 clocks. Overflow/missing hooks/missing exit trace fails evidence.
Trace stays in memory; one per-PID JSON is written at normal exit. Instrumentation memory/time is disclosed, not called uninstrumented performance.

Driver injection start/end and GLib monotonic timestamps use Linux CLOCK_MONOTONIC microseconds.
The GDK/X event server timestamp is only an event grouping key, not directly subtracted from the monotonic clock.
Each action is singly in flight. Propagation of the same event through widgets remains in raw records, grouped by event timestamp/type/code/hardware key.
Ambiguous/missing input, overlapping action windows, wrong PID/generation/clock, missing draw and failed host exit are refused.

Page/font require the changed numeric state and painted generation in the same frame as the target named GtkImage draw.
Shelf state may be published later by a viewport-save timer. Its preceding target-list draw is only a temporal candidate:
shelf causal attribution stays UNKNOWN, and its latency is explicitly event-to-candidate-paint, not proven matching-content presentation.
This limitation does not turn a missing draw into success or erase raw rows.

Explicit two-second driver-quiescent windows are not claims that the whole app or machine is idle.
Background inputs/state writes/draws are counted; all frame-counter intervals are retained, including long, mixed, counter-gap and unknown intervals.
No duration threshold deletes slow frames or relabels them idle. Phase time, state-write time and input-to-paint association stay separate.

## Presentation and acceptance

GDK complete=true means no more timing fields will arrive, not that presentation exists.
presentation=0 is exported null/unavailable; predicted presentation never substitutes for an observation.
Xvfb/Openbox has no physical display acceptance. Even a backend-reported presentation timestamp is not a hardware input-to-photon measurement.
No 60fps claim, percentile budget ratification or formal F08 promotion is made; score stays 95/108.

Official API references:
- https://docs.gtk.org/gdk3/class.FrameClock.html
- https://docs.gtk.org/gdk3/method.FrameTimings.get_complete.html
- https://docs.gtk.org/gdk3/method.FrameTimings.get_presentation_time.html
- https://docs.gtk.org/gtk3/signal.Widget.event.html
- https://docs.gtk.org/gtk3/signal.Widget.draw.html

The old artifact verifier runs unchanged. New same-run/attempt original ZIP digest, strict member inventory, raw trace recomputation and host/module hashes are additionally checked.
Only synthetic trace/evidence directories are uploaded; private profiles, clipboard state and runtime HOME stay outside.
Status: initial authorized run failed; original cohort passed, new causal cohort incomplete. See retained result below.

Retained host.bin and module.so are copied from the actual executed paths; the verifier is designed to recompute both raw binary hashes in the separate artifact audit (skipped in the failed initial run), without executing downloaded binaries.

Raw numeric state -1 means unavailable (including early painted generation); these rows remain in evidence. Matching effects require known nonnegative relevant fields and the same book as the injected action.

## Initial authorized run: failure retained (2026-10-31)

- Source: `878a3f67a2bcfad51d49c67292548e5892185f3d`.
- [Run 41169786301, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41169786301), started 04:44:26Z; sampling job 124445045025 ended 05:04:31Z with failure. The single authorized run is consumed; no automatic correction or rerun.
- All builds, exact seven-path/frozen-source guard and packaged-host identity passed. Original frame verification reported `evidence_complete=true`, 44 launches, 760 old samples and 2 positive plus 24 negative controls. Original 32-launch aggregation accepted all 520 samples; the separate original 12-launch cohort reported 240/240 and zero problems.
- New cohort launched all six processes. Page launches 0/3 and font launches 1/4 each recorded one attempted action then failed after approximately 180 seconds; shelf launches 2/5 each completed three actions. This is ten attempted actions, not eighteen successful observations.
- New verification rejected `top.accepted=false` at the driver admission check. The new 2+8 controls and causal joins were NOT reached. The dependent 20-minute artifact-authentication job was skipped. No latency/classification or physical-presentation conclusion is established.
- [Raw new-cohort artifact 13030394230](https://github.com/NoGod3524/EXReader/actions/runs/41169786301/artifacts/13030394230): 4,422,645 bytes; SHA-256 `d20d1b690625b914f16dadc958c7cbb1409c17681db96896190678d350d0c189`. Metadata and textual Actions logs were read; no archive was downloaded or parsed outside Actions.
- Static diagnostic candidate, NOT proven root cause: the new driver requires both shelf-loading and shelf-restoring flags to be clear even for page/font actions. The frozen successful reader scenario does not impose these shelf-only conditions. In production `shelf_restore`, leaving the shelf cancels its timer without clearing `shelf_restoring`; this can make the additional predicate inappropriate for a hidden shelf. Raw failed-launch state/input records must establish which predicate failed before a correction is justified.
- Next work requires a separately authorized bounded Actions package to inspect the fixed failed artifact and print exact failed predicates. Preserve this failure and every original assertion; do not infer a product performance defect from a driver timeout or relax generation/same-book checks. Formal score remains 95/108; F08 remains unaccepted.
