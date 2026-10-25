# Native GTK folder batch import

## Reboot checkpoint — 2026-10-25 00:36 UTC

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

Validation is pending. The new workflow builds from installed packages, reruns
the original nine-format batch consumers and review regressions, exercises the
real GTK chooser/receipt dialog, and preserves prior installed/host suites.
The two frozen-SDK whole-page light/dark palette failures remain required
failures and are not granted acceptance. Overall `accepted=false`.

The exact run, tested source, receipts and artifact identity will be recorded in
[the validation record](validation/reader-gtk-batch-import.json) after Actions.
