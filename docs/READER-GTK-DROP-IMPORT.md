# GTK book file drop and explicit paste

Implementation and tests are in development; no cloud result is granted yet.
The independent branch starts at common source `e4356a6e13223469fdf3b2f3d5171a6e99ab10a6`
and normally merges reviewed J03 HEAD `5988ee7fed3cfbf823f0ff55ffc1906a5166d145`
and batch owner fix `2df6040666635bcd7b0349b035b8f4885757fdd0`.
SDK remains `9854061be331fe603a1822d9b2b36ee357154927`, 3.40.0 / ABI 1.
Schema, wire, anchors and performance budgets are unchanged.

`EXR_READER_GTK_DROP_IMPORT=ON` requires the existing GTK batch importer and an
installed `EXReaderDesktopDrop 0.1.0` at `READER_DESKTOP_DROP_PREFIX`. Default is
off. The bookshelf scroll area accepts real GTK file drops. The existing Import
sources menu adds only **Paste book files**; ordinary Ctrl+V in text controls
keeps its existing meaning.

Native handlers copy at most 1 MiB of `text/uri-list` or
`x-special/gnome-copied-files` bytes into one job. Clipboard requests are
asynchronous, fall back from URI-list to GNOME files, and are cancellable with
Escape. A late response cannot restart a cancelled or closed request. At most
one native clipboard request remains in flight; the UI stays available while
its owner responds. No clipboard is cleared or taken and a `cut` payload never
deletes the original. Native drops finish as COPY, never MOVE.

J03 parsing and its filesystem `stat` calls run on the existing SDK worker,
not the GTK callback. Its immutable request holds at most 256 distinct entries;
repeated paths and overflow have separate counts. Only regular-file entries go
through the unchanged F4 per-item importer, including its no-follow reopen,
private stable copy, byte limits and exact content deduplication. A prior J03
classification is never trusted as a replacement for that validation. Directory,
remote, promised, missing and malformed entries produce bounded refusal receipts;
directories are never implicitly scanned. Existing Import folder remains explicit.

This reuses the serial batch owner, at most 32 candidate/receipt rows, accepted
reading frame barrier, product mapping repair and CLOSE transaction. A drop or
paste does not navigate automatically. Cancellation stops later uncommitted
items, committed originals survive and reopen never resumes the raw file request.
Accepted payload and request limits are not a claim about total process RSS or
memory allocated by the operating system while delivering a native selection.

The Actions workflow builds from installed SDK/packages, exercises a real native
source window with pointer DND and real clipboard ownership, and reads originals
back through the public SDK and product mapping API. It retains original batch,
records, navigation, search, settings, account, 2202-book shelf and targeted
accessibility checks. The two whole-page palette failures remain failures.
The final job authenticates the exact attempt, ZIP bytes and every bound report;
it never converts a retained failure into an overall pass.

See [the validation record](validation/reader-gtk-drop-import.json) for actual
source/run/artifact identities once cloud execution completes. No local builds,
tests, syntax checks or artifact processing are performed.
