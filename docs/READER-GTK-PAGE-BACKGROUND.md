# GTK page-background candidate

The Linux GTK SDK 3.41 candidate scope passed its full producer run and strict
raw-evidence authentication. Tested source is
`2cac2ac942d9ffe507a5482f890f93199f7b8f52`, run
[`40166893729`](https://github.com/NoGod3524/EXReader/actions/runs/40166893729),
attempt 1. Both producer `121089690838` and strict job `121094341719` succeeded.
This separate branch starts at common source `687def68862649479ce536d619c7b37ba2d2cc4b`.
The completed SDK 3.40 drop/paste delivery and its two palette failures remain
unchanged.

SDK candidate `edddc463c06ed5731195cdb8f06b2df6dff7699e` adds the public
`exr_render_page_background` API, SDK 3.41.0 / core 3.40.0 / ABI 1. Producer run
`40165924012` passed Linux, Windows and macOS consumers: each ran the original
164 native tests, 580 installed candidate assertions and 165 separately rebuilt
frozen assertions over 12 cases. Its original ZIPs were authenticated by validator
source `4a5a793ebe2a98a96ed119334399821e923c19ab`, run `40166642441`, without
reexecuting those programs. That is SDK API/frozen-oracle evidence, not GTK host
or whole-SDK acceptance. Shared version support `f680aeaddfb1ecc67ead353554f5b91a5703f72f`
passed both exact SDK configurations and mixed-SDK rejection in run `40166479919`.

The host keeps default `EXR_SDK_VERSION=3.40.0` and
`EXR_READER_PAGE_BACKGROUND=OFF`. Explicitly selecting 3.41.0 and enabling this
flag selects the new path. The SDK-owned trees are pinned unchanged to the SDK
candidate; shared package version selection comes from root's separate delivery.

The existing settings values cross the private worker queue by value. A private
system-theme snapshot now accompanies them and rolls back with the settings if
an operation fails. Pager CSS selects the effective light/dark foreground. The
single reflow render point supplies the selected RGBA canvas to the public API.
Authored backgrounds and images retain SDK ordering and colors. The foreground
keeps GTK/F3's existing explicit `*{color:... !important;}` user override. With
F3 enabled, its default Light foreground is also supplied before a settings file
exists; without F3/appearance enabled, book colors are left to the SDK. This
candidate does not silently change that existing default behavior.
Fixed PDF/CBZ rendering
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
Old 3.40 saved-reading-state migration is not granted by this page-color package.

The actual native program SHA-256 is
`a9ef741747927b4baf9b73cbedb6ff1513fce1ebc241d38189fb0388d4b4a7bd`.
The original settings report is `preferences-ui/result.json`, SHA-256
`1830fdcbb031a493866358b6ce435c0b738b2a0967c94fdfbb00dcb62674bd91`.
Its complete 41 original check objects, including observations, are copied from
the cloud log into the validation record. No check was dropped or renamed.

| Actual scope | Passed |
| --- | --- |
| Original versioned settings / additional bounded EPUB pixels | 35/35, 6/6 |
| Native file drop/paste / backend / J03 portable and GTK | 20/20, 23/23, 52/52, 28/28 |
| Folder UI / original F4 / F4 review / backend | 27/27, 668/668, 4/4, 684/684 |
| Allocation ownership | 4 scenarios, 3 actual allocation failures |
| Records / navigation / search / accounts | 30/30, 29/29, 30/30, 46/46 |
| Original UI / product / fixed pages / metadata / collections / fault regressions | 20/20, 5/5, 24/24, 15/15, 27/27, 4/4 |
| 2202-book shelf / targeted AT-SPI | 14/14, 10/10 |

On a 520×640 page, both Light and Dark tests found 9,992 selected-foreground
pixels and 299,606 selected-background pixels; outer pixels matched the selected
canvas. Real portal changes switched the page and interface. The bounded EPUB
kept its four original image samples (white/red/blue/green) through both palettes;
44,538 white pixels remained outside the image in its authored white background.
Book/part/anchor/font and original bytes remained unchanged, and the next chapter
used the selected canvas too. These counts are functional observations, not a
performance or corpus baseline.

The strict job rehashed the actual ZIP, program, all bound reports and native
PNGs, including 10 distinct referenced screenshot hashes, and rejected 15 protocol
mutations. The producer summary SHA-256 is
`9a0252d5783086a4ab0f61f4f87eee95588294656bbf197d2c18feadc8512503`.
Original ZIP artifact `12589751026` is 60,725,172 bytes,
`sha256:51c4822f4f2c2af4e181c3369f78b74c358177bc4799bf527a51f2f4039bfffd`.
Summary ZIP artifact `12588894157` is 2,692 bytes,
`sha256:1ae850e562c7545633dadaa7fe117e7e42829288e96c8daabafb69faa64ff02f`.
Both expire at `2027-01-23T05:49:07Z`.

This grants only the tested Linux 3.41 candidate scope. It does not transfer the
new palette result to the frozen 3.40 common line, change its recorded failures,
or grant full product, SDK-wide, other-host, performance, physical-device, Orca
or old-record migration acceptance.

See [the validation record](validation/reader-gtk-page-background.json). Builds,
tests, syntax checks, fixtures and artifact processing run only in Actions.

