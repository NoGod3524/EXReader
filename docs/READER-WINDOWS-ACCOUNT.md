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
"save to system secure storage" checkbox (ticked by default; unticking keeps the
secret *for this app session only*), and Apply / Sync / Cancel / Retry / Forget / Close. Control IDs follow the original
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

## Package verification

`.github/workflows/reader-windows-account.yml` runs on `windows-2022` and first
proves the exact source: `HEAD == GITHUB_SHA`, `f43baf9` is an ancestor, the
protected SDK tree, product SQL and the shared `apps/reader/desktop/CMakeLists.txt`
are byte-identical to their fixed points, and every changed path is inside this
package. It builds the product provider, the installed SDK, `extras/sideload`,
`extras/credentials`, and the `commands`, `desktop-metadata`, `sync`, `session`
and `revisions` modules, then builds the real Win32 host from `examples/reader.c`
through the independent `apps/reader/windows-account/CMakeLists.txt` (static
product package, EXE and link map).

Retained baselines re-run on this same source and artifact:

| step | checks |
| --- | --- |
| original evidence rejection + static SDK provider refusals | `account-negative/checks.json` (>= 26) |
| original Windows UI and eight bound screenshots | 158 / 158, 0 failed |
| original product checks | 10 |
| original worker checks | 5 |
| original 2202-book bookshelf UI | 13 |
| retained typed metadata edit and recovery | 18 |

The account checker (`tests/reader_windows_account/check_account_ui.py`) drives
the packaged `EXReader.exe` only through real control messages (`BM_CLICK`,
`WM_SETTEXT`, `WM_GETTEXT`, list-control messages, `WM_CLOSE`) against one
temporary HTTPS WebDAV server, six independent product profiles for the account
round and two more on a second account root for the reading captures. Each line
below is a recorded named check in `account-ui/account-ui.json`:

1. `default_shelf_has_one_secondary_account_entry_and_no_resident_account_controls`
2. `four_original_formats_are_imported_through_the_native_import_control`
3. `typed_metadata_edit_creates_the_remote_title_author_and_favorite_to_preserve`
4. `account_dialog_opens_from_the_real_button_with_sync_disabled_until_credentials_exist`
5. `non_https_account_root_is_refused_before_anything_is_bound_or_saved`
6. `credentials_are_saved_in_windows_credential_manager_and_binding_stores_only_uuid_and_root`
7. `a_different_account_root_is_refused_for_a_bound_library`
8. `whole_local_library_originals_are_staged_exactly_and_published_after_source_release`
9. `four_format_originals_and_metadata_revisions_reach_native_https_with_session_authorization`
10. `session_only_credentials_are_used_without_writing_secure_or_plain_storage`
11. `cloud_only_books_are_imported_from_verified_private_files_and_mapped_to_a_second_sdk_library`
12. `remote_title_author_and_favorite_survive_import_and_mapping`
13. `cloud_only_books_open_and_render_on_the_receiving_device`
14. `hand_authored_reading_wire_round_trips_to_the_second_device_byte_exactly`
    (renamed: this line proves exact transport of hand-authored reading wire. The
    previous name claimed real SDK captures; runs up to `40082869006` reported it
    under that name and that record stays in the artifacts)
15. `remote_progress_arrives_and_metadata_applies_while_the_active_reading_page_is_not_moved`
16. `exit_and_reopen_loads_saved_credentials_and_a_repeat_scan_adds_no_duplicates`
17. `forget_removes_the_credential_manager_record_and_disables_scanning`
18. `fault_round_1_network_interruption_fails_visibly_and_explicit_retry_completes`
19. `network_cancel_is_visible_and_retry_resumes_to_completion`
20. `fault_round_2_mapping_failure_after_import_is_reported_and_repaired_without_reimport`
21. `fault_round_3_closing_during_a_native_scan_waits_for_closed_then_exits_cleanly`
22. `reopened_library_resumes_after_closing_mid_scan`
23. `independent_account_root_sees_none_of_the_other_accounts_books`
24. `no_plaintext_credential_survives_any_product_shutdown`
25. `installed_native_consumer_captures_all_eighteen_cases_from_the_four_real_originals`
26. `eighteen_real_captures_cross_the_real_host_https_as_exact_anchor_v2_bytes`
27. `seventeen_real_captures_resolve_found_and_the_planted_ambiguity_stays_ambiguous`
28. `product_owned_annotations_leave_zero_sdk_note_copies_on_both_hosts`
29. `reopened_receiver_repeats_the_same_eighteen_resolutions_and_wire_hashes`
30. `planted_concurrent_pending_and_tombstone_heads_stay_explicit_without_projection`
31. `conflicted_local_original_still_reads_offline_with_unchanged_heads_and_no_page_jump`
32. `link_graph_contains_native_session_credentials_sideload_and_winhttp_without_webview`

Check 24 walks every byte under every profile twice. While the hosts run it may
skip only files a live owner holds with share mode 0 (the bound session's own
`<product>.sync-account`, plus `.lock`, `-journal`, `-wal` and `-shm`); once every
product has exited it re-reads exactly those files and re-walks every profile with
no exemption at all, looking for the username, the password, the exact
`Authorization` value, its base64 form and the password's hex form.

The strict summary job (`tests/reader_windows_account/verify_summary.py`)
re-downloads the uploaded ZIP, recomputes its SHA-256 against both the upload
step output and the API digest, and requires every retained and account report to
be bound to this source, run and attempt.



### Real reading captures (checks 25-31)

`tests/reader_windows_account/consumer/probe.cpp` is a separate installed native
consumer. It links only installed packages (`EXReaderReadingState`, the product
catalog and the revisions module) and it never reads SDK tables: every selector
comes from a public capture call on a real document, every receiver state from a
public resolve call.

* Cases are the unchanged `tests/reader_reading_v2` definition: four real
  originals (`book.txt`, `book.epub`, `pages.pdf`, `pages.cbz` from
  `tests/reader_reading_state/make_fixtures.py`, digests re-checked against
  `manifest.json` in the checker) and eighteen captures.
* Capture runs on the host's own library and product store while that host is
  closed: `exr_library_document` + `exr_anchor_create` for TXT, the bounded
  publication + pager for EPUB parts, `exr_library_fixed` +
  `exr_fixed_anchor_create` for PDF/CBZ. Offsets are located by searching the
  real text, never guessed. The two whole-book EPUB reflow cases use a scratch
  library built from the host's own verified original, because a host stores EPUB
  originals bounded (chapter-local) by design.
* Each live capture is encoded by `reader_rs_encode_v2` (anchor v2, chapter scope
  and spine index preserved) and committed by the product revisions module; the
  real Win32 host then publishes all eighteen over its own native HTTPS WebDAV
  session, and a second real host receives them.
* On the receiver the same consumer calls `reader_rs_decode` on the retained
  bytes and the public `reader_rs_resolve_reflow` / `reader_rs_epub_record_part`
  + `reader_rs_resolve_epub` / `reader_rs_resolve_fixed` path. Result: seventeen
  FOUND with exact start/end, one AMBIGUOUS (`txt-ambiguous`), zero mislocated.
* Product-owned annotations leave zero SDK note copies on both hosts, and a
  reopened receiver repeats the same eighteen states and wire digests.

Checks 30-31 plant the three explicit head states directly in the receiver's own
product store and then drive the real sync: a book with two competing metadata
heads, a book revision whose parent never arrives, and a tombstone over a
previously projected cloud-only book.
### Accepted run

Source `dde92e8990ec14888b2f500d6000db596f03c601`, run `40089084258`, attempt 1,
job `120857884310`: every step above succeeded, all 32 named account checks
passed, and the strict summary job `120859348468` accepted the artefact with no
problems.

* artefact `reader-windows-account-40089084258-1`, id `12558044881`,
  44,066,535 bytes, SHA-256
  `2adb9134b9e704ed23c059b0f0a0e7b50d84cb198422c45fd567651f242e9e3d`
  (identical in the API, the upload step output and the ZIP re-hashed inside
  Actions), expires 2027-01-22T11:14:16Z.
* summary artefact `reader-windows-account-summary-40089084258-1`, id
  `12558770821`, 786 bytes, SHA-256
  `a8a1cfd6341397a40f4ff4e1dfd165fd3d8a42b1638a7c7c20e2cdfc74badcbb`.
* counts: original UI 158/158, product 10, worker 5, bookshelf 13, metadata 18,
  evidence rejections >= 26, account 32.
* capture consumer identity in the same run: reading-state `0.1.0`, SDK
  `3.40.0`, parser version `exreader-sdk-3.40.0`; receiver `17 FOUND,
  1 AMBIGUOUS, 0 mislocated`.
* the packaged EXE digest is `program_sha256` in `account-ui/account-ui.json`
  and the capture consumer plus its link map are
  `build/account-capture/reading-capture-probe.exe` and
  `.../reading-capture-link.map` inside that artefact.

Earlier failures on this branch are kept, not rewritten: run `40080415165`
(the credential scan read the session's share-mode-0 manifest as a leak), run
`40081525331` (the mapping-repair round opened a row by its pre-rename title),
run `40082268762` (the summary compared a `sha256:` prefixed API digest with the
bare upload value), run `40085544703` (the reopened reading host had no
session-only credential to scan with), run `40086502382` (the reading revisions
were counted in the wrong account root) and run `40087140475` / `40088432339`
(the planted parents were head objects, and a shared parent stops being a head).
## Not covered by this package

Mirrored in `docs/validation/reader-windows-account.json` and never a claim for
these items:

* Windows Credential Manager `UNAVAILABLE`: the runner always has a working vault,
  so only the session-only branch is exercised.
* Screen-reader narration of the new window.
* `CONCURRENT`, pending-parent and tombstone heads are planted directly in the
  receiver product store. The host's counters, the absence of projection and the
  untouched heads are real UI and product observations, but no second remote peer
  produced that branch over the wire, and no clock-, merge- or restore-policy
  case is claimed.
* Cancel during receive/import; cancel is exercised during the network scan.
* A real remote HTTPS collection: the run uses loopback TLS with a runner-local
  test CA that is removed afterwards.
* Reading captures for a *bounded* EPUB part beyond anchor (0,0): the eighteen
  cases use the specified fixture selectors, not arbitrary in-chapter positions.
* Product performance and any unified six-target product claim.

