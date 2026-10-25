# Android130 common caller preparation

Status: **prepared; no Android acceptance run at this common source**.
The sealed `57bc3966…` / `40178247177` result remains owned by that original
source. It does not grant the new common source or parser-policy combination.

## Exact baseline and production ownership

- Caller preparation starts at `b5e49d1753a6b4b88811b03fa904fe9447865247`.
- Common production/configuration is `49b2a7c86173181f8f79a760315ddb8ca2312bd1`.
- SDK protected trees are exactly `edddc463c06ed5731195cdb8f06b2df6dff7699e`.
- Android theme/test ownership is sealed delivery
  `1b3cfd1413fa5ebade31be6958f835f6de3b5290`, whose actual tested source is
  `57bc3966c20171f2f51e3fc6bf02f1ad1f7e5165`.
- The only Android production differences from that theme delivery are
  `NativeCbz.java`, `NativeReadingSdk.java` and `ReadingParserPolicy.java`;
  all three match `b1a7b7891cd394671842164a07a86c8e316dace3` exactly.
- The revisions, reading-state, reading-commands and annotation-view module
  trees remain exactly the original theme's versions. The actual header still
  declares `READER_REVISION_ANCHOR_MAX_VERSION 2u`. Schema1 is unchanged.
- Debug sender138 and raw-selector v3 are not adopted by this caller.

## Unchanged full producer and strict judge

The registered `reader-android-page-theme.yml` retains the original complete
16 authored producer steps, actual API34 `default` x86_64 emulator, APK builds,
fixture creation, instrumentation and every original business check. All
original theme/inherited test trees, Java case bodies, fixtures, candidate
adaptation generator, audit tools and strict checker remain byte-identical.

The same nine report groups remain mandatory: host-session16, search15,
navigation18, reading16, preferences17, CBZ10, fixed-pan8, host-import20 and
page-theme10, totaling **120 inherited + 10 theme = 130**. Existing actual
kill-boundary markers, installed APK identities, actual RGBA/PNG equivalence,
preserved image/authored-background samples, anchors and native provider checks
remain in the original strict judge.

Only the source guard section is replaced with the common exact guard and
syntax coverage for its thin entries. `guard_android.py` pins all existing
production/tests to the baseline, enforces the exact three Java owners and
MAX2 modules, and compares each original producer step and strict step. The
strict checkout gains full Git history for that provenance check; package
installation adds only the pinned YAML parser used to compare caller syntax.

`aggregate_android.py` validates the common source and exact workflow identity,
then executes the original strict checker without replacing any result or
altering any of its 130 raw-report/PNG/APK/ZIP assertions. Workflow path, job
name `android` and artifact identities stay unchanged.

Only four caller/document paths may change after the baseline: this document,
the workflow and `tests/reader_hosts_341/{guard_android,aggregate_android}.py`.
Production and all original tests/judges are unchanged in this preparation.

## Final dispatch remains pending

No local execution or Actions run was performed for this preparation. Commits
use `[skip ci]`; this branch is outside the workflow's automatic push filter.
Wait for the Windows delivery and root's final common production merge, then
set the explicit `guard_android.BASE` to the reviewed boundary and precisely
list further caller-owned paths. Only then run the complete producer and
strict job at that final SHA alongside the other common gates. Physical
devices, TalkBack, performance and full interoperability remain separate.
