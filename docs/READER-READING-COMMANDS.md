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
  Only a new bookmark/highlight may leave `annotation_id` empty; it is allocated and returned for retries.
- Exact retry (same ID, same inputs) is a no-op (`created == 0`), before the stale-head check, also
  after ack or after later edits. Same ID with different bytes is the revision module's COLLISION.
- Note edit reads the retained revision itself (retry) or the single safe selected head that equals the
  observed head, decodes it, and re-encodes with only text/ID/parents changed. The result must decode to an
  identical selector, anchor version, part, page and chapter scope, else `READER_RC_SOURCE`. The original
  anchor version is kept, so a v1 head stays v1; no re-anchoring, rounding or relocation happens.
  A tombstone refuses an edit: restore is explicit and needs a real capture.
- Text is strict UTF-8 (no NUL, overlong, surrogate or > U+10FFFF), at most 65536 bytes.
- No SDK note copy, no SDK progress write and no current-page change. Product schema 1, wire v1, anchor v1/v2
  and the revision module are untouched. One call uses the store's owner worker without callbacks, so there is no reentry.
  Error text is fixed and at most 159 bytes; no input is echoed.
- Failures leave history and outbox unchanged, because the single transaction is the revision module's.

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

Not covered: host UI/adapters, other formats, applying a committed revision to the SDK, transport, and process
kill during commit (revision-module scope). A catalog locked by `BEGIN EXCLUSIVE` cannot be read either, so
that variant would fail in the selector instead of the commit and is not used as commit-failure evidence.
