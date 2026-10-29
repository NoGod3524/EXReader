# Android F07 retrospective original-capture audit

Source-only proposal; independent review and Actions validation are pending.
No product build, install, launch or local artifact processing is performed by
this audit. It preserves successful capture run 40773048325/1 unchanged.

## Exact evidence and allowed source scope

- Audited product source: `ffdb3e5a84dbc05159c8f1982160dc39dff0f951`.
- Original capture: [40773048325/1](https://github.com/NoGod3524/EXReader/actions/runs/40773048325).
- Capture upload `12853023869`, 187,948,355 bytes,
  SHA256 `3f47dd3a2a5d5549f1636b8393929fb8ae769c01635c662936618b007cdad4d1`.
- F06 upload `12854136422`, 19,702,592 bytes,
  SHA256 `61b2de12f916f39cacd690852cb4b91130952fea6b14cdd3d2bc6e18494a88cb`.
- Actual installed original APK:
  `c4f681aade60a4b1621153a65bbd2e6a7c2bf3f00436c5f130f49ec4762968eb`.
- New branch `codex/android-f07-audit-20261028`; only new
  `tests/reader_android_f07_audit_20261028/`, this document and
  `.github/workflows/android-f07-audit-20261028.yml` may differ from the capture
  source. Original producer/collector, SDK, owners, old tests and budgets remain
  untouched. The new audit has its own 45-minute ceiling, not a finish ETA.

## Independent replay

Actions authenticates original run/attempt/SHA/workflow/branch and successful
producer job; original upload metadata and downloaded ZIP bytes; safe nested
extraction and every retained raw file hash. It independently matches the separate
F06 upload, all payload checksums, actual installed/pulled/final APK bytes and
original F06 launch evidence. New native inspection uses the exact original NDK
27.0.12077973 inspector hashes, not artifact-supplied executables or commands.
No downloaded native payload is launched. Every APK library must match all
allocated sections and PT_LOAD virtual layout of an actual retained raw link
output; an unexplained SDK install transformation stays blocked.

## Substantive boundaries, not a producer-boolean pass

Installed CMake exports own each product archive. Each exact module install
manifest assigns installed headers and package files. Public C declarations are
derived from those headers, never borrowed from an entire shared include prefix.
Dependencies come from actual exported target links. Same-package implementation
archives may resolve their own helpers; another installed package may not borrow
them unless an actual public declaration and allowed defining owner exist.
Every undefined symbol, including weak and non-prefixed/C++ names, must resolve
to that public boundary or an exact independently observed symbol in the pinned
NDK system stubs/actual authenticated external inputs. Unknowns fail closed.
There is no OPDS-wide or application-private-prefix exemption.

The source review already identifies potential real blockers to be measured:
Android sync calls `opds_sha_*` from the separately owned Revisions hash archive,
whose implementation header is not public. Also
`reader_selector_bytes_detail.h` explicitly labels itself private C++
implementation while installed; cross-package source includes are reported
separately. Installation or absence of an undefined symbol does not turn that
header into a public API. Such findings must remain visible, not waived to green.
The same frozen source also directly redeclares and calls the private C++
`reader_rs_encode_retained_raw_v3` helper from ReadingCommands across the
ReadingState package boundary; it is absent from installed public headers.
Linux's independent audit observed that native import. Android's equivalent
candidate source path is enabled, but its actual archive result remains unrun.

All packaged images, including full unstripped map-bound host/product tables,
are checked for duplicate SDK/public SQLite implementations. The APK SONAME/
NEEDED graph must resolve only to exact bundled images or pinned API26 system
libraries. Product SQLite must have one actual definition, be hidden dynamically,
have no SDK-private SQLite, and map to the exact installed ProductCatalog SQLite
archive, not a matching basename elsewhere. Native/link/ownership evidence and
all substantive findings are retained even when the final audit fails.

## Scope of any eventual result

This is a **retrospective static audit of the original API34 x86_64 debug APK**,
with its existing same-source install/launch evidence; it is not a fresh runtime
or device test. `android_static_closure_accepted` may become true only after these
checks pass. `full_six_platform_f07_accepted` is always false here. Independent
Windows/Linux/Apple results, same-final-source composition, full behavior, physical
devices and release remain separate. A substantive private-entry failure requires
an authorized product fix and fresh product evidence, not changing this audit's
public boundary. No formal 108-item count is incremented by this packet.

## Superseding source review while publication is held

The initial reviewed tree `e3583b9b22c3b298575862f534f82f8fc73a4b36` was created
remotely, but its remote commit action was denied at 2026-10-28 22:08 UTC. No
Android audit branch or Actions run was created. That denied payload is preserved
unchanged in its original worktree; this separate source revision supersedes it
and remains unexecuted and unpublished pending new authority and peer review.

The revision accepts indentation on generated CMake property closing lines,
without weakening export/owner/archive equality. This addresses a likely parser
defect exposed by independent Linux audit run `40777704309/1`, not an already
observed Android artifact result. Exact parsed exports and missing/extra archive
sets persist before assertion. Complete installed include-file coverage must
equal uniquely manifest-owned headers; an unowned inline or unsupported-suffix
include cannot silently evade the private-header check. Exact missing/extra
coverage persists before rejection. New protocol fixtures cover indented and
incomplete CMake blocks, missing/extra header ownership, and unknown suffixes.
Public declarations now use conservative C syntax rather than a guessed name
prefix list, retaining actual installed `rfl_*` and `roe_*` APIs while excluding
static/inline implementation declarations and callback typedefs. SDK functions
must carry the actual `EXR_API` declaration; all public imports still require one
actual defining reachable package owner. Corresponding negative fixtures are
authored, not locally executed. Inline function-body calls and C/C++ control
statements cannot grant public declaration authority; pointer-return declarations
and `extern "C"` public wrappers remain supported. Balanced function/aggregate
bodies and non-linkage quoted content are excluded, so a function-local extern
declaration or text example cannot become a public import authority.
All tests and artifact/native processing remain Actions-only and have not run.

## First actual audit and bounded retained-failure diagnosis

Following renewed exact publication approval, reviewed source
`9ee16b298f89e2a1aff613df7b7076bcbd28250f` ran
[40780887828/1](https://github.com/NoGod3524/EXReader/actions/runs/40780887828).
All 20 protocol tests passed. Exact original upload/F06/APK and raw ELF replay
completed (`original_capture_replayed=true`). Native audit stopped at the pinned
NDK `system-008` inspection before any installed-module verdict. Original failed
artifact `12856916312`, 207019263 bytes, SHA256
`e78cc22ad3f6b810c038fb22877e880090deb5ca128d37c20b140303f3628325`
is preserved. Its exact command/stdout/stderr must be recovered in Actions before
an evidence-based parser repair; no cause is assumed from the label alone.

The `[android-f07-diagnostic]` commit marker skips NDK installation and full
native audit. After source guard and all protocol tests, a bounded helper
authenticates that original failed upload and reads only the failed system-tool
record/output; it neither executes retained commands nor reexports the old ZIP.
The old failure remains a failure, not a new semantic acceptance.

Known include-coverage limitation: the original collector retained Ninja commands
and compdb but not compiler depfiles, `.ninja_deps`, or `ninja -t deps`. A module
root glob is not actual compiled source/dependency completeness. In particular,
ProductCatalog compiles out-of-root `apps/reader/original-import/original_import.cpp`,
which includes OriginalExport's private `src/sha256.inc` inside an anonymous
namespace. This source-backed cross-package implementation lead is not an
artifact-proven import. Exact compiled-input/include-owner coverage and missing
compiler dependency evidence remain explicit separate blockers to full F07.
# Exact NDK-input follow-up (diagnostic only)

Run [40783606650](https://github.com/NoGod3524/EXReader/actions/runs/40783606650)
passed 26 controls and original artifact replay, then refused the NDK metadata
schema before native module verdicts. The [official generator](https://android.googlesource.com/platform/ndk/+/2b394f4ddaa03f89e7f123c0fdb827d974ce7a12/ndk/checkbuild.py)
serializes API directory names as decimal strings. The narrow correction
accepts only canonical positive decimal strings or positive integers, still
rejecting booleans, signs, whitespace, zero, leading zeroes and nonnumeric
values. Exact installed metadata bytes/hash are now retained before parsing.
No metadata value changes a stub's ELF requirement or actual DT_NEEDED scope.

Pinned-input probe [40782970059](https://github.com/NoGod3524/EXReader/actions/runs/40782970059)
passed all 22 controls and confirmed the exact 19 script bytes with the prior
failed-input digest. Its selected `libc++_shared.so` candidate was ELF, 1617608
bytes, SHA256 `936e1150309bdae86216f14e493f478d39e588095f1577105856da6d0f24f149`.
This is current pinned-toolchain evidence, not an original application provider.

The subsequent narrow parser uses `meta/system_libs.json`, as documented by
the [official r27 guide](https://android.googlesource.com/platform/ndk/+/ndk-r27-release/docs/BuildSystemMaintainers.md),
to identify real OS stubs. Supported `INPUT(-lname...)` scripts resolve only
through exact API26 then target-triple directories; unsupported directives,
paths, symlinks, cycles and missing targets fail closed. The one observed
`libc++.so` and its target must match their pinned hashes. Its filename and
resolved target are not added to runtime providers or system symbol allowances.
Actual APK DT_NEEDED closure and original inspector hashes remain unchanged.
Four additional Actions-only controls cover script syntax, path/cycle/alias
refusal, exact target search and non-promotion of linker scripts to providers.

The incomplete compiler-dependency capture now explicitly prevents even the
Android static-closure flag from becoming true; native symbol findings are
reported separately. Module-root source scans still miss out-of-root compiled
inputs such as ProductCatalog's original-import source and its source-declared
OriginalExport `sha256.inc` dependency. Complete compiler dependency evidence
requires a purposeful additive producer capture, not a source-scan waiver.

The preserved audit failed on API26 `libc++.so`, not a project archive.
Diagnostic run [40782004065](https://github.com/NoGod3524/EXReader/actions/runs/40782004065)
authenticated the prior failure and its input SHA256
`f5e33f488b74ee4efb1b398bbb72e0c14b9006f9c0e6db62c5c967e1e9336955`.
The [official NDK generator](https://android.googlesource.com/platform/ndk/+/d7c0ef0df49e73d47dcbc62ee6b0081cd2e7efb1/ndk/checkbuild.py)
creates API-specific `libc++.so` as `INPUT(-lc++_shared)`, rather than an ELF.
This source-backed hypothesis is not yet an observation of the pinned input.
The `[android-f07-ndk-probe]` push therefore installs only pinned NDK 27,
requires the exact previously observed failed-input digest, retains its bytes
and the fixed candidate target's identity/magic, and runs no native tool,
SDK build or original artifact replay. It cannot grant acceptance. A later
reviewed parser must resolve supported script inputs exactly and fail on
unknown, escaping or cyclic inputs, without granting a script filename
dynamic-provider status or allowing unrelated NDK symbols.

