# Optional local font library (D02)

Standalone static C ABI package, version 0.1.0, default **OFF**. Fixed host start
`a826a65c9c66e43620eff61b49cb79f941a3c953`; SDK **3.40.0 / ABI 1** at
`9854061be331fe603a1822d9b2b36ee357154927`. There is no production host wiring,
font chooser, system font registration, second parser, synchronization entity,
private SQL, fallback change, or layout-engine modification.

## Installation / consumer

Run only in GitHub Actions for this work package:

```sh
cmake --preset reading-core
cmake --build --preset reading-core
cmake --install build/reading-core
cmake -S apps/reader/font-library -B build/font-package \
  -DREADER_FONT_LIBRARY_BUILD=ON \
  -DCMAKE_PREFIX_PATH="$PWD/build/reading-core/stage" \
  -DCMAKE_INSTALL_PREFIX="$PWD/build/font-stage"
cmake --build build/font-package
cmake --install build/font-package
```

Consumers use `find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)`
and link `EXReaderFontLibrary::reader_font_library`. Include only the installed
`reader_font_library.h`; see the installed C and C++ consumer sources under
`tests/reader_font_library/consumer`. No top-level/default product target changes.

```c
rfl_library *library = NULL;
rfl_record record = {0};
int created = 0;
rfl_lease *lease = NULL;
exr_font *borrowed = NULL;
/* Error handling omitted here; every status must be checked by the host. */
rfl_open(private_absolute_directory, NULL, &library, &error);
rfl_import_file(library, selected_absolute_file, "My selected font", NULL,
                &record, &created, &error);
rfl_font_open(library, record.hash, 0, &lease, &error);
rfl_lease_font(lease, &borrowed, &error);
/* Use borrowed with SDK glyph/shape/layout APIs, without concurrent calls. */
/* Destroy all layouts/pagers referencing it first. Never exr_font_free(borrowed). */
rfl_lease_release(lease, &error);
rfl_close(library, &error);
```

## Concrete contract

- The host creates and secures an existing absolute, normalized, private
  directory. Relative paths, invalid UTF-8, symbolic-link path components,
  Windows reparse points/junctions, device/alternate-stream paths and nonregular
  input files are rejected. File handles are checked **after opening**. Input
  files are never renamed, deleted or written. Paths are limited to 4096 UTF-8
  bytes; display names are 1–255 strict UTF-8 bytes, exclude control characters
  and slash/backslash, and are not used as paths.
- Internal names are lowercase SHA-256 of actual copied bytes plus `.font`.
  The hash is verified on reopen and each font open. Duplicate bytes return
  `created=0` and preserve the first display name. Records are sorted by hash;
  lookup/index failures clear outputs instead of returning partial records.
- Default font/entry/directory limits: **16 MiB / 64 / 128 MiB**. Hard maxima:
  **64 MiB / 256 / 512 MiB**. At most **32 live leases / 128 MiB encoded font
  bytes**. Custom lower budgets are supported. The copy and hash buffers are
  individually 64 KiB; no whole-font module heap buffer is created. Mapping is
  used only to supply the real installed `exr_font_create` API. **That SDK copies
  the entire encoded font and allocates decoded/cache state**: total peak memory
  is NOT 64 KiB, nor are SDK caches covered by the encoded-byte lease budget.
- File imports keep a native read handle, check size/identity/modification
  metadata around reads, reject extra bytes beyond declared size, and reread
  the selected bytes for the same SHA-256. A callback source follows the same
  immutable seekable contract and second-pass validation. Short reads are
  retried, zero before declared EOF is rejected, EOF must report zero even when
  probed with capacity one. An adversarial provider that lies consistently is
  outside this borrowed-source contract; no claim of a filesystem snapshot.
- A copied temporary file is fully hashed, synced, mapped and validated through
  `exr_font_create` before publication. Import validates face 0; a TTC remains
  one content-hash record/file. `rfl_font_open(hash, face_index)` delegates an
  explicit caller-selected face **0..65535** to SDK validation. It does not
  enumerate faces. An invalid face returns `FONT`; encoded named-instance
  selection above 65535 is `UNSUPPORTED`. No all-faces-import claim.
- Each library and lease is affine to its opening thread. Calls from other
  threads return `THREAD`; callbacks reentering a live operation return `BUSY`.
  Callbacks execute synchronously on that thread and must not throw. Internal
  C++ exceptions are caught at every C ABI boundary. Callers serialize lifetime
  changes; calling an already-freed pointer remains invalid C usage.
- Leases own SDK handles. Borrowed font pointers remain valid until explicit
  lease release. `remove` and `close` return `BUSY` while a relevant lease exists.
  The host must destroy SDK layout/pager objects before releasing their lease.
  Separate SDK shape/layout/render operations on one font are not concurrent.
- Progress stages `copy`, `verify`, `validated`, `file-published`, `committed`
  are public synchronous observations. Nonzero cancels before manifest commit;
  retry is allowed after cancellation. `committed` is notification only: its
  return value/exception cannot undo a successful commit. Callbacks are not
  internal test switches and cannot alter OS or SDK results.

## Local storage, commit, recovery

Only an independent versioned **local** manifest is maintained. `manifest.rfl`
starts `RFL1\n`, followed by sorted canonical `hash byte-count hex-UTF8-name`
records. It is strictly bounded (160 KiB), parsed without product-schema access,
and written through a same-directory exclusive temporary file. The initializer
marker distinguishes a missing manifest from a new empty directory.

A native exclusive directory lock (`flock` / `LockFileEx`) is held for the whole
library lifetime and is released by process termination. The host must not
mutate the directory externally or delete the lock file while owners run.
Windows directory/file handles deny deletion while open. This is cooperative
single-writer private-directory storage, not a sandbox against same-account
malicious filesystem actors.

Import order: bounded copy → verification → SDK validation → file sync →
exclusive hash-name publication → directory sync (POSIX) → temporary manifest
sync → same-directory atomic manifest replacement → directory sync (POSIX).
The manifest is authoritative. Publication conflicts never overwrite existing
font bytes. Before commit, errors/cancellation clean temporary/new files and
preserve the prior manifest. If a process dies before manifest replacement,
reopen removes orphan hash-named files and temporary files after verifying the
manifest and orphan content hashes. After replacement, reopen sees the new set.
Unrecognized/nonmatching orphan files cause corruption errors rather than being
silently deleted. Missing listed fonts, missing initialized manifests, corrupt
records, and unknown versions are distinct failures. No user original is ever
part of recovery cleanup.

Removal first atomically commits the manifest without that font, then unlinks
its managed file. After-commit sync/unlink errors return `COMMIT_UNCERTAIN`,
poison mutation/query use until close/reopen, and do **not** pretend the old set
was restored. Precommit failures do not change the previous set. POSIX uses
`fsync` for files/directories; Windows uses `FlushFileBuffers` and
`MoveFileExW(MOVEFILE_WRITE_THROUGH)` on the same volume. **Process termination is
tested; sudden power loss, filesystem/controller durability and network shares
are not accepted capabilities.** Local disk and host-controlled private access
are required. Lock files and initializer markers are not deleted on close.

## Validation and provenance

`reader-font-library.yml` builds/installs the frozen SDK, verifies its installed
font header, installs this optional package, then separately compiles and runs
real C and C++ consumers on Ubuntu 22.04, Windows 2022 and macOS 15. The consumers
exercise SDK glyph lookup, shaping and layout. No source-relative SDK includes,
private parser APIs or generated pass stubs are used. Build logs, link map,
original binaries, installed static module, selected input bytes and license
bytes are preserved even on failure.

Fixed font sources: Adobe Source Serif release 4.005R, commit
`2823e993c53fca27c5c8749f529b56a5a7c77b6b`, `TTF/SourceSerif4-Regular.ttf`,
`OTF/SourceSerif4-Regular.otf`, `LICENSE.md` (SIL Open Font License 1.1). Their
exact Git blob identities and lengths are pinned in `run.py` and verified in
Actions before use; SHA-256 is recorded from actual received bytes. A two-face
TTC is generated **only in Actions** with pinned fonttools 4.58.0 from two copies
of that unmodified licensed TTF. This fixture tool is not a product parser or
runtime dependency. Corrupt/truncated fixtures are Actions-only derivatives.

Named expected cases are fixed in `cases.py`, including actual killed child
processes before/after manifest commit, cross-process locks, owner/thread and
lease lifetime, bounded sources, Unicode, directory limits, cancellation retry,
manifest classification and real native write/publication failures. POSIX uses
`RLIMIT_FSIZE`; Windows denies manifest replacement with a real sharing lock.
These are observed filesystem failures, not mocked successful capabilities.

The strict same-run verifier authenticates completed successful jobs with the
same source/run/attempt, unique artifact IDs/names, expiry, nonempty sizes, API
SHA-256 against downloaded ZIP bytes, unique ZIP members and JSON keys, exact
case sets, original module/source/binary/link-map/input/license identities, and
30 named negative verifier mutations. Artifacts are downloaded/parsed only in
Actions. No local build, test, syntax check, fixture creation or artifact parsing
is authorized. Actual run identities are added only after real terminal runs.
