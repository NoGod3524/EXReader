# EXReaderLocalDownloads 0.1.0

Optional C ABI package that removes **only the local original and the local SDK
mapping** of a downloaded book. The global product book, shelves/tags/series,
revision history, outbox and every remote object are never read or written, and
no deletion tombstone is created. It is not part of the default reading build;
it links only installed public packages (`EXReader` library, `EXReaderSideload`,
`EXReaderProductCatalog`) and reads no private SDK SQL.

Interface: `reader_local_downloads.h`, target `EXReaderLocalDownloads::reader_local_downloads`.

| Call | Purpose |
| --- | --- |
| `reader_ld_remove` | Remove the local copy of `format:sha256`. Cloud-only keys and repeated requests succeed with `already_cloud`. |
| `reader_ld_recover` | Finish or roll back the single pending intent. Idempotent. |
| `reader_ld_pending` | Read-only inspection of the intent; touches neither database. |
| `reader_ld_reimport` | Attach a downloaded file again; it must match the original format and SHA-256. |

## Calling contract

* Run on the thread that owns the `exr_library` and the `reader_catalog`.
* Release every `exr_source`/reader opened on the book and stop network tasks that
  touch the original **before** calling. Report anything still in use through
  `is_busy`; the call then returns `busy` and changes nothing. Deleting an SDK row
  permanently invalidates sources previously opened on it (SDK contract).
* A rejected or failed call leaves the SDK rows, the mapping and all metadata
  readable, so a source opened before a refused call stays valid.
* Use a state directory that only this module writes to. No thread or network is created.

## Durable intent

There is no cross-database transaction, so the module writes
`state_dir/intent.rdi` (temp file, flush, atomic replace, SHA-256 checked) and
advances it only after the previous step verifiably finished:

| Stage | Meaning | Recovery |
| --- | --- | --- |
| `begun` | request recorded, nothing destructive done | roll back (clear exports, drop intent) |
| `prepared` | identity proven by a verified export; byte-identical SDK copies and legacy data known | roll back while the mapping exists; if the mapping is already gone, roll forward |
| `unmapped` | local mapping removed, SDK rows still hold bytes | roll forward |
| `deleted` | verified SDK rows deleted | roll forward (remove export, intent) |

Every step is idempotent, so a kill between a step and its stage write is harmless.
A second removal or a re-import is refused with `pending` while an intent exists.

## Identity and duplicates

The mapped SDK row must have the key's format, and its exported original must have
exactly the key's size and SHA-256, or the call fails with `identity` and changes
nothing. Ordinary SDK imports may create several rows with identical bytes; every
row is accepted into the removal set only after its own size and SHA-256 match
(at most 8). Rows with the same title but other bytes are never touched. Before
each delete the row is verified again; a row that no longer matches is skipped
and counted in `copies_skipped`.

## Legacy SDK-only notes and progress

Notes and reading progress stored only in the SDK are never dropped silently, and
no product revision is assumed to cover them. The default policy `reject`
returns `legacy_data` (with note/progress counts) before any change. The
`backup` policy first writes a verified `exr_library_backup` copy
(`state_dir/legacy/<sha>-<n>.exrbackup`, never overwritten, never deleted by this
module; it holds the whole SDK library, so it can be large) and then removes the
original. If such data appears between a crash and recovery, recovery with
`reject` puts the mapping back (`restored`) and keeps every row.

## Re-download

`reader_ld_reimport` checks the file's size and SHA-256 against the key, imports
it with `exr_sideload_import_file`, and attaches it with the stored product
metadata, so the identity stays format + original SHA-256. A new SDK row ID is
normal; IDs are never wire identities.

## Validation

`.github/workflows/reader-local-downloads.yml` builds the frozen SDK, sideload
and catalog packages, installs this module, and judges it through independent C
and C++ consumers on Windows, Linux and macOS. The probe terminates itself with
`_exit` inside the durable-stage hook at each of `begun`, `prepared`, `unmapped`,
`deleted` and `cleaned`; fresh processes then reopen and recover. Python reads the
product database independently and compares reader tables, revisions, tombstones,
outbox and a simulated remote object tree before and after each case.
`docs/validation/reader-local-downloads.json` records only what a same
source/run/attempt actually granted; nothing here is granted until it says so.

Not covered: UI/host wiring (owned elsewhere), real devices, large-library
backup cost, PDF fixtures, and any sync protocol. The module designs none.
