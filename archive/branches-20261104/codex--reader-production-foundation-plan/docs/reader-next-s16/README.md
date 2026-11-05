# S16 jump history: explicit raw3 compatibility

The reader jump history is a bounded in-memory back/forward stack of reading
positions. S16 adds an explicit, default-off raw candidate to that one module
and does not touch reading-state, revisions, the product schema, the wire or any
host.

- Package: `apps/reader/jump-history` (EXReaderJumpHistory).
- Default install: `EXReaderJumpHistory 0.1.0` on `EXReaderReadingState 0.1.0`
  and `EXReaderRevisions 0.3.0`.
- Explicit raw candidate install: `EXReaderJumpHistory 0.2.0` on
  `EXReaderReadingState 0.2.0` and `EXReaderRevisions 0.4.0`.
- The raw candidate is an independent module capability. It is **not** an
  accepted SDK, not a product default, and it grants no GUI and no host wiring.

## What is reused, not reinvented

The module keeps its own public header, its own bounded store and its own copy
semantics. The raw capability is only the installed public
`reader_reading_state.h` surface (`reader_rs_encode_fixed_v3`,
`reader_rs_decode_raw_v3`, `reader_rs_resolve_fixed_v3`) reached through the
installed package; no SDK private header, archive or SQLite build is added, no
second parser is vendored, and no database or schema row is introduced.

## Public additions (raw candidate only)

| Symbol | Meaning |
| --- | --- |
| `READER_JH_INSTALL_VERSION` | `"0.2.0"` in the raw install and `"0.1.0"` in the default install. `READER_JH_VERSION` (ABI/wire) stays `"0.1.0"` and `READER_JH_STRUCT_VERSION` stays 1 in both, so every original consumer assertion and every structure layout is unchanged. |
| `reader_jh_commit_fixed_v3` | Encodes a `fixed_page` capture with `reader_rs_encode_fixed_v3` (anchor v3) and records it. It never inserts. |
| `reader_jh_commit_wire_raw_v3` | Stores a wire the raw validator accepts, including an unchanged retained anchor v1/v2 wire whose version and bytes are preserved exactly. |

Both calls follow every rule of `reader_jh_commit`: same-landing
`UNCHANGED`, `PAGE`-after-`PAGE` coalescing, forward truncation, bounded
eviction, accounting, atomic refusals, item copy semantics and owner-thread
rules.

The default calls stay exactly as they were **in this install too**:
`reader_jh_commit` still encodes through `reader_rs_encode_v2` and
`reader_jh_commit_wire` still decodes through `reader_rs_decode`, so a legacy
entry refuses an anchor v3 wire and a raw store, and a raw entry refuses a
legacy store. A module and a store of different families never mix in either
direction.

## Selector identity

An anchor v3 selector is bytes, not a C string. The private canonical location
key therefore records, for anchor v3 only, the **presence** and the **byte
length** of `exact`, `prefix` and `suffix` before the bytes themselves:

- an embedded NUL never ends a selector, so two points whose context differs
  only after a NUL are two different places;
- a NULL context is a different place than an allocated empty one, so a stored
  entry always reproduces the wire the host really captured instead of silently
  "emptying" it;
- an allocated empty quote (`exact_size == 0`, non-NULL) stays a real point:
  that is what a textless fixed page produces.

A v1/v2 record keeps the identical key it had before S16, so the default
install and its stored bytes are unchanged.

The component still never navigates. A wire whose selector has no navigable
exact bytes (a NULL expression) is refused with `READER_JH_ARGUMENT` instead of
being emptied, and a non-point progress range is refused by the installed
validator (`READER_JH_REVISION`, nothing stored), because the shared wire decides
what a reading position is. The host decodes a stored wire with
`reader_rs_decode_raw_v3`, reloads the book and resolves; only `FOUND` allows
`reader_jh_complete`.

## Installed-version distinction and mixed-install refusal

The two installed families never share a version, and a mixed install is refused
four times over:

1. `find_package(EXReaderReadingState 0.1.0 EXACT)` / `0.2.0 EXACT` - a raw
   jump-history build cannot configure against a legacy adapter and the default
   build cannot configure against a raw adapter;
2. at build time the exact imported adapter target must also carry
   `EXR_READER_SELECTOR_BYTES_CANDIDATE=1` when this package is the raw candidate
   and must not carry it otherwise, so a faked version file cannot smuggle the
   other family in;
3. the installed package version itself (`0.1.0` vs `0.2.0`) refuses a consumer
   that asks for the other one;
4. the installed package config repeats the origin/capability guard through
   `_exr_raw_guard_target` for the adapter targets and for this package.

At runtime the store family is the second gate: a raw entry on a legacy store
and a legacy entry on a raw store both fail with `READER_JH_REVISION` and change
nothing.

## Acceptance

`.github/workflows/reader-next-s16.yml` runs on ubuntu-22.04 and windows-2022.
Each job, from installed packages only:

1. guards the fixed start `e67d87c`, the approved SDK source `edddc463`, product
   schema `f32bb8aa`, the shared reader modules and the S16 ownership list with
   `git merge-base` and `git diff --exit-code` (no shell grep filter);
2. builds the product provider, the approved 3.41.0 SDK and **three** families:
   the fixed-start baseline jump history, the default `0.1.0` family and the
   explicit raw `0.2.0` family;
3. reruns the **unchanged** original suite (`tests/reader_jump_history`) on the
   baseline, on the default install and on the raw install; the raw install uses
   a copied consumer CMakeLists whose only changed line is the requested package
   version, asserted in the driver;
4. requires the default install to reproduce the baseline case by case
   (originals, stored-wire cases, lifecycle steps, named checks, no-write
   verdicts) and requires the default header to be the baseline header plus
   insertions only, with no raw symbol in the default archive;
5. runs the new raw consumer: real public-SDK captures from the public PDF
   original whose text contains NUL, a generated TXT, EPUB and CBZ; anchor v1/v2
   replay; anchor v3 storage; NULL/empty and NUL identity; back/forward,
   truncation, cancellation, staleness, cross-history tickets, entry and byte
   caps, thread rules, item lifetime and the no-write proof;
6. exercises four mixed-install negatives (raw against default, default against
   raw, the original consumer against the raw install, and a faked version file
   that must be refused by the capability check);
7. preserves logs, originals, evidence, installed headers and archives, and the
   result; the `evidence` job authenticates both same-run ZIPs through the
   GitHub API (size, SHA-256, expiry, head SHA), rebinds every summary to this
   source/run/attempt, re-hashes the uploaded probe against the recorded program
   hash and requires the two runners to agree on originals, cases, lifecycle,
   versions, semantics and the no-write verdict.

Nothing here runs on a developer machine: no local compiler, generator, parser,
fixture or download.

## Scope

This is the reader **module** only. Not covered: host wiring, menus, shortcuts
or dialogs in the four production hosts; persistence or cross-device behaviour;
real user libraries or private storage; latency or CPU budgets; acceptance of
the raw candidate as an SDK or product default. `host_wiring_accepted`,
`gui_accepted` and `adopted` stay false in every report.
