# Native C validation

## 0.17 generic navigation and NCX

`native-navigation` passes 145 checks using seven original deterministic fixtures
from `tests/make_navigation_fixtures.py`. Tests cover explicit NCX selection over
an earlier manifest candidate, EPUB 3 preference, nested/group labels, Unicode and
percent-encoded targets, separate navigation roles, external links and ambiguous
repeated spine paths. Bad XML/entity declarations or missing NCX references fail
only on navigation requests; chapter loading remains available. A seekable source
checks lazy loading, cached reuse, cancellation/retry and rejected reentry. Custom
navigation verifies deep copies, arbitrary roles/URIs, UTF-8, parent/part validation
and failed-construction ownership. All 27 local CTest suites pass. The control
milestone passed all six CI jobs at
[d21f902](https://github.com/NoGod3524/EXReader/actions/runs/38998166360).

## 0.16 operation control

`native-control` passes 3555 checks. It cancels style computation, lookup work in a
long mark run, partial rendering and seekable reading, verifies cleared outputs,
then repeats successfully. A cancelled cache miss retains the prior borrowed page;
after clearing control it restores a checkpoint and matches an uncancelled pager's
pixels. Progress callbacks validate stage/count bounds and rejected pager reentry.
Source cancellation preserves failed-open ownership and permits later load retry.
All 26 local Windows CTest suites pass. The source milestone passed all six jobs at
[83a18ac](https://github.com/NoGod3524/EXReader/actions/runs/38997470863).

## 0.15 seekable sources

`native-source` passes 463 local Windows checks. An EPUB is generated in memory
from the original font fixture plus an 8 MiB stored, unused member. Indexed opening
reads less than a quarter of its bytes; loading text and embedded fonts still reads
less than half. The reader never supplies the unused member wholesale. Cases cover
short reads, zero/oversized callback results, input limits, failed-open ownership,
transient load failures and successful retry. A loaded chapter continues reading
resources after publication release; its final release closes the source exactly
once, and its retained page/fonts still render afterward. All 25 local CTest suites
pass. The checkpoint milestone passed all six CI jobs at
[bc27700](https://github.com/NoGod3524/EXReader/actions/runs/38997073291).

## 0.14 pagination checkpoints

`native-checkpoints` passes 3922 checks. Uncached seeks compare glyph IDs, source
ranges, exact line geometry, boxes and rendered pixels against a pager with
checkpoints disabled. Cases cover Latin ligatures, mixed Arabic/Hebrew paragraphs,
pending rowspan groups, embedded fonts, defaults, disabled/tiny budgets and invalid
settings. A backward seek from page 40 to 37 generates at most four pages with the
configured checkpoints, while the control regenerates 38. Table and bidi cases use
the same state restoration rather than a separate output path. All 24 local Windows
CTest suites pass. The preceding font milestone passed all six CI jobs at
[8ba092c](https://github.com/NoGod3524/EXReader/actions/runs/38996703264).

## 0.13 book fonts

The original `font-book.epub` is reproduced by `tests/make_font_book.py` using only
the repository's geometric font fixtures. `native-book-font` passes 136 checks:
CSS-relative and percent-encoded Unicode URLs, corrupt-source fallback, unused
declarations, family lists and CSS escapes, weight/style selection without double
synthesis, chapter scope, table cells, indexed EPUB sessions, continuation and cache
replay. Host overrides and disabled book fonts/styles retain host fallback behavior.
Borrowed effective font bytes can be used by a host renderer; retained pages still
render after document, pager and original host font release. The existing wrong-font
rasterization validation remains in `native-font`.

## 0.12.1 audit fixes

Local Windows Release passes all 22 CTest suites: 295398 shaping, 34943 line-boundary,
295 anchor, 74 note-limit, 1999 XML-export, 116 RTF-fallback and 120 HTML-raw checks.
The existing pager snapshots, table layouts, byte budgets, Unicode conformance,
bitmap validation and benchmark smoke tests also pass.

All seven installed SDK host examples and the renderer pass with only Windows
system directories on PATH, including Chinese book/font/output paths. Same-session
0.12.0/0.12.1 measurements use matching EPUB/font hashes; raw results and line-boundary
reshaping costs are recorded in [PERFORMANCE.md](PERFORMANCE.md).

The audit fixes seven behavior and resource-limit defects:

1. Long mark attachment uses cached visible/base predecessors, and integrated
   source-range mapping uses binary searches with repeated-cluster reuse.
   `test_shaping.c` checks long combining runs alongside the existing attachment
   and source-range assertions.
2. Anchor resolution compares every chapter with the stored path. The deterministic
   `repeated-spine.epub` fixture in `test_anchor.c` checks AMBIGUOUS for selections
   and point bookmarks in repeated chapters, plus missing and unique scopes.
3. Note text is limited to 64 MiB before any database write. `test_note_limit.c`
   checks exact-limit insert/read/edit, rejected oversized inserts and updates,
   unchanged prior selectors, and normal operations after reopening. Large accepted
   notes use an in-memory database. The same suite checks that passing `&note.id`
   as the output preserves the original ID through repeated updates without
   inserting duplicates.
4. XML exports reject characters forbidden by XML 1.0 with EXR_ENCODING and empty
   output. `test_export_xml.c` covers C0 controls, U+FFFE/U+FFFF, allowed Unicode
   boundaries and escaped entity-looking text. Only serialized fields are checked:
   HTML/FB2/EPUB include title and body; DOCX includes body only. TXT/RTF retain
   their representable control characters.
5. Layout finalizes shaping at actual line boundaries rather than carrying pair,
   cursive or Arabic joining context across lines. The shared raw/provisional/final
   queue serves pager, complete layout and table cells. `test_line_boundary.c`
   uses an original font with explicit pair/cursive/Arabic expectations, source
   ranges and hit tests, then compares page continuation, cache replay and pixels.
6. RTF Unicode fallback counts a whole control word, symbol or hex escape as one
   item, and `\binN` plus its payload as one item. Group delimiters terminate
   fallback; raw CR/LF do not consume it. `test_rtf_fallback.c` covers these cases,
   nested groups, skipped destinations, surrogate pairs and ordinary controls.
7. HTML script/style content is skipped as raw text until its matching end tag.
   `test_html_raw.c` covers embedded less-than signs, quotes, misleading tag-name
   prefixes, mixed-case endings, outer skipped regions and subsequent body text.

The three resident line arrays have a combined 16 MiB capacity budget. Temporary
shaping results and the shaper's own working memory are additional. Queue shaping
input/output work is capped at 64 Mi records (67,108,864) per document layout;
final line fitting permits at most 256 retreats, and an unfinished shaping segment
at most 8192 scalars. Exceeding these bounds returns EXR_LIMIT. These workspaces,
paragraph BiDi data, font tables and renderer bitmaps remain outside cache-byte
budgets; the 16 MiB limit is not a process-RSS bound.

## 0.12 native shaping and bidirectional text

The Unicode 17 UAX #9 run passes all 861948 official paragraph-direction cases:
770241 cases expanded from the 490846 property sequences in `BidiTest.txt`, plus
91707 explicit-character cases in `BidiCharacterTest.txt`. Both files are complete,
unmodified and verified by pinned SHA-256 values. Each case checks resolved levels
and the visual scalar index order through L2. Additional checks cover UTF-8 ranges,
embedded NUL, multiple paragraphs, per-line L1 resets, Unicode missing/default
properties, embedding/isolate overflow, long mark sequences and input limits.

`tools/generate_bidi.py` reproduces the class, bracket and mirroring tables;
`tools/generate_shaping.py` reproduces Unicode joining types and Latin/Arabic script
tables. Their normal C builds use the committed headers and require no Python or
Unicode download. The additional data retain the Unicode-3.0 license.

The independent shaping suite uses the original 1000-UPM font in
`tests/fixtures/shaping`. Explicit assertions cover glyph IDs, advances, offsets and
UTF-8 source-cluster ranges, including `ffi` / `fi`, feature disabling, one-based
alternate selection, multiple substitution and Context/ChainContext formats 1/2/3.
Extension and reverse substitution, glyph/class pair positioning, cursive anchors,
mark-to-base, mark-to-ligature and mark-to-mark positioning have separate cases.
Marks on the first versus last source component of a ligature check component
provenance rather than always selecting the final component.

Arabic checks cover isolated/initial/medial/final forms, lam-alef, transparent fatha,
ZWJ/ZWNJ, adjacent nontransparent run context and logical-order RTL glyphs. Anchor
expectations use logical-pen offsets; BiDi applies visual cluster order afterward.
API tests cover owned output arrays, empty input, invalid UTF-8, fontsize/style/
direction/feature limits and clearing both output pointer and count on failure.
Two fonts retain valid outline/cmap tables while replacing the GSUB or GPOS
LookupListOffset with an out-of-range value; shaping rejects them with EXR_FONT.

Fixture values were independently checked with HarfBuzz 14.6.0 through the
development-only uharfbuzz 0.56.3 package. The public API retains raw GPOS yAdvance;
horizontal HarfBuzz suppresses that component. Supplemental smoke checks compare
glyph multisets for Latin/Arabic samples in Arial, Tahoma, Times New Roman and
Segoe UI. Those system fonts and the oracle library are not distributed in the SDK.

The complex-layout suite uses the same original font to check Latin ligatures,
Arabic forms and marks, Hebrew order, punctuation mirroring, paragraph direction,
visual-cluster hit testing, source ranges and line-end L1 resets. Mixed style and
table-cell paths exercise the integrated shaper; pager pages are compared with
complete layout, including render output and page lifetime after source release.
Legacy geometric fonts without GSUB/GPOS continue through the scalar path and
retain the old pager snapshots. Fonts with OpenType output now expose shaped
cluster ranges and visual glyph order instead of one glyph record per scalar.

The implemented script preprocessing covers Latin and Arabic; the generic GSUB
1–8 / GPOS 1–9 parser does not supply Indic / USE syllable analysis or prebase vowel
reordering. Canonical normalization, AAT, variation selection, cmap 14, vertical
layout, dotted-circle insertion and color glyphs remain outside this stage.
Selected VariationIndex data return EXR_FONT. Same-size/font glyphs within one
cluster use its first color/bold/italic style; a size change splits shaping and
limits cross-size mark attachment. Inline isolation requires explicit Unicode
text controls rather than inline dir/CSS creating new isolate scopes.

Integrated no-break OpenType segments are limited to 8192 scalars. Paragraph BiDi
metadata and OpenType/font working data are outside page-cache byte budgets, so
cached payload totals do not represent peak RSS. The archived 0.10/0.11 performance
measurements remain associated with their recorded engine versions in
[PERFORMANCE.md](PERFORMANCE.md).

## 0.11 resumable layout, cache budgets and performance baseline

The 0.11 installed Windows SDK's six host examples compile using only its header
and library and run with PATH restricted to system directories. The new page
example reads an EPUB through a Chinese path and renders via the bounded page cache.

2026-10-16. All fourteen local Windows Release CTest suites pass. The new
native-pager, native-page-cache and native-budget suites report 238749, 4887 and
118 checks respectively; the ten earlier suites retain their 0.10 check counts.
The remaining new suite checks the standalone benchmark and its JSON runner.
Cross-platform results are tracked by the final source commit's workflow.

The pager suite compares single-page output with the complete-layout API and with
89 pages recorded using the installed 0.10.0 engine. These independent snapshots
use the committed original primary/fallback geometric fonts. Canonical field hashes
cover every glyph, line, box and page field after normalizing page-local indices;
geometry is recorded at 1/64 px. Separate hashes cover every gray and RGBA pixel.
The fixture covers styled EPUB, PNG/JPEG resources, nested margins/padding/backgrounds,
rowspan/colspan groups, explicit page breaks, narrow cross-style grapheme clusters
and one long text paragraph. New eager layout drains the same cursor to EOF, so the
old-engine snapshots continue to provide an independent layout regression check.

An additional 1 MiB single-paragraph test requests only the first page and requires
the scanned UTF-8 position to stay below 1/64 of the complete normalized text. This
exercises within-paragraph demand layout rather than collecting all glyphs before
splitting them into pages. Tests also check repeated NULL EOF output, pure-table
position progress, zero-width solid borders, complete cluster ranges at page edges
and rendering retained pages after freeing both the document and pager.

Page-cache checks cover the default one-page cache, incompatible owned/borrowed
access modes, hits without more scanning, forward continuation, LRU eviction and
replaying an evicted old page from the beginning. Count and payload-byte limits
apply together. Exact fits, immediate eviction on lower limits, oversized-page
rejection, out-of-range requests and retry after cache-miss failure exercise cache
contents and LRU order. The previous borrowed layouts remain usable after a failed
request. Host image decoder checks include reentrant access rejection and image
reuse while replaying previously visited pages.

The session-budget suite exercises the same count/byte rules for whole-part
document-plus-layout entries: zero/unlimited and exact-fit budgets, LRU reduction,
oversized new entries, failed loaders and failed layout while preserving the old
cache. Loader reentry cannot change the active session's budget. Memory-accounting
checks verify copied resource bytes, exact attribute/string allocation changes and
repeatable document/layout payload totals.

These counters measure owned allocation payload and allocated capacity, excluding
allocator overhead and shared or borrowed sources. Shared archive storage, fonts,
pager base/work state, pending loads and renderer bitmaps are outside cache budgets;
shared image pixels are conservatively charged in full to each referencing page.
A document is still parsed completely, and an indivisible large grapheme or rowspan
group can require substantial temporary work. Cache budgets therefore bound resident
cache payload, not the process peak RSS or every allocation during a page request.

`examples/page.c` is the installed-SDK page host. It loads a requested EPUB part,
sets a three-page / 8 MiB borrowed cache, requests one page and writes its PNG while
reporting scan progress and resident payload. Command-line page and part indices are
zero-based; the returned single-page layout is rendered with page index 0.

The benchmark measures opening, first visible page, continuation, gray rendering,
complete page requests and process peak RSS independently. Its smoke test covers
JSON structure, counts, percentiles, Unicode paths, generated deterministic EPUBs,
both layout modes, stopping at the requested page sample limit, EOF totals and bad
parameters. No machine-specific timing threshold is used. Reproduction commands,
measurement boundaries, raw JSON and the 0.10/0.11 Windows results are recorded in
[PERFORMANCE.md](PERFORMANCE.md).

## 0.10 host-supplied font fallback

2026-10-16. All ten local Windows Release CTest suites pass, including 152
native-font checks. The nine earlier suites retain their previous check counts.
All five independent host examples compile against a fresh installed SDK and run
with PATH restricted to Windows system directories. The font example also reads
Chinese font paths containing spaces and writes a PNG through the public API.

The new native-font suite uses three tiny original geometric fonts and a two-face
collection, generated by tools/generate_test_fonts.py. Their disjoint coverage,
different advances/ascent/descent and deliberately colliding face-local glyph IDs
make the tests independent of system-installed fonts. fontTools is only needed to
regenerate these fixtures, not to build or run the C engine.

Checks cover copied memory inputs, Unicode cmap coverage, supplementary scalars,
collection face selection, input/order/size/count errors and cleanup after a bad
second face. The 32nd face exercises the high bit of the cluster candidate mask.
Layout checks cover whole-cluster preference across styles, scalar fallback when
no face covers the entire cluster, hidden joiners, explicit missing-glyph flags,
input ordering, same-face kerning and suppression across faces. Actual fallback
metrics affect line height and pagination; table copies and cached publication
sessions retain the selected face index.

Gray and RGBA rendering of a fallback glyph is compared byte-for-byte against the
same glyph laid out directly with that face. Rendering after releasing input bytes
and the document also passes. These checks establish cmap-based fallback; complex
shaping, CSS family matching and visual BiDi remain separate work. Cross-platform
results for each source commit are available in its workflow run.

## 0.9 Unicode boundaries and cluster-safe flow

2026-10-16. All nine local Windows Release CTest suites pass, including 335521
`native-text` checks and all 766 vectors in Unicode 17.0.0's unmodified official
`GraphemeBreakTest.txt`. Independent PNG/BMP checks also pass.
The corpus supplies an independent boundary oracle; the
test compares every byte position, including zero-valued UTF-8 continuation bytes,
and checks start/end boundaries and that line flags occur only at grapheme boundaries.
Cases cover controls and CRLF, combining marks, Prepend/SpacingMark, Hangul, Indic
conjuncts, emoji ZWJ and Regional Indicator pairing. Additional long runs exercise
60001 Regional Indicators and a long combining sequence inside an emoji ZWJ cluster.

API checks cover explicit-length input, an empty string, embedded U+0000 treated as a
control scalar, invalid UTF-8, missing pointers, the 64 MiB limit, failure output reset
and freeing the independently owned boundary map. This does not change the document
model's NUL rejection, normalized text projection or ASCII whitespace handling.

Layout tests join clusters across inline nodes with different sizes, colors and weights.
They verify source scalar/cluster ranges, line/page endpoints and hit-test results in
wide and deliberately over-narrow layouts. Combining sequences, emoji ZWJ, flags, Indic
conjuncts and Hangul remain on one line and page per cluster. NBSP, NNBSP, WJ and FEFF
hard groups remain intact even when wider than their content box; ordinary long text
still permits emergency wrapping. CJK punctuation, curly quotes, ZWJ followed by text
and WJ followed by combining marks exercise protected boundaries. ZWSP permits wrapping,
while NEL and Unicode line/paragraph separators force new lines. Hidden controls,
Combining Grapheme Joiner and Mongolian variation selectors retain offsets with zero
advance and the hidden flag; rendering these documents produces white pages.

Line-break tests cover the documented UAX #14 subset: spaces, CJK opportunities and
punctuation restrictions, hard spaces/joiners, zero-width space, soft-hyphen opportunities
and mandatory breaks. Full numeric/quote context and dictionary segmentation are not
implemented or covered by an official LineBreakTest conformance run. Soft hyphens remain
hidden rather than generating a visible hyphen at a wrap.

`tools/generate_unicode.py` reproduces the committed 85932-byte property header from
fixed official URLs and SHA-256 pins. A fresh-cache `--download --check` run reproduced
the header and official fixtures byte for byte; explicit checks reject modified source
hashes and overlapping intervals. C builds consume the generated header without Python
or Unicode network access. Unicode-3.0 licenses apply to the data and derived tables;
the complete notice is included in the installed SDK.

The installed-SDK `examples/text.c` builds as `exreader-text-example` without a font
or command-line arguments. It validates four graphemes in 25 UTF-8 bytes and prints
their ranges. Desktop workflows run it on Windows, Linux and macOS alongside the
existing construction, anchor and lazy examples.
All four examples compiled against a fresh installed Windows SDK and passed with
PATH restricted to Windows system directories. Construction, custom/EPUB lazy loading
and the installed renderer also passed with Chinese input/output paths containing spaces.

This stage still renders one FreeType glyph per Unicode scalar and lays out logical
LTR text. Cluster-safe boundaries do not provide OpenType shaping/GPOS, font fallback,
BiDi or correct visual shaping of Arabic, Indic and emoji sequences. Stable-anchor
capture remains scalar-based; hosts can use the boundary API to choose whole clusters.
The earlier eight-suite regression results are recorded below; runtime and mobile-build
results for later commits are available in their respective workflow runs.

## 0.8 indexed loading and bounded part cache

The installed Windows construction and lazy examples use a shared Unicode command-line
entry and pass UTF-8 paths to the SDK. Native tests exercised Chinese input/output paths;
the Windows workflow repeats this with an EPUB and PNGs inside a path containing Chinese
characters and a space.

Validation for this stage covers metadata-only EPUB opening, loading one XHTML part at a
time, spine and auxiliary-part ordering, non-linear/nav loading, resource access through
shared archive storage and links to unparsed chapters. Custom loader checks exercise
copied metadata, independently owned documents, context release, session retention of
the publication, copied configuration, LRU hits/eviction, cache clear and failure paths
that retain existing entries. Part-local ranges and stable anchors are checked separately
from the existing whole-book library offsets.

The cache bounds resident part count, not bytes; a new load can temporarily add one part.
Each part is still parsed and laid out in full. Tests in this stage do not establish
page-level layout resumption, a hard memory budget or handling of arbitrarily large
single chapters.

2026-10-16. Local Windows Release passes all eight CTest suites, including 39215
native-lazy checks. All three independent host examples compile using only the
installed SDK header and library. The lazy example runs both a custom loader and the
indexed EPUB path: the custom publication reports part 1 of 3, one resident part and
one loader call; `layout.epub` reports part 1 of 2 and one resident part. Part indices
are zero-based. The current commit's workflow supplies cross-platform runtime,
sanitizer and mobile build status.

## 0.7 stable text anchors

The anchor integration suite covers selection and point-bookmark capture, UTF-8 scalar
boundaries, owned selector strings, context limits, text inserted or removed before a
selection, chapter-scoped resolution and selections spanning chapters. Exact quote and
context matching distinguish a unique result from missing and equally ranked repeated
content; unresolved and legacy results must not expose a usable range. Chapter paths
restrict resolution, and a missing chapter does not silently broaden the search.
Host-constructed documents exercise the same API without the SQLite library.

Library coverage includes capturing selectors for new notes, retaining selectors when
only a note's text changes, explicit re-anchoring, persistence across close/reopen and
backup, and transactional schema-v1 migration that preserves legacy notes without
inventing historical quote evidence. Matching does not claim fuzzy edit recovery,
Unicode normalization, CFI interoperability or document fingerprint validation.

2026-10-16. Local Windows Release passes all seven CTest suites, including 256 anchor
checks and 282 library-anchor checks. The earlier native-core, native-flow and
native-construct suites retain 70073, 2553 and 349 checks respectively. The independent
anchor example builds using only the installed SDK header and library and runs without
a font, reporting relocation from byte 18 to byte 39 after inserting a preface.
The current commit's workflow supplies cross-platform runtime, sanitizer and mobile build status.

## 0.6 host-constructed documents

The native-construct integration suite supplies a document tree, reading-order and auxiliary
chapters, attributes, CSS and PNG bytes through `exr_document_create()`. It changes or releases
the source arrays, strings and resource bytes after construction, then checks the independent
document title, raw node text, normalized UTF-8 projection, ranges and parent/sibling links.
Checks also exercise auxiliary links with encoded literal `%`, `#` and `?` path characters,
resources without bytes, valid empty resources, search, TXT/EPUB text export, styled layout,
image pixels and rendering after freeing the document.

Invalid-input checks cover missing arrays, invalid roots and parent relationships, non-preorder
nodes, nested chapters, leaf-node children, duplicate resource paths/IDs and attributes,
invalid UTF-8, unsafe or noncanonical virtual paths, resource-size limits and excessive depth.
Failure leaves the output document NULL. This API accepts host parser output directly;
there is no parser registry or serialized custom-document storage in this version.

2026-10-16. Local Windows Release passes all five CTest suites, including 349 construction
checks. The independent host example compiles using only the installed SDK header and library,
constructs a styled document and renders a PNG; the output was visually inspected.
Name-based checks cover arbitrary vocabulary, XHTML opt-in and CSS on nameless semantic nodes.
The workflow also builds and runs the installed host example on Windows, Linux and macOS;
the current commit's workflow supplies cross-platform runtime, sanitizer and mobile build status.

## 0.5 CSS, images and table flow

2026-10-16. Local Windows Release has four passing CTest tests: native-core, native-flow,
native-png and native-color-png. The native-flow integration suite covers CSS specificity,
source order, important declarations, inheritance, chapter scoping, malformed declarations,
host overrides, disabling author styles, bold/italic metrics, indentation and alignment.
It checks PNG/JPEG pixels, alpha blending, image-only pages, damaged/missing image placeholders,
image and stylesheet limits, caller-supplied decoders and release callbacks on success/failure.
Rendering and decoded image access remain valid after freeing the document.

Table checks cover colspan/rowspan geometry, row-group pagination, right-column hit testing,
source positions, forced page breaks and an explicit EXR_LIMIT for a row taller than a page.
A regression checks that block padding and borders remain inside page margins.
The independent PNG checker validates gray and RGBA files, chunk CRCs, scanlines and known
image colors including alpha composited over white. Damaged PNG decode/release paths are repeated.
The installed Windows MinGW SDK renders with PATH restricted to Windows system directories;
compiler runtime support is statically linked. BMP output is independently checked for BGR ordering.

Fixtures are original publications generated by `python tests/make_layout_fixtures.py`;
Pillow is only needed to regenerate their JPEG sample. Checked-in fixtures run without Pillow.
`styled-page.png` was generated by the C CLI with Microsoft YaHei and visually inspected:
mixed text sizes and styles, block backgrounds, scaled transparent PNG, merged table cells,
JPEG and an unstyled second chapter. The font file is not distributed.

The workflow runs the same suites on Windows/MSVC, Linux/GCC and macOS/Clang, plus
ASan/UBSan/leak checks and Android/Apple mobile cross-compilation. Read the current commit's
workflow result for its status. Mobile jobs check native libraries, not device rendering or apps.

## 0.4 structured EPUB model

Local Windows Release tests cover the document tree, parent/sibling connectivity, UTF-8 ranges,
spine ordering, non-linear and auxiliary chapters, nested lists, table cells, inline styles,
embedded style text, EPUB 3 navigation, footnotes, source ownership, and PNG/CSS resource reads.
Link tests include chapter-local fragments, cross-chapter targets, Chinese IDs and filenames,
literal percent signs in paths, missing targets, unsafe traversal, external URIs and invalid encoding.
Missing chapters, duplicate manifest entries, malformed XHTML, external entities and excessive
nesting are rejected. Oversized non-text resources fail on demand without inflating them at open.
In 0.4 image-only publications retained structure without rendering; 0.5 adds image-only pages.
Original fixtures are reproducible with `python tests/make_structure_fixtures.py`.

The existing format, layout, rasterization, conversion and SQLite integration tests also pass.
Workflow runs for the current commit validate desktop runtime and mobile cross-compilation;
historical run links below cover the earlier implementation.

2026-10-15. Native engine 0.3.0 replaces the JavaScript source on the primary development line.

Local Windows / MinGW GCC 16.2 / CMake 4.4 checks passed:

- C11 shared library and standalone renderer build, with warnings treated as errors for engine sources.
- Native integration suite: format decoding, UTF-16 surrogate handling, EPUB spine order/path resolution, blocked XML entities, ZIP expansion limits, page geometry, glyph coverage, position persistence across reflow, hit testing, native rasterization, six conversion round trips, SQLite metadata/cover/annotation persistence, cascade deletion and database backup/reopen.
- Corrupted copies of FB2, EPUB, DOCX, RTF and MOBI fixtures are opened and released to exercise parser failure paths.
- Independent Python PNG check validates chunk CRCs, decompression, scanline structure and rendered ink. Python is a test tool, not a runtime dependency.
- Chinese filenames and output paths exercised through the native Windows CLI.
- Installed SDK includes the public C header, native shared library, CLI and third-party license texts.
- Actual rendered Chinese page: native-page.png. Uses the locally installed Microsoft YaHei font; the font file is not redistributed.

GitHub workflow native.yml checks Windows, Linux, macOS, ASan/UBSan and mobile cross-compilation. Results must be read from the workflow; adding a job does not establish that platform support has passed. Mobile cross-compilation checks do not constitute device runtime or application-package validation.

## First native CI

[Run 38839605921](https://github.com/NoGod3524/EXReader/actions/runs/38839605921) passed all six jobs: native runtime tests and SDK installation on Windows/MSVC, Linux/GCC and macOS/Clang; AddressSanitizer/UndefinedBehaviorSanitizer; Android ARM64 cross-compilation; iOS/iPadOS ARM64 device and simulator cross-compilation. This run covers the initial native implementation at 60e3e03. Later changes add font metric caching and installed-SDK smoke checks and are checked separately.

## Local performance sample

Windows, MinGW GCC 16.2, Release build, system Microsoft YaHei font. A generated repetition-based Chinese text of 2,919,999 UTF-8 bytes (approximately one million characters) produced 2,223 pages and a native rasterized first page. Process CPU time reported by the CLI was 3.339 seconds before caching repeated font metrics, and 0.086 seconds after caching. This is a synthetic sample, not a general publication benchmark. Cold and reused-font layouts are compared after font-size changes to detect stale metrics.

## 0.12.0 最终本地验证

Windows GCC 16.2 C11 Release 的 17 个 CTest 项全部通过。新增双向测试包含完整 Unicode 17 的 861,948 条官方用例，共 24,401,500 项断言；原生塑形测试 450 项，复合布局测试 37,354 项。旧页级布局 238,749 项及页面缓存 4,887 项继续通过，0.10 记录的 89 页几何与像素快照保留。

安装后的 7 个独立宿主示例均构建成功，并在 PATH 仅保留 Windows 系统目录的进程中运行，覆盖中文书籍、字体与输出路径。`tests/fixtures/complex-text.epub` 由同目录 `complex-text.html` 的原创文本与样式生成；[真实字体渲染样张](complex-text.png) 使用宿主 Arial，已检查阿拉伯文、希伯来文、附标和数字混排。字体文件没有打入项目。

0.12.0 的九份新进程性能记录已归档至 `docs/benchmarks/0.12.0-windows-paged/`，口径与结果见 [性能记录](PERFORMANCE.md)。

## 0.18 structured EPUB export

`native-export-epub` round-trips styled tables/images, embedded font selection, EPUB 2 NCX,
EPUB 3 navigation, repeated spine entries and host-constructed Unicode paths. It compares
normalized text, linear flags, encoded non-XHTML resource bytes, navigation labels/roles/parents,
and rendered pixels after reopening. XML namespace attributes and CR/LF/tab values survive.
Missing bytes, illegal XML names, reserved paths, cancellation and package encryption metadata
fail with empty outputs. Plain text receives a generated chapter and navigation. The legacy
XML/text conversion regression remains unchanged.

## 0.19 rich FB2

`native-fb2` verifies original generated PNG bytes, cover designation, URI-decoded image IDs,
inline emphasis, headings, tables, note links, metadata exclusion and exact rendered pixels after
structured EPUB round-trip. Strict base64 cases include empty/full/padded/whitespace values,
invalid alphabet, noncanonical pad bits, incomplete groups, extra padding and data after padding.
Duplicate binary IDs, missing images, wrong namespaces/roots and entity declarations are rejected.

## 0.20 rich DOCX

`native-docx` opens an original package whose main part is outside word/document.xml.
It checks inherited/default/direct formatting, headings, bookmarks, links, a Unicode image path
with literal #/%/?, embedded dimensions, horizontal/vertical cell merges, row grid offsets,
alternate-content selection and revision/field text. Structured EPUB round-trip compares text
and exact rendered pixels. Regressions reject missing relationships/resources, traversal targets,
relationship ID collisions, invalid namespaces, style cycles and orphan merge continuations;
external image URIs remain metadata without network reads.

## 0.21 DOCX notes

The DOCX fixture adds repeated footnote references, an endnote, backlinks, a non-default notes
part path, separator/orphan exclusion, and an image relation that reuses a main-part ID for a
different asset. Every generated fragment resolves, resources have unique IDs, and text/rendering
survive EPUB round-trip. Missing notes, missing bodies and duplicate note IDs are rejected.
Structured export also rejects chapter/non-XHTML resource path collisions with empty outputs.

The 0.20 sanitizer job stopped at a GCC debug-build format-truncation diagnostic in relationship
path construction (before running tests). 0.21 checks the length before copying fixed path
segments, shared by main/notes parts, with no formatted truncation path.

## 0.22 DOCX numbering

The generated fixture verifies multilevel references, independent numId counters, continuation,
start overrides, style-derived numbering and never-restart levels. Visible labels and list nodes
survive structured EPUB round-trip with identical rendering. Additional cases cover zero,
zero-padded decimals, alphabetic rollover, subtractive Roman numerals, large-value fallback,
bullets, suppressed labels, missing definitions and unsupported numbering formats.

## 0.23 styled RTF

`native-rtf` verifies group-scoped bold/italic, explicit size and color, paragraph properties,
semantic underline/strike nodes, metadata exclusion, paragraph/soft breaks and exact pixels after
EPUB conversion. Invalid palette components/references and font sizes fail atomically. All 29
existing Unicode fallback cases remain unchanged and pass through the new tree adapter.

## 0.24 RTF pictures

PNG/JPEG cases exercise both hex and binary pict streams, twip dimensions, optional shppict,
nonshppict suppression, exact encoded bytes and identical rendered pixels after EPUB round-trip.
Malformed hex/signatures fail. A known word nested in an unknown optional destination cannot
reactivate that skipped content. The existing Unicode fallback suite remains unchanged.

## 0.25 RTF fields/fonts

RTF tests cover Unicode font/title metadata, default/explicit font names, scoped formatting in
external hyperlinks, internal bookmark resolution and a non-hyperlink field's visible result.
Titles, links, style requests and pixels survive EPUB conversion. Empty font names and skipped
metadata with later known destinations remain valid without leaking metadata into body text.

## 0.26 text decorations

`native-decoration` checks semantic/CSS defaults, ancestor propagation, user overrides,
combined lines, visible raster output, preserved OpenType flags, Latin ligature boundaries and
Arabic joining forms. Eager pages match borrowed paged/replayed output exactly. DOCX tests
verify inherited underline, direct removal and strike, then compare EPUB round-trip pixels;
RTF regressions now assert underline/strike glyph flags as well as semantic nodes.

## 0.27 MOBI compression

`native-mobi` uses original generated PalmDB/HUFF/CDIC fixtures: fixed/short/long codes,
multiple dictionaries, recursive phrases, UTF-8/Windows-1252, multiple records and trailer flags.
Cases reject bad tables/offsets/prefixes, missing/truncated dictionaries, phrase cycles,
65-level nesting, expansion-budget overflow, record-directory corruption and bad trailers.
PalmDOC tests distinguish valid in-record overlap from invalid cross-record references.


## 0.28 KF8 reconstruction

`native-kf8` checks two-chapter SKEL/FRAG assembly, multiple data INDX records,
multiple control bytes, TAGX byte-length prefixes before value payloads, repeated insertions,
zero-fragment skeletons, unsplit XHTML and FDST auxiliary streams. Chapter paths, structure,
resource bytes and text survive structured EPUB round-trip. Corrupt headers, total counts,
IDXT offsets, masks, VWI, fragment bounds/order, unsupported ORDT, orphan indexes, malformed
XHTML and truncated/gapped FDST fail atomically.


## 0.29 KF8 assets

`native-kf8` includes PNG/JPEG reuse, transitive/cyclic CSS resource references, inline CSS,
untouched comments/string literals/body text, and FONT flag combinations 0/1/2/3. Recovered
font bytes equal the original geometric font, layout selects that font and CSS color, and
rendered pages match EPUB round-trip pixels. Cases reject malformed/overflowing/out-of-range
Base32 URIs, conflicting MIME types, bad signatures, FONT flags/offsets/keys/size, compressed
corruption/trailing bytes and oversized font declarations. The suite totals 290 checks.


## 0.30 KF8 positions

Tests verify cross-chapter/return links, targets inside start tags, chapter-top fallback,
legacy named anchors, XML IDs, duplicate IDs in different chapters and URI-escaped Unicode IDs.
Every translated target resolves to the same chapter/anchor after EPUB round-trip. Malformed
prefixes/separators, missing numbers, overflow, invalid fragment/offset bounds and duplicate
IDs within a chapter fail atomically. Position offsets come from the shared XML parser's
64-bit source byte index and never replace public normalized text offsets.

The 0.29 sanitizer run found a test-only over-read: binary CSS returned by the resource API
was passed directly to strstr. Commit a1ab85a copies and explicitly terminates test strings;
the binary resource API continues to return an exact byte array without a terminator contract.


## 0.31 KF8 authored navigation

The 582-check KF8 suite verifies a three-level authored NCX with explicit and derived parent
relationships, multiple CNCX records, escaped Unicode/quote/ampersand labels, stable part/anchor
targets and matching navigation after structured EPUB export and publication loading.
Document navigation snapshots remain readable after the source document is released; empty
and invalid-output cases are checked. Invalid title keys, level jumps, parent/child ranges,
leaf declarations, targets, CNCX lengths/padding/counts fail atomically.

Both the sanitizer repair (a1ab85a) and the 0.30 feature commit (42e362f) passed all six CI jobs,
including AddressSanitizer/UndefinedBehaviorSanitizer.


## 0.32 hybrid MOBI/KF8

Tests read declared hybrid boundaries with chapter reconstruction, authored navigation,
all/partial/no shared assets and HUFF text records. Font bytes, image reuse and EPUB rendering
remain unchanged; legacy text is excluded. Explicit absent boundaries retain legacy decoding.
Malformed EXTH signatures/lengths/counts/entries/duplicates, boundary pointers/markers,
target versions/encryption and shared-resource starts fail atomically. Legacy fallback rejects
unsupported encoding/compression even after successful optional EXTH parsing.


## 0.33 KF8 guide landmarks

Fixtures cover combined TOC/landmarks, guide-only chapter fallback, tag 3 and tag 6 offset
forms, shared hybrid containers, thumbnail suppression, normalized start types and preserved
custom type metadata. Navigation roles/labels/targets survive EPUB conversion independently of
role grouping order. Missing strings, invalid targets/types and invalid XML characters fail;
a 9998-guide + 2-chapter book reaches exactly 10000 navigation entries, while 10000 guides plus
chapters returns EXR_LIMIT.

The 0.32 commit e8aa242 passed all six CI jobs, including sanitizers and Apple/Android builds.


## 0.34 KF8 SVG resources

The 1231-check KF8 suite adds SVG/XLink names, unnamespaced/foreign extensions, CDATA CSS,
style attributes, unchanged literal text, CSS/SVG dependency cycles and URI fragments.
An independent Expat parse checks expanded names and translated references. A host test decoder
uses the SVG's resolved embedded PNG to exercise the existing decoder contract, font selection,
release ownership and matching rendered pages after EPUB export; it is not a vector renderer.
Malformed XML/roots/namespaces/entities/references/fragments fail atomically.

The 0.33 commit be7bdc1 passed all six platform and sanitizer CI jobs.


## 0.35 ORDT and external KF8 validation

Fixtures exercise ORDT fragment labels, NCX/guide indexes, inherited/explicit matching tables,
UTF-8 headers carrying maps and hybrid books. Cases reject bad counts/pointers/signatures,
wide mapping values, overlapping tables, out-of-range labels, missing maps, conflicting local
maps and a late guide-label failure after prior labels have allocated. Identical repeated SKEL
values are accepted; conflicting repeated counts are rejected.

An external validation used Project Gutenberg's Pride and Prejudice KF8 on 2026-10-17:

- Source: https://www.gutenberg.org/cache/epub/1342/pg1342-images-kf8.mobi
- SHA-256: `7d22f45b5f2f19a1af24e854ac5ecf62eb0a9b532f38f0cb556caf18220d8cae`
- Input: 25,333,914 bytes; normalized text: 745,266 bytes.
- Reading order: 76 parts; authored navigation/landmarks: 64 entries; retained resources: 245.
- Structured EPUB output: 24,701,445 bytes. Reopening preserves exact normalized text,
  navigation role/label/href/part tuples, and every non-XHTML resource's bytes and media type.

The external ebook is not redistributed in this repository or required by CI. Its repeated
SKEL tuples exposed a compatibility gap and are covered by the original generated regression.
This check measures format fidelity, not a controlled performance baseline.

The 0.34 commit 46750e0 passed all six platform and sanitizer CI jobs.


## 0.36 MOBI/KF8 metadata

Tests cover UTF-8 updated titles, Windows-1252 full names, NUL suffix padding, repeated/empty
updated values, unreferenced and reused covers, legacy MOBI and modern/legacy hybrid fallback,
modern metadata overrides and an explicit absent cover. Titles and cover image data remain
usable after EPUB conversion; an in-memory library import adopts the parsed title. Invalid
header title ranges/lengths, UTF-8/internal NUL, oversized titles, cover indexes/types/lengths
and conflicting duplicate cover declarations fail atomically.

The external Gutenberg file also opens and passes text/navigation/nonchapter-asset round-trip
with its newly parsed title and cover metadata. Its EPUB output byte size changes as metadata
is now included. The 0.35 commit fdcc9e4 passed all six CI jobs.


## 0.37 library cover import

`native-cover-import` adds 97 checks for EPUB, FB2 and KF8 source covers, user title overrides,
whitespace-separated property tokens, exact copied bytes, retained original source blobs,
the exact 8 MiB boundary, a larger original cover and a misleading non-cover property name.
A missing declared cover aborts without adding a database row or returning a book ID.
The deterministic ZIP fixtures use the project's original PNG and fixed metadata.

The 0.36 commit 82d4270 passed all six platform and sanitizer CI jobs.


## 0.38 positioned layout foundation

`native-positioned` checks exact raster equality when an existing text layout is reconstructed,
paint-order occlusion, proportional scaling/letterboxing, hit tests, source-array/document/font
release, image sharing and host release callbacks, fontless image/blank pages, multiple page
ranges, cancellation, allocation accounting and input extension rules. Invalid spans, UTF-8
boundaries, NaN/Inf, indexes and array budgets fail atomically. A new original geometric font
checks oversized glyph bitmap rejection before raster allocation. All existing reflow/paged
rendering suites continue to pass after sharing the image and raster primitives.

The 0.37 commit 10d81b3 passed all six platform and sanitizer CI jobs.


## 0.39 PDF object foundation

The private native parser reads bounded PDF scalar/collection values, exact signed 64-bit
integers, escaped names/literal/hex strings, indirect objects, traditional cross-reference
tables, incremental revisions and raw/single-Flate streams. Object loading is lazy; newest
revision entries and free tombstones take precedence. Undefined or generation-mismatched
references resolve to null, while reference/length/Prev cycles fail. Encrypted files and
unsupported filters fail explicitly. Limits cover input, syntax depth, values, string bytes,
stream expansion, cache capacity and parsing/decompression work.

`native-pdf-objects` uses deterministic original fixtures for values, generations, revision
inheritance/deletion, stream lengths/cache reuse, checksum/tail errors, unsupported parameters,
expansion limits and every truncated prefix. All 37 suites pass. Public PDF document opening
is still unconnected: this milestone supplies internal object parsing, not page rendering.
The 0.38 commit 12f12cf passed all six platform and sanitizer CI jobs.


## 0.40 PDF cross-reference and object streams

The same private parser now reads cross-reference streams with 0..8-byte fields, default
entry types, Index subsections, raw/Flate data, compressed object streams and hybrid tables.
Compressed objects are parsed on demand from bounded slices; stream headers are validated
once and cached with a 32 MiB aggregate index budget. Direct bootstrap values prevent
reference cycles before the object table exists. Newest entries still override older streams
and tables, including free tombstones and transitions between compressed/uncompressed objects.

Original fixtures cover compressed catalogs, stream lengths stored in object streams, shared
index reuse, wide fields, optional fields, split ranges, hybrid precedence, both incremental
container transitions and invalid widths/ranges/generations/headers/indexes/object bodies.
Public PDF page reading remains unconnected. The 0.39 commit 3301cf3 passed all six CI jobs.


## 0.41 PDF filter pipelines and predictors

PDF streams now support up to 16 ordered filters with matching DecodeParms arrays:
Flate, ASCIIHex, ASCII85 and RunLength (including their PDF abbreviations). TIFF horizontal
prediction supports 1/2/4/8/16-bit samples and multiple components. PNG prediction restores
all five per-row filters and strips row tags in place. Cache accounting includes allocated
capacities and the previous filter's temporary buffer; output and decompression work are bounded.

Original fixtures check odd hex nibbles, ASCII85 z/partial tuples, literal/repeated runs,
empty streams, chained encodings, exact packed TIFF samples, all PNG row filters and PNG
prediction inside normal/hybrid cross-reference streams. Invalid terminators, tails, tuples,
row lengths, tags, parameter shapes/counts and unsupported values fail atomically. Public PDF
page reading remains unconnected. The 0.40 commit 2ac097a passed all six CI jobs.


## 0.42 native PDF LZW

A bounded C LZW decoder adds clear/end codes, 9..12-bit widths, both EarlyChange modes,
full-table handling and the code-equals-next case. Its output uses the same filter pipeline,
TIFF/PNG predictors, temporary-memory accounting and work budgets. Original fixtures cover
literal-only width boundaries through a full dictionary, dictionary references, long repeated
runs, table resets, empty data, PNG prediction and malformed codes/terminators/parameters.
The fixture compressor uses string dictionaries and emitted-code counts, independently of
the reader's prefix/suffix representation. PDF page reading is still unconnected.


## 0.43 PDF page tree and content assembly

Private page snapshots preserve document order, normalized MediaBox/CropBox rectangles,
inherited Resources/Rotate/boxes, per-page UserUnit and borrowed content/annotation IDs.
Traversal validates node types, parents, exact subtree counts, repeated/cyclic nodes and
bounded depth/node/page counts. Null inherited entries behave as absent; CropBox can extend
beyond MediaBox and is retained for the later rendering clip. Content streams remain lazy:
raw/filtered streams and arrays are concatenated exactly with no inserted bytes, up to 64 MiB,
using two passes and one exact output allocation. Errors return no partial snapshot/buffer.

`native-pdf-pages` covers ordered nested trees, sibling isolation, reverse-coordinate boxes,
negative/large quarter-turns, null/overridden/inherited properties, user units, empty trees,
compressed/hybrid object containers and split tokens across content streams. Malformed
geometry/types/counts/parents/resources/depth and content failures are rejected. The public
PDF document/rendering path remains unconnected. The 0.41 commit 6018c88 passed all six CI jobs.


Manual external-file verification on 2026-10-17 also opened the official RFC 9110 PDF:
https://www.rfc-editor.org/rfc/rfc9110.pdf (2,858,365 bytes, SHA-256
`60b30efa1048900833d1758440247fe8ac85a3134f2327388dcb24e07d814c89`). The native parser
returned 194 ordered pages and decoded/assembled all page content streams, totaling 3,817,384
bytes; the first MediaBox is [0, 0, 595, 841]. The downloaded document and local check harness
stay in ignored build/pdf-reference, outside repository fixtures/CI. This verifies object/page
and stream reading on an external file, not text interpretation or visual rendering.
The 0.42 commit 605a50f passed all six CI jobs.


## 0.44 PDF content operand lexer

The private content walker reuses the object lexer for numbers, names, strings, arrays,
dictionaries, booleans and nulls, then delivers each operator with its borrowed operands.
An arena is cleared after each callback and retains only its high-water allocation, rather
than appending every operand to the persistent document graph. Bounds cover operand count,
operator name length, operation count and nested values. Indirect references in content,
trailing operands, malformed delimiters and inline images fail explicitly. Inline-image data
is not guessed by searching for EI; support remains pending. Cancellation and callback errors
propagate. Operator-specific validation and execution remain pending.

Tests check mixed operands and decoded strings, nested arrays/dictionaries, 10,000 arena
reuses, cancellation/callback errors and invalid grammar/limits. Manual verification of the
same RFC 9110 PDF walked all 101,754 operators across its 194 pages without retaining all
operands. This is syntax traversal, not execution or rendering.

The 0.43 commit aaebfa0 passed all six platform and sanitizer CI jobs.


## 0.45 PDF ToUnicode CMaps

A private C ToUnicode reader supports 1..4-byte variable-length codespaces, bfchar mappings,
bfrange string/array destinations, UTF-16BE surrogate pairs and multi-character mappings.
Code ranges stay compact and are looked up with binary search. Unmapped valid codes yield
U+FFFD. Overlapping/ambiguous codespaces, overlapping mappings, malformed blocks/UTF-16,
range overflow and unsupported inherited/cid/notdef maps fail explicitly. A lookup that would
increment a range into invalid UTF-16 fails without consuming source bytes. Limits cover
codespaces, records, destination sizes and total payload; parsing supports cancellation.
The shared syntax walker allows larger CMap operand groups while page content retains its
64-operand limit. No PostScript is executed.

`native-pdf-cmap` covers mixed code widths, surrogate pairs, ligatures, array/compact ranges,
byte carry, null/empty destinations, missing codes, adjacent codespaces, UINT32_MAX source
codes, 100-record blocks, malformed input and cancellation. The external RFC 9110 verification
also parsed all nine distinct page-font ToUnicode streams. Public PDF document creation,
font selection/metrics, operator execution and raster drawing remain pending. The 0.44
commit 03778cc passed all six CI jobs.


## 0.46 PDF font descriptions and declared metrics

A private font reader preserves simple Type1/TrueType descriptions, Differences glyph names,
embedded Type1/TrueType/CFF/OpenType programs, ToUnicode maps and Identity-H/V composite
fonts. CID metrics use compact sorted W/W2 ranges with array/constant forms, DW/DW2 defaults
and binary lookup. CIDFontType2 maps declared CIDs to glyph IDs through Identity or a decoded
CIDToGIDMap; CIDFontType0 retains the CID for later native CFF glyph resolution. Program bytes
borrow the file while names, metrics and Unicode maps are owned by the font record.

`native-pdf-font` checks exact horizontal/vertical metrics, default metrics, CID glyph maps,
Unicode ligatures/surrogate pairs, original embedded TTF data, Differences names, unembedded
CFF descriptions, cancellation and malformed font arrays/ranges/program declarations.
The external RFC 9110 file opens all nine distinct page-font records, including embedded
simple TrueType, CID TrueType and CID CFF programs. Simple fonts without declared Widths,
custom composite Encoding CMaps, Type3 execution, base-encoding Unicode fallback and actual
font-face/glyph selection remain pending; missing ToUnicode yields U+FFFD rather than guessed
text. This is internal font data preparation, not public PDF rendering. The 0.45 commit
477d357 passed all six CI jobs.


## 0.47 PDF text state and glyph geometry

The private text walker executes BT/ET, Tf, Tm/Td/TD/T*, Tc/Tw/Tz/TL/Ts/Tr, Tj/TJ and both
quote operators. It composes text matrices with cm transforms, restores text parameters/CTM
through q/Q without incorrectly restoring the current text matrix, and supports ExtGState
Font selection. Horizontal spacing and Identity-V origins/advances follow declared metrics;
word spacing applies only to single-byte code 32. Each streaming callback receives owned-value
character/Unicode data, a borrowed font and a glyph-to-PDF-user-space transform (1000 units).
The cache is bounded to 128 fonts/128 MiB owned metadata; glyph/state/coordinate budgets,
cancellation and callback failures are enforced. Nontext drawing operators are skipped;
Form execution, inline images, ActualText replacement and visual clipping remain pending.

`native-pdf-text` checks exact affine/rotated positions, character/word spacing, TJ adjustments,
line/quote operators, q/Q semantics, vertical origins, ExtGState fonts, invisible text modes,
compatibility sections, malformed state/operands, truncated codes, callback cancellation,
stack/coordinate limits and a 129-font cache admission case. Manual verification executes
all 194 pages of RFC 9110 and emits 450,578 glyph records with 456,338 UTF-8 bytes. This verifies
content-order glyph geometry/Unicode, not reading-order reconstruction or visual rendering.
Public PDF opening remains unconnected. The 0.46 commit 3255a25 passed all six CI jobs.


## 0.48 recursive PDF Form text

The text walker now executes Form XObjects with Matrix composition, local/inherited Resources,
implicit graphics-state restoration, isolated text/line matrices and protected q/Q stack floors.
A Form cannot consume its caller's saved state. Active-path cycle detection permits repeated
reuse while rejecting recursion; nesting is bounded to 32 Forms and all nested streams share
one operation/glyph/font-cache budget. FormType/BBox/Matrix/Resources and balanced nested
states are validated. Image XObjects remain skipped by this text-only walker. BBox clipping,
transparency, vector drawing and ActualText are still outside this geometry stage.

Original fixtures check nested/local/inherited font resources, combined affine transforms,
repeated reuse, parent font/matrix restoration, empty Forms, cycles, illegal caller-stack pops,
unbalanced nested states, invalid dictionaries and depth exhaustion. Public PDF opening and
raster rendering remain pending.

The 0.47 commit 325a7f0 passed all six platform and sanitizer CI jobs.


## 0.49 glyph-only font input

The additive public exr_font_create_glyphs constructor uses the existing copied font-input
model and the same limits, while accepting scalable faces without Unicode charmaps. Those
faces use no character mapping rather than treating an arbitrary encoding as Unicode. Direct
glyph loading/rendering remains available; existing exr_font_create/open keep their Unicode
requirement. This format-neutral capability supports embedded subsets and host glyph models.

A new original primary-outline fixture removes cmap and PostScript glyph names (FreeType can
otherwise synthesize a Unicode cmap from names). The positioned suite verifies ordinary
constructor rejection, glyph-only acceptance, absent Unicode coverage, source/font release
and exact RGBA raster equality for identical glyph IDs. Existing font/fallback suites pass.

The 0.48 commit 9a35ebb passed all six platform and sanitizer CI jobs.


## 0.50 native vector scan conversion

A format-neutral private C raster primitive fills closed edge contours using nonzero/even-odd
rules, four vertical subpixel samples and exact horizontal span coverage. It supports gray or
straight RGBA targets and matching 8-bit clip masks. Half-open edge activation and grouped
crossings handle shared vertices and winding holes. Input/bitmap/edge/work budgets are bounded;
the work counter is shared across calls and cancellation is checked per row. No external path
renderer is used. Curve flattening, strokes and display-list/PDF integration remain pending.

`native-vector` checks integer/fractional rectangles, opposite/same-winding holes, even-odd
fill, shared triangle edges, clip opacity, cancellation, aliasing and work/input limits.
The shared raster pixel helper retains exact opaque-target arithmetic and adds correct
straight-alpha source-over for transparent targets, including very low destination alpha.
Existing positioned/image/PNG suites pass. The 0.49 commit 47c50b9 passed all six CI jobs.


## 0.51 native path flattening

The format-neutral path model adds move/line/quadratic/cubic/close commands and owned
polylines with explicit contour boundaries/closure. Curves are transformed first and split
adaptively by De Casteljau subdivision using a pixel tolerance. Flatness measures distance
to the finite chord, preserving collinear overshoot/return curves. Vertex, subdivision and
shared-work budgets and cancellation are enforced. Edge construction preserves explicit
closure or optionally closes open contours for fill; errors return no partial output.

The vector suite samples independent Bernstein polynomials against the flattened geometry,
checks transformed quadratic and collinear cubic curves, closure/current-point behavior,
curved-region raster pixels, ownership/free, invalid coordinates/tolerances and cancellation
/work limits. Stroke construction and display-list/PDF integration remain pending. The 0.50
commit cf835bb passed all six platform and sanitizer CI jobs.


## 0.52 native stroke outlines

The vector core constructs positive-winding polygon unions for segment bodies, butt/round/
square caps and miter/round/bevel joins. Miter limits fall back to bevel; round joins use only
the outer arc rather than a whole disk, preserving short-segment geometry. Round caps/arcs
subdivide by target-pixel tolerance. Positive widths are outlined in source coordinates and
then transformed, preserving anisotropic scaling; zero-width hairlines are outlined as one
pixel after transforming the centerline. Shared vertex/work/coordinate budgets, cancellation
and atomic owned output apply. Flatten tolerance now accepts any finite positive value within
the coordinate budget, allowing callers to choose source tolerances for scaled strokes.

Tests cover exact cap/join pixels, miter fallback, nonuniform transforms versus device-space
hairlines, short round joins, zero-length round dots, single-application stroke alpha at
component overlaps, invalid styles, output aliasing, cancellation and work exhaustion. Dashed
paths and display-list/PDF integration remain pending. The 0.51 commit 2a72314 passed all six
platform and sanitizer CI jobs.


## 0.53 native dash geometry

The vector core splits source-coordinate polylines by even/odd dash arrays and positive or
negative wrapped phase, restarting the pattern per source contour. It preserves zero-length
on entries as dot contours, retains joins across unbroken source vertices, copies solid paths
independently and merges visible runs across closed seams. Dot contours before/after the seam
remain intact with contiguous spans. Tiny lengths that cannot advance a coordinate fail with
a precision limit rather than looping. Pattern, vertex, source, shared-work and cancellation
budgets apply; failures return no partial owned path.

Tests cover exact intervals, odd arrays, phase/reset behavior, zero gaps/dots, full closed runs,
wrapped joins with leading/trailing dots, independent solid copies, dash/stroke/fill raster
pixels, invalid/all-zero patterns, tiny-length limits and cancellation. Display-list/PDF
integration remains pending. The 0.52 commit ff33a4b passed all six CI jobs.


## 0.54 PDF drawing events and vector integration

The unified private content interpreter emits borrowed path/glyph/image/state events with
an optional initial output transform. Paths capture construction-time CTMs; paint snapshots
retain the painting-time CTM, device gray/RGB/CMYK components and alpha, line style and dash
profiles. It supports m/l/c/v/y/h/re, all basic fill/stroke operators, deferred W/W* clipping,
color-space aliases and basic ExtGState line/dash/alpha settings. q/Q restores paint parameters
without restoring the current path. Forms isolate paths/state, emit implicit save/restore and
BBox clips. Active path storage and immutable dash profiles have aggregate byte budgets.
Unsupported non-device spaces, blend modes, soft masks, transparency groups, shadings and
Type3 drawing fail explicitly; text-only traversal continues to skip paint operations.
Image events preserve references but do not decode pixels yet. Text clip rasterization and
actual glyph drawing remain pending. Public PDF document opening remains unconnected.

`native-pdf-graphics` runs an original complete one-page vector PDF through the native object,
page/content and drawing interpreters into the C flatten/dash/stroke/fill primitives. Exact
pixels check colors/alpha, deferred stroke-before-clip, nested clip restoration, even-odd/empty
clips, output scale/y-flip and Form BBox/state isolation. Other checks cover mixed construction
CTMs, curve shorthand, line/dash metadata, glyph colors and image events, invalid/unsupported
operations and callback failure. The RFC 9110 drawing visitor traverses 450,578 glyphs, 2,162
path paint events and 2,004 clips over 194 pages; this remains event validation, not a rendered
RFC comparison. Raster scanlines now use the actual horizontal shape bounds, with a work-size
regression test preventing tiny glyphs from scanning a whole large page width. The 0.53 commit
4b20178 passed all six CI jobs.


## 0.55 PDF encoding facts and standard font metrics

Simple fonts now retain descriptor Flags, resolve base-encoding glyph names and
Differences independently of ToUnicode, and extract Unicode through the Adobe
glyph lists when ToUnicode is absent. The native mapper handles suffixes,
underscore components, multi-scalar names, strict uniXXXX groups and uXXXXX
scalars; Zapf names apply only to ZapfDingbats. Unknown builtin encodings remain
unknown, and an existing ToUnicode map remains authoritative even for unmapped
codes. Type1 standard 14 fonts can omit Widths; their metrics use the selected
glyph name, including Differences. Nonstandard fonts still require Widths.

Pinned reproducible fact tables add no runtime dependency. Tests cover the full
set of 14 standard font names, encoding-vector exceptions, ligatures, private
names, multi-scalar/supplementary Unicode, invalid surrogates/hex/scalars,
ToUnicode priority, malformed Flags/encoding, and default missing widths.
These facts do not supply standard-font outlines; actual glyph rasterization
and public PDF document opening remain pending. The 0.54 commit ba0b13f passed
all six CI jobs.


## 0.56 PDF glyph selection and native outline rendering

A private PDF face adapter opens embedded scalable programs without copying
program bytes or requiring a Unicode cmap. CID TrueType uses explicit GIDs;
CID CFF builds a bounded sorted reverse CID index. Simple fonts use glyph names,
glyph-name Unicode when names are unavailable, Microsoft symbolic cmap rules,
or the Type1 builtin encoding. A host can explicitly supply fallback bytes for
unembedded simple fonts. Missing glyphs select glyph zero; ToUnicode text never
selects a glyph. Symbolic TrueType without ToUnicode retains replacement text
rather than trusting a possibly ignored simple Encoding vector.

The reusable outline adapter loads unhinted outlines through FreeType and
copies line/quadratic/cubic segments into owned 1000-em C paths. The existing
native flatten/edge/fill pipeline performs the rasterization, including arbitrary
output transforms. No FreeType bitmap rasterizer or external PDF renderer is
used. Work/count/coordinate limits and cancellation apply; failed calls expose
no partial path. Input bytes and the FT library outlive each face; required metadata is copied.

`native-pdf-outline` checks actual embedded fonts with/without glyph names,
symbolic cmap, a cmap-free GID font, simple cubic CFF, sparse CID CFF, 2000-em
normalization, empty glyphs, missing CIDs, fallback selection, cancellation and
exhausted work. Pixel checks traverse PDF content -> chosen glyph -> owned
outline -> C flatten/fill, distinguish semantic A from the selected fi shape,
and verify y-flip. Public PDF page creation and a complete page raster backend
remain pending.


A manual RFC 9110 pass visits all 194 pages and selects/loads outlines for
450,578 glyphs, with zero glyph-zero substitutions and 11,849,269 copied outline
segments. This verifies the nine real embedded fonts and the outline pipeline;
it is not yet a full-page pixel comparison. The 0.55 commit 79c8cd3 passed all
six CI jobs.


## 0.57 Native PDF text/vector page raster backend

The private content raster backend now combines the PDF interpreter, cached
font faces, native outline/curve/dash/stroke/fill code, straight RGBA or gray
pixels, and device-color/alpha paint. Text modes 0..7 include glyph-outline
clipping: glyph paths accumulate as a text-object union and intersect the current
clip at ET. Path clips and Form BBox clips are immutable reference-counted masks;
q/Q shares them instead of copying a page bitmap. A configurable mask byte budget
(default 64 MiB), shared vector work budget, bounded face/CID caches, cancellation
and failed-output disposal apply. Unembedded simple fonts have an explicit host
program callback; bad embedded programs are not silently substituted.

The raster suite checks mixed text/path color, fill/stroke/invisible/text-clip
modes, glyph-clip union, empty glyph clips, nested masks, restore, even-odd holes,
deferred clip after painting, Form isolation, transparent targets, grayscale
backgrounds, callback/cache behavior, cancellation and mask exhaustion. A chain
of 120 q saves succeeds with exactly one 144-byte clip budget. Singular stroke
CTMs, image drawing, non-device spaces and unsupported transparency still fail
explicitly. Public PDF opening/page models remain pending.

The manual RFC 9110 renderer produces all 194 pages (388,306,520 aggregate RGBA
output bytes, freed page by page). A local 72-dpi pass took 18.784 seconds; this
is a single development run, not the benchmark suite. Its first page was visually
compared with Poppler at the same 595 x 841 dimensions: positions, wrapping,
colors and rules agree, with rasterizer antialiasing differences. Poppler remains
an independent development oracle and is not linked or distributed. The 0.56
commit e84c996 passed all six CI jobs.


## 0.58 Packed PDF images and affine image painting

A native image reader decodes raw or supported lossless-filter image streams
with 1/2/4/8/16-bit DeviceGray/RGB/CMYK components, independent packed row padding,
Decode arrays, resource color-space aliases and one-bit tinted stencil images.
It validates exact sample sizes, dimensions, boolean values and decode ranges,
with 16-million-pixel, work and cancellation limits. Image events now pass the
current resource dictionary, so Forms use local aliases correctly.

The reusable affine-image primitive maps normalized RGBA images with arbitrary
rotation/shear/scale, nearest or bilinear sampling, subpixel edge coverage,
nonstroking alpha and clip masks. Bilinear color is interpolated with premultiplied
alpha before straight-alpha composition, avoiding transparent-edge color fringes.
The PDF backend flips image rows into PDF user space and releases decoded pixels
after each draw. Source/target aliasing, invalid transforms, storage and work
exhaustion are checked. JPEG/DCT, inline images, indexed spaces and external/color
key/soft image masks remain pending and fail explicitly.

Tests check actual packed PDF sample bytes, row padding, inverted Decode,
RGB/CMYK/16-bit gray, stencil tint/transparent bits, nested Form aliases, image
orientation and clip pixels, rotation, interpolation, alpha, transparent-neighbor
fringes, malformed dictionaries/data, cancellation and exhausted work. The 0.57
commit d3435f9 passed all six CI jobs.


## 0.59 Terminal JPEG filters and PDF JPEG rendering

The stream layer can explicitly preserve a final DCT codec after decoding its
lossless prefixes. Cached entries retain the codec/parameter IDs; the ordinary
stream API still rejects encoded image tails, including already cached ones.
A DCT filter in the middle of a pipeline fails. Raw/object/content decoding
retains its previous contract and limits.

The image backend checks JPEG SOF dimensions, precision and component count
against the PDF dictionary, then uses the existing bounded stb_image decoder
for baseline/progressive RGB and grayscale JPEGs. Decode maps, affine painting,
alpha and clips use the same path as raw samples. Original quadrant/gray fixtures
cover bare/wrapped JPEGs, cache identity, inverted gray and real page pixels.
Mismatch, truncation, non-JPEG bytes, explicit unsupported ColorTransform overrides
and invalid pipeline order fail without exposing output. CMYK JPEG, explicit
ColorTransform overrides and other image codecs remain pending. The shared image
helper now also supplies an error diagnostic on final pixel allocation failure.

The source image generator requires Pillow only during development; builds use
committed original bytes. No decoder dependency was added. The 0.58 commit
b536469 passed all six CI jobs.


## 0.60 Indexed images, independent opacity layers and image mattes

The PDF image reader supports Indexed palettes over device spaces, literal or
stream lookup tables, hival clamping, index Decode maps and pre-Decode color-key
ranges. It also loads explicit stencil masks and grayscale soft masks, supports
soft-mask Decode/interpolation and removes RGB/gray preblended Matte colors.
SMask overrides Mask as specified. Unsupported indexed/CMYK Matte combinations
fail explicitly. Image/mask cycles, more than 16 layers and more than 128 MiB of
simultaneously owned image pixels fail without leaking partial output.

The generic affine texture primitive retains color and opacity as independent
layers, with their own resolutions and interpolation choices. It samples all
layers in normalized coordinates at target pixel samples, then performs matte
removal and alpha composition. Masks are not reduced to the parent color-image
resolution. This is checked by painting a one-pixel red image with a four-pixel
opacity mask: all four opacity levels survive magnification. The private bitmap
decoder can flatten a texture when explicitly requested; page rendering keeps
its independent layers until painting.

Tests cover literal/stream palettes, inverse Decode, pre-Decode color keys,
stencil/soft masks of different sizes, interpolation, matte reconstruction,
SMask precedence, final page pixels, independent texture dimensions, invalid
mask types/ranges/palettes/mattes, texture alias/cycle errors, mask cycles,
16-layer depth and a real 128-MiB aggregate pixel budget failure. A manually
assembled image page was also compared with Poppler; opaque and constant-mask
interiors agree, while image boundary antialiasing/interpolation differs.
The 0.59 commit 99ee06d passed all six CI jobs.


## 0.61 Generic page viewports and PDF page raster coordinates

The public allocation-free viewport helper accepts arbitrary page bounds,
source y-axis direction, unit scale and clockwise quarter-turn rotation. It
returns top-left/y-down natural dimensions and both affine matrices, for drawing
and native-coordinate hit tests. Bounds, dimensions, matrix and inverse precision
are checked. It is independent of PDF or rendering callbacks.

The private PDF page raster entry intersects inherited CropBox with MediaBox,
applies page UserUnit and rotation, selects bitmap dimensions, and clips to the
exact viewport rectangle even when dimensions require fractional-pixel rounding.
It handles content extraction and page painting without caller-built transforms.
Disjoint crop/media boxes and oversized outputs fail before bitmap allocation.

The viewport suite covers both source axes and all quarter turns, nonzero/negative
origins, scale/unit multiplication, corner mapping, inverse round trips and
invalid/precision-limited input. Original seven-page PDF fixtures check actual
rotated colored quadrants, crop/media intersection, fractional clip pixel values,
empty intersection, initial clip validation/byte limits and oversized pages.
Public PDF document opening is still pending. The 0.60 commit 154a2d9 passed
all six CI jobs.


## 0.62 Public immediate canvas shared by the PDF backend

The generic path/point/fill/stroke and layered RGBA texture types are now public.
The public canvas owns a bounded bitmap, immutable shared clips, a 160-entry clip
stack, work/cancellation state and first-failure diagnostics. It supports path
fill/stroke, independently defined stroke coordinates, affine masked images,
clip intersection, memory queries, borrowed bitmap access and ownership transfer.
Failed drawing poisons the canvas and prevents delivery of partial pixels.

PDF rasterization now delegates geometry, images, clip references and internal
text clip-union operations to this same canvas, removing its duplicate painter.
Font selection/outlines and PDF color/state interpretation remain in the format
adapter. Clip-union group construction remains private while the scene model is
being developed; the public canvas can be used without any document or parser.

The public-DLL canvas suite checks actual fill/dash/stroke pixels, non-scaling
strokes, independent image/mask resolution, borrowed-input lifetimes, output
ownership after canvas destruction, clip save/restore and stable memory over
120 saves, mask byte limits, 160-level stack limits, cancellation, invalid paths,
first-error preservation and bitmap limits. Existing PDF/image/vector suites
continue to exercise the same rendering through the refactored backend. The
0.61 commit dd68de3 passed all six CI jobs.


## 0.63 Public direct-glyph outline paths

The SDK can read owned 1000-em unhinted Bézier paths from an existing font face
and actual GID, including cmap-free faces. It reuses the same outline adapter
as PDF and exposes no FreeType types. Paths survive font/input destruction and
can be painted by the generic canvas or consumed by a host renderer.

The public-DLL suite checks named/nameless TrueType, CFF, cmap-free fonts,
normalization, stable repeated reads, independent path lifetime, actual canvas
pixels, empty glyphs, quadratic curves, invalid indices/GIDs and cancellation.
A shape-before/outline/shape-after check verifies that outline access preserves
normal shape advances/offsets. No runtime dependency or parallel font wrapper
was added.

The 0.62 commit f080abd passed all six CI jobs.


## 0.64 Streaming draw sinks independent of pixel output

The public draw sink carries borrowed path/style/matrix, layered images, clip
operations and clip-state/group events. A canvas supplies this sink through a
checked borrowed adapter. Partial consumers can inspect selected operations;
callbacks can stop traversal. The PDF paint adapter now emits only this generic
protocol. Raster output is a separate canvas consumer with a shared work counter.

Public canvas sink tests check disjoint clip unions, empty/no-op groups, explicit
empty clips, state save/restore, unknown state/accumulate values and poisoned
sink access. Private PDF tests inspect real vector paths and loaded glyph outlines
without creating a bitmap, verify glyph clip-group events, ignore unsupported
clip painting without loading an unnecessary host font, and stop from a callback.
Existing complete page/image pixel suites run through the same sink adapter.
The 0.63 commit dcb66ab passed all six CI jobs.


## 0.65 Open fixed-page provider documents

The public fixed-document model copies a bounded UTF-8 page directory and
geometry, accepts custom stable IDs/labels and an on-demand drawing provider,
and takes provider-context release ownership only after successful creation.
Effective page IDs are checked for duplicates with a sorted temporary index.
Geometry is validated at a representable scale so large unit multipliers do not
force preallocation or reject pages that can be rendered at a smaller scale.

Metadata queries never draw. Direct drawing emits the provider stream with a
caller transform and no implicit clip. The render helper creates a viewport,
exact page clip and generic canvas, and discards partial output after provider
failure/cancellation. Reentry is rejected, progress callbacks are guarded, and
provider errors without diagnostics are normalized. Owned-memory reporting
explicitly excludes the opaque provider payload.

A custom two-page provider test checks copied metadata lifetimes, source axes,
units/rotation, actual pixels, inspection without rasterization, no eager draw,
context release, first failed render followed by a successful retry, cancellation,
reentry rejection, invalid matrices, duplicate/default IDs, UTF-8 and size limits,
zero/nonzero unknown tails, large/tiny unit geometry and bitmap limits. No file
format is required by this test.

The 0.64 commit 8031631 passed all six CI jobs.


## 0.66 Public fixed-PDF reader and installed host example

The built-in PDF provider now connects to the public generic fixed document.
Memory opens copy source bytes; file opens adopt the UTF-8 reader buffer without
a second full-file copy. Only directory/geometry is prepared at open; page
content/fonts/images remain lazy. Optional host fonts are retained and expose
selected collection indices. Matching same-page programs share FT face references
while retaining independent PDF encoding/metric metadata. Bad embedded programs
remain errors. A failed/cancelled page discards lazy reader state, allowing the
next page to rebuild safely instead of inheriting a sticky object/stream error.

Public-DLL tests free/overwrite original bytes, render embedded text and soft
images, inspect generic paths/images, ignore unknown image codecs in partial
consumers, stop callbacks, recover from missing fonts/unsupported streams/bad
embedded programs, retain a host TTC face after its original handle is freed,
validate option tails and open malformed/oversized input. Shared-face tests close
the original wrapper before using its retained clone. The installed example
builds against only exreader.h and the installed import library/DLL and renders
Chinese-named input/output paths successfully. CI now runs the installed fixed
example on all three desktop platforms, including Windows Unicode paths.

A manual public-only client opens RFC 9110 and renders all 194 pages, with
388,306,520 aggregate RGBA bytes freed page by page. One development pass took
24.482 seconds (not the benchmark suite). The public fixed host example also
renders its 595 x 841 first page. Public search/selection/annotation data and
remaining unsupported PDF features are not claimed complete. The 0.65 commit
ed66563 passed all six CI jobs.


## 0.67 Format-independent fixed text snapshots

Owned explicit-length UTF-8 snapshots preserve embedded NUL, overlapping ranges,
multiple quads per range, source coordinates and vertical/invisible flags. The
optional provider is lazy and shares the draw reentry guard; partial failures and
cancellation discard output. Previous fixed-input prefixes remain accepted.
Tests verify copied lifetimes, UTF-8/range/coordinate/byte limits, cancellation,
provider failures, old prefixes and truncated optional function pointers.
All 53 local suites pass. The 0.66 b167c58 CI run passed all jobs.


## 0.68 Public PDF semantic text and source-space quads

The built-in provider exposes independent owned snapshots using the existing
text-only C walker. Descriptor heights (or documented estimates), declared
widths, vertical advances and nested Form transforms define logical cells.
No font rasterization or image decode is required. Content order and semantic
mappings are preserved, including ligatures, embedded NUL and non-BMP scalars.
Original public fixtures verify exact transformed corners, invisible/vertical
flags, no eager extraction, malformed-font/content failure with no partial
snapshot, recovery and snapshots outliving documents. All 53 local suites pass.
A public-only RFC 9110 client extracts all 194 pages: 456,338 UTF-8 bytes and
450,578 regions in one 0.159-second development pass (not a controlled benchmark).
The installed host example now exercises the text entry point before rendering.


## 0.69 Fixed text search, selection and geometric hits

A bounded linear KMP helper serves explicit-length fixed snapshots and existing
reflow document search. Tests cover embedded NUL, UTF-8 continuation starts,
malformed queries, empty text, 1 MiB query limits, cancellation and a repeated
1 MiB source with 64 KiB near-match queries. Selection preserves duplicate and
whole-ligature regions and discards cancelled copy output. Hit tests exercise
exact edges, tie order, distance limits, invisible filtering, skewed quads where
bounding-box hits would be wrong, and zero-area line cells. Public PDF tests
search a semantic ligature, select its one full quad and hit transformed text.
All 53 local suites pass. The 0.68 CI run passed all six jobs.


## 0.70 Page-scoped stable fixed text anchors

The existing quote/context matcher now consumes a length-delimited text view,
shared by reflow and fixed providers. New public selectors own page IDs and
explicit-length UTF-8 quotes/contexts, including NUL. Tests capture across NUL,
free the source snapshot, relocate ranges and point bookmarks, enforce page
scope, preserve ambiguity despite a matching old offset, bound contexts at 32
Unicode scalars, reject malformed host selectors, recover empty-page bookmarks
and cancel both before and during search. Public PDF ligature anchors resolve
back to the original range. Existing reflow anchor/library tests remain covered.
All 53 local suites pass; the added long-search cancellation case also passes.
The 0.69 dacd144 CI run passed all six jobs.


## 0.71 PDF library, page progress and persistent fixed notes

PDF imports retain original source and page-count extent. Fixed document lookup,
page progress, metadata and covers use the existing library. Fixed-note writes
capture selectors from the stored source, scope updates to the correct book and
respect cancellation before insertion. Quote/context BLOBs preserve embedded NUL.
Schema 3 adds a cascading fixed-note table; v1/v2 upgrades are transactional.
Public tests import malformed/valid PDFs, reject incorrect API families, retain
progress/cover edits after reopen, save ligature/NUL/page-only notes, resolve
reopened selectors, update ID aliases, reject cross-book edits and bad ranges,
backup/restore, delete and cascade. Damaged selector types/UTF-8 yield no partial
results. Migration tests verify schema versions after success and rollback and
preserve existing reflow rows; previous v1 rollback cases remain covered.
All 54 local suites pass. The 0.70 934dd91 CI run passed all six jobs.
