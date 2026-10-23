# Native Apple product shelf

The shelf reads product metadata from the existing schema-1 catalog. Each query
returns at most 50 rows, ordered by the binary `(sort_title, book_key)` pair.
Both directions use exclusive keyset cursors; startup/refresh can include the
saved top key. Title and author search binds an escaped literal `LIKE` value,
including `%`, `_` and backslash. No SDK, binding or schema change is required.

The native SwiftUI `List` retains at most three catalog pages, or 150 rows.
Appending/prepending evicts only the opposite page when it cannot remove the
currently visible rows. List geometry supplies the visible top source key;
pagination, refresh and viewport changes restore that key. Query generation
rejects late results. Search text, top source key and selected source key are
saved separately from the reader's existing exact progress and annotation state.
An interrupted same-query refresh retains its previously saved cursor. An idle
visible source key is also saved after a short debounce, so process termination
does not require a preceding background event to preserve the last settled view.
At the global tail, a taller native List may be unable to keep the old top row
at the top. The host accepts its actual earlier first row only after observing
both the requested row and terminal row in the viewport; it never invents an
offscreen anchor. Search uses the same NFC/256-scalar bound at UI and SQL layers.
Title matching uses the normalized sort title; author matching binds both NFC
and NFD literals. Stored display title and author bytes are preserved.

The reader's compatibility/fallback metadata is separately capped at 50 rows.
It remains available when an SDK import is saved but its product index is pending
repair. Opening a shelf row uses its SDK ID, including IDs outside either cache.

## Memory and timing boundary

This bounds retained UI metadata, not the whole startup or reader process.
The current public SDK still returns a complete `books()` enumeration during
startup repair and some existing open/state/export paths. Those transient arrays,
font data, SQLite buffers and the reader's rendering memory are not covered by
the 150-row shelf limit. The compatibility 50 rows are additional retained data.

Cloud observers record the real process peak RSS, shelf creation to its first
visible native layout, bounded layout-observation intervals and screenshots of
the actual native views. Layout observations are not display FPS measurements;
no hard size, memory or frame-time budget is granted by this package.

## Independent cloud acceptance

`tests/apple_host/shelf/ShelfReview.swift` creates 2,202 distinct stored originals
using the actual public macOS SDK and attaches all their actual fingerprints to
the product catalog. The closed SQLite files are portable inputs for macOS,
iPhone simulator and iPad simulator. The seed includes 130 identical titles,
one unique author, a title containing literal `%_`, and decomposed Unicode
title/author bytes queried with canonically composed text.

Native checks cover both complete keyset traversals, stable equal-title keys,
title/author/literal/empty searches, inclusive restoration and a deterministically
late query result. Independent UI input scrolls the production native List in
both directions, searches and refreshes it, resizes/rotates it, backgrounds and
restarts the process, then opens an actual stored original and returns to its
filtered shelf. Its collector checks all 2,202 stored source hashes against the
product mappings, plus screenshots, observations, SDK/source identities and
database snapshots.

The original Apple 13 UI / 67 steps / 50 attachments per platform, all original
21 self-checks, SDK21 / Model18 / Bounded15 / 97 rejection regressions remain
requirements. The separate Apple import-mapping catalog8 / SDK16 and three
platform 5 UI / 22 steps / 14 attachments remain requirements as well. Their
assertions are unchanged. All three workflows must pass on the same final source.

## Candidate record

Base: `a6d7dd81eef36e83e004fdc381a565a2ffee5462`, the delivered Apple import-mapping
head. This work uses independent branch `codex/reader-apple-shelf`; PR12 is
unchanged. Frozen SDK: `9854061be331fe603a1822d9b2b36ee357154927`.

- `655edfc98e1d0c39eeb66fe201c09fbd5c67bd49`, native bootstrap run
  [40034248093](https://github.com/NoGod3524/EXReader/actions/runs/40034248093):
  both SDK jobs completed; the superseded run was cancelled before native
  acceptance and grants no validation credit.
- `3bd55c1a16eeb88e0a6d426e66da7d86f4c25f77`, first complete UI candidate:
  [shelf 40034880367](https://github.com/NoGod3524/EXReader/actions/runs/40034880367),
  [mapping 40034880402](https://github.com/NoGod3524/EXReader/actions/runs/40034880402),
  [original Apple 40034880345](https://github.com/NoGod3524/EXReader/actions/runs/40034880345).
  These superseded runs were requested to cancel, retaining their records;
  none contributes validation credit.
- `e34b54ed1f84a9a0b8702bbd9bf0d9860fd9fdc1`, layout acknowledgement and
  13 native checks: [shelf 40035801727](https://github.com/NoGod3524/EXReader/actions/runs/40035801727),
  [mapping 40035801688](https://github.com/NoGod3524/EXReader/actions/runs/40035801688),
  [original Apple 40035801800](https://github.com/NoGod3524/EXReader/actions/runs/40035801800).
  Cancellation was requested after these candidates were superseded; their
  final cancellation state remains to be confirmed. No acceptance is granted.
- `f7ea68025b50a18e16ed1697f76f53adc84cc6dc`, terminal viewport clamping,
  idle cursor persistence and scalar-bound correction:
  [shelf 40036560455](https://github.com/NoGod3524/EXReader/actions/runs/40036560455),
  [mapping 40036560497](https://github.com/NoGod3524/EXReader/actions/runs/40036560497),
  [original Apple 40036560509](https://github.com/NoGod3524/EXReader/actions/runs/40036560509).
  Their SDK jobs are queued; no P4 compilation or functional acceptance has
  completed on this source.

All compilation, syntax checks, test execution, SQL and artifact processing run
in GitHub Actions. Physical devices and VoiceOver remain separate acceptance.
