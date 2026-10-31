# F04 reading-state bidirectional preparation — 2026-10-31

## Status and authority

**Implementation-only preparation; no build, syntax check, test, ZIP parsing or CI
has run for these new files. This is not F04 acceptance.**

User approval at 2026-10-31 23:13:25 UTC permits exactly ten new files on
`dot/f04-reading-sync-20261031`, with **0 CI**. The fixed preparation source is
`94fb236a4a2da87dfbaf4f1dd2a47885d615a230`; SDK content remains
`8357eafa28423a7ab93ba08b823af80f01ad1505` (3.42.0).
The official catalog stays 96/108. No shared branch, product, SDK, old test,
external owner, PR, tag or release is changed.

Apple annotation product work remains with its owner. UI/F08, F03, F05, F07 and
F10 remain with their assigned writers. The new drivers invoke existing real
application UI; they do not write application databases or synthesize reading
revisions. Every raw revision is authored by the application and preserved by
the staged authenticated HTTPS service.

## Ten owned files

All eight files under `tests/dot_f04_reading_sync_20261031/`:
`contract.json`, `admission.py`, `fixtures.py`, `relay.py`,
`apple_driver.swift`, `android_driver.java`, `run.py`, `audit.py`;
plus `.github/workflows/dot-f04-reading-sync-20261031.yml` and this document.

The workflow has no push, pull_request or schedule event and its only job has
literal `if: false`. Preparation commits carry `[skip ci]`. Dispatch/build
wiring requires new bounded approval, not silent activation.

## Reused evidence, not transferred acceptance

- Run [40625252316](https://github.com/NoGod3524/EXReader/actions/runs/40625252316),
  source `0ec6d3aa34297f30e016af9f1cb2416ed79709f2`, proved SDK 3.41
  iPhone -> Android -> fresh iPhone single-EPUB progress (original anchors
  207 -> 878). Its own summary sets all_platform_F02_F04_accepted=false.
- Run [40181402323](https://github.com/NoGod3524/EXReader/actions/runs/40181402323),
  source `b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7`, accepted Android
  sender 138 checks, four originals, 19 revisions, 11 records; incoming Apple
  remained pending and bidirectional_interoperability_accepted=false.
- Run 41170540560's three green Apple sync jobs concern authorization failure,
  credential update and HTTPS retry. Their name does not prove F04.
- Formal catalog `5db41cb19673fb75bb0b498c677d770931ac33e8` leaves F04 pending
  and iPad annotation exchange partial. iPhone individual acceptance is not
  all-host interoperability.

## Prepared execution path

1. `admission.py` binds the base, SDK objects and exact ten-file path ownership.
2. `fixtures.py` acquires the original fixed real Alice EPUB using the retained
   manifest commit and exact 189249-byte/SHA256 identity. It does not choose a
   replacement after test results.
3. `run.py prepare`, only inside Actions, creates test adapter copies under
   build/f04-driver. It checks old source bytes against the fixed baseline,
   preserves original assertions and fails if any exact substitution drifts.
   It never overwrites the retained drivers or product code.
4. Apple creates actual progress, a point bookmark and a selected-text annotation
   through UI and syncs them. Android receives original bytes and exact records,
   uses real record-jump controls, verifies the displayed page contains original
   anchors, then creates return progress/bookmark/annotation by UI.
5. A fresh iPhone receives the Android progress and explicitly jumps to the
   returned bookmark and annotation. Read-only host-state checkpoints bind
   actual part/path/reading offset and rendered page identity.
6. `audit.py` first runs the retained relay strict assertions in an admitted
   generated copy, including program/ZIP identity and original retained suites.
   Then it verifies exact raw revision bytes, unique heads, point/range
   distinction and receiver landings. Even a passing stage leaves
   F04_accepted=false and six_target_accepted=false.

The Android instrumentation must be built using generated
`build/f04-driver/init.gradle`, class `org.exreader.host.F04AndroidTest`.
Apple uses the admitted 3.42 producer from
`tests/apple_sdk342_host/build.py`. Existing SDK artifact prefixes and retained
job roles are required by the unchanged original verifier. The later workflow
assembly must preserve them and the original 39 Apple cases, Android sync
phases and 24 receive checks. No old 3.41 program may be substituted.

## Remaining before any CI request

- Static independent review of these uncompiled drivers, including native UI
  labels, annotation kind after note edit, read-only owner queue usage, and
  exact source adapter substitutions.
- Build/workflow integration for SDK 3.42 Android and new instrumentation
  without mutating the retained workflow or product files.
- Decide and approve exact producer matrix, original affected regressions,
  job timeouts, one-run budget, and final gate. This document grants none.

Historical relay job runtime was about 130.05 runner-min; its original job
timeout caps sum to 700. Neither is a six-host estimate or an authorization.
A blanket 600-minute estimate was withdrawn before execution.

## Still required for complete F04

Windows, Linux GTK, macOS and iPad are not implemented by this stage. Full
six-host same-source proof must also cover required original-anchor formats,
bidirectional progress/bookmarks/annotations, non-FOUND/no-mislocation behavior,
and remote updates not forcibly moving an active reader. Existing old negative
tests remain; additional full-host evidence must be produced, not inferred from
this two-platform happy-path stage. Source compile/runtime defects are possible
until Actions validates them.

No runtime success or completion count is claimed. Failures and later fixes
must retain exact run/attempt/job/artifact identity. No new CI may begin under
this zero-CI preparation grant.

Static source follow-up: point records remain BOOKMARK after note-text edits (annotation_view.cpp classifies point before note_size). The new strict selector also refuses missing/foreign parents, duplicate parents and cyclic history before accepting one head. These are static findings, not executed tests.

Static review caught BookStore construction invoking repairMissingMappings(): the prepared Android driver now borrows the actual MainActivity worker/store for list, retained-wire and public original reads; it does not open a second application BookStore/SDK connection. Its independent chapter-boundary fixture remains a separate isolated test library. No runtime proof is claimed for this correction.
