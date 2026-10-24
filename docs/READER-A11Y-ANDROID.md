# Android accessibility audit (device semantics, API 34)

Base `f43baf9182d75907c0cb5d6f77048f27bca8c950` (product candidate `codex/reader-reading-v2`). This package
adds an audit only: no production file, manifest, JNI, Gradle module or shared workflow changes, and the
audited application keeps its own identity.

**Two decisions are recorded separately and are not interchangeable.**

| decision | value for this source | meaning |
| --- | --- | --- |
| `audit_completed` | **true** | all 15 declared cases ran on API 34 against the installed host, and every raw hierarchy, parsed tree and screenshot the report names exists and matches |
| `accessibility_accepted` | **false** | four declared requirements failed with named findings and minimal patches; see below |

A completed audit is not an accessibility pass. Nothing here grants TalkBack speech on a physical device,
another API level, RTL or a colour-contrast verdict.

## What ran

| piece | identity |
| --- | --- |
| audited source | `2bdfee69f82b5607bd5d43db7f80ea817640c1d5` |
| run / attempt | `40082957400` / `1` (push, audit job `120840087102`, success) |
| artefact | id `12556261406`, `reader-a11y-android-40082957400-1`, 44,086,158 bytes, `sha256:5c723e84bc8790bc45c0d178f5f93ddddb9a5fb9e6308b072cc0349573f5baee`, not expired |
| artefact re-read | run `40083655133` downloaded that exact artefact on Actions; the recomputed digest matched |
| device | API 34, x86_64, `pixel_6` profile, `default` system image |
| instrumented process | `org.exreader.host.a11y.test` (a separate APK; the host is untouched) |
| installed host | read back from `pm path org.exreader.host`; byte-identical to the owner build record |

The host APK is built by its own owner build (`tools/build_android_host.py`), installed unchanged and only
observed. The audit APK contains no production code and is never linked into `org.exreader.host`.

## Method

`tests/reader_a11y_android/harness` is a standalone Gradle root that produces `org.exreader.host.a11y` and its
androidTest APK. `A11yAuditTest` drives the installed host through `am start`, real touch/key events and the
public accessibility tree (`AccessibilityNodeInfo`, UiAutomator, window hierarchy dumps). Per capture point it
retains:

* `trees/<name>.xml` - the raw UiAutomator window hierarchy;
* `trees/<name>.json` - the parsed node tree (name, class, text, description, hint, state description, live
  region, actions, bounds in px and dp, visibility, extras) plus the flat interactive-node list;
* `shots/<name>.png` - the screen.

No real account, private file or user document is touched: the imported book is the deterministic
`Sample.epub` fixture that `tools/build_android_host.py` generates, pushed to the emulator downloads folder
and picked through the system document picker.

### Cases

| case | captures | requirement |
| --- | --- | --- |
| `shelf_semantics` | 01 | shelf panel, title, import/refresh/more, search, status and list are present, named, reachable and inside the display; every control is at least 48 dp |
| `hidden_panels` | 02 | `notes_panel`, `reader_panel`, `loading_overlay` and `selection_bar` stay out of the tree while gone |
| `status_announcement` | 03 | a changed status text is announced (`live_region` polite or assertive) |
| `import_picker` | 04, 05 | the import entry opens the real system picker, the picker returns to the host and the imported book reaches the shelf |
| `shelf_row_and_search` | 06, 07 | a row exposes one name carrying title, format and size; the list exposes its rows; search filters them |
| `organize_panel` | 08 | every organizer control is named and at least 48 dp; no control is collapsed, off-screen or overlapped |
| `back_navigation` | 09, 10, 11 | Back closes the organizer, leaves the reader and returns to the shelf |
| `reader_line_nodes` | 12 | the reading surface exposes its text as per-line accessibility nodes and describes its position |
| `reader_page_turn` | 13 | a screen reader can change pages through advertised actions that actually work |
| `reader_toolbar_state` | 15 | the font controls carry the value they change |
| `annotate_flow` | 16, 17, 18, 19 | select mode, selection, the annotation dialog (title, labelled field, 48 dp buttons) and the updated count |
| `notes_panel` | 20, 21 | the annotation list shows the saved note and Back returns to the page |
| `rotation` | 22, 23 | the same book and a page stay open in landscape and nothing collapses or overlaps |
| `large_font` | 24, 25 | 200% font scale: shelf and reader stay complete, named and non-overlapping |
| `display_scaling` | 26 | 480 dpi display override: the shelf stays complete, named and non-overlapping |

## Results: 15 cases, 11 pass, 4 findings

```
shelf_semantics          pass    import_picker         pass    notes_panel      pass
hidden_panels            pass    shelf_row_and_search  pass    rotation         pass
annotate_flow            pass    back_navigation       pass    large_font       pass
reader_line_nodes        pass    display_scaling       pass
status_announcement      FAIL    organize_panel        FAIL
reader_page_turn         FAIL    reader_toolbar_state  FAIL
```

### Findings and minimal patches (owner files; not applied by this package)

1. **`status_not_announced`** - `03-shelf-status`: after Refresh the status text reads `Shelf refreshed` but its
   node reports `live_region = 0`, so a screen reader user gets no notice that the operation finished.
   *Patch*: `android:accessibilityLiveRegion="polite"` on `status_text` and `reader_status` in
   `examples/android/app/src/main/res/layout/activity_main.xml`.

2. **`page_turn_not_reachable_by_semantics`** - `13-reader-actions`: `reader_view` advertises no
   `ACTION_SCROLL_FORWARD`/`ACTION_SCROLL_BACKWARD`, and no Next/Previous control exists anywhere in the tree.
   The only page-turn path is a raw left/right tap zone, which a screen reader user cannot reach.
   *Patch*: in `ReaderView.onInitializeAccessibilityNodeInfo` add both scroll actions and route
   `performAccessibilityAction` to `listener.onTapZone(1)` / `onTapZone(-1)`; visible Next/Previous buttons
   work too.

3. **`control_state_not_exposed`** - `15-reader-toolbar`: `font_up` is named `Increase font size` and its
   `stateDescription` is empty, while the page shows `Size 24` on an unrelated label. The value the control
   changes is not part of the control (WCAG 4.1.2 name/role/value).
   *Patch*: set an accessibility delegate state description (API 30+) or include the current size in the content
   description of `font_up`/`font_down` in `MainActivity.applyPage`.

4. **`layout_integrity_08-organize`** - `08-organize`: the organizer is added on top of the shelf, and the shelf
   controls stay in the accessibility tree underneath it. The overlapping pairs recorded in that capture are
   `Close~import_button Up~import_button Up~refresh_button Kind~refresh_button Kind~more_button
   Removed~more_button New~import_button New~shelf_search Books~import_button Books~refresh_button
   Books~shelf_search Add book~refresh_button Add book~more_button Add book~shelf_search
   Saved intent~more_button Saved intent~shelf_search Previous~book_list Next~book_list Refresh~book_list
   Cancel~book_list`. A screen reader user can therefore focus and activate shelf controls that the organizer
   visually covers.
   *Patch*: while the panel is visible set `shelf_panel` to `IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS`
   and restore it in `hide()`, or host the organizer in its own dialog window. Its own
   `setClickable(true)` + `contentDescription` container is a related nuisance but no longer the only defect.

### Advisories (measured, not acceptance criteria)

| capture | control | measurement |
| --- | --- | --- |
| 01-shelf-default, 08-organize | `shelf_search` | 379 x 45 dp, below the 48 dp recommended target (`android:minHeight="48dp"` clears it) |
| 26-shelf-density480 | `shelf_search` | 328 x 45 dp at the 480 dpi override |
| 23-reader-landscape | `page_label` | reflow repagination: page `p.1` before and `p.1` after; the reading offset is retained |

## Coverage ledger

| surface | implemented | cases | outcome |
| --- | --- | --- | --- |
| shelf | yes | `shelf_semantics`, `shelf_row_and_search` | pass |
| import | yes | `import_picker` | pass |
| organize | yes | `organize_panel` | finding 4 |
| read | yes | `reader_line_nodes`, `reader_page_turn`, `reader_toolbar_state`, `rotation`, `large_font`, `display_scaling` | findings 2, 3 |
| annotate | yes | `annotate_flow`, `notes_panel` | pass |
| navigation | yes | `back_navigation` | pass |
| account | **no** | - | the application has no account, purchase or sync screen; nothing was audited and nothing is granted |

## Not verified

* **TalkBack speech** - a semantic tree on an emulator is not a screen-reader transcript.
* **Physical device** - no real Android device ran this audit.
* **Other API levels and vendor skins** - only API 34 `default` ran; API 26-33 and OEM builds stay unverified.
* **RTL and other locales** - only the default locale and LTR layout ran.
* **Colour contrast** - not measured from the semantic tree; the screenshots are retained for review.
* **Account surfaces** - none exist in this application.

## Rejecting altered evidence

`tests/reader_a11y_android/check_reader_a11y_android.py` re-derives every verdict from the retained evidence and
separately re-checks the installed APK against the owner build record, the source/run/attempt binding and every
screenshot/hierarchy byte count. It refuses a report that claims acceptance while a case failed, a case list
shrank, a case was skipped, a screenshot or hierarchy is missing, truncated or replaced, the source moved, or
the installed APK is not the built one. Its corruption suite mutates eight copies of the evidence in a temporary
tree and requires refusal for each; all eight were refused in this run (`missing_screenshot`, `empty_xml`,
`source_mismatch`, `acceptance_mismatch`, `case_set`, `skipped_cases`, `screenshot_bytes`, `installed_identity`).

## Shared interfaces

* `tools/build_android_host.py` is an owner tool whose ownership window assumes the caller owns
  `examples/android` and `tests/android_host`. This package owns neither, so the workflow anchors the builder at
  `f43baf91` (`ANDROID_CANDIDATE_SDK_BASE`, `ANDROID_OWNERSHIP_HEAD`). The binding constraints are the workflow's
  own checks: the frozen SDK tree at `9854061b...` must stay byte-identical, `001_catalog.sql` must equal the
  base commit, and every changed path must sit inside this package's four entries. No owner file was edited to
  make the audit pass.
* If the owner wants the four findings closed, the patches above are the minimal production changes. This
  package adds no production hook and no hidden test shortcut: every case uses the installed public surface,
  the real system picker and platform settings a user can change.

## Reproduction

`.github/workflows/reader-a11y-android.yml` runs on pushes to `codex/reader-a11y-android`: it verifies the source
and package whitelist, builds the unchanged host and its fixtures, builds the audit APK, installs both on an
API 34 emulator, runs the audit, refuses altered evidence, and preserves the trees, screenshots and records as
`reader-a11y-android-<run>-<attempt>`. A `workflow_dispatch` run with `diagnostics_run`/`diagnostics_attempt`
re-reads a preserved artefact of that exact run instead of executing a new audit.

All builds, execution, parsing and artefact inspection happen on GitHub Actions; nothing is executed locally.

### Runs that failed first (kept, not reused)

| run | what failed | correction |
| --- | --- | --- |
| 40076530338 | shared builder refused the package ownership window | anchor the builder at this package's start; the workflow's own frozen-tree and whitelist checks stay binding |
| 40077262983 | harness compile error: `dumpWindowHierarchy` returns void | assert the dumped file instead |
| 40077918078 | the picker never listed `Sample.epub` and stayed in front of every later case | scroll the picker list instead of leaving the download folder |
| 40079479165 | the host titles an import with the picked file name; a fitting list is not scrollable | match the real row text; require exposed rows, not `isScrollable` |
| 40080432881 | unescaped quote in an advisory note | corrected |
| 40081249134 | platform dialog buttons render upper case; reflow repagination on rotation | case-insensitive label match; hold the book identity and record the drift |
| 40082174522 | `By.textMatches` does not exist in uiautomator 2.3.0 | use `By.text(Pattern)` |

## What this grants

* `audit_completed` for source `2bdfee69f82b5607bd5d43db7f80ea817640c1d5` on API 34 x86_64 emulator semantics.
* Four named, reproducible accessibility gaps with minimal patches - **not** an accessibility pass.
* Nothing for TalkBack speech, physical devices, other API levels, RTL, contrast or account surfaces.
