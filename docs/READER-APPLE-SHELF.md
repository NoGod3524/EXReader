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
Prefetch uses the last actually visible row, so a tall viewport that initially
fits a complete 50-row page can fetch its next page without needing a scroll range.

The reader's compatibility/fallback metadata is separately capped at 50 rows.
It remains available when an SDK import is saved but its product index is pending
repair, including when older product rows already exist. This fallback shows the
50 newest local SDK books and explicitly pauses product search until startup
repair succeeds. Opening a shelf row uses its SDK ID, including IDs outside either cache.

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
- `2bc6e8abdd782230bef00a9a14d4effb0000e929`, canonical title/author matching:
  [shelf 40037999708](https://github.com/NoGod3524/EXReader/actions/runs/40037999708),
  [mapping 40037999715](https://github.com/NoGod3524/EXReader/actions/runs/40037999715),
  [original Apple 40037999790](https://github.com/NoGod3524/EXReader/actions/runs/40037999790).
  Superseded by the pending-index and tall-viewport corrections; cancellation
  was requested and no acceptance is transferred.
- `d94893372658871353e9585924d18af4098049e0`, pending SDK fallback and tall
  viewport prefetch: [shelf 40039402715](https://github.com/NoGod3524/EXReader/actions/runs/40039402715),
  [mapping 40039402856](https://github.com/NoGod3524/EXReader/actions/runs/40039402856),
  [original Apple 40039402733](https://github.com/NoGod3524/EXReader/actions/runs/40039402733).
  The first shelf native job compiled the Swift model and passed catalog8, then
  failed its canonical title/author assertion. Its seed assigned the decomposed
  title's author with an ambiguous grapheme prefix; the correction compares the
  complete fixture title. The assertion is unchanged. Native failure artifact
  `12539137105` is retained. UI and summary were skipped and grant no acceptance.
- `5f924754a9a089dd927e4dd5bfcbba1583e19c6f` corrected fixture identification:
  [shelf 40041333550](https://github.com/NoGod3524/EXReader/actions/runs/40041333550),
  [mapping 40041333658](https://github.com/NoGod3524/EXReader/actions/runs/40041333658),
  [original Apple 40041333686](https://github.com/NoGod3524/EXReader/actions/runs/40041333686).
  The shelf native job passed catalog8, canonical title/author byte preservation,
  and complete forward/reverse traversal, then failed
  `refresh_interruption_retains_saved_top_key`. Native failure artifact
  `12539344540` is retained. UI and summary were skipped. The following candidate
  adds state diagnostics around that unchanged assertion; no acceptance is granted.
- `0d15ef75afa35383187ea27d069b4dc961a6e30d` recorded the failure state in
  [shelf 40042762989](https://github.com/NoGod3524/EXReader/actions/runs/40042762989).
  Native job `120722123008` showed the saved cursor and top source key were
  present before refresh; the pending refresh had zero rows, was loading, and
  retained the same top key. Only the stored JSON bytes changed because a fresh
  encoder did not guarantee object-key order. Failure artifact `12540267821`
  is retained. Cursor writes now sort JSON keys; the byte-preservation assertion
  is unchanged. A manual native-only diagnostic reuses the authenticated frozen
  macOS SDK artifact `12539811656`, and always reports `diagnostic_only: true`
  and `accepted: false`. It cannot replace final same-source three-workflow acceptance.
- `9c4636e3b89169d7eeb85e1ab2088040b1e121f8` passed the single native-only
  [diagnostic 40044750632](https://github.com/NoGod3524/EXReader/actions/runs/40044750632),
  attempt 1: catalog8 and all original shelf16 checks completed. The refresh
  observation changed from `saved_unchanged=false` to `true`; exact restored
  layout, terminal viewport clamping and tall-viewport prefetch also passed.
  Artifact `12540554730` is 821,246 bytes with uploaded/API ZIP digest
  `sha256:8308ae0400760dff42bfc0442efe66f1b6360df0d17bb81c282ea8b47b6a127c`.
  Its outer scope remains `diagnostic_only: true`, `accepted: false`.
  The following complete candidate changes only this record and requires fresh
  shelf, import-mapping and original Apple acceptance on its own full source.
- `8ed6f228fccc242dbcaf093dd595b81b4395370f`: import mapping
  [40045317086](https://github.com/NoGod3524/EXReader/actions/runs/40045317086)
  completed all six jobs, and the original Apple host
  [40045317171](https://github.com/NoGod3524/EXReader/actions/runs/40045317171)
  completed all eight jobs. These independent regressions do not accept the new shelf.
  [Shelf 40045317110](https://github.com/NoGod3524/EXReader/actions/runs/40045317110)
  passed catalog8/shelf16 and built the actual SwiftUI host, but macOS job
  `120731101014` failed all seven UI cases while waiting for readiness. Failure
  artifact `12543115466` is retained. The narrow macOS diagnostic now reports AX
  decoding, visible-row and readiness conditions, using the authenticated SDK
  and 2,202-original seed from this source. It grants no acceptance.
- The single macOS case at `67f9efae4a84abbbacbefd9758ae92489eca1924`,
  [diagnostic 40050301786](https://github.com/NoGod3524/EXReader/actions/runs/40050301786),
  proved that the AX snapshot returned an empty label and a 512-character static
  text value, truncating the JSON mid-string before readiness could inspect it.
  Artifact `12542857759` preserves that failure. Review telemetry now exposes
  200-scalar fragments, reconstructed from one container snapshot; the original
  readiness, cache and layout assertions remain unchanged.
- `b3c7e8e648fa0b9eb31731ca90a5fd316b89efeb` passed the unchanged macOS
  initial-layout case in 7.341 seconds in
  [diagnostic 40051025211](https://github.com/NoGod3524/EXReader/actions/runs/40051025211).
  Artifact `12543178370` preserves the 50-row/5-visible-row observation.
  On `8ed6f228`, both iPad and iPhone passed complete bidirectional traversal
  (1,001.198 and 961.273 seconds), equal-title/literal/author searches and real
  stored-original reading. Their refresh and viewport/process-restoration
  assertions failed; artifacts `12542868969` and `12542929679` are retained.
  A narrow two-case iPad diagnostic now records actual visible row geometry
  and requested versus observed source keys. It grants no acceptance.

All compilation, syntax checks, test execution, SQL and artifact processing run
in GitHub Actions. Physical devices and VoiceOver remain separate acceptance.
