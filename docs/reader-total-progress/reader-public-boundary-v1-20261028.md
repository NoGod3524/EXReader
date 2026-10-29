# Public module boundary v1 — authorized source integration

Status: source authored and independently reviewed before publication; no local
build, test, syntax check, fixture creation or artifact replay. All execution is
GitHub Actions only. Runtime outcomes must be added from actual Actions evidence,
not inferred from this source description.

## Authority and immutable predecessor

The user explicitly authorized the previously reviewed 17 owner + 7 new validation
paths at 2026-10-28 22:52:52 UTC, replying to the exact module/public-interface
scope: “我不想再说一遍了，我明确授权”. This supersedes the prior no-owner-edit
restriction only for the listed paths. SDK, old tests, producer semantic flags,
budgets, main, PRs, tags and releases remain outside this package.

Base is `f331d5da3ac491143d8f525089140f5d2365fa97`, the terminal Linux auditor
whose run `40780766726/1` passed 22 protocol controls but correctly rejected one
ReadingCommands→ReadingState private C++ call, three consumers of Revisions'
private selector header and three unresolved final weak runtime names. The prior
47 import candidates were classifier noise plus the one real call—not 47 proven
product violations. Original capture source `ffea3f173415a7c46afd6d69d09539e71b0648a1`
and every failed audit remain unchanged evidence.

Feature branch: `codex/reader-public-boundary-v1-20261028`.

## Exact source scope

17 module-owner paths (three new files, fourteen modifications):

- `apps/reader/revisions/{CMakeLists.txt,EXReaderRevisionsConfig.cmake.in,include/reader_selector_bytes_v1.h,src/selector_bytes_v1.cpp}`
- `apps/reader/reading-state/{CMakeLists.txt,EXReaderReadingStateConfig.cmake.in,include/reader_reading_state_retained_raw_v1.h,src/reading_state.cpp}`
- `apps/reader/reading-commands/{CMakeLists.txt,EXReaderReadingCommandsConfig.cmake.in,src/reading_commands.cpp}`
- `apps/reader/annotation-import/{CMakeLists.txt,EXReaderAnnotationImportConfig.cmake.in,src/annotation_import.cpp}`
- `apps/reader/annotation-export/{CMakeLists.txt,EXReaderAnnotationExportConfig.cmake.in,src/annotation_export.cpp}`

Seven added validation paths:

- `tests/reader_public_boundary_v1_20261028/{CMakeLists.txt,codec_v1.c,retained_v1.cpp,run.py,test_contract.py}`
- `.github/workflows/reader-public-boundary-v1-20261028.yml`
- this document.

The new guard requires this exact 24-path name/status set relative to the base,
freezes every other file and records source/run/attempt plus per-file SHA-256.
No generated helper source hides a source-scope expansion.

## Public interface contract and compatibility

Revisions raw package remains 0.4.0, ReadingState and existing raw consumers remain
0.2.0; all legacy versions remain unchanged. New additive capabilities have public
API version 1.0.0 and `_v1` names. Availability is checked by exact header version,
exported static target capability, installed canonical archive/header/config origin and
current raw family—not inferred from package version alone. The new public guard
requires one comment-stripped literal version definition and one literal
capability `=1`; commented-good/real-bad versions and conflicting definitions fail.
This is not a general C preprocessor evaluator.

`reader_revision_selector_encode_v1` / `reader_revision_selector_decode_v1` live
in the existing Revisions archive. They retain the same owner-private codec
internally; no copied implementation, new archive or second SQLite. The C ABI uses
caller buffers, exact lengths, no implicit NUL, overflow checks, size query,
no partial output on error and exception containment. Input NULL/count zero is
empty; positive count with NULL is invalid. Wire callers still preserve absent/
NULL versus present-empty. Decode retains canonical Base64, strict UTF-8 including
embedded NUL, 64-KiB exact-selector and original context byte/scalar ceilings.
Allocation and unexpected C++ exceptions are tested inside the new test process,
not by replacing SDK/VFS return values.

`reader_rs_encode_retained_raw_v1` is public in the existing ReadingState codec
archive whenever the existing raw switch is selected. API revision v1 is separate
from raw-v3 store identity and permitted anchor wire versions 1/2/fixed-page 3.
It clears failure outputs and delegates the same encode core without inserting
history/outbox/revisions. ReadingCommands retains its own provenance/head checks;
its handwritten private declaration and private call are removed.

Apple's existing PURE_CAPTURE setting remains OFF. Linux/Windows/Android retain
ON. No platform switches/defaults change. Existing optional pure API and legacy
entries remain untouched. The private selector detail header stays in its owner
source but is no longer installed; fresh prefixes and an explicit stale-header
negative prevent accidental acceptance of leftover old installed headers.

## Execution and unchanged original assertions

The workflow keeps original producer budgets: Linux150, Windows100, Android210,
Apple F06 110 minutes. It reuses the current SDK342 adapters, not older F06 defaults
that selected3.41. Linux retains its original raw/legacy build, navigation, folder,
owner-fault and GUI steps. Windows retains the original F06 builder and original
26 checks; only verbose commands and Ninja response-file retention are added.
Android retains API26 x86_64/C++ static native build and API34 emulator installation.
Apple retains original raw/wave3/page-theme flags, separately launches macOS,
iPhone and iPad entries, and executes the probes in fresh iPhone/iPad simulators.
No physical-device claim is made.

New C/C++ probes exercise installed public targets, buffer/query/error/overflow,
allocator/exception containment, actual SDK TXT/PDF/EPUB captures, real NUL bytes,
repeated spine indices, v1/v2 byte parity, fixed-v3, invalid calls, raw-store refusal,
no history/outbox writes and existing optional pure-entry equivalence.

Original selector consumer sources and unchanged protocol/graph assertions run on
all six entries. Original C06 consumer sources, legacy-OFF and raw-ON legacy output
parity, and unchanged `raw_phase` assertions cover export/import preview/commit,
NULL/empty/NUL, wrong entries, corruption, cancellation, budgets and zero-write
failures. Their historical source/build orchestrators and baseline-archive/Mac-record
orchestration do not run; those exclusions are named, not patched into passing
results. Old consumer warning profiles are preserved; strict warning flags apply
only to the two new probes. Device transport changes only invocation/file transfer,
never old assertions. Test-data transfer is an exact snapshot replacement with
complete hash/file/directory inventories, including deletions; merge-back copying
cannot hide missing keep-files or stale WAL/SHM files.

Named source-guard exclusions are GTK342 guard, Android342 guard, original F06 guard,
selector-bytes main source/build orchestration and C06 guards/main historical
orchestration. The new exact authorized scope guard replaces only these conflicting
source admission routes. Frozen old files and behavioral assertions are not edited,
weakened or represented as wholly rerun historical workflows.

## Evidence and acceptance boundary

Capture retains actual installed SDK/module prefixes, headers/exports/archive bytes,
full final host/package/unpack entries, original F06 reports, compiler objects,
Ninja commands/dependency groups and response files, Make dependency/link files,
maps, source/run identity, raw native symbol tables and logs. For each repaired
consumer TU it binds the exact source dependency group to an object selected by
the actual archive command, then proves the built archive byte-identical to the
installed owner. Ninja declared dependency counts and complete Make rule structure
are checked; missing, truncated, stale, ambiguous and wrong-source groups fail.
Every inspected archive is bound to the actual configured imported target TARGET_FILE and its unique install manifest, not an unused same-prefix filename. The actual public include path must be installed under the expected prefix, and
the private detail header must be absent. Native archive symbols must show exactly
the named public definitions and client imports; the old private C++ entry is absent.

The independent Actions authenticator pins same run/attempt/SHA/workflow/jobs and
artifact ID/size/digest, verifies every inventory file and nested F06 archive,
inner/outer manifest/checksum list, every delivered/unpacked file and actual entry
identity. It requires exactly six nonempty retained-wire names per entry and
cross-platform equality of those actual captured bytes. It never executes a
retrieved package. Partial captures and failed producer jobs cannot authenticate.

`named_six_boundary_accepted` means these four named installed-module boundaries
and their behavioral compatibility were measured. **It is not full F07.** This
package does not replace the complete final-image provider/runtime audits; those
must consume the newly retained same-source evidence separately. The unrelated
Android OPDS/hash private edge, OriginalImport→OriginalExport private `.inc` source
copy lead, final weak/runtime imports and complete six-platform provider closure
remain separate blockers/gaps. `f07_accepted` and `full_six_f07_accepted` remain false.
