# EXReaderReadingCommands 0.1.0

Optional C ABI module that turns product reading intents into one new local revision each:
save progress, bookmark a point, highlight a range, edit an annotation body, and
explicitly delete or restore. It reuses `reader_rs_encode_v2` (wire v1 envelope, reading anchor
v1/v2) and commits with `reader_revision_local_reading`; callers read the result back through
`reader_revision_get/heads/selected/outbox`. Header: `reader_reading_commands.h`.
Package: `EXReaderReadingCommands::reader_reading_commands` (static, installed, not in the default reading build).

## Contract

- The capture is a real public-SDK selector the caller already made: `REFLOW_GLOBAL`
  (`exr_anchor_create`), `EPUB_CHAPTER` (`exr_pager_anchor_create` + part path + spine index),
  `FIXED_PAGE` (`exr_fixed_anchor_create` + zero-based page). A repeated spine path is told apart by the
  spine index (anchor v2 `part`) plus the path. Nothing is derived from a percentage or page number.
- `kind`: progress (point or range), bookmark (point only), highlight (non-empty range only),
  note text (body edit). `operation`: put, delete (names only the capture mode), restore (real capture again).
- The caller supplies the stable 32-hex lowercase `revision_id` and the complete observed head set
  (0..32 unique IDs). Stale, partial or superset heads are refused as `READER_RC_UNSAFE`; nothing is committed.
  Only a new bookmark/highlight may leave `annotation_id` empty; it is allocated and returned.
- A retried empty `annotation_id` never allocates a second identity: while building the command the module looks
  the `revision_id` up in the product catalog and, when a revision is already retained under it, reuses that
  revision's annotation identity (the host does not need to remember the first response). The rebuilt wire is then
  the same bytes, so a lost response is an exact no-op. If the payload really differs it stays the revision
  module's COLLISION; a retained ID of another entity or another book is `READER_RC_SOURCE`.
- Exact retry (same ID, same inputs) is a no-op (`created == 0`), before the stale-head check, also
  after ack or after later edits. Same ID with different bytes is the revision module's COLLISION.
- Note edit reads the retained revision itself (retry) or the single safe selected head that equals the
  observed head, decodes it, and re-encodes with only text/ID/parents changed. The result must decode to an
  identical selector, anchor version, part, page and chapter scope, else `READER_RC_SOURCE`. The original
  anchor version is kept, so a v1 head stays v1; no re-anchoring, rounding or relocation happens.
  A tombstone refuses an edit: restore is explicit and needs a real capture.
- Text is strict UTF-8 (no NUL, overlong, surrogate or > U+10FFFF), at most 65536 bytes.
- A product revision is never copied into SDK notes, and no SDK progress or SDK note write happens at all: the
  revision module keeps reading entities as selected payloads. The current page is not changed by this module;
  only a host that resolves a committed revision to the public `FOUND` result and gets an explicit user accept
  may navigate. Product schema 1, wire v1, anchor v1/v2 and the revision module are untouched. One call uses the
  store's owner worker without callbacks, so there is no reentry. Error text is fixed and at most 159 bytes;
  no input is echoed.
- Failures leave history and outbox unchanged, because the single transaction is the revision module's.
- The probe replays the real lost-response path with an empty `annotation_id`: first commit, discarded result,
  same `revision_id` and the same command again must return the original annotation ID and entity key with
  `created == 0`, one history entry and one outbox row, no requeue after ack, and COLLISION for a different payload.

## Acceptance (GitHub Actions only)

`.github/workflows/reader-reading-commands.yml` builds on Windows, Linux and macOS: product SQLite,
revisions, the unmodified reading-library SDK, reading-state, commands, this module, then independent C11 and C++
consumers from installed packages. The probe imports generated TXT, EPUB (global and bounded), PDF and CBZ originals,
captures through the public SDK, and judges every command by public readback of wire, heads and outbox, with SDK
blobs, notes and progress compared against a baseline. `check_artifacts.py` re-downloads the three same-run ZIPs
and compares size, digest, upload log and identity. The result of a run belongs in
`docs/validation/reader-reading-commands.json` and is granted only for the exact source, run and attempt named there.

A writer-blocked commit is covered end to end: a second connection holds `BEGIN IMMEDIATE` on the
product catalog, so the capture still encodes and validates and the failure lands on the module's own
`reader_revision_local_reading` write lock. The probe then proves the retained history, heads and outbox are
the exact pre-lock public readback, that no bytes were retained for that ID, and that retrying the same ID
commits once.

Not covered: host UI/adapters, other formats, transport, and process kill during commit (revision-module scope).
A catalog locked by `BEGIN EXCLUSIVE` cannot be read either, so that variant would fail in the selector instead
of the commit and is not used as commit-failure evidence. Copying a product revision into SDK notes is not
pending work of this package: reading entities stay selected payloads, and the current page is navigated only by
a host that already has the public `FOUND` result and an explicit user accept, which this module neither
performs nor authorizes.

## Accepted cloud run

Tested source `6ba1ad0d0c3c74dfc5c5267521f60dfd3210a48a` on `codex/reader-reading-commands`, run
[40081701747](https://github.com/NoGod3524/EXReader/actions/runs/40081701747) attempt 1: success.

| job | id | result |
| --- | --- | --- |
| reading commands (ubuntu-22.04) | 120836421578 | 1402 checks, 0 failures, 21 cases, 6 race rounds |
| reading commands (windows-2022) | 120836421497 | 1402 checks, 0 failures, 21 cases, 6 race rounds |
| reading commands (macos-15) | 120836421599 | 1402 checks, 0 failures, 21 cases, 6 race rounds |
| same-run artifact evidence | 120837153821 | `problems: []`, three ZIPs re-verified inside Actions |

Artifacts, each named with run and attempt and valid until 2027-01-22T09:22:34Z: Linux `12555347919`
10,297,711 B `sha256:1ec3eda...cd9424`; Windows `12555602070` 8,529,139 B `sha256:dcf071f...7e1d7f6`;
macOS `12555502324` 9,185,764 B `sha256:d7915e0...24fa88d`; evidence `12555273459` 1,886 B
`sha256:6f7ce89...474f97b8`. The three systems produced byte-identical originals (txt, edited txt, epub,
pdf, cbz, spacer) and exactly one vendored SQLite archive each.

Earlier failing runs 40078160945 (`58fa6021`), 40078549084 (`03027bcb`) and 40079084692 (`b2d587f6`) stay
recorded and are not reclassified. Host UI/adapters and applying a committed revision to the SDK remain
outside this acceptance (`host_integration_accepted: false`).
