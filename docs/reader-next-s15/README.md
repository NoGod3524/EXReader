# S15: existing original export on the approved SDK 3.41 install graph

Fixed start: `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8` (branch
`codex/reader-next-s15`). Approved SDK 3.41: `edddc463c06ed5731195cdb8f06b2df6dff7699e`.
Frozen SDK 3.40: `9854061be331fe603a1822d9b2b36ee357154927`. Reused module:
`25cd7b4b15d952e3f7a10e39ed80ae16a3d9a3ee` (`apps/reader/original-export`).

## Scope and change

`apps/reader/original-export` was copied from the fixed module commit with
`git checkout <module> -- apps/reader/original-export`. `include/`, `src/` and
therefore the public C ABI, item layout and behavior are byte-identical to that
commit; the CI guard re-proves it every run with
`git diff --exit-code <module> HEAD -- apps/reader/original-export/include apps/reader/original-export/src`.

The only functional change is the install graph:

| Before | After |
| --- | --- |
| `find_package(EXReader 3.40.0 EXACT ...)` hard-coded | `EXR_SDK_VERSION` exact pin, default `3.40.0`, only `3.40.0`/`3.41.0` accepted |
| `find_dependency(EXReader 3.40.0 EXACT ...)` hard-coded in the installed config | `find_dependency(EXReader @EXR_SDK_VERSION@ EXACT ...)`, so the installed package records the graph it was built against |
| no prefix hint | optional `-DEXR_SDK=<prefix>` prepends the installed SDK |

Approved SDK 3.41 differs from frozen 3.40 in exactly the version macros, one
added `exr_render_page_background` entry point and the canvas fill refactor;
`include/exr/library.h`, `exr_library_source` and the bookshelf snapshot used by
this module are unchanged, so only the install pin was needed. Nothing in the
SDK tree, the host, the sideload exporter or any other package is modified:
`git diff --exit-code <start> HEAD -- apps/reader/store apps/reader/revisions
apps/reader/commands extras/sideload apps/reader/local-downloads apps/reader/session`
runs in every job.

## Reuse, not a second codec

Originals always come from the public SDK. The module calls `exr_library_source`
and copies with 64 KiB `read_at` chunks; it never reads the ZIP archive cache,
never issues SQL against the SDK library, and adds no new parser, container or
transfer codec. The unchanged `extras/sideload` package is built and used as an
independent byte oracle: `exr_sideload_export_original` exports the same CBZ and
both files must match the frozen fixture and each other.

## Acceptance evidence (all in Actions)

`reader-next-s15.yml` runs only on `codex/reader-next-s15`:

1. `export` on ubuntu-22.04, windows-2022 and macos-15: builds and installs the
   approved SDK from an isolated `git archive` of `edddc463`, installs the
   unchanged sideload/product packages, installs this package with
   `-DEXR_SDK_VERSION=3.41.0`, compiles fresh C and C++ consumers from a copied
   directory against installed packages only, then runs the named checks.
2. `frozen`: builds the real frozen SDK 3.40 from `9854061b`, proves the default
   pin still builds, links the installed C consumer, exports a real original
   byte-exactly, refuses the 3.41 opt-in on that graph, and keeps an existing
   target untouched on re-export.
3. `evidence`: downloads every artifact ZIP, re-hashes it, checks run/job/artifact
   identity, expiry and every named case, binds the ZIP members (installed module
   archive, consumers, fixtures, originals, snapshots, install-graph logs) and
   tries to make the verifier accept mutated reports and tampered members.

Named runtime checks cover: nine non-streamed originals plus large/changed
originals byte-identical to frozen fixtures; streamed storage (bounded source
import for EPUB/CBZ and file import for PDF) exporting the same hashes as the
non-streamed counterparts; Unicode destination; whole-batch size preflight;
existing target never overwritten; display-name slug restrictions; invalid
UTF-8, traversal and device-name rejection; directory and target aliases;
100/101 selection bounds; per-book, batch and hard byte limits; owner refusal,
wrong thread, reentry; missing source and mid-read invalidation; cancellation
before start and after a commit; verified temporary readback; truthful cleanup
receipt; a real killed process, orphan cleanup from the receipt and reopen/retry
after a kill (both before and after publication); single balanced owner lease
per run and no handle retained across sequential runs; SDK originals, notes and
progress plus raw product history/outbox unchanged. POSIX adds a real
`RLIMIT_FSIZE` mid-stream write failure; Windows adds an actual locked-temporary
cleanup failure. Windows mid-stream disk-full/fsync injection stays
**UNAVAILABLE**, never mocked.

The mixed-SDK negative relabels only the package metadata of the approved 3.41
install to 3.40 (shipped archives are hashed before and after and must be equal),
first proves that graph resolves as 3.40, and then requires the installed module
to refuse it. The authentic frozen-graph test is the separate `frozen` job.

## Not claimed

No host selector, no UI, no new transport codec, no SDK acceptance: this module
build remains an unadopted candidate even though the SDK version string already
says 3.41.0. Orphan discovery is still the host's receipt-keeping job; no
unattended crash cleanup, no share registration, no six-device claim.

## Evidence record

See `docs/reader-next-s15/evidence.json` for the recorded run identity,
artifact IDs/sizes/digests/expiry, binary identities, job identities and the
verifier rejection list.
