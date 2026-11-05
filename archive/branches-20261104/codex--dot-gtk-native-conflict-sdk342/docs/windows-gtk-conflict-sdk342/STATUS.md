# Windows–GTK conflict recovery on frozen SDK 3.42

This independent source candidate composes base
`d81e0d6f8bc944baf5d7e1b5c47eb9acde3e980c` with exactly seven accepted
metadata/GTK product files from `0c737428c6a85869f5191a3ed64f9e54beb1138f`.
The three already-identical Windows accounts/wave3 files are not reapplied.
`src`, `include`, all `cmake`, and top-level `CMakeLists.txt` remain identical
to SDK anchor `8357eafa28423a7ab93ba08b823af80f01ad1505`.

## Admission and disclosure

Historical conflict run `40666624326` had 11 successful jobs on SDK 3.41.
It is retained as historical evidence only; it does not accept this composed
source. The new `windows-gtk-conflict-sdk342.yml` retains all 11 jobs, original
D23/conflict semantics, original current/legacy GTK checks, timeout budgets,
authenticated sequential HTTPS snapshots, native host interactions, and
artifact-chain assertions. The accepted chooser adapter and profile mode
restoration are preserved byte-for-byte with their disclosures.

C09 and the raw owner helper/probe originals remain byte-identical. They
contain three real 3.41 identity gates, so this package does **not** claim an
unmodified old invocation: it authenticates their exact Git blobs and SHA256,
then explicitly selects 3.42. The package-owned owner CMake/probe copies differ
only at the exact SDK identity sites (including the matching diagnostic).
The deliberately malformed `exreader-sdk-exreader-sdk-3.41.0` parser negative
case remains unchanged. The sole adapted `owner_run` condition is the expected
SDK string; original and transformed function hashes are authenticated. C09
command adaptation changes only exact `-DEXR_SDK_VERSION=3.41.0` arguments and
the one owner-probe source directory. No version value is spoofed, no original
assertion or fixture is weakened, and no check is skipped.

## Actual evidence required for acceptance

Each platform builds and runs a new public consumer of its actual installed
`EXReader 3.42.0 EXACT` package. It must report `exr_version() == 3.42.0` and
`exr_abi_version() == 1`. Reports retain compile/link/cache resolution evidence,
installed SDK/product/module file hashes, module source trees, actual prefixes,
native Windows self-tests / GTK version output, and packaged program hashes.
Windows uses raw0.2/revisions0.4 modules; GTK uses legacy0.1/revisions0.3.
Uniform SDK identity does not imply identical product ABI families or equal
architecture-specific binary hashes.

The final Actions-only audit binds both producers, C09, both retained GTK
suites, D23 and all conflict phases to one source SHA, run ID and attempt. It
checks the real exercised package programs and authenticates original artifact
IDs, sizes and SHA256 digests through the same-run GitHub API. Acceptance is
only the successful final new-SHA 11-job run and its `sdk342-result.json`.
No local build, test, syntax check, fixture generation or artifact parsing is
part of this package. Old failures and artifacts are never deleted or rewritten.

## Scope

Same-book metadata conflict resolution and tag delete/restore propagation.
Not book trash, not GTK-authored stale-preview/UI-resolution certification,
and not six-platform certification. The migration, aggregate, Apple, Android,
production records owners, original tests and common SDK/F06 workflows remain
outside this package. No main merge, PR, tag or release is authorized here.
