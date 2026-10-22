# WP13 Windows native host

Status: H8 default bounded EPUB adoption passed its complete same-source Windows
cloud acceptance on `codex/r5-windows-bounded`; tested source is
`2a9dcff8131543f27cad358fe254b6d4253423c0`. The original WP13 package remains recorded below.
This package closes the Windows host loop only; it is not a whole-WP13 or product
acceptance and does not include migration, OPDS, TTS or other platform hosts.

## Baseline

- Implementation baseline: `a2552d7feb786cd2345d2b0b3eb894777b3254db`.
- SDK: 3.40.0 (core 3.39.0, ABI 1, library schema 7) consumed from an installed prefix.
- H8 initial SDK candidate: `96c4f2c035a737ccf3f5be890d127d6efdd946f8`;
  final SDK candidate and host source must receive their own cloud results.
- Current frozen SDK: `9c69bc4c7efb0cff68ced27562709fe597189041`.
  The `ce5d664` freeze was withdrawn after Apple exposed a same-unit window recursion;
  the corrected SDK passed all six freeze groups. H8 revalidated the corrected implementation
  on `8c51264b9017c255345b7ba2056c4f6bd1f1969a` in run `39871687848`;
  the current-K ancestry guard and all four hosts still await their common-source run.
- Source: `examples/reader.c` (Win32, one translation unit) with an independent
  consumer build in `examples/windows/`.

## What changed

The previous host could open one file and keep a page number in `reader.ini`. The
package replaces that with a real library-backed session while keeping the original
26-check native self-test unchanged:

- **Bookshelf**: `exr_library_open/books/import_file/import/import_unique/update/delete`
  with metadata, exact-byte dedupe, per-book progress and SQLite-backed annotations.
- **Non-blocking work**: import, open, page, font and zoom work runs on one serialized
  worker; the UI thread only applies completed results. A new request cancels the
  current job and replaces any pending one, so a stale result cannot be published to a
  newer book. Closing the window cancels and joins the worker before freeing SDK objects.
- **Reading**: reflow pages (720x1040, 80-300% font scale) and fixed PDF/CBZ pages
  (25-400% zoom, bounded render size). Previous/next, page limits, window resize and
  unsupported input are reported explicitly.
- **Selection and annotations**: page-level select-all plus mouse drag selection.
  Reflow notes use `exr_anchor` selectors; PDF/CBZ notes use `exr_fixed_note` with page
  ranges. Add, edit (comment only), delete and jump-to-note are implemented; copy
  quote uses the clipboard.
- **Restore**: reflow progress is stored as a point anchor plus the numeric text offset;
  fixed progress is the zero-based page index. Restart resolves the anchor; ambiguity
  and missing matches are shown explicitly and fall back to the saved offset, never to
  a guessed nearby location. Font/window changes re-layout and re-anchor the current
  page.

## Build and consume

Build the SDK and install it, then build the consumer project against the installed
prefix (see `examples/windows/README.md`):

```powershell
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_JNI=OFF -DEXR_ENABLE_AAC=OFF
cmake --build build/native --config Release --parallel 4
cmake --install build/native --config Release --prefix stage
cmake -S stage/examples/windows -B build/win-host -DEXR_SDK="$PWD/stage" -DCMAKE_BUILD_TYPE=Release
cmake --build build/win-host --config Release --parallel 4
python tools/build_windows_host.py --sdk stage --binary build/win-host/Release/EXReader.exe --output build/wp13-windows
```

`examples/CMakeLists.txt` stays untouched; the installed tree contains the same
consumer project because the top-level install copies `examples`. The portable payload
contains `EXReader.exe`, the installed `exreader.dll`, `Reader.otf`/OFL, license
notices and the sample books, and is zipped by `tools/build_windows_host.py`.

## Runtime layout

- `%LOCALAPPDATA%\EXReaderHost\library.sqlite`: books, covers (SDK), progress and
  annotations (owned by the SDK, not the host settings file).
- `%LOCALAPPDATA%\EXReaderHost\host.ini`: font size, zoom, window size and the last
  active book only.
- `--data DIR`, `--library PATH`, `--font PATH` override the defaults for a portable
  profile. `--drive SCRIPT --evidence DIR` enables the acceptance driver.

## Supported input

| Format | Path | Notes |
| --- | --- | --- |
| New EPUB | bounded reflow | Controlled source import → SQLite original → publication → chapter pager; part/path/point progress and `epub_notes` |
| Legacy memory-import EPUB | snapshot reflow | Existing mode preserved on open and exact deduplication; original global progress and notes remain separate |
| TXT/HTML/FB2/DOCX/RTF/MOBI/AZW3 | reflow | as reported by the installed SDK decoders |
| PDF | fixed | `exr_library_fixed_source`; anonymous mapping, text selection when the page exposes text |
| CBZ | fixed | `exr_library_fixed_source`; retained library source, image pages have no selectable text |

Host limits: import file size 96 MiB (single cancellable read); SDK snapshot limits
still apply (64 MiB normalized text). Fixed render is capped at 4096 pixels per side;
font 80-300% of the 28-point base (1.5 line height), zoom 25-400%. Over-limit or
unsupported input is displayed, never silently clamped. Encrypted PDFs are reported as `EXR_PASSWORD`; there is no password
prompt in this package.

The default EPUB path uses `exr_publication_pager_create`: 8 MiB chapter workspace,
64 KiB preferred source windows, two cached pages / 8 MiB, and eight checkpoints /
4 MiB. These are independent SDK budgets. The owned frame holds at most 1 MiB
UTF-8 page text and 65,536 glyph records; bitmap and Win32 DIB bytes are reported
separately. Exceeding a budget produces a visible error.

Chapter-local offsets never enter legacy global tables. Previous/next navigation
skips auxiliary parts while preserving repeated spine routes by part plus path.
Only normal pager EOF may cross a chapter; I/O, limits and malformed chapters remain
errors. Font changes and note jumps publish candidates only after unique anchor
resolution for notes. Missing/ambiguous bounded progress validates the stored
part/path and UTF-8 offset, then explicitly reports a numerical fallback rather
than exact reanchoring. It preserves the stored selector until an explicit user
page turn accepts a new position. Font changes use the same stated numerical
fallback on the same stored source. New EPUB notes use `exr_library_epub_note/notes/remove_epub_note`;
cross-chapter single-note selection is unsupported.

Page text, clipboard input, highlights and evidence previews share the accepted
frame's owned data. Bounded drag hits run on the serialized worker with book,
part, page, frame generation and gesture guards. Down and up cannot be replaced
by coalesced move events. Point selectors are captured on the worker, and only
accepted frames enqueue an owned save job. That job completes before queued
navigation/close; failure retains the visible position and blocks silent close.

H8 acceptance preserves all original 26 self-test checks, 158 UI actions, eight
screenshots, evidence-refusal tests and worker candidate/baseline reverse tests.
The original `Sample.epub` bytes and generator remain unchanged for the 26-check
self-test and an independent repeated-quote ambiguity-refusal regression. The
158 positive UI actions use the additional `Sample-positive.epub` with unique
paragraph identifiers; all actions, assertions and screenshots remain, and an
extra check binds the note jump to the original part/page/range. Both fixture
hashes are sealed. Passing this positive plan does not claim the original-byte
UI plan passed; runs `39862590539` and `39863379537` retain those original failures.
`tests/windows_host/bounded/check_bounded.py` adds long-chapter eviction, cross-part
notes/restore, duplicate paths, missing chapter errors, selector rejection, and a
public memory-import compatibility fixture using the normal distributed binary.
The original failures identify ambiguous font/progress points and a correctly
rejected repeated quote. They remain retained alongside the passing revised scope.

### H8 cloud result

Tested source `2a9dcff8131543f27cad358fe254b6d4253423c0` passed
[run 39865943512](https://github.com/NoGod3524/EXReader/actions/runs/39865943512),
attempt 1, job `120129784734`; every job step succeeded.

| Gate | Result |
| --- | --- |
| Installed SDK / normal distributed host build | Passed |
| Original native self-test, original `Sample.epub` bytes | 26/26 |
| Original UI action/assertion plan with sealed unique positive EPUB | 158/158, 0 failures, eight screenshots; A/B/C exit 0 |
| Evidence forgery/incompleteness refusals | 51/51 |
| H8 source, long chapter, routes, notes, fallback and legacy checks | 80/80, strict `accepted=true`, no failures |
| Worker ownership/fault candidate | 11/11 |
| Original host reverse verification | 11/11 rejected, `reverse_verification=true` |

The H8 gate verifies the SDK candidate is an ancestor and all eight protected
SDK trees match it exactly. The long UI fixture has 6,000 independently numbered
paragraphs and crosses multiple 64 KiB windows; this is synthetic UI coverage,
not a transfer of the SDK's separate 10/50/100 MiB benchmark results.

Artifact `EXReader-WP13-Windows`, ID `12464188909`, is 39,607,521 bytes,
digest `sha256:a920f5d5db09baefeff2b34c08347a8065f64111af2096bbc814e53a621561bf`.
GitHub metadata binds it to the same run/source; it was unexpired at verification
and expires on `2027-01-20T22:34:28Z`. The committed pointer record is
`docs/validation/r5-windows-bounded.json`; raw generated evidence stays in the cloud artifact.

Earlier passing development source `4a6f7e7` / run `39865681259` used SDK `6f0d759`;
it is not substituted for the final SDK candidate run above. Original failed runs
`39862590539`, `39863379537`, `39864142767`, `39864506016` and cancelled pending
runs remain retained. The comment-update observation race in the latter two was
fixed by waiting for the actual worker completion before taking the pilot state;
the update content assertion was kept.

## Controls, focus and names

| ID | Control | Accessible name |
| --- | --- | --- |
| 101 | import path edit | "导入路径" label |
| 102-104 | import/open/delete | "导入", "打开", "删除" |
| 105-117 | reading, annotation, font/zoom, cancel | button text |
| 118-120 | shelf/list, notes list, comment edit | "书架", "标注列表", "批注" |
| 121 | page view (custom) | window text "阅读区域" |
| 122-123 | page label and status | static text |

The main window is `WS_EX_CONTROLPARENT`; the message loop runs
`IsDialogMessageW`, so Tab and Shift+Tab traverse controls in creation order and the
page view receives arrows (`WM_GETDLGCODE` asks for arrows/chars). Mouse selection,
wheel paging and Ctrl+A/Ctrl+C/Ctrl+O/Ctrl+I are handled by the page view. Labels,
button text and control IDs are stable for the WP14 accessibility work, but this
package does not claim a screen-reader acceptance.

## Concurrency and ownership

- One `host_job` owns the SDK documents/pager/fixed handle for its lifetime; jobs are
  serialized. A second request marks the first cancelled, keeps a pending request and
  starts it only after the first posts completion.
- The worker owns `exr_document`/`exr_pager`/`exr_fixed_document` creation; the live
  session is swapped only after a complete page render. The UI keeps its own rendered
  bitmap, so worker parsing never blocks painting.
- `exr_control.cancelled` is wired into pager creation, page layout/render, fixed
  render, fixed notes and library openings. Import reads the file in 256 KiB chunks and
  checks cancellation between chunks; a cancellation that lands after the SDK insert
  removes the just-created row before reporting cancellation.
- Closing the window cancels and waits for the worker (20 s guard) before freeing the
  session, library and font. The guard exists only for a broken SDK callback; a timeout
  exits the process instead of freeing objects still in use.

## Acceptance

Run the dedicated cloud workflow (no local UI tests):

```
.github/workflows/wp13-windows.yml
```

It builds the SDK, installs it, builds the host from the installed prefix, runs the
preserved native self-test (26 documented checks; the report records the actual count),
then runs three UI phases through the real executable. The driver sends real
`BM_CLICK`, `WM_COMMAND`, `WM_KEYDOWN`, `WM_LBUTTONDOWN/UP` and resize messages to the
created controls and records what the application observed. It is not an SDK unit test:
each row below is a UI/lifecycle step.

| # | Phase | Step (driver action) | Expected |
| --- | --- | --- | --- |
| 1 | A | start state | empty shelf, no book |
| 2 | A | import Sample-positive.epub (sealed script parameter) | shelf 1, success status |
| 3 | A | import the same EPUB again | shelf still 1, dedupe status |
| 4 | A | open EPUB | reflow book, page 1 |
| 5 | A | next | page 2 |
| 6 | A | next | page 3 |
| 7 | A | previous | page 2 |
| 8 | A | font + | font 160%, page renders |
| 9 | A | font - | font 150% |
| 10 | A | resize 1120x820 | repaint, reading position retained |
| 11 | A | select all page | non-empty selection |
| 12 | A | copy quote | clipboard contains page text |
| 13 | A | add note | notes 1 |
| 14 | A | edit note comment | notes 1, updated status |
| 15 | A | previous + jump to note | note page loaded, highlight and status message |
| 16 | A | mouse drag selection | non-empty selection |
| 17 | A | add second note | notes 2 |
| 18 | A | delete selected note | notes 1 |
| 19 | A | import Pages.pdf (generated, 4 renderable pages) | shelf 2 |
| 20 | A | open PDF | fixed book, page 1 |
| 21 | A | select all + add PDF note | fixed note count 1 |
| 22 | A | next + jump to PDF note | page 1 with highlight |
| 23 | A | next to page 4 + next again | explicit last-page status |
| 24 | A | delete PDF note | fixed note count 0 |
| 25 | A | import and delete Extra-Book | shelf back to 2 |
| 26 | A | import .bin | explicit unsupported status, shelf 2 |
| 27 | A | import Broken.epub | explicit format failure, shelf 2 |
| 28 | A | asynchronous import + cancel | cancellation status, shelf 2 |
| 29 | A | asynchronous import + open another book | new book stays visible, no shelf row |
| 30 | A | quit | process exits cleanly |
| 31 | B | restart | same book, page 3, notes 1, explicit restore message |
| 32 | B | select note + jump | annotation navigation works after restart |
| 33 | B | open PDF | fixed page 4 restored, fixed notes 0 |
| 34 | B | open EPUB + font + | font 160%, anchored re-layout |
| 35 | B | quit | process exits cleanly |
| 36 | C | restart after font change | font 160%, notes 1, anchored offset restored |
| 37 | C | quit | process exits cleanly |

The checker additionally enforces: no failed UI step, shelf equality across restart,
annotation identity across restart, anchored offset equality after a font change,
screenshot presence, exact package hashes, and the zero-tolerance conditions
(no lost saved note, no stale import frame on a new book, no silent wrong restore).

### Original WP13 cloud result

- Implementation run: [39710580316](https://github.com/NoGod3524/EXReader/actions/runs/39710580316),
  commit `11ac64e4542b53980a0adb1cc995750258b05361`, conclusion **success**.
- Final HEAD verification run: [39711090216](https://github.com/NoGod3524/EXReader/actions/runs/39711090216),
  commit `40c45799131b3e7f2927d5cdb09a1bf72d9452db`, conclusion **success**.
- Preserved self-test: **26/26** checks.
- UI phases A/B/C: exit 0, **158/158** steps passed, 8 screenshots.
- Artifact `EXReader-WP13-Windows` (39,316,660 bytes).
- Evidence JSON: `wp13-evidence/wp13-windows-evidence.json` inside the artifact; the
  committed summary is `docs/validation/wp13-windows.json`.

## Evidence

The CI artifact `EXReader-WP13-Windows` contains:

- `wp13-windows/EXReader-Windows.zip` and `build.json` (file hashes, source SHA, SDK version)
- `wp13-windows/report.json` and `page.png` from the preserved self-test
- `wp13-evidence/wp13-windows-evidence.json` (steps, states, shelf, notes, hashes)
- `wp13-evidence/A|B|C/drive.log` and the PNG screenshots
- `wp13-fixtures/` (generated acceptance books) and raw phase stdio logs
- `h8-evidence/h8-evidence.json`, generated route/long-chapter fixtures, phase logs,
  screenshots and isolated legacy/refusal profiles
- `wp13-negative-evidence/checks.json` and `wp13-worker-review-evidence/worker-review.json`

The original summary is `docs/validation/wp13-windows.json`; the H8 result is
`docs/validation/r5-windows-bounded.json`. Both reference their own cloud identities.

## Known limitations / not in this package

- Fixed annotation writes still parse the stored original through the SDK, on the
  serialized worker; a complete fixed-document memory/performance budget is not granted.
- The bounded note list shows the saved chapter with pending resolution; legacy
  notes show global offsets. Jumps require unique quote resolution.
- No cover thumbnails, book rename UI, search, migration, OPDS, TTS, audio or other
  platform hosts.
- Other reflow formats keep their snapshot limits. Cross-chapter single annotations,
  automatic legacy-coordinate migration and a whole-book page/percentage index are not implemented.
- Screen-reader verification (WP14) is not claimed. Control IDs, names and Tab order
  are stable inputs for that work.
