# iPhone / iPad organization acceptance — 2026-10-28

## Scope and status

New dedicated acceptance package on common source
`8f8acf3234cba747165f001c0c96efe1b911e6ad`, explicit SDK **3.42.0**.
Source-only until the exact feature-branch Actions run and original artifacts
are authenticated. No result here claims complete product acceptance or physical
device execution. No old test, product owner, SDK source, schema or budget is edited.

Exclusive paths: this directory and
`.github/workflows/apple-ios-organization-20261028.yml`.
Feature branch: `codex/apple-ios-organization-acceptance-20261028`.
Original 60-minute job and 300/600-second per-test budgets are retained. There are
no test retries or CI-success overrides. The package is capped at one initial
Actions run plus at most two materially changed, independently reviewed fixes;
no unchanged reruns or duplicate dispatches. A permission rejection stops
publication until new specific authorization. Build, fixtures, test execution, and
artifact parsing are Actions-only.

## Observed prior gap

[Original common-source run 40635727935](https://github.com/NoGod3524/EXReader/actions/runs/40635727935)
at `716c1409168960a276e282ce694d32ed82497bc9` built all three targets.
macOS passed all six old cases. iPhone job `122642118983` and iPad job
`122642119222` each passed five cases and failed only
`OrganizationUITests.testGroupLifecycleAndProcessRestart`, at selecting the removed
`Renamed Shelf`. The failure accessibility tree shows `organization.removed`
as a labelled outer Switch and an unlabelled nested native Switch, **both value 0**.
Rename and removal had succeeded; the generic outer-element tap had not enabled
removed filtering. This is evidence for an input-target mismatch, not proof of a
persistence defect. The old test and its failure remain intact.

At inspection, this common workflow's branch had only that run. The earlier
`codex/apple-organization-reopen-20261028` run `40635405044` also had failed mobile
jobs and a successful macOS job. This is a new independent suite, not a retry or
rewriting of either historical result.

## Native acceptance

Six methods run independently on both simulator families:

* Shelf, tag, and series each: import a real bundled EPUB; create and identify a
  group; bootstrap from verified original; add a specific book; verify member row
  and ordinal; process restart; remove the relation; process restart preserving
  its tombstone; restore relation; rename without changing group identity; remove
  group; enable and assert native switch state; process restart preserving group
  tombstone; restore group and relation; final process restart.
* Nested shelf: distinct parent/child IDs, parent navigation excludes the child at
  root, and parent-child identity survives real process restart.
* Durable staged intent: terminate at the existing review-only durable boundary;
  reopen pending state, retry once, refresh and restart without duplicate group
  or remaining pending operation. Does not claim a second invocation of retry.
* Stale snapshot: existing review-only independent writer commits while the old
  snapshot remains held; stale edit is refused; restart retains pending conflict;
  retry remains refused; abandon preserves competing revision and stable identity
  across another restart. This is stale-snapshot concurrency coverage, **not**
  simultaneous-process sync or a two-device synchronization claim.

The switch helper chooses the nested UISwitch if present and asserts its actual
value, rather than tapping a broad label or adding a production workaround.
Membership assertions use the exact book identity and native projected member row,
not merely the status label. Every case retains exact steps, observations, a PNG
and the native accessibility hierarchy.

## Build identity and evidence

`prepare.py` first limits all tracked changes relative to the common base to the
new package/workflow. It invokes the unchanged SDK342 package builder, including
its SDK candidate-content guard, exact installed SDK/product identity and unpacked
signed bundle checks. It generates separate build-directory copies of the old
Xcode generators with only three declared adaptations: SDK342 version allowlist,
SDK342 theme allowlist, and generator path. Original sources and all behavioral
assertions remain unchanged; old source and fixture hashes are retained.

`collect.py` runs even on test failure, exports native diagnostics before rejecting
failed cases, and binds passing cases, exact steps, native observations, source,
run/attempt, simulator family, executable and SDK runtime to retained hashes.
The exact tested application is retained as `EXReaderHost.zip`; aggregate
authentication recomputes its executable, SDK runtime and bundled fixture hashes.
The final job checks original producer success plus GitHub's original artifact ZIP
SHA-256, same-source/run/attempt identity and every selected evidence file digest.
No summary from another branch or source can substitute for these outputs.

This suite does not claim to rerun or repair the old organization tests, macOS
acceptance, legacy SDK compatibility, signing for devices, distribution, or release.
