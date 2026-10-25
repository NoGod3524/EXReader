# EXReaderAnnotationImport 0.1.0 (D04)

Optional default-OFF static C ABI package; standalone configure with
`-DREADER_ANNOTATION_IMPORT_BUILD=ON`, installed `EXReaderRevisions 0.3.0` only.
No host wiring or SDK default changes. Public header documents ownership,
callbacks, cancellation and item cursor. The independent installed C/C++ example
is `tests/reader_annotation_import/consumer`.

## Exact accepted input contract

Only unchanged G05 `EXReaderAnnotationExport 0.1.0` JSONL format1, including its
published field order, LF record termination and ascending annotation/head IDs.
This is deliberately not a general-purpose JSON or third-party import endpoint.
UTF-8 and JSON escapes (including valid surrogate pairs) are checked strictly;
duplicate/reordered/unknown/missing keys, numbers outside bounds, wrong original
book `format:sha256`, head identities, wire length/hash, duplicate IDs, missing or
incorrect footer and trailing bytes fail before the first receive. The original
wire is decoded from its JSON string, never normalized/re-encoded, and validated
with the installed public revisions API. An existing ID with different bytes is
rejected during whole-file preflight, even if it occurs at the end of the file.

One regular, non-symlink input is opened. A private spool is filled once under a
16MiB default /64MiB hard budget and then validated completely. Commit replays
that SAME private spool, never a reopened input path. A decoded wire is bounded
by the public1MiB maximum (up to two wire buffers during existing-ID comparison); the parser streams fields/heads without aggregating a
JSONL line or the file. At most65536 unique32-byte revision IDs are tracked.
The POSIX anonymous spool is unlinked immediately; Windows uses an unpredictable
publicly generated ID with CREATE_NEW, no sharing and DELETE_ON_CLOSE, refusing a
reparse-point temp directory. No caller-supplied spool path is accepted. Spool
and source handles close on success, cancellation and every exception.

## Commit boundary

`reader_revision_receive` is the sole mutation API. Each item is one independent
revision transaction. No private SQL, new entities, clock overrides, capture,
anchor resolution, SDK note/progress writes or unsafe projection. Results expose
created/exact-duplicate/committed plus real receiving head state, including
concurrency, missing parents, tombstones and blocked restoration. A failed item
has committed=0; previous items remain committed. If a graph read fails after a
successful receive, committed remains1 and the cursor advances. Callback failure
or cancellation similarly cannot undo an already reported commit.

Retry from zero is safe: public receive does not duplicate history or requeue
outbox. `next_index` can resume on the SAME stable input and store, but it is not
a content-authentication token. Concurrent external writers can still cause a later per-item public rejection; validation is not a store-wide lock. All resumed inputs are fully revalidated before
any receive. Owner/thread checks precede input I/O; importer reentry is refused
without resetting the outer stats. Callbacks must not mutate or close the store.

## Explicit lossless-import gap — accepted=false

G05 emits current head wires only, plus aggregate graph counters. It does NOT
emit non-head ancestor wires. A fresh receiver therefore retains exact parent
IDs but reports missing parents where the source had complete ancestry. Nothing
in the public API can recreate bytes omitted from the file. Re-import after
public arrival of the original omitted revisions restores the original graph;
this is NOT reconstruction by the importer.

`book_title`, `selection`, `tombstone` and source `graph` are validated and exposed
unchanged through the metadata callback. They are advisory export snapshots,
not writable revision entities. The module does not silently turn them into new
book revisions or overwrite a receiving graph. Hosts may retain the input or
copy callback metadata; the importer does not persist it as a second schema.
`omitted_history` counts source revisions absent from the exported head set.
`complete_product_accepted` always remains0. Task acceptance is false regardless
of success of the narrower exact-head import capability. No host import UI.

## Actions validation

All builds, tests, fixture generation and artifact handling run exclusively in
`.github/workflows/reader-annotation-import.yml`, on Ubuntu22.04, Windows2022 and
macOS15. No local validation. The fixed start, frozen SDK and exclusive paths
are guarded. The unchanged original G05 corpus is generated in Actions and the
real installed unchanged exporter produces every valid input. Installed C and
C++ consumers check exact wires, original graph restoration with public parent
arrival, duplicate/replay/outbox stability, cancellation/resume, actual process
kill/reopen, source replacement after preflight, owner/reentry, platform storage
failure and named malformed files against an unchanged existing database.

The report distinguishes `measured_capability_passed` from `accepted=false`.
The evidence job authenticates same-source/run/attempt completed successful
producer jobs; unique nonempty unexpired artifact ID/name/digest; recomputed ZIP
size/SHA; unique ZIP/JSON members; exact case set; installed binary/package
hashes and frozen original-module tree identities. Executable verifier rejection
cases are run, not just described. See validation JSON for actual final results.
