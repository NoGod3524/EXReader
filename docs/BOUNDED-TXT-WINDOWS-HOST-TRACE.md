# Windows bounded TXT host integration: starting point

This is a staged integration, not a host acceptance. The SDK scanner/pager and
product-original checks are component evidence only. The Windows host still
uses the existing SDK library path for TXT; no product-owned TXT is exposed by
this change.

The picker in `examples/reader.c` calls `import_path` and submits `JOB_IMPORT`.
`job_import` streams EPUB into the SDK but reads other formats, including TXT,
into memory and calls `exr_library_import_unique`. The product attach job maps
an SDK book into the product catalog. Startup schedules `JOB_PRODUCT_REPAIR`
on the host worker; that job opens and closes its own product catalog
connection. The shelf query uses `reader_catalog_local_page` and
`product_page_row` discards rows without an SDK ID. Group views likewise use
local SDK mappings. An original-only row therefore cannot currently be selected
or opened.

`JOB_OPEN` looks up an SDK book ID and chooses fixed, resident, or bounded EPUB
storage. The bounded branch opens a publication and restores EPUB progress;
its render, navigation, search, annotation and record paths make publication
or EPUB location assumptions. `JOB_SAVE` persists SDK or product reading
records for that existing identity. Restart repairs SDK mappings and restores
those existing reading records; it does not recover product original staging
or restore a bounded TXT anchor. Product-original verification and the TXT
pager alone do not change any of these host paths.

A complete integration must establish an exclusively managed private original
root and call recovery on the catalog owner before allowing imports; connect
picker cancellation, duplicate and failure handling to that owner; make ready
originals selectable without inventing SDK IDs; authenticate the original on
reopen and keep its source immutable for the pager lifetime; persist and
resolve a TXT-specific position across process restarts; and explicitly
refuse unsupported search, notes and bookmarks in the native UI. It must also
handle layout changes, deletion, worker cancellation and failures without
regressing existing SDK books or the frozen SDK release. Existing EPUB paths
cannot be reused as TXT feature implementations.

The candidate-branch `sdk-bounded-txt-windows-host` workflow runs the existing
installed Windows host build, original compact UI checks, bulk checks, owner
recovery checks and network/peer checks on this source, retaining their output.
It is a baseline, not a replacement for the original workflows or their source
guards, and does not test the large TXT host path. Acceptance still requires a
real native host Actions driver on the original 16,792,975-byte fixture: picker
import, page turns, close and restart at a saved position, duplicate and
interrupted recovery, plus existing-book compatibility, with evidence retained.
