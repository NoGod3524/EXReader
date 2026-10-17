# Native C validation

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
