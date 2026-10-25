# Native GTK folder batch import

## Current cloud result

Tested source `8e883e5ca19a3611eb38230b414e8f6cc0f1ba33`, run
[40155787513](https://github.com/NoGod3524/EXReader/actions/runs/40155787513),
attempt 1, job `121056796996`, completed with overall **failure**. The new
folder-import scope passed: native UI **27/27**, backend **684** checks, original
installed F4 consumer **668/668**, and fixed module review **4/4**. The strict
same-source checker authenticated those reports and the retained records UI
**30/30**, then correctly refused the incomplete retained Navigation suite.
Its output has `batch_import_scope_passed=true`, `ok=false`, `accepted=false`.

The native flat scan imported 37 candidates as 35 additions, one exact duplicate
and one damaged EPUB failure, using at most 32 receipts and zero pending mapping.
Cancellation, graceful close, actual source readback and reopen checks passed.
The orphan-frame regression retained accepted Font26 after dropping Font28 and
proved real NEXT/PREVIOUS page transitions. The binary SHA-256 is
`072ac73aa5fefc241cad4d92533a1af66df01705866102c96d4ce65cf1cfd09a`.

Retained Navigation failed at its fourth attempt to observe an active 9000-row
scan before parent close: the actual scan had already completed (`phase=3`,
`polls=40`). Retained Search failed when the fourth result's pointer click did
not advance the action count. Both are preserved as failures; Search geometry
still requires Actions-only inspection of the original failure tree. Settings
remained exactly 33/35, with the two existing whole-page palette failures.
All other steps, including Account and the original 2202-book shelf suites,
completed successfully. No complete retained-suite or overall acceptance is
granted from this run.

Artifact `12585101839`, `reader-gtk-batch-import-40155787513-1`, is 55,357,250
bytes, SHA-256 `87b235ecc6660c6e4e3c5cad756193315d67f8d7d3df39317593af46cfac05b2`,
expires `2027-01-23T02:47:24Z`. Source reports and original logs remain inside;
no artifact was downloaded or parsed locally.

The previous source `b9d793f8b1a5512cea3fbfcf84f4519f84bc9ac9`, run
`40153960628`, had passed the same 27 native and 684 backend checks, plus the
retained Navigation/Search suites. Its strict checker wrongly required every
legacy F4 check name to be unique. The unchanged legacy consumer exports both
receipts of one duplicate book, intentionally repeating precisely three names
twice. The current checker permits only that exact paired ID/path pattern;
eight Actions-only positive/negative protocol cases passed. Previous evidence
is not transferred to the current source.

Root owns the shared Navigation/Search driver repair and the next common-source
integration. This package does not change either protected test directory.

## Historical reboot checkpoint — 2026-10-25 00:36 UTC

Branch `codex/reader-gtk-batch-import-ui` has implementation head
`0c302a4774ba693c261e786ac627bbfa0ddf4eb9`, verified equal to origin before
this checkpoint's evidence-only documentation commit. Host, probes and workflow
changes are committed; the new orphan-frame fix is included.

Full cold run [40147055374](https://github.com/NoGod3524/EXReader/actions/runs/40147055374),
attempt 1, job `121030532723`, is still in progress on that exact source. The
observed step is installation/checking of the unchanged Search package. The
new orphan-frame backend regression and full native UI27 have not executed yet
in this run at the checkpoint. No cloud run is restarted for the computer reboot.

The prior full run [40146396866](https://github.com/NoGod3524/EXReader/actions/runs/40146396866)
on `70ecc1f4` has a failed folder UI step; its actual failure detail still needs
to be read after reboot. Earlier completed sources passed 673 host backend
checks, but that count does not include the newest orphan-frame test. The native
chooser diagnostic `40146055189` passed its eight scoped checks with 80 extra
parent directories and real offscreen cell focus, then 37 candidates produced
35 additions, one duplicate and one damaged-file failure. That diagnostic used
the verified older `cac48f05` program, separately identifies its test source,
and remains `accepted=false`.

`accepted=false`, `batch_import_scope_passed=false` and native UI27 acceptance
remain unchanged. Both real page-palette failures remain failures. No native
page-palette implementation has started. After reboot, read the previous UI
traceback and latest full run, then finish all declared host and retained checks
on one final source. All execution and artifact processing remain on Actions.

The optional GTK folder importer uses the installed `EXReaderBatchImport 0.1.0`
package over the unchanged SDK 3.40.0 / ABI 1. Its fixed implementation tree is
`40ccc040a65970df056dfb635f247517f8c382df`, with sideload tree
`40a8fcfdd70807f4d1ac4d8fd099f74d715ca40f`, as present at
`ba25961961ae69222bfed4f7a98cb02bb1dc6847`.

Enable `EXR_READER_GTK_BATCH_IMPORT=ON` and supply the installed package prefix
in `READER_BATCH_IMPORT_PREFIX`. The default host configuration is unchanged.
The existing Import F1 button still chooses one file. Its adjacent import menu
offers File and Folder; Folder uses the GTK native directory chooser with
Include subfolders explicitly off by default. Progress and results appear in a
temporary modeless dialog. The reader and bookshelf remain available.

## Owner and limits

The existing serial SDK worker owns enumeration, imports and catalog repair.
It imports one candidate per queue job, yielding between jobs. No thread pool,
schema, product SQL, SDK API or wire-format change is introduced. The worker
retains one module batch of at most 32 candidates and 32 receipts; the UI shows
only that latest group. Candidate paths remain subject to the fixed module's
published path and retained-memory limits. UI path labels show at most 100
Unicode scalars. The source is copied through the unchanged module into an
app-private 0700 temporary directory, removed when its owner closes.

Default enumeration bounds remain depth 8 (when explicitly recursive), 4096
directories, 4096 candidates, 4096 path bytes and 1 MiB retained enumeration
paths. `complete` only describes the module's normal scan end. `truncated`
reports omitted/limited/unreadable entries. The module offers no skipped-entry
count, so neither the UI nor this host invents one. The total remains unknown
while enumeration continues. Nonregular files, linked roots, file symlinks and
linked parent paths remain subject to the corrected module's rejection rules.

Folder cancellation uses its own request identity, independent of transient
reading generations. A committed SDK result always remains committed. Cancel,
dialog close and application close stop future imports and reconcile already
committed IDs. Process restart repairs existing SDK-to-product mappings through
the established startup repair; it never silently resumes a folder scan.

## Existing reading and product transactions

A displayed page must finish its normal COMMIT before another import can
invalidate borrowed SQLite sources. The worker yields while a frame is pending.
Only an explicit UI confirmation of no pending acceptance/save may release an
orphaned unaccepted frame left after cancelling a reading generation. The new
backend case verifies that the abandoned Font28 frame is not adopted and the
accepted Font26 remains the reading source.
Each actual item reuses `reader_import_suspend` / `reader_import_resume`, retains
the accepted old reading position, and does not navigate automatically to a new
book. Imports pause while other source-owning Search, Directory or Reading
records dialogs are open. Existing single-file import remains available.

SDK and product commits remain separate. The frozen public SDK exposes a
metadata listing, without a metadata-by-ID getter. Once per 32 items, or on
stop/close, the host takes one temporary public SDK book snapshot and feeds the
existing `reader_catalog_sdk_repair`. It immediately frees that snapshot; only
bounded receipts cross the queue. This temporary snapshot follows the SDK's
existing all-books API and is not claimed to have a constant library-size
memory cost. Each committed receipt separately reports whether its real product
mapping exists. Catalog failure retains the original SDK book and stops further
folder work; reopen retries the existing repair path. No filename is substituted
for actual embedded metadata or duplicate metadata.

## Cloud validation

The bounded batch scope above passed; complete retained-suite validation remains
pending. The workflow builds from installed packages, reruns
the original nine-format batch consumers and review regressions, exercises the
real GTK chooser/receipt dialog, and preserves prior installed/host suites.
The two frozen-SDK whole-page light/dark palette failures remain required
failures and are not granted acceptance. Overall `accepted=false`.

The exact run, tested source, receipts and artifact identity will be recorded in
[the validation record](validation/reader-gtk-batch-import.json) after Actions.
