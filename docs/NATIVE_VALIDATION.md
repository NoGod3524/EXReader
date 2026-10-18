# Native C validation

Historical sections S013–S100 refer to development steps, formerly numbered
0.13–0.100. The [milestone version map](VERSIONING.md) defines the current release
numbering. Original binary versions, measurement labels, commit IDs and CI results
in the records below retain their original identities.

## S017 generic navigation and NCX

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

## S016 operation control

`native-control` passes 3555 checks. It cancels style computation, lookup work in a
long mark run, partial rendering and seekable reading, verifies cleared outputs,
then repeats successfully. A cancelled cache miss retains the prior borrowed page;
after clearing control it restores a checkpoint and matches an uncancelled pager's
pixels. Progress callbacks validate stage/count bounds and rejected pager reentry.
Source cancellation preserves failed-open ownership and permits later load retry.
All 26 local Windows CTest suites pass. The source milestone passed all six jobs at
[83a18ac](https://github.com/NoGod3524/EXReader/actions/runs/38997470863).

## S015 seekable sources

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

## S014 pagination checkpoints

`native-checkpoints` passes 3922 checks. Uncached seeks compare glyph IDs, source
ranges, exact line geometry, boxes and rendered pixels against a pager with
checkpoints disabled. Cases cover Latin ligatures, mixed Arabic/Hebrew paragraphs,
pending rowspan groups, embedded fonts, defaults, disabled/tiny budgets and invalid
settings. A backward seek from page 40 to 37 generates at most four pages with the
configured checkpoints, while the control regenerates 38. Table and bidi cases use
the same state restoration rather than a separate output path. All 24 local Windows
CTest suites pass. The preceding font milestone passed all six CI jobs at
[8ba092c](https://github.com/NoGod3524/EXReader/actions/runs/38996703264).

## S013 book fonts

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

## S018 structured EPUB export

`native-export-epub` round-trips styled tables/images, embedded font selection, EPUB 2 NCX,
EPUB 3 navigation, repeated spine entries and host-constructed Unicode paths. It compares
normalized text, linear flags, encoded non-XHTML resource bytes, navigation labels/roles/parents,
and rendered pixels after reopening. XML namespace attributes and CR/LF/tab values survive.
Missing bytes, illegal XML names, reserved paths, cancellation and package encryption metadata
fail with empty outputs. Plain text receives a generated chapter and navigation. The legacy
XML/text conversion regression remains unchanged.

## S019 rich FB2

`native-fb2` verifies original generated PNG bytes, cover designation, URI-decoded image IDs,
inline emphasis, headings, tables, note links, metadata exclusion and exact rendered pixels after
structured EPUB round-trip. Strict base64 cases include empty/full/padded/whitespace values,
invalid alphabet, noncanonical pad bits, incomplete groups, extra padding and data after padding.
Duplicate binary IDs, missing images, wrong namespaces/roots and entity declarations are rejected.

## S020 rich DOCX

`native-docx` opens an original package whose main part is outside word/document.xml.
It checks inherited/default/direct formatting, headings, bookmarks, links, a Unicode image path
with literal #/%/?, embedded dimensions, horizontal/vertical cell merges, row grid offsets,
alternate-content selection and revision/field text. Structured EPUB round-trip compares text
and exact rendered pixels. Regressions reject missing relationships/resources, traversal targets,
relationship ID collisions, invalid namespaces, style cycles and orphan merge continuations;
external image URIs remain metadata without network reads.

## S021 DOCX notes

The DOCX fixture adds repeated footnote references, an endnote, backlinks, a non-default notes
part path, separator/orphan exclusion, and an image relation that reuses a main-part ID for a
different asset. Every generated fragment resolves, resources have unique IDs, and text/rendering
survive EPUB round-trip. Missing notes, missing bodies and duplicate note IDs are rejected.
Structured export also rejects chapter/non-XHTML resource path collisions with empty outputs.

The 0.20 sanitizer job stopped at a GCC debug-build format-truncation diagnostic in relationship
path construction (before running tests). 0.21 checks the length before copying fixed path
segments, shared by main/notes parts, with no formatted truncation path.

## S022 DOCX numbering

The generated fixture verifies multilevel references, independent numId counters, continuation,
start overrides, style-derived numbering and never-restart levels. Visible labels and list nodes
survive structured EPUB round-trip with identical rendering. Additional cases cover zero,
zero-padded decimals, alphabetic rollover, subtractive Roman numerals, large-value fallback,
bullets, suppressed labels, missing definitions and unsupported numbering formats.

## S023 styled RTF

`native-rtf` verifies group-scoped bold/italic, explicit size and color, paragraph properties,
semantic underline/strike nodes, metadata exclusion, paragraph/soft breaks and exact pixels after
EPUB conversion. Invalid palette components/references and font sizes fail atomically. All 29
existing Unicode fallback cases remain unchanged and pass through the new tree adapter.

## S024 RTF pictures

PNG/JPEG cases exercise both hex and binary pict streams, twip dimensions, optional shppict,
nonshppict suppression, exact encoded bytes and identical rendered pixels after EPUB round-trip.
Malformed hex/signatures fail. A known word nested in an unknown optional destination cannot
reactivate that skipped content. The existing Unicode fallback suite remains unchanged.

## S025 RTF fields/fonts

RTF tests cover Unicode font/title metadata, default/explicit font names, scoped formatting in
external hyperlinks, internal bookmark resolution and a non-hyperlink field's visible result.
Titles, links, style requests and pixels survive EPUB conversion. Empty font names and skipped
metadata with later known destinations remain valid without leaking metadata into body text.

## S026 text decorations

`native-decoration` checks semantic/CSS defaults, ancestor propagation, user overrides,
combined lines, visible raster output, preserved OpenType flags, Latin ligature boundaries and
Arabic joining forms. Eager pages match borrowed paged/replayed output exactly. DOCX tests
verify inherited underline, direct removal and strike, then compare EPUB round-trip pixels;
RTF regressions now assert underline/strike glyph flags as well as semantic nodes.

## S027 MOBI compression

`native-mobi` uses original generated PalmDB/HUFF/CDIC fixtures: fixed/short/long codes,
multiple dictionaries, recursive phrases, UTF-8/Windows-1252, multiple records and trailer flags.
Cases reject bad tables/offsets/prefixes, missing/truncated dictionaries, phrase cycles,
65-level nesting, expansion-budget overflow, record-directory corruption and bad trailers.
PalmDOC tests distinguish valid in-record overlap from invalid cross-record references.


## S028 KF8 reconstruction

`native-kf8` checks two-chapter SKEL/FRAG assembly, multiple data INDX records,
multiple control bytes, TAGX byte-length prefixes before value payloads, repeated insertions,
zero-fragment skeletons, unsplit XHTML and FDST auxiliary streams. Chapter paths, structure,
resource bytes and text survive structured EPUB round-trip. Corrupt headers, total counts,
IDXT offsets, masks, VWI, fragment bounds/order, unsupported ORDT, orphan indexes, malformed
XHTML and truncated/gapped FDST fail atomically.


## S029 KF8 assets

`native-kf8` includes PNG/JPEG reuse, transitive/cyclic CSS resource references, inline CSS,
untouched comments/string literals/body text, and FONT flag combinations 0/1/2/3. Recovered
font bytes equal the original geometric font, layout selects that font and CSS color, and
rendered pages match EPUB round-trip pixels. Cases reject malformed/overflowing/out-of-range
Base32 URIs, conflicting MIME types, bad signatures, FONT flags/offsets/keys/size, compressed
corruption/trailing bytes and oversized font declarations. The suite totals 290 checks.


## S030 KF8 positions

Tests verify cross-chapter/return links, targets inside start tags, chapter-top fallback,
legacy named anchors, XML IDs, duplicate IDs in different chapters and URI-escaped Unicode IDs.
Every translated target resolves to the same chapter/anchor after EPUB round-trip. Malformed
prefixes/separators, missing numbers, overflow, invalid fragment/offset bounds and duplicate
IDs within a chapter fail atomically. Position offsets come from the shared XML parser's
64-bit source byte index and never replace public normalized text offsets.

The 0.29 sanitizer run found a test-only over-read: binary CSS returned by the resource API
was passed directly to strstr. Commit a1ab85a copies and explicitly terminates test strings;
the binary resource API continues to return an exact byte array without a terminator contract.


## S031 KF8 authored navigation

The 582-check KF8 suite verifies a three-level authored NCX with explicit and derived parent
relationships, multiple CNCX records, escaped Unicode/quote/ampersand labels, stable part/anchor
targets and matching navigation after structured EPUB export and publication loading.
Document navigation snapshots remain readable after the source document is released; empty
and invalid-output cases are checked. Invalid title keys, level jumps, parent/child ranges,
leaf declarations, targets, CNCX lengths/padding/counts fail atomically.

Both the sanitizer repair (a1ab85a) and the 0.30 feature commit (42e362f) passed all six CI jobs,
including AddressSanitizer/UndefinedBehaviorSanitizer.


## S032 hybrid MOBI/KF8

Tests read declared hybrid boundaries with chapter reconstruction, authored navigation,
all/partial/no shared assets and HUFF text records. Font bytes, image reuse and EPUB rendering
remain unchanged; legacy text is excluded. Explicit absent boundaries retain legacy decoding.
Malformed EXTH signatures/lengths/counts/entries/duplicates, boundary pointers/markers,
target versions/encryption and shared-resource starts fail atomically. Legacy fallback rejects
unsupported encoding/compression even after successful optional EXTH parsing.


## S033 KF8 guide landmarks

Fixtures cover combined TOC/landmarks, guide-only chapter fallback, tag 3 and tag 6 offset
forms, shared hybrid containers, thumbnail suppression, normalized start types and preserved
custom type metadata. Navigation roles/labels/targets survive EPUB conversion independently of
role grouping order. Missing strings, invalid targets/types and invalid XML characters fail;
a 9998-guide + 2-chapter book reaches exactly 10000 navigation entries, while 10000 guides plus
chapters returns EXR_LIMIT.

The 0.32 commit e8aa242 passed all six CI jobs, including sanitizers and Apple/Android builds.


## S034 KF8 SVG resources

The 1231-check KF8 suite adds SVG/XLink names, unnamespaced/foreign extensions, CDATA CSS,
style attributes, unchanged literal text, CSS/SVG dependency cycles and URI fragments.
An independent Expat parse checks expanded names and translated references. A host test decoder
uses the SVG's resolved embedded PNG to exercise the existing decoder contract, font selection,
release ownership and matching rendered pages after EPUB export; it is not a vector renderer.
Malformed XML/roots/namespaces/entities/references/fragments fail atomically.

The 0.33 commit be7bdc1 passed all six platform and sanitizer CI jobs.


## S035 ORDT and external KF8 validation

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


## S036 MOBI/KF8 metadata

Tests cover UTF-8 updated titles, Windows-1252 full names, NUL suffix padding, repeated/empty
updated values, unreferenced and reused covers, legacy MOBI and modern/legacy hybrid fallback,
modern metadata overrides and an explicit absent cover. Titles and cover image data remain
usable after EPUB conversion; an in-memory library import adopts the parsed title. Invalid
header title ranges/lengths, UTF-8/internal NUL, oversized titles, cover indexes/types/lengths
and conflicting duplicate cover declarations fail atomically.

The external Gutenberg file also opens and passes text/navigation/nonchapter-asset round-trip
with its newly parsed title and cover metadata. Its EPUB output byte size changes as metadata
is now included. The 0.35 commit fdcc9e4 passed all six CI jobs.


## S037 library cover import

`native-cover-import` adds 97 checks for EPUB, FB2 and KF8 source covers, user title overrides,
whitespace-separated property tokens, exact copied bytes, retained original source blobs,
the exact 8 MiB boundary, a larger original cover and a misleading non-cover property name.
A missing declared cover aborts without adding a database row or returning a book ID.
The deterministic ZIP fixtures use the project's original PNG and fixed metadata.

The 0.36 commit 82d4270 passed all six platform and sanitizer CI jobs.


## S038 positioned layout foundation

`native-positioned` checks exact raster equality when an existing text layout is reconstructed,
paint-order occlusion, proportional scaling/letterboxing, hit tests, source-array/document/font
release, image sharing and host release callbacks, fontless image/blank pages, multiple page
ranges, cancellation, allocation accounting and input extension rules. Invalid spans, UTF-8
boundaries, NaN/Inf, indexes and array budgets fail atomically. A new original geometric font
checks oversized glyph bitmap rejection before raster allocation. All existing reflow/paged
rendering suites continue to pass after sharing the image and raster primitives.

The 0.37 commit 10d81b3 passed all six platform and sanitizer CI jobs.


## S039 PDF object foundation

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


## S040 PDF cross-reference and object streams

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


## S041 PDF filter pipelines and predictors

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


## S042 native PDF LZW

A bounded C LZW decoder adds clear/end codes, 9..12-bit widths, both EarlyChange modes,
full-table handling and the code-equals-next case. Its output uses the same filter pipeline,
TIFF/PNG predictors, temporary-memory accounting and work budgets. Original fixtures cover
literal-only width boundaries through a full dictionary, dictionary references, long repeated
runs, table resets, empty data, PNG prediction and malformed codes/terminators/parameters.
The fixture compressor uses string dictionaries and emitted-code counts, independently of
the reader's prefix/suffix representation. PDF page reading is still unconnected.


## S043 PDF page tree and content assembly

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


## S044 PDF content operand lexer

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


## S045 PDF ToUnicode CMaps

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


## S046 PDF font descriptions and declared metrics

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


## S047 PDF text state and glyph geometry

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


## S048 recursive PDF Form text

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


## S049 glyph-only font input

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


## S050 native vector scan conversion

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


## S051 native path flattening

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


## S052 native stroke outlines

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


## S053 native dash geometry

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


## S054 PDF drawing events and vector integration

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


## S055 PDF encoding facts and standard font metrics

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


## S056 PDF glyph selection and native outline rendering

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


## S057 Native PDF text/vector page raster backend

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


## S058 Packed PDF images and affine image painting

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


## S059 Terminal JPEG filters and PDF JPEG rendering

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


## S060 Indexed images, independent opacity layers and image mattes

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


## S061 Generic page viewports and PDF page raster coordinates

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


## S062 Public immediate canvas shared by the PDF backend

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


## S063 Public direct-glyph outline paths

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


## S064 Streaming draw sinks independent of pixel output

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


## S065 Open fixed-page provider documents

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


## S066 Public fixed-PDF reader and installed host example

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


## S067 Format-independent fixed text snapshots

Owned explicit-length UTF-8 snapshots preserve embedded NUL, overlapping ranges,
multiple quads per range, source coordinates and vertical/invisible flags. The
optional provider is lazy and shares the draw reentry guard; partial failures and
cancellation discard output. Previous fixed-input prefixes remain accepted.
Tests verify copied lifetimes, UTF-8/range/coordinate/byte limits, cancellation,
provider failures, old prefixes and truncated optional function pointers.
All 53 local suites pass. The 0.66 b167c58 CI run passed all jobs.


## S068 Public PDF semantic text and source-space quads

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


## S069 Fixed text search, selection and geometric hits

A bounded linear KMP helper serves explicit-length fixed snapshots and existing
reflow document search. Tests cover embedded NUL, UTF-8 continuation starts,
malformed queries, empty text, 1 MiB query limits, cancellation and a repeated
1 MiB source with 64 KiB near-match queries. Selection preserves duplicate and
whole-ligature regions and discards cancelled copy output. Hit tests exercise
exact edges, tie order, distance limits, invisible filtering, skewed quads where
bounding-box hits would be wrong, and zero-area line cells. Public PDF tests
search a semantic ligature, select its one full quad and hit transformed text.
All 53 local suites pass. The 0.68 CI run passed all six jobs.


## S070 Page-scoped stable fixed text anchors

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


## S071 PDF library, page progress and persistent fixed notes

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


## S072 Codec-independent audio timeline and text synchronization

Immutable owned audio metadata retains arbitrary host URI/media types and part
IDs. Tracks concatenate with checked uint64 durations; chapters may nest or
cross tracks and synchronization intervals may overlap. Boundary/EOF location
uses binary search. Time-to-text and text-to-time enumeration preserve provider
order and support cancellation without allocation. Tests overwrite input strings,
inspect copied tables, locate track boundaries and EOF, enumerate overlapping
intervals, query point ranges, preserve UINT64_MAX duration, reject overflow,
invalid parents/UTF-8/IDs/ranges/counts, exercise cancellation and extension tails.
This is timeline/sync data, not an audio decoder or device playback backend.
All 55 local suites pass. The 0.71 792076e CI run passed all six jobs.


## S073 Host playback commands, generations and stable resume points

A retained audio player lazily dispatches transport/rate commands to a host
backend, preserving independence from codecs and devices. Tests verify no eager
open, independent timeline lifetime, correct command sequences for seek/pause/
speed/EOF, cross-track continuation, restart, snapshot reads during callbacks,
mutating reentry rejection, no-op generation stability, stale/backwards report
rejection and invalid restore/rates. A failed rate change triggers best-effort
pause and a reload before recovery while preserving confirmed state. Stable
track-ID resume survives inserting an earlier track and remains paused. Backend
release ownership and close behavior are checked. These are controlled-backend
tests, not actual operating-system audio playback validation.
All 56 local suites pass. The 0.72 b6b31d7 CI run passed all six jobs.


## S074 Native bounded random-access WAVE PCM decoding

The C RIFF reader scans headers, skips payloads and reads samples with a 4 KiB
buffer. Public tests verify unsigned 8-bit, signed 16/24/32-bit, float 32/64-bit,
extensible valid bits/channel masks, normalization and clipping. A sparse virtual
source larger than 4 GiB opens with fewer than 32 short reads and seeks directly
to its final sample. Other cases cover file opening, source ownership, short-read
retries, overreported/failed source reads, UTF-8 file API reuse, malformed format/
RIFF/alignment, non-finite samples, EOF zeros, cancellation and reentry rejection.
The common file-source reader now uses native 64-bit seeks; publication opens
retain their original byte limit. No compression codec or device playback is
claimed by these tests.
Additional cases verify data-before-format, unknown odd-sized chunk padding,
duplicate formats, invalid extensible GUIDs and cancellation after PCM output
has already begun. All 57 local suites pass, including the expanded WAVE checks.
The 0.73 de65c24 CI run passed all six jobs.


## S075 Persistent audio resume points and time bookmarks

Independent host audio keys persist stable track IDs, uint64 offsets and rates.
Offset BLOBs retain UINT64_MAX without signed-integer truncation. Tests save,
update, reopen and backup/restore data; verify ID aliasing, per-key update scopes,
labels, empty results and invalid input; reject damaged offset/UTF-8 records
without partial output. A failing delete trigger proves clear_audio rolls back
the already-deleted resume row together with bookmarks. Schema 4 upgrades v1/v2
through existing migration tests; v3 tests verify successful upgrade and rollback
after the first new table was created. Saved time is validated against a concrete
timeline when restoring the player, rather than opening files during persistence.
All 58 local suites pass. The 0.74 a0ddece CI run passed all six jobs.


## S076 Standalone installed-SDK WAVE host example

The public-only decoder example scans an original 3200-frame 16 kHz mono PCM
fixture in bounded batches and reports its expected 0.5 peak. The fixture is
reproducible with Python standard-library math/struct/wave. CTest checks decoded
frame count and peak. Installed host builds include the example and desktop CI
runs it separately from engine build files; Windows also uses a Chinese filename.
All 59 local suites pass. An independent installed-SDK build compiles all host
examples, decodes the Chinese-named WAVE fixture to the expected 3200 frames /
0.5 peak, and runs the public PDF text/render example. The 0.75 c8f07c3 CI run
passed all six jobs.


## S077 Swift C module and owned host wrappers

The installed C module exposes the full public API. ARC wrappers retain native
PDF/font/text/WAVE handles and copy output data; mutable document and WAVE calls
are serialized per object. The Swift smoke client checks PDF page/text/render
results, native error propagation, embedded-NUL/Unicode snapshots, exact UTF-8
ranges, host TTC lifetime and partial-EOF PCM reads. Desktop macOS CI builds and
runs against the installed dylib; Apple mobile CI typechecks the wrapper against
separate device and simulator SDK headers. Actual iOS device execution is not
covered by typechecking.
All 59 Windows-native suites pass. The 0.76 333f2e2 CI run passed all six jobs.
Apple-specific Swift validation is performed by the new CI steps.
The 0.77 f5e92f1 CI run passed all six jobs, including actual macOS Swift
execution and device/simulator Swift typechecks.


## S078 Optional JNI adapter and owned Java host API

Java AutoCloseable handles serialize operations and prevent duplicate close/use
after close. JNI copies PDF/font inputs into the C model and returns independent
pixel/text/region/PCM arrays. Text remains standard UTF-8 bytes, preserving NUL
and supplementary scalars; file paths use validated UTF-16 to standard UTF-8.
The desktop JVM smoke client checks original-array disposal, font collection
selection, post-close snapshot lifetime, native error codes, duplicate closes,
Unicode/supplementary filename PCM reads and invalid ranges. CI enables optional
JNI on three desktops, runs the installed adapter with -Xcheck:jni and builds the
Android ARM64 adapter. Android device execution is a separate pending check.
All 59 Windows core suites pass with the optional JNI dependency disabled.
Desktop JVM and Android JNI checks run in the newly enabled CI configuration.
The 0.78 2aa97a9 CI run passed all six jobs. JNI smoke tests ran on Windows,
Linux and macOS with -Xcheck:jni, and the Android JNI library compiled.


## S079 RTF row and cell document structure

RTF row/cell controls produce generic table nodes, retaining empty cells, multiple
paragraphs, inline styling and declared cell boundaries. Tests inspect two
separate tables, trailing row definitions and a 20-row paginated document;
structured EPUB roundtrips compare text and every rendered page. Malformed row
sequences, definition counts/order, nested/merge controls and the 256-column
limit are checked. Optional destinations and Unicode fallback must not execute
table controls. Complex merged/nested tables remain explicitly unsupported.
All 60 local suites pass. The 0.78 JNI/Swift/desktop/mobile CI run passed all six jobs.


## S080 RTF horizontal, vertical and rectangular cell merges

Physical continuation cells are retained as generic content containers in the
merged owner, using standard colspan/rowspan and rebuilt parent/sibling links.
Empty continuation containers do not add visible blank paragraphs. Tests cover
horizontal content retention, vertical continuation with an empty physical row,
rectangular merges, parent ordering and hidden empty containers. Structured EPUB
roundtrips compare text and rendered pixels. Orphan continuations, conflicting
flags, changed boundaries, omitted definitions, interrupted vertical chains and
cross-table continuation are rejected.
All 60 local suites pass. The 0.79 c0c9808 CI run passed all six jobs.


## S081 RTF footnote/endnote structure and reference backlinks

Detached note nodes collect styled paragraphs/images independently from body or
parent table cells, then append after the main flow. Reference and backlink roles
resolve to stable document IDs; endnotes retain their distinct semantic role.
Tests inspect main-text order, note roles, parent ordering, links in both
directions, cell restoration, images inside notes and the 10000-note budget.
EPUB roundtrips compare normalized text and every rendered page. Nested notes,
tables inside notes, dangling/repeated markers and skipped destinations are
checked. Numbering uses source occurrence order; page-bottom placement and custom
RTF numbering schemes are outside this stage.
All 61 local suites pass. The 0.80 adfd228 CI run passed all six jobs.


## S082 RTF semantic list hierarchy and retained display labels

Modern ls/ilvl paragraphs and legacy pntext markers produce generic lists/items
without duplicating source labels. Tests inspect nested levels, bullet and legacy
markers, presentation-only labels, level-jump containers and list continuation
after a footnote. Cell-local lists remain independent. Structured EPUB roundtrips
compare normalized text and every rendered page; malformed IDs/levels are rejected.
Counter/listoverride definitions without supplied display labels remain pending.
All 62 local suites pass. The 0.81 fd411e4 CI run passed all six jobs.


## S083 RTF numbering definitions and automatic labels

Tests cover independent overrides, decimal continuation, supplied labels without
regeneration, Roman/letter/zero-padded formats, nfcn priority, multi-level legal
references and higher-level reset/norestart. Start-only and format-only overrides,
bullets, absent numbering, literal semicolons, signed minimum IDs/negative starts,
and 59/128/255-byte leveltext positions exercise metadata decoding. Mixed list
level types retain correct ol/ul containers even when entering at a deeper level.
Marker bold/size is independent of body styling; explicit zero indentation wins
over list defaults. EPUB roundtrips compare normalized text and every page pixel.
Malformed templates, duplicate metadata, missing override values, excessive levels,
unsupported formats without labels, int32 lexer overflow, hex NUL in body and
counter overflow are rejected. Shared numbering code also passes DOCX regression.
All 63 local Windows suites pass. The 0.82 0c311d8 CI passed all six jobs.


## S084 Structured HTML directory archives

The HTML exporter shares chapter serialization and path/resource validation with
EPUB, writes all chapters and assets into an ordinary ZIP, and returns an owned,
collision-free XHTML entry path. The entry includes reading order, nested NCX
navigation and links to authored EPUB navigation. Tests validate XHTML with Expat,
compare all chapter/member bytes against structured EPUB, and additionally compare
non-XHTML assets directly against source resource bytes. Fixtures include images,
embedded fonts, CSS, EPUB 2/3 navigation and repeated chapter paths. Custom models
cover XML escaping, entry-path collision, generated chapter paths, invalid names,
missing resources and early/final-progress cancellation. Encrypted/obfuscated
package export fails with empty outputs. All 64 local Windows suites pass.
The 0.83 4973ea6 CI passed all six jobs.


## S085 Opt-in atomic exact-source deduplication

Unique import compares complete original BLOBs after format/length filtering and
returns the oldest matching row without changing its metadata. Tests retain edited
title/progress/favorite, cover and notes; ordinary import still allows intentional
copies. Changed bytes and different formats remain distinct. Shared-connection and
two-connection worker threads each produce one created row and one reused ID.
Invalid PDF input, forced INSERT failure and deferred-foreign-key COMMIT failure
leave no added rows or output IDs, and subsequent operations succeed. PDF binary
sources, backup/reopen, reuse after deleting the oldest copy, invalid stored IDs,
invalid arguments and the source byte limit are covered. No schema migration,
new digest implementation or mandatory index is added. All 65 local Windows suites
pass. The 0.84 8292325 CI passed all six jobs.


## S086 Chapter-local CFI content paths

The native XML-tree path implementation counts child elements separately from
potentially empty character-data chunks, merging adjacent text nodes logically.
Tests verify literal CFI strings with escaped IDs, XML IDs, raw whitespace,
supplementary Unicode/UTF-16 surrogate interiors, element child boundaries, empty
chunks, virtual first/last elements, implicit zero offsets, side bias and unique
ID correction. Duplicate IDs fail during correction rather than guessing. Text
nodes across layout/font/navigation EPUB fixtures roundtrip through canonical
paths at both endpoints. Invalid grammar, leading-zero/overflow integers, excessive
offsets, malformed escapes, unsupported suffixes, missing IDs, byte budgets,
invalid UTF-8, invalid arguments and cancellation clear outputs. All 66 local
Windows suites pass. The 0.85 713c2a8 CI passed all six jobs.
This is a content-path building block; full package CFIs and text assertions are
separate work, rather than synthesized from assumed spine positions.


## S087 Original-package full point CFIs

Full CFI creation/resolution reads the original OPF on demand and reuses the DOM
path engine. The synthetic package places spine at element 10 and adds a spine
extension before itemrefs, proving neither /6 nor child ordinal shortcuts are
assumed. Duplicate references to the same resource, linear=no, package/content ID
correction and supplementary UTF-16 offsets roundtrip. Five existing EPUB fixtures
exercise full point CFIs through each spine chapter. Auxiliary chapters and partial
publication-load snapshots are rejected as complete spine mappings. Malformed
wrappers, non-spine/virtual/biased package targets, repeated indirection, unsupported
range syntax, missing IDs, excessive offsets and cancellation clear outputs.
All 66 local Windows suites pass. The 0.86 5db01d0 CI passed all six jobs.


## S088 Indexed publication point CFIs

The indexed EPUB provider routes through original package metadata before loading
only the target chapter. A fixture with a malformed second spine XHTML fails an
eager whole-document open but successfully creates/resolves a CFI into its first
chapter. Addressing the damaged chapter fails atomically. Tests cover repeated
spine parts, returned-snapshot lifetime after publication disposal, rejection of a
snapshot from another archive instance, callback reentry, cancellation and custom
providers without an EPUB package. Generic local paths remain independently usable.
All 66 local Windows suites pass. The 0.87 27746e4 CI passed all six jobs.


## S089 Simple CFI ranges and point-context range starts

Range generation extracts a common sequence of complete steps and emits P,S,E.
Tests cover same-text/zero-length/cross-spine ranges, literal canonical output,
UTF-16 offsets, escaped assertion commas and numeric 2-before-10 ordering.
Resolution corrects both endpoints through IDs before validating order, including
an intentionally reversed-looking stale itemref pair. Biased endpoints, reversed
ranges, offset-bearing parent paths, missing/extra separators and cancellation
fail atomically. Full document and indexed-publication point resolvers accept a
range's start; a range ending in a damaged unrelated chapter still resolves its
valid start without loading the other chapter. All 66 local Windows suites pass.
The 0.88 2135309 CI passed all six jobs.


## S090 CFI text assertions and quoted point creation

Text assertions validate a collapsed XML-whitespace view spanning inline elements;
stale or out-of-range text offsets recover only through a unique complete context.
Tests cover preceding/following/both contexts, empty XML, raw whitespace boundaries,
UTF-16 supplementary text, cross-element contexts, escaped punctuation, preserved
side bias, missing/ambiguous correction and a direct valid match amid repetitions.
Quoted local/full/indexed-publication APIs capture bounded Unicode-scalar context.
Inserting text before the target still resolves to the intended DOM location.
Surrogate-interior capture, invalid context limits and invalid side values fail;
bare point CFIs continue to represent UTF-16 interiors. Cancellation occurs while
building the assertion view. No per-character position map or resident cache is
created. Full CFI and ordinary/range regression suites remain passing.
All 67 local Windows suites pass. The 0.89 ab8550e CI passed all six jobs.


## S091 ABI epoch and relocatable installed CMake package

ABI epoch 1 is exported at runtime and documented with fixed array strides,
size-versioned prefixes, ownership, callback and synchronization rules. A C consumer
compiled with the original fixed-provider input prefix still creates/reads a fixed
document and observes no optional text provider. All 68 local Windows suites pass.
The installed SDK config exports only the public shared target and include path;
all ten C host examples build independently through find_package. Compat, PDF and
WAV hosts run against that installed SDK. Copying the SDK to a different directory
with spaces and configuring a new consumer still succeeds, and an independent
C++17 consumer links the C ABI and exercises document ownership. Desktop CI now
builds/runs the imported-target C and C++ consumers on all three systems.
The 0.90 fb49403 CI passed all six jobs.


## S092 Optional generic persistent text index

SQLite FTS5 case-sensitive trigrams select candidates; the shared C KMP prefix
builder supports an incremental literal byte matcher with overlapping results.
Tests cover empty indexes/parts, source filters, Chinese one/two/three-scalar
queries, emoji, accents/case, quoted punctuation, spaces, embedded-NUL queries
and matches after NUL. A 128 KiB repeated-prefix source exercises streaming
continuation without rebuilding the pattern table per hit. Active-query write
rejection, a concurrent WAL writer with a stable read snapshot, retained query
lifetime after owner close and persistence/reopen are checked. Forced INSERT and
deferred-FK COMMIT failures retain the previous index; part/source deletion,
corrupt UTF-8, invalid input/byte limits and cancellation clear outputs. Index
schema validation/creation occur under a write transaction and reject an ordinary
book library. All 69 local Windows suites pass. A separate index-disabled build
passes availability/open checks and still opens a TXT document. Release DLL sizes
for this local compiler configuration are 4,073,866 bytes enabled and 3,810,969
bytes disabled; these are binary-size observations, not open/RSS benchmarks.
The 0.91 7dc8d8a CI passed all six jobs.


## S093 Atomic streaming source replacement

The callback provider recycles and poisons its previous part buffer before loading
the next part, exercising borrowed-input lifetime without retaining all chapters.
Tests confirm all parts commit together while newly opened independent WAL readers
continue seeing the old complete source. Reentry into the writer is rejected.
Duplicate IDs, provider failure/error detail, invalid found flags, oversized text,
invalid UTF-8, missing bytes and cancellation at final progress preserve the old
source; empty replacement clears only its selected source. Active queries prevent
replacement before any provider calls. The installed SDK's new search example
loads one EPUB chapter at a time and streams matches; all eleven C consumers build
independently, and the search host returned 20 bounded matches from layout.epub.
All 70 local Windows suites pass. The 0.92 891f818 CI passed all six jobs.


## S094 Stored reading-position selectors and schema 5

A host-captured point selector and numeric position commit atomically without
reparsing the source on each update. Tests resolve saved context after reopen and
backup, preserve it across metadata-only edits and unique-source reuse, and clear
it after legacy numeric-position changes. INSERT and deferred-COMMIT failures
restore both old position and selector. Invalid input, malformed stored UTF-8,
inconsistent saved positions, missing books and fixed-page unit mismatches fail
without partial outputs. Source deletion cascades saved selectors. A conflicting
v4 migration trigger rolls back the newly created table and version; successful
v1/v2/v3/v4 upgrades preserve old rows and expose unanchored progress as LEGACY.
All 71 local Windows suites pass. The 0.93 1d30b03 CI passed all six jobs.


## S095 Transactional book reprojection and relocation

The relocation suite checks unique annotation/point recovery after a shifted,
shortened source projection, retained missing/ambiguous/legacy selectors, and
later recovery from unresolved state. Public unresolved ranges are SIZE_MAX;
comments and historical selector ranges survive reopen and backup. Comment-only
edits work without resolving a range. Invalid UTF-8 inputs/stored comments and
fallbacks inside UTF-8 continuation bytes fail. The original source blob remains
byte-identical. Triggered writes, deferred-COMMIT failure and final-callback
cancellation restore all old notes and progress. A conflicting v5 migration table
rolls back table/trigger/version changes; retry preserves progress and upgrades to
schema 6. Existing v1-v4 migrations continue passing. All 72 local Windows suites
pass. The 0.94 695d092 CI passed all six jobs.


## S096 Text annotation interchange

The new native-annotation suite round-trips quoted UTF-8 selection, plain-text
comments, optional identifiers and context through compact Web Annotation JSON,
then resolves the imported unpositioned selector in a document. Tests cover all
truncated prefixes, reordered/escaped keys, surrogate pairs, control escapes,
unknown metadata, JSON number grammar, duplicate recognized fields, altered
contexts, unsupported target constraints/types, invalid UTF-8, NUL/lone surrogate,
trailing data, nesting and output byte budgets. All 73 local Windows suites pass.
All eleven C consumers build against the independently installed 0.96 SDK; the
anchor host exchanges JSON before relocating a quote after an insertion, and the
compat host verifies ABI epoch 1. The 0.95 a0a50a1 CI passed all six jobs.


## S097 Lazy generic fixed metadata and PDF Info

An owned generic UTF-8 key/value snapshot preserves duplicate keys and survives
provider/document release. Tests check legacy input prefixes, truncated callbacks,
reentry, provider error detail, invalid counts/pointers/UTF-8, cancellation and the
aggregate 8 MiB budget. Original in-memory PDFs exercise indirect Info strings,
PDFDocEncoding special characters, UTF-16BE/surrogates, BOM UTF-8, explicit null,
xref streams and inherited/replaced/removed Info across incremental revisions.
Malformed metadata can fail repeatedly while page rendering still succeeds; field
byte limits and null indirect references are covered. PDF library import obtains
title/author, preserves host title precedence and creates no row on metadata
failure. All 74 local Windows suites pass. The 0.96 17a826d CI passed all six jobs.


## S098 Shared XMP extraction and PDF metadata merge

The metadata suite now parses independent UTF-8/UTF-16 XMP, namespace aliases,
Description attributes, simple/empty literals, ordered duplicate Seq/Bag values,
x-default preference and first-language fallback. Structured properties discard
all partial values. Tests reject malformed XML, DTD/entity declarations, named
subjects, mixed container text, duplicate defaults, excessive nesting/value count,
large literals/packets and namespace-expanded aggregate allocation. Cancellation
at start/final progress clears outputs. PDF fixtures cover both raw and Flate XMP
streams overriding Info keys while retaining other Info fields; malformed packets
leave page rendering available. Library import retains XMP title precedence and
joins multiple authors. All 74 local Windows suites pass. The 0.97 07d952f CI
passed all six jobs.


## S099 Swift and Java metadata consumers

Swift and JNI now copy metadata into owned language strings, preserving repeated
keys and order. Expanded host checks exercise supplementary-plane Unicode,
multilingual text, multiple authors, 4096 duplicate properties, invalid packets,
cleared input buffers and closed PDF handles. JNI conversion releases per-entry
local references and keeps standard UTF-8 transport. All 74 local Windows core
suites pass; the new language-host cases are verified by the platform CI jobs.
The 0.98 520db83 CI passed all six jobs.


The 0.99 Swift fixture variable collision was corrected in 5e0d2d9; all six CI
jobs passed, including real Swift/macOS and JVM runs with 4096 multilingual
metadata values, Android JNI builds and Apple device/simulator typechecks.
Independent installed C and C++ consumers also passed locally. Nine fresh-process
0.99 Windows 11 / Arial paged measurements (three runs per fixture, eight page
samples) produced these medians; OS disk cache remains uncontrolled:

| Text-only EPUB fixture | Publication open ms | First visible ms | Turn p95 ms | Process peak MiB |
| --- | ---: | ---: | ---: | ---: |
| 16 KiB short | 2.310 | 15.879 | 12.300 | 10.86 |
| 1 MiB single paragraph | 4.183 | 29.629 | 14.266 | 13.04 |
| 32 chapters, 32 KiB each | 2.534 | 18.328 | 16.356 | 10.97 |

These measure the first reading-order part and do not characterize complex PDF,
image-heavy books or metadata parsing. Local Release DLL: 4,110,947 bytes.

## S100 Generic page annotation snapshots and native PDF annotations

Original in-memory PDFs cover indirect annotations/strings, null/unknown
references, normalized rectangles, raw QuadPoints, multilingual comments, missing
names, and five common text properties. Snapshots survive document release.
Invalid subtypes, geometry shapes/types/ranges, non-string comments, overlong
lists and the aggregate 8 MiB budget return no partial output; page rendering and
retry remain available. A custom provider verifies independent copies, reentry,
errors, invalid UTF-8/nonfinite coordinates, overflow-sized quads, truncated input
extensions, absent providers and empty results. Legacy metadata-capable input
layout is checked. All 75 local Windows suites pass.


## Milestone 0.18.0: version consolidation

Current product declarations, runtime version and installed CMake metadata use
0.18.0. Historical development steps S013-S100 map to milestones 0.13-0.18;
original commit/build/measurement identities remain intact. No engine behavior,
ABI epoch or database schema changed. The native ABI check passes. All eleven
installed C examples build, and installed C compatibility and independent C++17
consumers report 0.18.0 / ABI 1. EXACT package selection rejects a preserved
historical 0.99.0 SDK, preventing its larger old number from winning selection.


## Milestone 0.18.0 development: PDF annotation editing and appearances

The product version remains 0.18.0. The new `native-pdf-write` suite covers
Text/Highlight creation, NM-based updates across multiple revisions, removal,
independent no-match copies, Popup links, direct/indirect annotation dictionaries,
nonzero generations, classic xrefs, xref streams and object streams. It checks
byte-identical original prefixes, Root/Info/ID preservation, unchanged nested
unknown fields, raw binary strings/names, multilingual text and supplementary
characters, original QuadPoints order, rendered output and metadata after reopen.
Unknown real-number spellings remain stable across repeated edits.

Writer boundary cases cover duplicate NM, unsupported kinds/properties, invalid
UTF-8, nonfinite/zero-area/oversized geometry, degenerate or out-of-bounds quads,
invalid options, UTF-8 and encoded UTF-16BE string limits, cancellation and clear
failure outputs. The writer limits encoded strings, including the BOM, to 64 KiB
as well as limiting UTF-8 input to 64 KiB. Supported writes require a PDF header
of 1.4 or newer; removal does not add that version restriction. Each annotation
is limited to 32768 quads, matching the parser's 262144 array-item limit.
Permission-constrained
catalogs are rejected for actual edits. Incremental removal preserves historical
bytes and is not secure erasure; SDK library notes are not automatically synced.

The `native-pdf-appearance` suite covers direct and state-selected normal Forms,
Rect/BBox/Matrix mapping, reversed rectangles, shear/rotation, bounding-box clips,
nested Forms, own/inherited resources, visibility flags, missing appearances,
page/annotation graphics-state isolation and generic drawing callbacks. Malformed
geometry/resources/Form types, unsupported transparency groups, too many
annotations, cancellation and recovery on another page are exercised. NoZoom,
NoRotate and Form Group appearances remain unsupported.

The object suite additionally checks active indirect identities, reference-preserving
serialization, binary name/string escaping, top-level dictionary filtering,
stream rejection, exact signed integer limits, failure rollback and decimal
formatting across finite double boundaries and available numeric locales.

All 77 local Windows suites pass, including the corrected annotation syntax
regression and the final writer/appearance/object checks. The writer suite makes
492 assertions. Independently installed pypdf (strict parsing with its numeric
token limit raised for the deliberately huge retained REAL fixture) verifies
the output dictionaries, generations, Unicode strings, binary ID and Form
resources. PyMuPDF renders red/0.5 as (255,128,128) and yellow/0.35 as
(255,255,166); overlapping highlight quads retain the same alpha as a single
quad, matching EXReader pixels. These are development checks, not runtime
dependencies. The installed Windows SDK also passes an independent C++17 host.

Commit `5ff51c3` passes all six jobs in
[CI run 39055589599](https://github.com/NoGod3524/EXReader/actions/runs/39055589599):
Windows, Linux and macOS runtime suites and installed host consumers;
ASAN/UBSAN; Android ARM64 compilation; iOS/iPadOS device and simulator
compilation with Swift type checking. Mobile compilation does not establish
device runtime or application validation. Product version 0.18.0, ABI epoch 1
and library schema 6 remain unchanged.


## Milestone 0.18 development: line markup, Unicode line breaking and audio

The local Windows integration run passes all 81 suites. Unicode 17 default UAX
#14 passes all 19,338 official raw line-break cases; the public/layout map also
passes the UAX #29 intersection, suppressing 1,388 grapheme-internal opportunities.
The existing 766 grapheme cases, cross-style lookahead and page continuation
regressions pass. Pinned tables regenerate byte-for-byte with standard Python,
without runtime dependencies.

Line-markup tests cover native Underline/StrikeOut/Squiggly creation, updates and
removal; Z/perimeter/reversed-order quads, vertical orientation, overlap alpha,
invalid diagonal edges, cancellation and bounded path complexity. Independent
PyMuPDF 1.28.2 confirms subtype, raw quads and visible line positions.

FLAC tests build original bitstreams for every supported predictor, residual,
bit depth and stereo family, including 33-bit side channels, CRC failures,
seek points, sparse retry, unknown duration, cancellation and source ownership.
The generic PCM test covers custom providers and WAV; the FLAC suite checks
PCM dispatch and length discovery. Independent FFmpeg-encoded original mono,
stereo and 8-channel inputs compare correctly; 120 truncation/bit-flip development
checks finish without crashes. FFmpeg is not a production dependency.

Native audio output tests validate contracts without touching devices. Actual
Windows, Apple, Android and Linux hardware playback remains manual validation.
This batch requires a fresh cross-platform CI run; product version remains
0.18.0, ABI epoch 1 and library schema 6.


Commit `3b27c84` passes all six jobs in [CI run 39056812314](https://github.com/NoGod3524/EXReader/actions/runs/39056812314): desktop runtime/SDK/JNI/Swift, ASAN/UBSAN, Android and Apple mobile compilation.

## Milestone 0.18 development: gapless MP3, visible soft hyphens and PDF metadata

MP3 fixtures are original FFmpeg-encoded short waveforms embedded in the test,
not upstream copyrighted test audio. MPEG-1 stereo VBR/44.1k, MPEG-2 mono CBR/24k
and MPEG-2.5 mono/8k sample counts match FFmpeg (8837/4817/1617); independent
PCM comparison max error is 1.70e-6. Tests exercise sample-exact random seeks,
complete decoder-state checkpoints, sparse retry, a 1.2 TB virtual source with
lightweight open, cancellation/ownership, and the 64 KiB sync-candidate boundary.
An independent CMake EXR_ENABLE_MP3=OFF build passes native-mp3/native-pcm/native-flac
without fetching minimp3.

Soft-hyphen tests verify hidden unbroken text, visible pixels only at selected
line ends, font fallback, mixed size/color, RTL, hit-to-original-source mapping,
width retreat and full-layout/sequential-page/random-checkpoint agreement.

PDF metadata tests cover Info-only and XMP synchronization, encoded streams,
Unicode, aliases/attributes, whole-property deletion/replacement, UTF-16 XMP,
default namespaces, complex unknown RDF, comments/PI/CDATA and attribute character
references, date precision/timezones, invalid input, cancellation and byte-identical
original prefixes. Independent pypdf/PyMuPDF checks verify eight output PDFs,
unchanged rendered pages and equivalent Info/XMP date instants.

All 84 local Windows suites pass after integration, including the installed-host
PCM example contract. The MP3-disabled build separately passes its MP3, PCM and
FLAC suites. The Swift and JNI PCM wrappers add owned sample arrays, serialized
handle access and unknown-duration reporting; their host compilation and runtime
smokes require the fresh cross-platform CI run for this batch. Version 0.18.0,
ABI epoch 1 and library schema 6 remain unchanged.


Commit `4b3d166` passes all six jobs in [CI run 39057987271](https://github.com/NoGod3524/EXReader/actions/runs/39057987271), including desktop runtime and installed C/C++/JNI/Swift hosts, ASAN/UBSAN and mobile compilation. Two test portability defects found in preceding runs were fixed: the integer-limits include and the Unix math-library link. The installed Windows PCM host also decodes all 3200 WAV frames with peak 0.5.

## Milestone 0.18 development: vertical layout, Type3, AAC/M4B and EPUB edits

Vertical fixtures are original rectangle/triangle fonts with vmtx, vert/vrt2 and vkrn. Checks cover both column directions, U/R/Tu/Tr orientation, real versus absent vertical alternates, em fallback, mixed/upright/sideways overrides, clusters crossing styles, physical matrix/pixels/hit tests, unchanged logical anchors, full/sequential/random-checkpoint agreement and positioned-array pixel round trips. The pinned Unicode 17 VerticalOrientation data reproduces a 4420-byte header with 189 ranges. Random-page reset now restores the writing mode; upright CJK shaping retains vertical kerning across soft break opportunities.

PDF Type3 tests cover d0/d1, six-component FontMatrix, nonstandard units, translation, scale/shear/rotation, parent ToUnicode and selection quads, all text rendering modes, resources, paths/Form/stencil/nested text, .notdef fallback, recursion/work limits, graphics-state isolation and cancellation recovery. Type3 glyphs use the shared content interpreter, not FreeType. Independent PyMuPDF/Poppler development renders verify ordinary and transformed glyphs. For translated FontMatrix EXReader agrees with PyMuPDF; nested inherited color agrees with Poppler. Custom sinks verify balanced nested SAVE and text-clip groups after cancellation.

AAC fixtures are original LC/PNS/SBR/PS audio. AAC-enabled tests check deterministic reopen/backward replay, interleaved independent handles, frame counts, cached seeks, bounded replay retry, cancellation, malformed headers and source ownership. M4B adds stsz/stz2, stco/co64, streamed chunk/time tables, moov before/after mdat, version-1 time headers, edit trimming/leading silence, offsets over 4 GiB and a billion-packet virtual source. Nonzero composition offsets are explicitly rejected. Original LC M4B outputs match FFmpeg sample counts (8837 and 4817) and PCM within 2.38e-7; SBR/PS frame counts also agree. PS waveforms are checked against deterministic FAAD2 replay, not claimed sample-identical to FFmpeg. FFmpeg/FDK are fixture-development tools only. AAC-disabled symbols and PCM dispatch are tested separately.

EPUB edit checks reopen the result and verify UTF-8/UTF-16 package input, title/author updates, optional empty/deleted values, percent-encoded transitive refinements, unknown namespace/QName attributes/comments/PI/CDATA semantics, existing/new/cleared covers, first uncompressed mimetype, and byte-identical compressed chapters/styles/other resources. Signed/rights-controlled packages, duplicate/unsafe member names, encrypted cover resources, required empty title/language, invalid values and cancellation are exercised. Font-only obfuscation metadata is retained while editing an unencrypted cover.


All 89 local Windows suites pass, with the corrected EPUB boundary fixture rerun after the full suite. The separate AAC-enabled build passes AAC/M4B/EPUB-edit integration tests; the default AAC-disabled build retains all symbols and passes its disabled-codec tests. Release DLL sizes on this Windows MinGW build are 4,314,085 bytes with AAC disabled and about 4.83 MB enabled. These are build artifacts, not peak runtime-memory measurements. This batch awaits its own six-job CI run with AAC explicitly enabled; version 0.18.0, ABI epoch 1 and library schema 6 remain unchanged.


Commit `5e82ba3` passes all six jobs in [CI run 39059214579](https://github.com/NoGod3524/EXReader/actions/runs/39059214579), with AAC enabled on desktop/sanitizer/mobile builds. CI found two portability/test defects in the previous batch: a BMFF table-row initializer and treating a non-terminated extracted ZIP member as a C string. Both are fixed; the latter is in the test helper, not the EPUB writer.

## Milestone 0.18 development: orthogonal blocks, font variations, WSOLA and inline images

Orthogonal tests exercise every pair of the three writing modes, long blocks, nested tables/rowspan, opposite-axis cells, nested blocks and images, explicit dimensions and trailing padding/margins, forced page breaks, hidden chapters, budgets, continuation/checkpoint replay, source anchors and positioned-array pixel round trips. The old cell walker was removed in favor of the same pager engine. The 89-page prior golden corpus retains every label/page/gray/RGBA hash; ten geometry hashes change only because box source ranges are now clipped to their containing page. The previously rejected tall table remains rejected.

The original 2688-byte variable font has two axes, hidden width, avar, a named heavy instance, gvar/HVAR/VVAR, variable kern/mark positioning and conditional rvrn. It regenerates byte-for-byte (SHA-256 02c1529a150e918a053ce709a98cb037f2c37cc85604654a3114b6d80a322553). Public tests cover axes/ownership, independent instances, avar, named instance, outlines, metrics, font-list merging and rejection contracts. Separate synthetic tables check longWords signed 32/16-bit, shortWords 16/8-bit, malformed item/region indices and FeatureVariations. Independent HarfBuzz comparison of eight axis/text cases matches glyph IDs with max coordinate/advance error 0.000123 px at 100 px size. It exposed and fixed the existing PairPos format-1 device-offset origin (PairSet, not PairPos). HarfBuzz/fontTools are development checks, not SDK dependencies.

WSOLA tests check exact duration at fixed/Q32-edge rates, one-frame/random input and varied output chunking, bit-identical 1x pass-through, 1–8 channel phase coherence, finite extremes, empty/short EOF, backpressure, cancellation/retry/reentry and reset. A 440 Hz input remains approximately 440 Hz at 0.5/0.75/1/1.5/2x; a 220 Hz input at 1.333333333x measures 219.938 Hz. All checks are numeric and silent.

Inline-image tests verify binary pixels containing EI/whitespace, CRLF ID, packed/16-bit samples, stencil reversal, all supported filter boundaries/chains/predictors, JPEG APP false EOI/entropy stuffing/restart, cross-arena resource aliases, Form/Type3 scope, malformed input, cancellation and the shared decode budget across repeated Forms. Independent PyMuPDF/Poppler pixels and text match six original PDFs (JPEG pixel tolerance 6).


All 94 local Windows suites pass. After the final hidden/empty-chapter viewport fix, orthogonal/vertical/flow/pager were rebuilt and rerun successfully. The installed Windows SDK passes a separate C++17 consumer using ABI epoch 1. This batch still requires its own cross-platform CI run; product version 0.18.0 and library schema 6 remain unchanged.


Commit `0f45262` passes all six jobs in [CI run 39060107810](https://github.com/NoGod3524/EXReader/actions/runs/39060107810), including installed C/C++/JNI/Swift consumers, sanitizer runs and mobile builds.

## Milestone 0.18 development: Devanagari, ruby, PDF colour spaces and mobile reflow wrappers

The new Indic suite uses 64 HarfBuzz 14.6.0 reference cases recorded from original
3984/4008-byte modern/legacy Devanagari fonts, covering basic forms, nukta,
reph/pre-base matras, conjuncts, join controls, broken syllables and positions.
All glyph IDs and advances/offsets agree within 0.016 px at size 100. Independent
Noto Sans Devanagari checks match glyph order on the same 32 sequences; existing
FreeType hinting accounts for up to 0.3 px metric differences from unhinted HB.
Tests also check monotone syllable source ranges, cancellation/error cleanup,
paging and rendering. Unicode 17 source SHA-256 hashes and regeneration match.

Ruby tests cover horizontal/vertical-rl/vertical-lr, over/under, source and anchor
ranges, hit testing, multi-page implicit groups, explicit rb/rtc/rbspan, positioned
round trips, sequential pagination and checkpoint restoration. The helper builds
EPUB input so the real structure-preserving parser is exercised. Two test defects
were corrected: using the HTML text-extraction path, and mutating a shared CSS
buffer between reference and pager construction. Production groups share an
8192-shaped-glyph limit across all their base and annotation fragments.

524 PDF colour checks compare vector/XObject/inline output, calibrated and Lab
ranges, Indexed lookup scaling, ICC Alternate/Range fallback, initial colours,
q/Q/Form resource scopes, invalid/cyclic spaces, and cancellation. Independent
MuPDF rendering of CalGray/CalRGB/Lab/Indexed fixtures agrees within one byte at
the sampled vector and image interiors; the deliberately invalid ICC stream
exercises Alternate fallback. The old graphics test now rejects a missing
colour resource instead of treating valid Lab as unsupported.

All 97 native local suites pass. A separately compiled JNI adapter passes real
JDK 21 execution with -Xcheck:jni: Unicode input, node attributes, lazy EPUB parts,
page snapshots, variable-font source axes, embedded images, hit/render, EOF,
invalid inputs and closing parents before children. Swift smoke covers matching
ARC ownership and record snapshots; this batch awaits its own real macOS runtime
and iOS/iPadOS type checks in CI. Default AAC-off Windows DLL is 4,409,868 bytes;
this batch adds no production dependencies. Version stays 0.18.0, ABI 1, schema 6.


Commit `55fb274` passes all six jobs in [CI run 39068978337](https://github.com/NoGod3524/EXReader/actions/runs/39068978337), including real JVM/Swift execution, iOS/iPadOS typechecks, Android builds and ASAN/UBSAN.

## Milestone 0.18 development: independent M4B metadata inspection

The AAC decoder and metadata inspector now reuse the same bounded ISO-BMFF box,
byte-source and time-header helpers, compiled independently of FAAD2. This moves
existing parsing rather than adding a second box parser. All 98 local default
AAC-off suites pass; a separate AAC-on build passes AAC/M4B/metadata suites after
the refactor. The new 2726-check suite covers multi-value UTF-8/UTF-16BE metadata,
JPEG cover copying, v0/v1 Nero chapters, source/child ownership, conversion into
the open audio timeline, every byte-truncation boundary, read errors/cancellation,
malformed Unicode/time ranges, value limits and overflow. A virtual source skips
a 5 GiB mdat and reads under 1000 bytes to obtain a later moov.

An independently FFmpeg-authored 4009-byte fixture has Unicode title/artist,
JPEG cover, both chapter representations and 200 ms duration. Inspection matches
FFprobe's two [0,100)/[100,200) chapter intervals and metadata; the implementation
currently consumes Nero chpl. Java's real -Xcheck:jni run reads the same fixture
with AAC disabled. Swift has matching smoke assertions awaiting this batch's CI.
The Windows default DLL is 4,421,644 bytes; no new production dependencies.
Version remains 0.18.0, ABI 1 and schema 6.

Commit `7ea57fc` passes all six jobs in [CI run 39069835100](https://github.com/NoGod3524/EXReader/actions/runs/39069835100), including Swift/JNI audiobook snapshot consumers and mobile builds. A separate C++17 host compiled against the installed AAC-off SDK reads M4B metadata, creates the generic audio timeline and retains that timeline after freeing inspection.

The Swift font adapter keeps its pre-existing glyph-only-font acceptance: both Unicode and non-Unicode scalable faces use exr_font_create_glyphs, which selects Unicode when present. Normal reflow fonts retain their Unicode cmap; direct-glyph PDF hosts can still supply cmap-less faces. A Swift smoke case exercises that constructor and PDF ownership.


Commit `43ef9ac` passes all six jobs in [CI run 39070116417](https://github.com/NoGod3524/EXReader/actions/runs/39070116417), including the Swift cmap-less-font regression case.

## Milestone 0.18 development: Separation and scalar PDF functions

The PDF colour suite now has 840 checks. New cases compare paths, XObject and
inline image tints for Type 2/3 functions, scalar and CMYK alternate spaces,
default and null C0/C1/Range, domain/range clipping, fractional/negative exponents,
reversed stitching, half-open boundaries and a zero-width final interval. None
uses a valid but unneeded Type 4 stream to prove that ignored transforms need
no calculator implementation. It preserves underlying fill/stroke/images, q/Q,
subsequent RGB paint, and text semantics. Invalid function dimensions/domains,
unsupported types, indirect cycles, depth/node budgets and mid-compilation
cancellation all fail without returning partial pixels.

Both exported original spot PDFs independently render in MuPDF with RGB samples
within one byte of the C output at the path, image and inline-image interiors.
All 98 native local suites pass; the final added cancellation assertion passes
the colour suite. This batch awaits its own six-platform CI. Default AAC-off
Windows DLL is 4,432,198 bytes, with no new dependencies, public ABI changes,
version bump or schema change.


Commit `c59d1b8` passes all six jobs in [CI run 39071009611](https://github.com/NoGod3524/EXReader/actions/runs/39071009611), including ASAN/UBSAN and all installed platform consumers.

## Milestone 0.18 development: linear sampled PDF functions

The colour suite now has 1191 checks. Type 0 tests use all eight permitted sample
bit depths with packed RGB tables and real ASCIIHex streams, checking paths,
XObjects and inline images. Separate tests amplify the low nibble of a 12-bit
sample and the lowest byte of a 32-bit sample so truncation cannot hide inside
pixel rounding tolerance. Cases cover reversed Encode/Decode, one-sample and
zero-width domains, table indexing, and a sampled child of a stitching function.
Invalid/missing dimensions, Range, bit depths, cubic order, mapping arrays,
short/long tables and allocation limits fail without partial pixels.

All eight exported sampled-function PDF fixtures independently match MuPDF at the
three sampled interiors within one RGB byte. All 98 local native suites pass.

## Milestone 0.18 development: bounded PDF calculator functions

The standalone calculator suite has 254 checks over every permitted operator,
integer-to-real promotion, strict integer/boolean operands, logical shifts,
negative division/remainders, signed and extreme rolls, conditional syntax,
skipped invalid branches, comments, decimal syntax and all source truncations.
It exercises 32/33 nesting, 4096/4097 instructions, exactly 100 and overflowing
stacks, source length, memory/cost accounting and compile/execution cancellation.
PLRM specifies round(-6.5) = -6; this is checked directly because MuPDF's
negative-half behavior differs from that specification.

The colour suite has 1290 checks. Five exported calculator PDF fixtures cover
stack math, both conditional branches, trigonometry and four-channel output
through paths, XObjects and inline images. RGB/gray interiors match MuPDF within
one byte; the CMYK case matches equivalent direct DeviceCMYK painting in MuPDF
within one byte. EXReader's simple DeviceCMYK conversion differs from MuPDF's
CMYK conversion, independently of the function evaluator. Additional cases
check stitching, Domain/Range, invalid outputs and the shared vector colour-work
budget. There are now 99 native test suites. Version remains 0.18.0, ABI epoch 1
and library schema 6.

## Milestone 0.18 development: referenced QuickTime audiobook chapters

The ISO-BMFF inspection suite now has 8385 checks. Original text/tx3g tracks
exercise multi-run stsc/stts, fixed and variable stsz, stz2 4/8/16-bit sizes,
stco/co64, tkhd/mdhd and elst v0/v1, UTF-8 and BOM-marked UTF-16BE/LE,
leading empty edits, trimming through an active chapter and mixed-clock rounding.
One virtual 5 GiB mdat stores chapter text near its end; inspection reads fewer
than 20 KiB. Chapters remain usable through exr_audio_create after inspection
is freed. Tests include every synthetic-file truncation, cancellation at multiple
read positions, external data references, missing/duplicate track IDs, malformed
sample boundaries, incomplete time/chunk coverage, invalid Unicode, collapsed
millisecond timestamps, sample/table limits and overflowing edit durations.

The existing original FFmpeg metadata.m4b fixture has both Nero and QuickTime
chapters. Tests retain the nonempty chpl preference, then rename only chpl to a
free box without moving offsets. The resulting QuickTime-only book exposes
One [0,100) and Two [100,200) ms, matching ffprobe independently. No new binary
fixture or runtime tool dependency is needed. AAC and metadata inspection now
share the same bounded private BMFF sample-table helpers. The AAC-enabled M4B,
AAC and inspection suites pass alongside the default native regression suite.
The calculator batch (847de68) and QuickTime chapter batch (98ab5f2) pass all six
CI jobs: desktop Windows/Linux/macOS, Android, Apple mobile and sanitizers.

## Milestone 0.18 development: open named audiobook metadata

The ISO-BMFF suite now has 9559 checks, including keys/mdta and iTunes freeform
text, known-field aliases, unknown names, reversible percent escaping, duplicate
values/order, UTF-16 surrogate pairs and owned snapshots after input destruction.
Unknown raw ilst text retains its four-byte key; implicit binary/numeric values
and other keys namespaces are skipped. Invalid indices, key sizes/encoding,
versions, absent/empty mean/name, key/text limits and every named-book truncation
are covered. A separate real FFmpeg file made with use_metadata_tags exposes the
same title, author and custom string as ffprobe. Existing chapter and audio paths
remain available with AAC either enabled or disabled. No public ABI or runtime
dependency was added.

## Milestone 0.18 development: COLR v0 layers and CPAL snapshots

The new color-font suite has 40145 checks. The 3760-byte original color.ttf
fixture has two palettes, three palette entries, translucent/transparent colors,
foreground-color layers, 256/257-layer glyphs and an oversized outline layer.
Tests exercise owned layer snapshots after palette changes and font destruction,
palette queries, invalid arguments, cancellation, default palette restoration,
horizontal/sideways/vertical clipping, source alpha, grayscale output and single
decoration painting. A non-BMP emoji falls back to the second font while retaining
its original four-byte text cluster; retained layouts render after documents and
input fonts are released. Large overlapping glyphs hit the shared raster-work
limit and discard their output. Layer and bitmap limits are checked separately.

The exported 200x200 color fixture is byte-for-byte pixel identical to Pillow's
independent FreeType COLR compositor, including all overlapping interiors.
All 100 local native suites pass. A C++17 host builds and runs against the newly
installed SDK and links both new public color-font queries. The default Windows
DLL is 4,468,475 bytes. No runtime dependency was added; version/ABI/schema remain
0.18.0/1/6. The preceding named-metadata batch (58e907f) passes all six CI jobs.

## Milestone 0.18 development: native sbix bitmap glyphs

The color-font suite now has 80400 checks. The original 3652-byte bitmap.ttf
adds two sbix strikes, per-strike glyph coverage, two-color PNGs, a solid JPEG,
dupe chains and a deliberate cycle. Tests cover native/above/below strike sizes,
intrinsic RGBA, outline-relative origin, Unicode fallback and preserved advances,
empty-outline fonts, horizontal/vertical clipping, sideways painting, text
opacity, decorations and optional outline overlay. Snapshots outlive their font.
Malformed versions/flags, oversized strike lists, invalid offsets/duplicates,
missing target images, wrong encodings/signatures, decoded/scaled dimension
limits and cancellation clear their output. Repeated individually valid enlarged
bitmaps hit the shared page work limit without allocating enlarged images.

Pillow's independent FreeType sbix renderer agrees at the two colored interiors
and the outline-free background of the scaled exported fixture. All 100 native
suites pass; the installed C++17 SDK consumer also links and calls the new image
query. The default Windows DLL is 4,478,838 bytes. Parsing and scaling are native
C; PNG/JPEG decode reuses the existing decoder with no new runtime dependency.
Only validated strike directories are cached; decoded snapshots are caller-owned.
The preceding COLR v0 batch (f07af93) passes all six platform/sanitizer CI jobs.
Version, ABI epoch and library schema remain 0.18.0/1/6.

## Milestone 0.18 development: embedded sbix font selection

The common face opener is now used by both host font creation and embedded-font
probing. The original 3778-byte color-fonts.epub embeds sbix and COLR v0 fonts
under separate CSS aliases. Its two emoji resolve to distinct embedded font faces
and both still render after the document and host fallback are released. The
color-font suite now has 80408 checks. This closes the old embedded-only probe
that discarded sbix as non-scalable. The preceding sbix batch (77bfa02) passes
all six desktop/mobile/sanitizer CI jobs. No public ABI, dependency or version
change is involved.

## Milestone 0.18 development: CBDT/CBLC bitmap-only fonts

The original 3004-byte cbdt.ttf exercises both bitmap-only font metrics and
two native strikes, all five index formats and PNG image formats 17/18/19.
Tests cover sparse and absent images, continuous advances including hmtx tail
reuse, explicit/fallback vertical metrics, empty outlines, decorations, retained
snapshots, font fallback, embedded EPUB fonts and identical whole/paged pixels.
Malformed offsets, unordered/duplicate sparse IDs, unsupported encoding/depth,
wrong PNG sizes/signatures and cancellation are rejected with cleared outputs.
All index arrays are checked once in bounded reads before binary searches.

As an independent local reference, NotoColorEmoji.ttf from
googlefonts/noto-emoji `main/2D/fonts` (SHA-256
`15671215ab769fdc7162a045d56fd7d7e477c51b04e6b3c761d914d8fdd6cc44`)
has 4046 glyphs, of which 4004 have CBDT images. All 4004 decoded RGBA buffers
match fontTools-extracted PNGs decoded with Pillow exactly, including native
bearings; the remaining 42 return no image. The external font is not shipped.
This test also exposed an existing ZWJ substitution issue, tracked separately
from bitmap decoding. The preceding embedded sbix batch (126b1e0) passes all
six platform/sanitizer CI jobs. No runtime dependency or ABI/schema/version
change is involved.
All 100 local Windows suites pass, including byte-identical whole/paged bitmap
renders; the installed C++17 SDK consumer passes. The default release DLL is
4,492,143 bytes, 13,305 bytes above the preceding sbix build. This batch's
desktop/mobile/sanitizer CI is checked against its own commit after pushing.

## Milestone 0.18 development: explicit invisible OpenType components

The shared matcher now checks explicit glyph/coverage/class matches before
skipping eligible default-ignorables, while preserving GDEF lookup filtering,
ordinary ZWNJ barriers and Indic-specific ZWJ behavior. Ligature, contextual,
chaining and reverse substitutions use it. The original emoji.ttf covers ZWJ,
tag and keycap components, explicit ZWNJ, ignored marks, hidden-leading ligatures
and a whole-layout emoji with one preserved UTF-8 cluster.

`tools/check_bitmap_reference.py <library> <font> <emoji-test.txt>` compares
all images with fontTools/Pillow and all fully qualified sequences with
HarfBuzz (visible glyph IDs, advances and offsets; tolerance 0.02 pixels at
100px). Unicode 17's official `17.0.0/emoji/emoji-test.txt`, SHA-256
`1d8a944f88d7952f7ef7c5167fef3c67995bcae24543949710231b03a201acda`,
has 3944 fully qualified sequences; all match with the above Noto font.
Hidden unconsumed API records are excluded from this reference comparison;
the C regression suite checks their zero advances and cluster ownership.
All 100 local Windows suites pass. CBDT commit 3f8547d passes all six
platform/sanitizer CI jobs. Version/ABI/schema remain 0.18.0/1/6.

## Milestone 0.18 development: Unicode variation sequences

The 1440-byte original uvs.ttf has cmap 14 without GSUB/GPOS. C tests cover
default/non-default BMP and supplementary mappings, a missing nominal base
with a valid variant, unsupported/leading/repeated selectors, vertical shape,
font fallback preference and selectors split across differently sized spans.
Whole layout and paged output have identical pixels and intact four-byte
clusters. Font and document lifetimes remain independent of retained pages.
An independent HarfBuzz comparison of 28 base/selector combinations agrees
on visible glyph IDs and advances within 0.02 pixels at 100px, including
unknown and Mongolian selectors. Cmap decoding reuses the existing FreeType
C mapper; no new runtime dependency or public ABI is introduced.
All 100 Windows suites and the installed C++17 SDK consumer pass. The full
4004-image/3944-emoji independent reference still passes. The preceding
explicit-component commit 504e463 passes all six platform/sanitizer CI jobs.

## Milestone 0.18 development: PDF registration All

Native color conversion recognizes Separation /All, including escaped names,
and maps subtractive tint to additive output as R=G=B=1-tint, per the explicit
additive-device wording in ISO 32000-2 8.6.6.4. Its default tint is 1; alternate
spaces/transforms are not executed. C tests cover endpoints, intermediate tints,
clipping, Decode, paths, strokes, XObject/inline images, Indexed palettes,
Form inheritance and q/Q/direct-color resets. All remains excluded as the
alternate of another Separation color space. Text extraction remains available.

For a valid alternate whose gray transform also expresses 1-tint, MuPDF's entire
64x32 RGB render differs by at most 1 byte/channel; Poppler's three solid
interiors agree. Poppler paints an extra right-edge column on the image squares,
so whole-image pixel equality is not claimed. With a deliberately red alternate,
both reference RGB renderers use that alternate rather than the All complement;
the native regression intentionally follows the standard's special-All rule.
The reference discrepancy is isolated from ordinary spot-color conversions.
No new dependency, public ABI or product-version change is involved.
All 100 local Windows suites pass. The preceding Unicode-variation commit
9f52053 passes all six desktop/mobile/sanitizer CI jobs.

## Milestone 0.18 development: multi-input Type 4 and DeviceN

The shared calculator accepts 1–32 ordered inputs in its existing 100-item
stack. Function Domain/Range clipping is per component, with the same graph,
program, work and cancellation budgets. Scalar wrappers retain the old call
paths. DeviceN uses the multi-input transform for fixed RGB output; single
input also reuses Type 0/2/3. Optional NChannel dictionaries do not enable
physical ink simulation. Mixed None names still use the authored alternate
transform; all-None spaces suppress painting.

C regressions cover 2/3/32 inputs, 64 Decode/Mask entries including a mismatch
only in the last mask component, NChannel attributes, default tints, state
restoration, per-component clamps, scalar reuse and all-None transparency.
Malformed names, duplicates, All, empty lists, a 33rd component, invalid
attributes, invalid multi-input Type 2 and calculator stack overflow fail.
MuPDF's three solid path/XObject/inline-image interiors match the 2/3/32-input
fixtures within one byte per RGB channel. Multi-input Type 0 and Order 3
remain outside this batch; Type 2/3 are inherently single-input functions.
All-registration commit 7e2b55c passes all six platform/sanitizer CI jobs.
All 100 local Windows suites and the installed C++17 SDK consumer pass. The
PDF-color suite has 1753 checks. The default release DLL is 4,500,873 bytes;
runtime dependencies, ABI epoch 1, schema 6 and version 0.18.0 stay unchanged.
Code commit f3727ea passes all six jobs in CI run 39078721295: Windows,
Linux and macOS native tests/installed SDKs, Android ARM64, Apple device/simulator
builds and ASan/UBSan. Mobile builds do not establish device application/runtime
validation.

## Milestone 0.18 development: multidimensional and cubic sampled functions

Type 0 now accepts 1–32 input axes and Order 1/3 with 1–4 outputs. Samples
remain packed, with input zero varying fastest. Cardinal cubic convolution
(a=-1/2) replicates boundary samples, uses linear interpolation for two-point
axes, and applies Decode before final Range clipping, including overshoot.
The graph retains its 1 MiB payload budget. Grid multiplication is checked
before allocation; worst-case interpolation has at most 65536 neighboring
sample combinations and is charged to vector/image work budgets. Degenerate
axes do not multiply work. Evaluation checks cancellation every 256 neighbors.

Regressions cover all eight bit depths on two-axis RGB tables, a non-square
grid, trilinear interpolation, 32 axes with singleton/zero-width dimensions,
independent Domain/Encode/Decode mapping, cubic interior/endpoints/overshoot,
one/two/three-point axes, tensor cubic interpolation, malformed dimensions
and preallocation work limits. Ten linear fixtures (30 path/XObject/inline
interiors) agree with MuPDF 1.28.2 within one byte per channel. Cubic tests use
analytical expectations; no independent cubic-renderer equivalence is claimed.
All 100 local Windows suites pass. No runtime dependency or ABI/schema/version
change. Platform CI is checked separately after pushing this implementation.

Code commit 3ea8bca passes all six jobs in CI run 39082920611 (Windows/Linux/macOS,
Android ARM64, Apple device/simulator builds and ASan/UBSan).

## Milestone 0.18 development: CBZ fixed-page reader

The native reader reuses miniz, PNG/JPEG decoding, fixed-page geometry/draw sinks,
and the SQLite library. File opening retains a random-access file source up to
2 GiB; memory opening copies at most 128 MiB. Page discovery probes headers in
4 KiB chunks, capped at 1 MiB per page and 64 MiB of header work. Rendering
extracts, CRC-validates, decodes and releases just the requested image. No whole
comic pixel cache or new dependency is added. Unit, pixel-aligned transforms
preserve exact original pixels rather than applying a smoothing pass.

Regressions cover stored/deflate archives, PNG/JPEG, numerical sorting and
leading-zero ties, mixed-case extensions, UTF-8 member paths, pixel orientation,
scaled rendering, multi-chunk JPEG headers, ComicInfo title/author/description,
empty text snapshots, file/memory ownership, cancellation/retry, malformed XML,
external-entity rejection, unsupported image formats, unsafe/invalid names,
duplicate paths and lazy CRC failure confined to its page. Library tests cover
deduplication, metadata, page progress, page bookmarks and backup/reopening.
All 101 local Windows suites and an installed C++17 SDK consumer pass. Swift
and JNI smoke programs add CBZ coverage while retaining existing PDF entry
points. The 908-byte comic.cbz fixture is original 2x2 RGBA artwork and XML,
packaged with Python's standard ZIP/zlib libraries; no external artwork.

CBZ supports PNG/JPEG pages; known unsupported image codecs fail explicitly.
It does not run OCR, apply ComicInfo page semantics, split spreads, apply EXIF
orientation, automatically extract a cover, or write back ComicInfo. Book cover
editing uses the existing library API. C ABI epoch 1, schema 6 and product
version 0.18.0 remain unchanged. Platform CI is checked after push.

CBZ commit e7ce3ce passed Windows/macOS native and SDK tests, Android, Apple
mobile builds and ASan/UBSan. Its Ubuntu GCC 11 job rejected potentially
uninitialized decoder dimensions after extracting header probing into a helper.
The ICC batch initializes the decoder dimensions from that validated header;
the final batch CI must also verify this compiler fix.

## Milestone 0.18 development: ICCBased profile conversion

EXR_ENABLE_ICC (default ON) statically includes the MIT-licensed LittleCMS
2.19.1 C core, pinned by SHA-256. This is a color conversion dependency, not
a PDF parser/renderer. A private per-context allocator tracks aligned allocation
headers and live bytes, enforces 16 MiB, supports cancellation during compilation
and releases context/transform/profile state on every failure. ICC input is
capped at 4 MiB, 512 tags and 64 stages per inspected input pipeline. Actual
retained memory is charged to the existing color cache and conversion work to
the existing vector/image budget. Optimization precalculation and last-pixel
caching are disabled.

The native PDF path uses valid Gray/RGB/CMYK/Lab input/display/output/color-space
profiles before Alternate; unusable/mismatching profiles retain Alternate
fallback. ISO 32000-1 tables 68/69 define the accepted types and physical Lab
units. XYZ input profiles are outside table 68 and use Alternate. Native tests
cover v2/v4 matrix/TRC, a synthetic four-input CMYK-to-XYZ-PCS LUT, Lab ranges,
valid-profile precedence, channel mismatch, Indexed bases, paths, strokes,
XObject/inline images and mid-operation cancellation/retry. Five valid fixtures
agree with MuPDF 1.28.2 at ten path/image interiors within one RGB byte/channel.

All 101 local Windows suites, the ICC=OFF PDF-color suite and an installed C++17
SDK consumer pass. Default release DLL: 4,981,470 bytes (4.75 MiB); ICC=OFF:
4,515,472 bytes (4.31 MiB). Three-run, fresh-process EPUB text benchmarks using
Arial and the existing 720x1040 gray renderer measured median first-visible
times of 15.79/24.74/12.75 ms, page turns of 10.68/8.43/8.74 ms and process
peak RSS of 11.15/13.29/11.33 MiB for short/long-single/many-chapter-first-part.
Disk cache remains uncontrolled; these are text benchmarks, not ICC-PDF timing.

This batch fixes the rendering intent to RelativeColorimetric. Dynamic PDF ri,
image Intent, OutputIntent, proofing, transparency-group color management and
physical overprint are still pending; this is not full print-color conformance.
No public C layout, ABI epoch, schema or product-version change. Final platform
CI is checked after pushing this batch; further feature development pauses at
the user's request after this checkpoint.

ICC implementation 06893f3 passes all six jobs in run 39084326663. Final code
a4e70f6 additionally hides statically embedded CMS symbols from the shared
library's public surface and passes all six jobs in run 39084529119:
Windows/Linux/macOS native and installed SDK tests (including JNI and macOS
Swift), Android ARM64, Apple iOS/iPadOS device/simulator builds, and ASan/UBSan.
This also verifies the Ubuntu decoder-initialization fix. Mobile verification
remains library builds rather than application/device acceptance. Development
is paused here as requested; pending features are not marked complete.


## PDF CMYK/YCCK JPEG checkpoint (0.18 development)

The four-component adapter reuses the pinned stb entropy/IDCT, row upsamplers
and YCbCr conversion. It keeps all four samples until PDF Decode, color keys
and the existing color-space/ICCBased path run. No runtime dependency or public
ABI record changed. Existing grayscale/RGB decoding retains its path.

Original fixtures cover Adobe CMYK, YCCK, missing APP14, baseline/progressive,
odd 17x9 dimensions, subsampled four-color quadrants and independent K. The
PDF image tests check Decode/default inversion, color-key alpha, image SMask,
ICCBased Alternate, lossless-prefixed DCT, affine drawing and malformed
dimensions/component counts/truncation/Decode arrays. Inline cases verify both
rendered pixels and semantic text following CMYK/YCCK JPEG data. A public fixed
PDF case renders the authored page. Actual CMYK ICC LUT integration is checked
for CMYK and YCCK: K=32/255 produces neutral sRGB near 240, distinct from the
DeviceCMYK approximation (183,143,103).

Windows Release build and all 101 local CTest entries pass. The same default
DLL grows from 4,981,470 to 4,985,111 bytes (+3,641 bytes). Other platform
validation for this change is not yet recorded here. Explicit ColorTransform
overrides, 12-bit/non-supported JPEG variants and CMYK image Matte remain
unsupported. Image SMask support does not imply graphics-state soft masks or
transparency groups. See VERSIONING.md for the next compatibility milestones.

CMYK/YCCK commit aa3a329 subsequently passed all six platform jobs in run
39087678945 (desktop tests/installed SDK, ASan/UBSan, Android ARM64 and
iOS/iPadOS device/simulator library builds).

## PDF Standard security authentication (0.18 development)

Original independently generated pypdf 6.16.1 / cryptography 50.0.2 fixtures
cover R2-6 user/owner/empty passwords, object generation 17, Flate after crypto,
ObjStm and unencrypted xref streams, encrypted/clear XMP, Identity and explicit
Crypt, direct nested signature Contents with/without Type, and inherited
incremental revisions with a changed second file ID. Public adapter tests verify
page directories, semantic text, metadata, annotations and actual green pixels.
Failed page 1 followed by successful page 0 tests rebuilding with a retained
derived key after caller input and password buffers are destroyed. Wrong
passwords and malformed padding/permissions return no document/partial text.
Unicode cases exercise mapping-to-nothing, non-ASCII spaces, compatibility and
canonical composition, Hangul, Arabic bidi rules, prohibited/unassigned input,
invalid UTF-8 and 127-byte truncation. Cancellation is checked during R6 hashing;
options prefix/truncation, limits, unchanged security output on failure and
rejection by existing encrypted-input editing APIs are regression cases.

All 102 Windows CTest entries passed after the initial integration; additional
signature/incremental/cancellation cases also pass in native-pdf-crypto.
The installed Windows MinGW JNI host passed with -Xcheck:jni, including password
failure/retry, permission snapshot and encrypted parser recovery. The optional
crypto-disabled build passed native-pdf-crypto, native-fixed-pdf and native-abi.
Default Windows Release DLL: 5,164,761 bytes vs aa3a329's 4,985,111 (+179,650,
about 175 KiB); the crypto-disabled equivalent is 4,991,620 bytes. These numbers
measure the whole DLL, not package size or runtime memory. Platform CI for this
batch is recorded after pushing; no certificate/EFOpen or encrypted-write
support is claimed by these tests.

The final Windows batch passed all 102 entries. Re-running both fixture/table
generators reproduced every SHA-256. A separate deterministic 3,000-input
encrypted-PDF mutation run through public open/load-text returned 304 successful
opens, 2,319 format errors, 274 password errors and 103 unsupported-feature
errors without process failure. This mutation run is separate from sanitizer
evidence; sanitizer status is supplied by the platform CI run.

Authentication commit 65c32d9 passed all six jobs in run 39088903390, including
102 desktop/sanitizer CTest entries, installed SDK JNI and macOS Swift password
tests, Android ARM64, and iOS/iPadOS device/simulator builds with Swift typechecks.

## EPUB declared table columns (0.18 development)

Ten original EPUB fixtures cover CSS cell percentages, col/colgroup and group
span inheritance, HTML widths, colspan constraints beside a rowspan, leftover
space, proportional overconstraint, tiny columns, 64/65-column boundaries,
padding/borders and vertical-rl logical geometry. A 102-row fixture compares
cached/checkpoint pages against replay from the start and the complete layout:
glyph geometry, box geometry, hit-test results and every rendered RGBA byte.
The test forces cache-budget failure and recovery, eviction and backwards/random
navigation. The legacy native-flow/native-pager golden checks remain unchanged.
Ten fixtures are regenerated by tools/generate_table_columns_fixture.py.

All 103 Windows CTest entries pass, including the new table tests. No runtime
dependency/public ABI change; Windows Release DLL 5,164,761 -> 5,171,978 bytes
(+7,217). Row/cell allocation capacity is now included in table memory accounting;
column-edge storage is part of the cursor and every checkpoint's sizeof budget.
Content-driven intrinsic widths, vertical alignment and collapsed borders remain
separate pending steps. Platform validation is recorded after the feature push.

Declared-column commit d4d8fb3 passed all six jobs in run 39089391521, including
the 103-entry desktop/sanitizer suite and desktop installed SDK/mobile builds.

## EPUB intrinsic table widths (0.18 development)

The default auto algorithm measures legal-break and unwrapped content through
the actual native font/shaping/line pipeline. The fixed CSS alternative uses
declared columns/first row. Auto vectors use original fonts with known advances:
content shrinkage, minimum/preferred interpolation, excess space, late wider
rows, colspan, soft hyphen, font fallback/graphemes, Arabic lam-alef, CJK,
nested tables, explicit breaks, mixed sizes, block/image definite and percentage
sizes, padding/borders, centering and vertical flow. The fixture generator now
produces 33 EPUBs (10 declared-column and 23 additional auto/fixed cases).

Five hundred deterministic generated host tables vary widths, percentages,
spans, directions, fixed/auto selection and viewport sizes. Tests check bounded
finite cell geometry and preservation of every original A character. A long
8192-word row verifies streaming max measurement and final content preservation.
Random/backwards/evicted pages compare glyph coordinates, hit-test results and
RGBA bytes against both checkpoint-free replay and complete layout. Cancellation
during measurement returns no partial layout and a new open succeeds.

The old 0.10 pixel goldens now explicitly request standard full-width fixed CSS;
the old unnamed host table carries the same inline style. Those goldens are not
regenerated to bless auto output. Flow/complex-text checks now test real cell
adjacency/spanning instead of assuming equal default columns. Independent auto
vectors validate the changed default. All 104 local Windows CTest entries pass.

No dependency, public ABI or schema change. Default Windows Release DLL grows
from 5,171,978 to 5,177,756 bytes (+5,778). The reproducible 1000-row benchmark in
PERFORMANCE.md records the measurement cost and peak RSS. Column alignment,
collapsed borders and remaining CSS/table compatibility stay on the roadmap;
this checkpoint is not a claim of full CSS table conformance. Platform CI follows
the feature push.

Intrinsic-width commit a99f125 passed all six jobs in run 39090675225: 104-entry
desktop/sanitizer suite, installed desktop SDK/JNI/macOS Swift, Android ARM64,
and iOS/iPadOS device/simulator builds and Swift typechecks.

## Table alignment and height constraints (0.18 development)

Seventeen original alignment EPUBs exercise top/middle/bottom/baseline, mixed
sizes, image-only/empty cells, rowspan first-row baselines, nested table baselines
and fallback content edges, ruby main-line baselines, HTML group/valign inheritance
and CSS precedence, CSS baseline-fallback values, minimum/percentage heights,
vertical-rl/lr, opposite vertical directions and sideways alphabetic baselines.
Mode/control cases verify equal whole-cell backgrounds while glyphs, child
backgrounds and decoded blue image pixels move by the measured content inset.
Random/backward cached pages compare glyph geometry, hit results and full RGBA
against checkpoint-free replay and complete layout. Native rendering was also
visually inspected. The old fixed pixel goldens explicitly request top alignment;
the orthogonal spanning-cell test checks the actual row union rather than an
old top-aligned fixed height.

The 500 generated host tables now also vary font size, minimum height and all
four alignments, checking both axes and complete character preservation. This
found an independently reproduced rounding bug: adjacent edges around a float
exponent boundary yielded 0.999996 pixels despite a 1px column floor. An anchored
reverse edge pass now enforces the floor. A compact 175px five-column fixture
fails against the saved a99f125 DLL and passes against the fix; the generated
case is seed 180314, iteration 363. No tolerance was added to bypass validation.

The generator now produces 51 original EPUB table fixtures. All 105 local
Windows CTest entries pass. Default Release DLL: 5,177,756 -> 5,181,942 bytes
(+4,186); no runtime dependency, public ABI or schema change. Row baseline arrays
and per-cell alignment metrics participate in cursor/checkpoint byte accounting.
Collapsed borders and the remaining CSS/table requirements stay pending.


Alignment commit a0117c7 passed all six jobs in run 39091742470: the 105-entry
Windows/Linux/macOS/sanitizer suites, installed SDK consumers, JNI/macOS Swift,
Android ARM64 and iOS/iPadOS device/simulator library builds and Swift typechecks.

## Collapsed solid table borders (0.18 development)

Twenty-one original EPUBs cover shared vs separate geometry, content half-insets,
unequal widths, hidden-vs-none, table/rowgroup/row/column/cell conflicts, same-width
LTR/RTL tie breaking, column spans/declarations, rowspan/colspan interior removal,
inherited vs reset nested tables, inapplicable table padding/cell margins,
vertical-rl/lr, translucent junctions and multi-page boundaries. Expected basic
coordinates and exact blue/red/green/gray pixel values are independent assertions.
A native spanning-table render was visually inspected. The deterministic generator
now creates 72 EPUB table fixtures.

Five hundred additional generated host tables vary alignment, font/height,
colspan, fixed/auto/auto-width, LTR/RTL, border widths and solid/hidden/none;
checks preserve all source A characters and require finite page-bounded geometry.
Cached/backwards/evicted pages match checkpoint-free and full-layout glyphs,
hits and every RGBA byte. Public boxes/glyphs/lines rebuild through positioned
layout with identical pixels, including semi-transparent shared junctions.
A reversed vertical cell with asymmetric shared edges verifies physical-to-logical
inset conversion; the saved pre-fix DLL fails this new geometry assertion.
Invalid flag/kind/stroke combinations are rejected, and the 16M-pixel border-layer
budget returns EXR_LIMIT with no partial bitmap. The border test has 12,497 checks;
existing pixel goldens are unchanged.

All 106 local Windows CTest entries pass. Default Release DLL: 5,181,942 ->
5,205,547 bytes (+23,605). No new runtime dependency or public struct/schema
change. EXR_BOX_BORDER is an additive block flag; custom renderer grouping and
migration are documented. Collapse grids and checkpoint copies participate in
memory accounting; renderer layers are temporary and bounded, not page-cache data.
The 1000-row separate/collapse measurements in PERFORMANCE.md preserve raw
samples and hashes. CI status for this commit is recorded after pushing.

Remaining table work includes per-side/multi-value declarations, additional line
styles and join fidelity, CSS display row-group/column types, border-spacing,
repeating headers, row splitting, complex percentage constraints and broader CSS
formatting. Floats/wrapping and language dictionaries remain subsequent goals.


Collapsed-border commit 57c9f17 passed all six jobs in run 39092658253: 106-test
Windows/Linux/macOS/sanitizer suites, installed SDK examples/JNI/macOS Swift,
Android ARM64 and iOS/iPadOS device/simulator builds and Swift typechecks.

## Float contexts and dynamic inline corridors (0.18 development)

Forty-three original EPUBs cover left/right/multiple floats, ordering, clear
left/right/both/br, early/late inline anchors, full-width exclusion, fixed/auto
blocks, floating tables, cell BFC containment and synthesized cell baselines,
nested floats, minimum heights, empty floats, percentage width/max-width/padding,
auto shrink-to-fit in a neighboring corridor, margins and border/image pixels,
normal images and the current clearing behavior for normal tables, mixed font
heights, ruby, soft hyphens, LTR/RTL and vertical-rl/lr. A lam/float/alef case with
the original Arabic shaping font matches the no-float control's real ligature.
Native two-sided image wrapping was visually inspected.

Five hundred generated host documents (seed 180319) vary side, clear, width/auto,
height, margins, padding, font size, justification and paragraph direction.
Checks preserve every source A and keep visible clipped line rectangles outside
floating content. Source advances can include trailing spaces or indivisible
clusters; overlap checks use the same public clip bounds as the renderer.
Regular and nested orthogonal long chapters compare backwards/evicted/checkpoint
pages against replay and whole layout: glyphs, hit results and RGBA bytes agree.
Public records rebuild via positioned layout with identical pixels.

A narrow source-overlap EPUB independently reproduces a page lookup bug: a float
can remain on page 0 while earlier large text is carried to page 1. The saved
pre-fix DLL returns page 1 for source offset 17 actually drawn on page 0. Page
lookup now uses narrow actual glyph ranges only when page envelopes overlap;
positioned reconstruction accepts those envelopes and preserves the lookup.
Cancellation returns no partial layout, a fresh layout succeeds, tiny cache
budgets return no borrowed result, and oversized/129-live-float cases fail within
the documented limits. The float test has 105,364 checks. Pixel goldens stay fixed.

All 107 local Windows CTest entries pass. Installed JNI smoke with -Xcheck:jni
also checks float image coordinates, decoded image bytes and final page pixels.
The installed books/float-both.epub sample is used by JNI and macOS Swift CI.
No new dependency, exported function, public record, ABI epoch or schema change.
Default Release DLL: 5,205,547 -> 5,218,600 bytes (+13,053).
Float state is private to each BFC; owned copies and deferred immutable units
participate in checkpoint budgets. The 1 MiB text and 600-paragraph image
measurements record the cost in PERFORMANCE.md. This commit's platform CI is
recorded after pushing. Long float fragmentation, ordinary-table side-by-side
BFC geometry and broader CSS formatting remain open; this is not full CSS conformance.


A follow-up resource audit makes the old table-unit depth counter explicitly
format-neutral and checks it whenever any flow unit is created, including nested
floats without a table. Eight nested original floats succeed; the ninth returns
EXR_LIMIT with no partial layout. The pre-guard implementation accepted the ninth,
so the new limit is tested independently. The fixture generator now creates 45
float EPUBs. This uses the existing private counter and adds no public structure.
All 107 local tests pass after this guard; Release DLL 5,218,600 bytes.


## Long float continuations (0.18.0 development)

Long floats now retain a page cursor instead of laying out an entire unit up
front. The first probe is bounded to one page, short floats retain whole-unit
placement, and long floats use the current remaining space. Continuations run
before main flow on subsequent pages. Clear waits for the selected side, and
EOF drains unfinished floats even after all ordinary text has finished.

Twenty-two additional original EPUBs extend the float set to 67. Tests cover
long left/right/pair floats, float-only and short-main documents, partial first
pages, margins/padding/borders, empty/explicit/percentage heights, floating
collapsed tables, nested continuations, vertical and orthogonal writing modes,
and a descending-start source envelope. Public positioned reconstruction and
page lookup are checked alongside source containment and visible non-overlap.
Unbreakable lines/row groups, the existing 129-live-rectangle limit and a nested
130-cursor tree fail without returning a partial layout. The whole pager tree
is capped at 128 pending/committed floating contexts, in addition to depth 8.

Seven long variants compare random/backward cached pages against checkpoint-
free replay and full-document pixels/hit tests. A saved nested cursor is
cancelled during advancement and then restored; its recovered page matches
pixels before the cancellation. Tiny checkpoint budgets skip snapshots without
failing layout; tiny page budgets return no borrowed result. The float test has
584,942 checks, and all 107 native tests pass locally, with existing goldens.
Installed JNI passes -Xcheck:jni and renders the new float-long-main.epub through
EOF, counting all 7,500 A characters. Equivalent Swift smoke is part of macOS
CI. Native margin/border continuation pixels were inspected at 320 by 320.

At commit 9ec2349 ordinary tables still cleared external floats; per-side decoration slicing and
complete CSS fragmentation semantics remain outside the supported subset.
Large auto-width measurement, paragraph bidi analysis and parsed document
storage can still scale with the source. These are independent of retaining
only bounded output fragments and cursors. See PERFORMANCE.md for raw timing
and high-water-memory measurements. Commit 9ec2349 passed all six jobs in
[CI run 39096308241](https://github.com/NoGod3524/EXReader/actions/runs/39096308241):
Windows, Linux and macOS native/installed-SDK tests, macOS Swift smoke, JNI
smoke, ASan/UBSan, Android ARM64 and Apple device/simulator library builds.


## Ordinary table BFCs beside floats (0.18.0 development)

Ordinary tables now use an independent paginated BFC while external floats are
active. They contribute a baseline and normal-flow height. Initial probes check
the actual whole-fragment rectangle, not only its first row; a future float top
cannot cut through later rows or the table background. Width is selected before
commit, columns then remain fixed, and the fragment position is recomputed per
page. A failed narrow auto-width probe may choose a wider first fragment on the
next page. Explicit clear waits for the selected floating continuations.

Twenty-three new original EPUBs bring the float set to 90: left/right/both,
auto and declared widths, percent widths/padding, auto margins, clear, future
float tops, short vs long tables, long float continuations, collapsed borders,
vertical/orthogonal contexts, cell-local placement, and unbreakable errors.
A deferred auto table verifies width 200 on page 1 after its first narrow
attempt fails. A percent-height table started in a partial page keeps all six
cells at 500/3 pixels rather than recomputing height from remaining space.
Table backgrounds and cell/glyph arrays remain contained and do not intersect
external float rectangles. Width is checked across every table fragment.

Three hundred additional host-built documents (seed 180322) vary ordinary
2-column tables, rowspan groups, fixed/auto/percent width, margins, padding,
solid/collapsed borders, external float order and vertical writing. They join
the previous 500 generated float documents. Seven table documents compare
cached/checkpoint/backward pages against fresh replay, full-layout pixels and
hit tests; cancellation with an active table and floating cursor restores exact
pixels. The float test now has 683,956 checks. All 107 native tests pass locally.
Existing no-float goldens are unchanged. Native collapsed-table/image pixels
were inspected, and installed JNI -Xcheck:jni counts 3,350 A characters through
EOF while verifying each ordinary-table fragment's x=100 and width=100.
Equivalent Swift smoke and mobile builds run in CI.

This reuses the existing page cursor, table column allocator, image/font caches,
checkpoint ownership and resource limits. No new dependency or public record
layout is added. The 1 MiB float plus 1,800-row table benchmark records first
screen, complete traversal and peak process memory in PERFORMANCE.md. Complete
CSS table fragmentation and per-side decorations remain future work.


Commit 5fe3ca9 passed all six jobs in
[CI run 39097302823](https://github.com/NoGod3524/EXReader/actions/runs/39097302823):
Windows/Linux/macOS native tests and installed SDKs, desktop JNI, macOS Swift,
ASan/UBSan, Android ARM64 and Apple device/simulator library builds. Benchmark
source hashes and the installed DLL were checked against the committed source.


## Optional hyphenation dictionaries and providers (0.18.0 development)

The standalone C API builds immutable language registries or hosts a caller's
provider. A packed trie applies max-weight TeX-style patterns. Tests cover edge
anchors/minima, even suppression, duplicate pattern merging, parent language
lookup, untagged language isolation, Unicode 17 full folding, Greek final sigma,
Turkic I, Hebrew marks, emoji ZWJ and fold expansions that cannot split an
original character. Invalid UTF-8, byte/grapheme interiors, callback statuses,
reentry, cancellation, failed-create ownership and payload/work budgets are
checked. A 20,000-root adversarial dictionary terminates at the work limit.
An independent slow overlay oracle checks 30,000 generated ASCII words against
100 random pattern sets (seed 180324). The native test has 330,214 checks.
All 108 native tests pass locally. Unicode data regeneration is byte-exact.

The optional Pyphen 0.17.2 oracle checks 15,046 words and 18,664 break positions
using English US, Spanish, Italian and Russian dictionaries. The latter three
input files are unchanged; English COMPOUND minimum metadata is projected out
explicitly. Full-fold-expansion cases are native tests, not counted as a Pyphen
lower()-equivalence comparison. Native memory payloads are recorded along with
external dictionary hashes. No external dictionaries or Pyphen code are shipped.
The installed SDK C example independently links and prints hy-phen-ation.

Raw results and DLL provenance are under
benchmarks/0.18.0-hyphen-dictionaries-windows. This is a dictionary-query gate,
not verification of automatic line-breaking: CSS/language selection, synthetic
hyphens, final shaping, bidi/vertical drawing and page/checkpoint integration
remain required. Native compound/spelling-replacement grammars and canonical
normalization also remain pending. Existing manual soft-hyphen behavior is not
changed by this standalone module.
