# Native C validation

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
