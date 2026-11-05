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

## Verified desktop evidence — full acceptance remains false

Tested source: `9c7e276f13f42cb61a32507c36d1c22c4489bd01`.
[Actions run 40171486469](https://github.com/NoGod3524/EXReader/actions/runs/40171486469),
attempt 1, completed successfully on 2026-10-25. Ubuntu 22.04, Windows 2022 and macOS 15
installed C/C++ consumer jobs each passed **52 named cases** (156 platform-case
executions). Strict evidence job 121104074407 passed **17 executable verifier
rejection cases** and authenticated source/run/attempt, successful producer jobs,
unique artifact identities, recomputed producer ZIP bytes/digests, exact named
cases, frozen original module trees and actual installed binary/package bytes.

The original TXT export imported **26 exact head wires** and reported **9 omitted
non-head revisions**. Tests preserve that fresh-target missing-parent gap, then
prove the original graph returns only after the original ancestor wires arrive
through public receive. No history is synthesized and no unsafe head is selected.
Actual process termination after the first committed item, reopen/replay,
cancellation/cursor, callback exception, source replacement after preflight,
and real receiving-storage failures all ran. Malformed-file tests use an
existing target missing most incoming heads, so eager partial mutation would be
visible, rather than testing only no-op duplicate receives.

Artifact IDs/names/bytes/API digests/expiry, recomputed producer ZIP SHA256,
C/C++ consumer identities, installed importer/original exporter archives,
module tree IDs, all 52 case names and all 17 verifier-negative names are recorded
in [validation JSON](validation/reader-annotation-import.json). The summary
artifact's own identity comes from GitHub API/upload metadata; it is not
recursively re-downloaded by the same job that produced it.

Retained failures, with original expectations and artifacts preserved:

- Run 40170943525 / `7260e58b4d638b7ca5e8dcb43109a6604ca89f78`:
  Linux/macOS 45 cases passed; Windows strict MSVC rejected the safe-tombstone
  comparison with C4805 (int versus bool). Corrected the comparison without
  weakening `/W4 /WX`; strict evidence correctly refused the failed producer.
- Run 40171324393 / `6ba1dc485023cd22b4ca1c6015753d1805d00fa7`:
  all three consumers passed 50 cases, but strict evidence rejected Windows
  manifest backslashes as nonexistent ZIP member paths. Corrected producer
  paths to portable POSIX member names, retaining all verifier assertions.
  The final candidate additionally rejects inconsistent graph flags and
  impossible aggregate parent counts.

Remaining interface/validation limits: outer fields require G05's original
order; advisory metadata has no lossless product-write representation; omitted
ancestry cannot be restored from this JSONL alone. Windows source-symlink
creation was **not exercised** (regular-file rejection used a directory; POSIX
also exercised symlink rejection). No host UI, six-target product, physical
hardware, accessibility or performance grant. **accepted=false**, even though
the measured desktop exact-head importer and its strict evidence passed.

The separate evidence commit changes only this document and its validation JSON
with `[skip ci]`; implementation, consumers and workflow remain exactly the
tested source. The handoff supplies the resulting evidence HEAD explicitly.
