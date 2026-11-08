# Four-PR integration, 2026-11-08

Branch: `codex/integration-20261108`. Base: `e324059c7ae669f5aab98f91d41cb0877381d80c`.
Merge order: #91 → #92 → #93 → #94, with a separate merge commit and validation before proceeding.

## Build and comparison baseline

The existing `cjk-justify-20261106/build` belongs to a different source tree. This integration configures a new MinGW/Ninja Release build in this worktree's `build/`, using the existing dependency source directories. JNI, ICC, AVIF, TIFF, WebP, MP3 and PDF crypto are disabled, as in that existing build. Audio, library, PDF, PDF editing, JPX, text index, tools and tests are enabled. `CMAKE_PROJECT_EXReader_INCLUDE` enables all Windows selection test groups.

The same-source main baseline passes **212/212 ctests**, and the host self-test passes **26/26**. `tools/regress/run_realbooks.py`, `tools/regress/corpus.json`, `tools/regress/layout.json` and the same `Reader.otf` are used for every comparison: **19 books, 11,403 pages, 8,648,640 glyphs**. Per-page RGBA SHA-256, page counts and glyph counts are compared against this main baseline. Each stage rebuilds the integrated engine and compiles the Windows host with MinGW `-O2 -Wall -Wextra -Werror`.

Evidence: [`evidence/integration-20261108/`](evidence/integration-20261108/). Each stage retains full ctest output, registered test names, host build/check commands, the 26-check report, search acceptance, compressed per-page book results, comparison JSON and source/binary hashes.

## #91 — styles and footnotes

Source: `codex/style-footnotes-20261108`, `ec67487380b11a9aeec75d34c8283ff734512b4d`.

| Conflicted file | Resolution |
| --- | --- |
| `examples/reader.c` | Keep shelf and gesture includes alongside footnotes; retain style configuration, persistence and driver/message dispatch. |
| `examples/windows/check_shell_selection.c` | Include and dispatch both shelf and style checks. |
| `examples/windows/selection_tests.cmake` | Retain all existing groups and add `style`; the engine's four new style/footnote groups also remain. |
| `examples/windows/shell_d2d.cpp` | Keep the centered shelf-era book title and all eight style labels; move the tap-region label below the presets. |
| `examples/windows/shell_selection.inc` | Footnote and annotation clicks share the `!shell_drag_begin` guard, preserving text drag selection. |
| `examples/windows/shell_settings.inc` | Keep eight fields, presets, reset, theme and both tap-region buttons. Assign style IDs 1800–1842 because the shelf uses 180–182; the original overlap misrouted the font-size plus button to tap settings. |
| `examples/windows/shell_tokens.h` | Preserve all tokens. Resolve `SHELL_PANEL_H` to 636 DIP to accommodate styles and tap controls; preserve the incoming 12–32 font range and default 18. |

Additional integration fixes: the gesture handler checks footnotes before page-turn zones, and a page click that dismisses a popup is consumed instead of also turning the page. Returning to the shelf closes a footnote only after progress saving succeeds. Geometry helpers initialize the new style member, and the standalone geometry check links the SDK it now uses. The existing `check_shell_epub` compared normalized text to an unnormalized literal; it now checks exact before/after source text and the corresponding ideographic-prefix class, retaining the original layout assertions.

The top bar remains **shelf (←) · title · search · contents · settings**.

The style acceptance scenario no longer presses Esc before creating its first selection: an empty-selection Esc now correctly returns to the shelf under #89. All range, annotation, geometry and popup assertions remain in place.

Validation: **217/217 ctests**, MinGW host and installed-SDK host builds, all shell checks and **26/26 host self-tests**. Search: six scenarios pass. Real books: **19/19, 11,403 pages, zero page/glyph/hash changes**. Native style acceptance: 24 field changes, two persisted presets, 30/30 popup clicks with unchanged pages, three annotations retained across 18→24→18 and extreme-margin/front-contents checks. The annotation scenario uses long text lines so drags exceed the existing 4-DIP gesture threshold.

## #92 — metadata, series, tags and statistics

Source: `codex/shelf-metadata-20261108`, `7f56f8e2cee0354bb74affa21b8c7e07e7f9de64`.

| Conflicted file | Resolution |
| --- | --- |
| `examples/reader.c` | Keep footnotes, shelf, gestures, style driver and metadata driver together. Keep shelf anchor restoration and add metadata/statistics landing hooks; dispatch both timers. |
| `examples/windows/check_shell_selection.c` | Keep shelf/style checks and add shelf metadata checks. |
| `examples/windows/selection_tests.cmake` | Preserve every group and append `shelfmeta`. |
| `examples/windows/shell_screen.inc` | Keep the original back/search/contents/settings controls and the centered title. Remove the incoming temporary reading-toolbar shelf button; metadata refresh remains. |

The #89 recent-books page remains the default shelf. It gains **series/tags** and **reading statistics** buttons, metadata editing in the book context menu, and override title/author/cover rendering. The incoming grid/list/filter/statistics renderer is a child view of that shelf. Opening a book or returning to reading uses `shelf_open_index`; leaving reading uses `shelf_return`, including successful saves and content-anchor restoration. Original OPF authors and covers remain the fallback when no override exists.

Styles and metadata share the profile's `shelf.json` (or the explicit `EXREADER_SHELF_PATH` override). Each writer reads the current file and preserves keys it does not own; metadata accepts an existing settings-only file. The metadata check now exercises both write orders, preserved unknown keys, and stopped reading time during shelf/exit states. Reflow updates progress without incrementing page turns or resetting the idle timer.

Validation: **218/218 ctests**, MinGW host build, all shell checks and **26/26 self-tests**; six search scenarios pass. **19/19 books, 11,403 pages, zero page/glyph/hash changes**. Full metadata UI acceptance passes (edits, covers, series, tags, statistics, restart, rollback and idle accounting). Full shelf UI acceptance passes (30 region taps, 20 swipes, 10 drag selections, vertical navigation, restart/book-switch anchor restoration and saving an unsaved note on exit). The swipe test now permits a next-spine transition to page zero and checks that backward swipes exactly reverse the complete content/raster path.
