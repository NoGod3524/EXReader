# Windows cloud import and bulk organization (T01)

## Source and status

Fixed host start: `e4356a6e13223469fdf3b2f3d5171a6e99ab10a6`.
Ordinary merges preserve J01 `0d07d23bf53cd288de7a0af152d48553c18be241` and
J10 `757249aaed9a1dc6be981354f6af97e813233f04`; their complete package trees remain unchanged.
This implementation is **not accepted until the dedicated Actions run and strict summary pass**.
No local build, test, syntax check, fixture processing, server or artifact inspection is permitted.

## Native interface

The original default controls and list behavior remain unchanged. Right-click
Import (or press Ctrl+Shift+I) to browse the configured account. Right-click the
bookshelf / Details (or Ctrl+Shift+O) to expand the native multiple-selection
bookshelf. Ctrl/Shift select 1–100 visible books. The expanded list is a stable
snapshot of the existing bounded shelf (up to 150 rows); no unseen book is selected.

Cloud listing is Depth:1 over the existing account's HTTPS-only WebDAV client.
Directory and book selection are explicit; opening the picker never downloads.
Network jobs carry no SDK handle. A private J01 staging owner crosses to a new
serialized SDK job, and the existing public original-to-product mapping barrier
follows commit. Exact duplicates preserve the original and product metadata.
Committed, created, HTTP failure, cancellation and cleanup states remain distinct.
The append-only private receipt sidecar contains no credentials or remote titles.
A refused J01 discard retains the actual opaque owner and blocks new downloads.
An exclusive staging owner file prevents concurrent profile cleanup. After a
process death, orphan cleanup is explicit, nonrecursive, restricted to the
private generated staging names, and refuses links/directories.

Bulk actions are explicit favorite set/clear and add/remove existing shelf, tag
or series. Existing shelves support child navigation and keyset pagination.
Selected legacy books bootstrap only after public retained-original verification.
All J10 calls use the same product database and the existing metadata pending
path, on the owning serialized worker. Each item has its own transaction;
committed/created/conflict/not-run/replayed and original revision IDs are visible.
The durable J10 journal is inspected on reopen, never auto-submitted. Resume
uses the original request; acknowledgement removes only a completed journal.
A committed item remains committed if pending cleanup fails.

The owner window is modally disabled including its native accessibility state.
Dialog generation checks prevent a close/reopen from accepting a previous
listing or starting a late import. Close cancels only uncommitted work; running
workers finish ownership and receipt handling before their dialog is destroyed.

## Evidence contract

`reader-windows-import-organize.yml` builds one installed dependency graph and
one production host with search, navigation, reading records and T01 enabled.
It runs unchanged J01/J10 independent installed consumers, new real native UI
and independent public SDK original readback, then the retained F1 264, F2 130,
NavUI 31, records 32, original UI158, product, worker, 2202-book shelf, metadata,
account and accessibility suites. Existing test files and strict verifiers are
not edited. The dedicated verifier first calls the complete original strict
records→navigation→search chain, then binds the T01/module reports and link map
to the same source/run/attempt, completed successful job and uploaded binary.
It re-downloads the unique artifact in Actions, checks API/upload digest, ZIP
SHA/size, expiry, duplicate members, exact named reports and tampering refusals.

## Remaining acceptance scope

A Windows runner UI pass grants only the tested native desktop flows. It is not
screen-reader, performance, physical-device, real-provider or complete-product
acceptance. The T01 UI suite includes production-process termination with completed and
pre-commit retained requests, exact original-revision replay, and post-commit
pending cleanup refusal. External SQLite RESERVED locks hold the real apply
boundary; Windows file-sharing denial prevents pending deletion without changing
the host binary. For cloud cleanup, a paused real HTTPS GET and suspended UI
thread separate network publication from SDK import. A readonly published staging
file exercises success, corruption, cancellation, and process-death recovery.
These cases are not accepted merely because their source exists: the exact final
production binary and Actions results must authenticate each named case. The
unchanged J01/J10 regressions remain separate, additional module evidence.
