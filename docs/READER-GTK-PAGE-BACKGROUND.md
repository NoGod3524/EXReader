# GTK page-background candidate

Implementation is prepared; no GTK page-palette scope is granted until the
candidate's actual Actions run and raw evidence authentication finish. This
separate branch starts at common source `687def68862649479ce536d619c7b37ba2d2cc4b`.
The completed SDK 3.40 drop/paste delivery and its two palette failures remain
unchanged.

SDK candidate `b911815e26a10e7c45f50f56bf7c4e46cbca010b` adds the public
`exr_render_page_background` API, SDK 3.41.0 / core 3.40.0 / ABI 1. Its Linux
foundation run `40164920053` passed the original 164 native tests, 535 installed
candidate assertions and a separately rebuilt frozen pixel oracle. That is SDK
foundation evidence, not GTK host or whole-SDK acceptance.

The host keeps default `EXR_SDK_VERSION=3.40.0` and
`EXR_READER_PAGE_BACKGROUND=OFF`. Explicitly selecting 3.41.0 and enabling this
flag selects the new path. The SDK-owned trees are pinned unchanged to the SDK
candidate; shared package version selection comes from root's separate delivery.

The existing settings values cross the private worker queue by value. A private
system-theme snapshot now accompanies them and rolls back with the settings if
an operation fails. Pager CSS selects the effective light/dark foreground. The
single reflow render point supplies the selected RGBA canvas to the public API.
Authored paints and images retain SDK ordering and colors. Fixed PDF/CBZ rendering
keeps its existing white background and zoom path. No rendered pixels are
recolored or replaced.

A real system-theme notification updates the interface and schedules one
non-persistent settings operation after dialogs, other owners, reading work and
saves finish. Closing cancels the scheduled work; an operation failure is shown
without automatic retry. A notification cannot close a search or import dialog.

The candidate copies the **complete original 35-check settings suite** into a
separate test path. The old test and original batch/drop checkers are unchanged.
Only these expectations change with the explicitly selected SDK capability:

| Existing assertion | Frozen 3.40 evidence | New 3.41 candidate expectation |
| --- | --- | --- |
| Light foreground and background | Background failed on white canvas | Selected foreground and whole-page background |
| Dark foreground and background | Reading-page palette failed | Selected dark foreground and whole-page background |
| Real system-theme notification | Interface changes while page deliberately stays Light | Both interface and reading-page palette follow the effective theme |

All other geometry, controls, focus, gestures, zoom, persistence, save-failure,
recovery and shutdown assertions remain. Six additional real bounded-EPUB checks
cover the canvas margin, retained book/part/anchor/font, original image color
quadrants including white pixels, authored white paint outside the image,
unchanged image samples after a palette switch, and the next chapter's canvas.
The original source files remain byte-identical.

The candidate workflow retains every prior non-palette host suite and authenticates
their exact source, attempt, binary and raw reports with a new candidate summary.
It runs the unchanged original batch checker in its existing bounded-import-only
mode, then separately verifies records, navigation, search, accounts, original UI,
fixed pages, shelves, metadata, collections and fault regressions. Legacy schema
fields are never invented: missing self-reported attempt/hash fields are bound
externally through the finished producer job and authenticated ZIP. Actual SDK
identity comes from the packaged binary and exact installed candidate headers.
Native screenshot hashes and the authored image input are authenticated too.

See [the validation record](validation/reader-gtk-page-background.json). Builds,
tests, syntax checks, fixtures and artifact processing run only in Actions.

