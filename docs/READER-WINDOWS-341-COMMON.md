# Windows SDK3.41 complete common host caller

Current status: **candidate source, complete acceptance pending**. Reviewed production
boundary: `436c5bd57b2b6acc0076a0942e7c7f93f38fcb96`.

Preflight `40191472981` passed on source `84b53274`; complete attempt
`40191539835` stopped before business execution because Git Bash converted the
new `/MAP` linker flag into `C:/Program Files/Git/MAP`. The caller now disables
that automatic conversion only for the host configuration step. Original
checks and the failed attempt remain unchanged.

The main `ws-host` compiles SDK3.41, F3, cloud import, bulk organization,
reading records, search and navigation together. All original Windows suites
run on that same production executable: F1 264, F2 130, navigation31, records32,
UI158, product10, worker5, shelf13, metadata18, account32, accessibility24,
J01 47, J10 21, cloud-import UI and F3 25. The navigation-without-search build
and every original strict judge remain required. No production source changes.

The independent `baseline-host` compiles the frozen SDK3.40 at `9854061b`,
with its own installed modules and actual executable. It serves the original
F3 option-off pixel comparison. No old-source report fills current evidence.

`ws-package` and `wprefs-package` deliberately hold byte-identical copies of
the one full SDK3.41 production executable. `baseline-package` is distinct.
The thin F3 wrapper loads the unchanged original judge and replaces exactly
one baseline ZIP path literal. All original F3 assertions and recursive
F1/F2/records judges execute. The complete original import/organization strict
chain also runs unchanged in an isolated report directory.

The same full SDK3.41 source/options additionally compile the actual atomic
review and old-veto control executables. The original 13 named real-process
checks, actual before/after-save cancellation, reopen and old-veto rejection
run unchanged. The original atomic validator and its nine rejection controls
remain required. Candidate/review/control binaries and their maps are retained.

Two original consumer CMake entry points hard-code 3.40. New tiny 3.41 consumer
entry points reference their exact original C/C++ sources and original libraries;
they change only the explicit installed SDK version. Original consumer source,
test assertions, workflows and fixture bytes are unchanged from the boundary.

## Workflow and upper-collector contract

- Workflow: `.github/workflows/reader-windows-341-common.yml`.
- Whole full run: three jobs, `preflight`,
  `installed F1 and native Windows search controls and lifecycle`,
  `same-source native Windows search artifact authentication`.
- Push runs preflight only. Manual `mode=full` runs the complete producer and
  strict job after the same preflight. Every build/check/artifact operation is
  restricted to Actions.
- Raw artifact: `reader-windows-search-initial-{run_id}-{attempt}`.
- Strict artifact: `reader-windows-search-summary-{run_id}-{attempt}`.
- Complete F3 JSON: `windows-341-summary/full-f3.json`.
- Atomic JSON: `windows-341-summary/atomic13.json`.

Both required upper-collector Windows leaves may reference this same whole
run and explicit latest attempt. Each must verify its own report and scope;
one `accepted` flag never substitutes for both reports.

Both reports bind `source_sha/run_id/attempt`, `producer_job`, the raw
`artifact` API ID/name/bytes/digest/expiry, SDK3.41/ABI1, actual `identity.files`,
`consumer_sha256`, `atomic_review_sha256`, `old_veto_control_sha256`,
`production_map_sha256` and `original_judges_preserved=true`.
The full report separately requires F3 25 and every original count; atomic
requires `checks=13` and the full original `atomic_report` bound to actual
review/control bytes. All maps must contain installed F3, background, search,
navigation, records, cloud import and bulk symbols.

`identity.files` authenticates actual SDK headers/package configurations,
programs, maps and build caches. Production/F3 copies must have the same hash;
production, shelf review, atomic review, veto control and baseline must have
five distinct hashes. The installed SDK package is explicitly 3.41/ABI1; the
compatibility core remains 3.40 where the SDK declares it.

The new identity protocol has 13 synthetic rejection controls, in addition
to all original protocols. They are pending until Actions executes them.
All scope flags for complete product, performance, physical device, upgrades
and bidirectional interoperability stay false.

After final Apple/global integration the root may advance the caller's BASE
to the reviewed final production boundary, retaining identical Windows bytes,
then rerun the complete workflow at that exact final source.
