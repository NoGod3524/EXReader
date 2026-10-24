# Reader module composition: one prefix, real consumers, real rejection

This package answers one question with executed evidence: if every optional
reader module is installed into **one** prefix next to the frozen SDK, can a
fresh project that knows nothing but `find_package()` build a C11 consumer, a
C++17 consumer and one translation unit per installed header, then run a real
product chain through all of them - and does the gate still reject the usual
composition defects?

It adds no framework, no super-build, no merge of the module trees and no new
product code. Only `tests/reader_module_composition/**`,
`.github/workflows/reader-module-composition.yml`, this document and
`docs/validation/reader-module-composition.json` change.

## Fixed inputs

| Item | Value |
| --- | --- |
| Implementation start | `f43baf9182d75907c0cb5d6f77048f27bca8c950` |
| Frozen SDK tree | `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0, ABI 1) |
| Product schema | `apps/reader/store/001_catalog.sql`, unchanged since the start |
| Default reading build | `cmake --preset reading-library` (no optional module) |

The workflow refuses any source whose `src`, `include`, `cmake`,
`CMakeLists.txt`, `tests/fixtures`, `bindings`, `native.yml` or
`reliability.yml` differ from the frozen SDK commit, whose product migration
differs from the start commit, or whose changed paths leave this package's
whitelist.

## What is installed into the single prefix

The SDK is installed first with its unchanged preset, then the thirteen
independent packages, each with its own upstream `CMakeLists.txt` and the same
`CMAKE_INSTALL_PREFIX`:

```
EXReader (core, library)          EXReaderProductCatalog     EXReaderRevisions
EXReaderWebDAV                    EXReaderSideload           EXReaderCredentials
EXReaderSearch                    EXReaderPreferences        EXReaderBatchImport
EXReaderSync                      EXReaderCommands           EXReaderDesktopMetadata
EXReaderSession                   EXReaderReadingState
```

No module is added to the SDK build, no SDK target is rebuilt, and no module
build reads another module's source tree: each one is configured with the
prefix it installs into.

## The consumer, in a fresh directory

The consumer sources are **copied out of the repository** into `build/fresh`
before configuration. Its only inputs are `EXR_MODULE_PREFIX` and
`find_package()`; there is no `add_subdirectory` of product code, no relative
include and no test helper of another package.

* `composition-c` - one C11 translation unit (`C_STANDARD 11`,
  `C_EXTENSIONS OFF`) that includes every installed public header and runs the
  C-visible chain: credentials, preferences, product provider, typed book
  command, import, search capture, reading-anchor v2 encode, revision commit,
  decode and a resolve on a second SDK library. The C++-implemented packages are
  reached through their C ABI; `LINKER_LANGUAGE CXX` only selects the native
  linker.
* `composition-cxx` - one C++17 translation unit linked against the same set,
  running the full product chain including native WebDAV and the account
  session.
* one object library per installed public header, compiled once as C11 and once
  as C++17, each linked **only** to its own owning package. A package that
  forgets a public dependency or an `INSTALL_INTERFACE` include directory
  fails here, not in an integration branch.

## The executed product chain

```
batch import (sideload) -> SDK library
typed book command        -> product catalog row + history + outbox (one transaction)
search capture            -> reader_search hit anchor
reading-anchor v2 encode  -> reader_rs_encode_v2 (point and range)
product revision          -> reader_revision_local_reading, heads, selected, decode
desktop metadata          -> prepare/stage/apply/finish a favorite intent
sideload export           -> immutable original staged for the network worker
native WebDAV (TLS)       -> reader_sync push, ack, pull into a second provider
second SDK library        -> import of the delivered bytes, reader_rs_resolve_reflow
account session           -> 256-shard sweep on its own product provider
```

The WebDAV endpoint is a fixture created inside the same job: a self-signed
certificate is issued with `openssl`, trusted only in the runner trust store
(`certutil` on Windows, `security add-trusted-cert` on macOS,
`update-ca-certificates` on Linux) and served by a threading HTTP server that
implements `MKCOL`, conditional `PUT`, `GET` and `Depth: 1 PROPFIND` with
Basic auth. Every object holds the SHA-256 of the fixture it came from, every
revision leaf is `<id>-<sha256(body)>.json`, and the request journal proves the
method, status, depth and conditional headers that the installed client really
sent. Two independent roots let the relocated prefix run its own transfer
without inheriting the first run's single-head history.

## Judged properties

| Property | How it is decided |
| --- | --- |
| Installed prefix is complete | every package config, targets export, public header and archive exists in the manifest |
| Exported targets work | a fresh find_package-only configure names all seventeen imported targets |
| Headers are self-contained | one C11 and one C++17 TU per installed header, compiled against its owning package |
| Static dependencies are complete | the composed executables link with no extra `-l` and no source-tree include |
| One product SQLite provider | the final link map (`-Wl,-Map` / `/MAP`) lists exactly one archive that supplied `sqlite3.c` and it is `reader_catalog_sqlite`; no amalgamation object is linked directly |
| Relocatable | the prefix is copied to a different absolute path, the original is deleted, and the same consumer sources are rebuilt and run from the new path |
| Default reading build stays module-free | a prefix snapshot taken right after the SDK install is configured with a consumer that only asks for `EXReader`; it must find core+library, discover zero optional packages and see zero module targets |
| Real behaviour | the consumers' own named checks, the server journal, the stored bytes and digests |

Every item is reported by name, per platform, in `evidence/result.json`;
`gates/gates.json` reports the rejection controls.

## Rejection controls (all executed, not described)

| Defect | Control |
| --- | --- |
| Broken exported target | the consumer names `EXReaderRevisions::reader_revisions_typo`; configuration must fail |
| Missing declared dependency | `EXReaderWebDAV` is hidden in a prefix copy; `find_package(EXReaderSync)` must fail |
| Second SQLite provider | a duplicate `sqlite3_open_v2` object is linked into the composed consumer; the link must fail |
| Leaked source include | an installed targets file is edited to append the source `include` directory; the prefix audit must reject the copy while the untouched prefix passes |
| Detector blindness | synthetic GNU, MSVC and ld64 maps with one and two providers must be counted exactly as one and two |

## Explicit non-claims

* **Android and iOS are not covered.** This package grants Windows, Linux and
  macOS only. Mobile cross-compilation and device execution stay with the
  existing Android/iOS owners.
* **No host UI, no read-aloud, no product performance** is measured here. The
  composition runs headless binaries.
* The gate proves that the *installed public API* of these packages composes.
  It says nothing about an unimplemented feature of any module, and it does not
  re-grant any capability another package already described as incomplete.
* A successful `configure` never counts as a run: every property above is read
  from an executable's report, the fixture's journal or the linker's map.

## Files

| Path | Purpose |
| --- | --- |
| `consumer/CMakeLists.txt` | fresh-directory consumer project (find_package + header probes + interface snapshot) |
| `consumer/composition_c.c` | C11 consumer |
| `consumer/composition_probe.cpp` | C++17 consumer (real WebDAV and session) |
| `consumer/sdk_only/` | default reading build isolation probe |
| `consumer/negative_broken_target/`, `consumer/negative_missing_dependency/`, `consumer/duplicate_provider.c` | rejection controls |
| `webdav_fixture.py` | TLS WebDAV fixture, certificate trust, request journal |
| `check_prefix.py` | install manifest, include/relocation audit, default-build snapshot |
| `check_composition.py` | runs the consumers and the fixture, judges every named item |
| `check_gates.py` | runs and judges the rejection controls |
| `check_artifacts.py` | strict same-source aggregate over the three platform ZIPs |

## Reproduce

The workflow runs on `codex/reader-module-composition` pushes and on manual
dispatch. Locally, only Git and source edits happen; every build, every Python
execution and every fixture lives in GitHub Actions.

## Recorded evidence

Run [40081552526 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40081552526)
on source `4b1a17ca24eab43a765a3e984a707061d012083a` is the acceptance for this
package. All four jobs succeeded: the three `one-prefix composition` jobs
(ubuntu-22.04, windows-2022, macos-15) and the strict same-source aggregate.

| Platform | Composition items | Gate items | Product SQLite provider in the final map | Second-SDK resolve | Session sweep |
| --- | --- | --- | --- | --- | --- |
| Linux (GNU ld map) | 36/36 | 11/11 | `libreader_catalog_sqlite.a` (one) | FOUND | 1 sweep, 256 shards |
| Windows (MSVC map) | 36/36 | 11/11 | `reader_catalog_sqlite.lib` (one) | FOUND | 1 sweep, 256 shards |
| macOS (ld64 map) | 36/36 | 11/11 | `libreader_catalog_sqlite.a` (one) | FOUND | 1 sweep, 256 shards |

The composed consumers report 82 named items in C++ and 33 in C11 per platform;
the relocated copies report the same totals from the moved prefix. One install
manifest of 350 files with per-file SHA-256, one final link map and one consumer
interface snapshot are retained per platform in the run artifacts;
`docs/validation/reader-module-composition.json` records their digests together
with the artifact ids, byte sizes and expiry.

Defects this gate found in its own construction are recorded there too, so a
reader can see what was actually wrong before acceptance: a rejected workflow
expression, a CMake-generated JSON boolean, a header probed under the wrong
include spelling, an MSVC runtime mismatch, an ld64 map flag, a report key that
was a counter, a normalized text length compared against the raw file size, a
missing annotation id and parser version in the C consumer, an archive member
mistaken for a directly linked object, a withheld package still discoverable
through the lib/cmake name glob, a TARGET_OBJECTS generator expression written
with braces, and a summary that dropped the resolve state the aggregate checks.
