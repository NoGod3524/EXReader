# EXReader SDK compatibility

ABI epoch **1** was introduced in development step **S091** (original build
**0.91.0**, commit `7dc8d8a`), now part of milestone **0.18.0**. `EXR_ABI_VERSION` identifies the header's epoch;
`exr_abi_version()` identifies the loaded library's epoch. `EXR_VERSION` and
`exr_version()` identify the release. Epoch 1 does not retroactively classify older
SDK binaries that did not export the ABI query.

## Binary contract

Within one epoch, existing exported C symbols, calling conventions, enum numeric
values, public record sizes/alignment/member offsets, callback signatures and
ownership contracts remain compatible on the same operating system, architecture
and compiler ABI. Removing symbols or changing those layouts requires a new epoch.
Adding functions does not. Optional build features retain their public symbols;
for example, `exr_text_index_available()` reports whether FTS indexing is enabled.
A host using new functions also requires the release
that first provides them; an epoch alone does not imply that every later symbol
exists in an older library.

Use the platform's normal C calling convention, natural structure alignment and
normal enum representation. Do not compile the public header under packing or
short-enum options. C++ callers use the header's `extern "C"` declarations and keep
exceptions inside their own callbacks. `size_t` and pointers are native-width;
public structs are not an on-disk or network serialization format.

Existing array-element records cannot gain fields within an epoch, including
fields appended at the end: that would change their stride for older callers.
New array layouts require new types and entry points. Inputs explicitly carrying
`struct_size` may grow by preserving the original prefix. Zero-initialize them,
set the size of the header's actual type and leave unused fields zero. A library
rejects unsupported nonzero extensions instead of silently interpreting them.
The original fixed-provider prefix remains a tested consumer even though later
headers append optional text, metadata and annotation callbacks.

The 0.18 development PDF password interface appends `pdf_password`,
`pdf_password_size` and `pdf_security` to `exr_fixed_open_options`; the original
prefix remains accepted. Recompile hosts that need these fields. Error values
0-9 retain their numbers; 10 is `EXR_PASSWORD`, 11 is `EXR_UNSUPPORTED`.
`exr_pdf_security_info` is a new output type with its own `struct_size`.
`exr_pdf_crypto_available()` reports the optional build component. The Swift
initializer adds a defaulted `password: Data?` parameter, and Java retains its
original constructors while adding password-byte overloads and security snapshots.
Rebuild JNI together with its matching Java wrapper. Windows MinGW now installs
`exreader_jni.dll` with the filename expected by `System.loadLibrary`.

The later 0.18 table-layout update defaults to content-driven auto widths,
including shrink-to-content for tables without a definite width. Existing table
page counts and coordinates may therefore change, while source text positions
and public ABI layouts retain their contract. Use standard
`table {table-layout:fixed;width:100%}` CSS for the old full-width equal-column
presentation; unnamed host nodes can carry that inline style directly. The old
0.10 pixel goldens explicitly request this fixed presentation, while independent
auto-width vectors, random tables and checkpoint tests validate the new default.

Cell alignment now uses the CSS baseline initial value and HTML table-group
defaults, with top/middle/bottom/baseline support. Different font sizes/paddings
and spanning cells may therefore change row heights or content coordinates.
Request `vertical-align:top` on cells to preserve the old top-aligned presentation;
the legacy pixel-golden CSS does so explicitly. The first-line/row baseline
metadata remains private; public array strides and ABI epoch stay unchanged.

## Ownership and execution

Opaque handles are released with their matching `*_free`/close function. Allocated
arrays and nested records use their documented typed free routine. Plain returned
allocations use `exr_free`; never free SDK allocations through a host CRT. Borrowed
views expire with their owning handle. Copy a view when it must outlive its owner.
The API documentation specifies retained font, publication/archive and layout
relationships; those rules are part of the contract.

The engine invokes callbacks synchronously and creates no worker threads. Serialize
calls and lifetime changes for a shared mutable handle or shared archive graph.
Callbacks must not free/reenter the active object. Independent object graphs can
run independently. The atomic unique-import operation additionally protects its
lookup/insert transaction; it does not establish unrestricted thread safety for
all book-library operations.

UTF-8 byte offsets in normalized text, raw XML UTF-16 CFI offsets and fixed-page
coordinates are distinct units. Persist portable selectors/CFIs rather than raw
public structs. Rendering and normalization algorithms may improve across releases;
an ABI epoch describes the binary contract, not pixel-identical output. SQLite
schema versions and supported input-format subsets are tracked separately.

## CMake consumers

An installed SDK contains a relocatable config package:

```cmake
find_package(EXReader 0.18.0 EXACT CONFIG REQUIRED)
target_link_libraries(my_host PRIVATE EXReader::exreader)
```

The version renumbering keeps ABI epoch 1 and SQLite schema 6 unchanged. Update
old CMake requirements such as 0.91/0.96 to the new milestone number. Use EXACT
when selecting this SDK: older development packages numbered 0.91–0.100 sort
above 0.18 and must not be selected as supposedly newer compatible packages.
Historical versions are compared through the [version map](VERSIONING.md) and
commit IDs, rather than numeric ordering across the renumbering.

Set `CMAKE_PREFIX_PATH` or `EXReader_DIR` to the selected platform SDK. The imported
target carries its include path and actual platform import/shared-library path;
FreeType, Expat, miniz, SQLite and image decoder build directories are not required
by the consumer. `EXReader_VERSION` and `EXReader_ABI_VERSION` describe that package.
The host bundles the corresponding shared library using its platform's loader
rules. Keep SDK/runtime releases paired unless the host deliberately checks its
required release and ABI at startup.

`examples/compat.c` compares package, header and loaded runtime values. All installed
host examples now use the imported target; desktop CI configures, builds and runs
them independently from the engine source build. Windows copies the installed DLL
next to the examples. Swift and JNI remain separate optional adapters over the
same C contract.


The collapse CSS option adds `EXR_BOX_BORDER` (mask value 2) on block rectangles without
changing the exr_box layout, ABI epoch or library schema. Custom renderers must
preserve these flags and batch each contiguous same-node border run as one RGBA
layer, replacing rectangle pixels within the layer before one source-over blend.
Painting each translucent rectangle independently darkens junctions. Native and
positioned renderers implement the same grouping. Older hosts can request
`table {border-collapse:separate}` until their renderer handles the new flag.
Only the existing uniform solid/none/hidden border subset is implemented here;
side-specific and additional border styles remain pending.


The float update keeps the C/Swift/JNI record layouts and ABI unchanged, but
reflows documents that declare float/clear. Bookmarks remain source selectors or
CFIs. A page's start/end is now a source envelope that can overlap another page:
a float can stay on one page while earlier large text is carried to the next.
Do not infer a unique page from disjoint interval assumptions. Use
exr_layout_page_at for actual source placement; overlapping layouts consult
actual glyph ranges while ordinary layouts retain binary lookup. Positioned
reconstruction now permits overlapping and nonmonotonic-start envelopes with
per-page containment validation. Public inline clips remain authoritative for
indivisible advances and trailing spaces. Installed JNI/Swift smoke includes a
shared original image and long-float EPUBs, checking geometry/pixels and all
7,500 letters through EOF. Long text/table floats now retain independent page
cursors, including nested floats and fixed orthogonal viewports. Ordinary tables
now establish an independent BFC beside external floats: columns are fixed after
the first committed fragment, while each new page selects a fitting rectangle.
Width/padding percentages use the original containing block. Clear waits for
matching continuations. The installed float-bfc-stream.epub smoke counts 3,350
letters and verifies table coordinates through EOF. Tables without external floats
keep their existing pagination path. Unbreakable table row groups still must fit a
page. Checkpoint cloning owns and budgets all pending continuation contexts;
no public record size, ABI epoch or schema changes.


The optional exr_hyphenator adds standalone C provider/pattern-query functions.
Existing layout_config, glyph and pager structures are unchanged, ABI epoch 1
and schema 6 remain. Host callback ownership transfers only on successful
create. Native pattern objects own their packed trie and language keys; source
buffers can be released after create. Context lifetimes are serialized, with
reentry rejected. Native UTF-8 byte offsets refer to the original word even
when Unicode full case folding expands characters. The installed C example is
built/run independently by desktop CI. No language data or new binary dependency
is shipped. This step does not enable automatic hyphens in any layout; pager,
session, CSS and Swift/JNI integration are subsequent work.

Automatic dictionary hyphenation is now opt-in through
exr_layout_create_hyphenated, exr_pager_set_hyphenator and
exr_session_set_hyphenator. Set the pager dictionary before choosing cache or
sequential access mode; changing the session dictionary clears its borrowed
chapter cache. Objects retain the dictionary, while completed layouts contain
only resolved glyphs. Existing layout_config/glyph record sizes, ABI epoch 1
and schema 6 remain unchanged. EXR_GLYPH_GENERATED marks synthetic text; an
independent generated hyphen has an empty source range at its original UTF-8
break point. A font-created cluster containing source and generated text can
retain a nonempty range. Consumers must preserve this flag in snapshots and
positioned reconstruction; selection/copy use source text, not generated glyph
characters. Swift/JNI install dictionaries independently per pager before next.
No language dictionaries are bundled; pattern format limits and separate data
licenses still apply.

Native pattern matching now canonicalizes both patterns and words using Unicode
17 NFC -> full fold -> NFC. This deliberately adds break matches for canonically
equivalent spellings (e.g. decomposed accents). The original document and provider
callback bytes remain unchanged. Grapheme minima and returned offsets still use
original text; folded/decomposed interiors never become new source positions.
A canonically merged pattern preserves max-weight conflict resolution. Consumers
need no record/ABI/schema migration. The separately versioned Unicode 3.2 PDF
password preparation is unchanged. Compound and spelling replacement grammars
remain unsupported by the native parser.
