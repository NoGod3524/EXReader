# Windows account, sync and receive controls

The Win32 product host (`examples/reader.c`) gains an optional account feature
behind `EXR_READER_WINDOWS_ACCOUNT`. It reuses only installed public modules:
`reader_session_*`, `exr_credentials_*`, `exr_sideload_*`, the product
`reader_catalog_*` keyset pages and `reader_revision_entities_page` /
`reader_revision_book_title` / `reader_revision_project`. It does not read SDK or
product SQL, add a server, WebView or script UI, or change the frozen SDK
(`9854061be331fe603a1822d9b2b36ee357154927`), product schema 1 or any wire format.

The shared `apps/reader/desktop/CMakeLists.txt` is untouched. The independent
`apps/reader/windows-account/CMakeLists.txt` compiles the same `examples/reader.c`
against the installed SDK and installed product, credentials, sync, session and
sideload packages.

## Entry point and default shelf

The default shelf has no resident account panel. The only addition is one small
**账号** button on the second control row (and `Ctrl+Shift+A`). It opens a modal
**账号与同步** window with server address, username, masked password, a
"save to system secure storage" checkbox (unchecked means *this app session only*),
and Apply / Sync / Cancel / Retry / Forget / Close. Control IDs follow the original
metadata editor IDs (137–149), so original IDs 100–136 are unchanged.

## Credentials and binding

* The address must be an HTTPS collection root ending in `/`. `account.ini` stores
  only `[account]` `id` (lowercase UUID) and the exact `root`; it is created once,
  never replaced, and the session module independently binds the product database
  to the same pair. A different account or root is refused before any network I/O.
* With the checkbox on, the username/password record goes to Windows Credential
  Manager (`org.exreader.reader.webdav` + library UUID). If it reports
  `UNAVAILABLE` nothing is written; the dialog says so and asks the user to untick
  the checkbox, which keeps the secret **only for this session**. No plaintext
  credential, Authorization value or password is written to any file.
* Forget clears the in-memory secret and requests deletion of the system record.
  A restart loads the saved record (password stays hidden) so Sync is available
  without retyping it.

## Preparation, network and close

1. **Preparation** runs as serialized host jobs, one local book per job, so the
   window and Cancel stay responsive. The catalog is read with
   `reader_catalog_local_page` (50 rows per keyset page; no OFFSET and no
   whole-library list). Each original is identified through the public SDK source,
   bootstrapped into history when needed, exported with
   `exr_sideload_export_original` (64 KiB copy blocks, 128 MiB ceiling) to an
   immutable `<sha256>.<format>` private file, and re-hashed. The SDK source is
   released before the next step; no network starts until staging is finished.
2. **Network** is the native `reader_session`: its own worker thread, cancel, resume
   from the last good cursor on Retry, and a fresh scan after a new connection.
   The UI thread only observes `IDLE/RUNNING/CANCELLING/CANCELLED/FINISHED/FAILED/
   CLOSING/CLOSED` by timer and never waits for the network.
3. **Receive** (after `FINISHED`) walks the `book`, `shelf`, `tag`, `series` and
   `membership` entities in 50-entity pages. Only a `SAFE` non-deleted head is
   projected (`reader_revision_project` with the host's NFC sort title).
   `CONCURRENT`, `PENDING_PARENTS`, blocked-restore and tombstones are counted and
   shown; none is auto-selected, resurrected or hidden. Progress and annotation
   history is retained and never applied here, so the page a user is reading is
   never moved by remote data.
4. **Import**: each cloud-only catalog row whose verified original is in the private
   download cache is hashed again, imported with `exr_sideload_import_file` under
   the remote title, and mapped with `reader_catalog_sdk_attach`, which preserves
   the projected title, author and favorite. A committed SDK import is always
   mapped even if Cancel arrives. A failed mapping is reported as "mapping pending";
   the host then runs the existing repair job, and the shelf *refresh* button or a
   restart repairs it without re-importing.
5. **Close**: `WM_CLOSE` cancels work, requests session closure and keeps pumping
   until the session reports `CLOSED`, destroys it, then finishes the normal close
   barrier. Closing the dialog only cancels; the handle stays for Retry.

## Not covered by this package

Listed in `docs/validation/reader-windows-account.json`; nothing here is a claim
for those items.
