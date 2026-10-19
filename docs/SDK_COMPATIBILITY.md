# EXReader SDK compatibility

ABI epoch **1** was introduced in development step **S091** (original build
**0.91.0**, commit `7dc8d8a`), now classified as **3.4.0** in the [changelog](../CHANGELOG.md). `EXR_ABI_VERSION` identifies the header's epoch;
`exr_abi_version()` identifies the loaded library's epoch. `EXR_VERSION` and
`exr_version()` identify the release. Epoch 1 does not retroactively classify older
SDK binaries that did not export the ABI query.

## Binary contract

Within one epoch, existing exported C symbols, calling conventions, enum numeric
values, public record sizes/alignment/member offsets, callback signatures and
ownership contracts remain compatible on the same operating system, architecture
and compiler ABI. Removing symbols or changing those layouts requires a new epoch.
Adding functions does not. Codec/algorithm feature gates retain their public symbols;
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
find_package(EXReader 3.33.1 EXACT CONFIG REQUIRED)
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
password preparation is unchanged.

Native UTF-8 pattern input now accepts two NEXTLEVEL rule sets, compound minima
and NOHYPHEN. No record size, ABI or schema change. Input left/right minima
continue to override whole-word minima, while component defaults come from the
file. File global minima of zero now consistently select the format default 2.
Without NEXTLEVEL, ordinary rules use implicit hyphen/apostrophe/en-dash/curly
apostrophe segmentation and suppression; this deliberately changes matching
of compound tokens. A file without NEXTLEVEL supplies the ordinary level;
its NOHYPHEN field does not replace the implicit layer's defaults. Use explicit
NEXTLEVEL to customize whole-word suppression. Inline gathering retains internal joiners,
so providers also see complete compound tokens. Original bytes and source
positions are unchanged. Structural segmentation may use protected punctuation,
but final visible opportunities still obey GLUE/grapheme protection. Native
matching enforces inward minima even for short leaves. The original provider
bitmap cannot express replacement text; the following query API adds that data.


Discretionary replacements add new C records/functions without changing existing
record sizes, callbacks, ABI epoch 1 or schema 6. exr_hyphenator_query returns an
owned immutable exr_hyphenation; all strings remain valid until result free,
independently of source/dictionary/provider lifetimes. The new discretionary
provider emits synchronously into a copying sink; sink errors are latched even
when ignored by a provider. Original bitmap providers remain supported.

Native dictionaries now accept pattern/before=after[,start,cut]. Malformed
ranges are EXR_FORMAT, not silently truncated. Explicit cut=0 is insertion;
replacement strings are literal by default; the explicit case policy is described below. Equal-weight plain
rules win over rewrites; conflicting equal-weight rewrites suppress the point.
The old breaks API intentionally omits spelling-changing opportunities. Layout
now selects the richer query when needed, including Swift/JNI pagers. Conditional
compound rewriting remains pending. Changed word remainders now receive fresh mapped queries. The installed C example exercises both APIs. An unsupported
raw TeX command now checks failed installation in Swift/JNI smoke, rather than
using slash as an unsupported token after slash grammar became supported.


Layout now renders discretionary before/after strings and includes them in final
shaping/width measurement. Generated glyph source ranges may be nonempty and
cover the replaced original text; do not discard them from hit/range mappings
or copy their characters into source text. Expansion sides retain protected source
selection ranges independently of display grapheme identity. Empty right-side deletions retain an invisible generated source span.
Strings remain literal and inherit their original side's style; display bidi
resolution is described below.
Internal U+00B7 now stays inside gathered words, including host-provider input.

Pending edits and cached word edits are deep-copied with pager checkpoints and
counted against line/checkpoint payload budgets. The three glyph buffers plus
owned word/edit capacities share the 16 MiB line budget. Existing public record
sizes, ABI epoch 1 and schema 6 are unchanged. After each committed replacement,
stale original dictionary bits are cleared and the actual display remainder is
queried again. Fresh ordinary/replacement opportunities must align with protected
display grapheme/GLUE boundaries, preserve original graphemes and advance display positions. Multiple generated points may share a source offset. Erase ranges may
start within a generated side; private raw indices preserve the exact display
range. Candidates whose left context was consumed by an ordinary break are
dropped with their automatic bit. Generated sides remain atomic to selection.
Derived tokens exceeding 256 scalars/1024 bytes use ordinary/emergency fallback.
Future edit context and generated-side wrapping are covered by the supplements below; the explicit Unicode case policy is described below. Installed Swift/JNI smoke now
checks actual replacement glyphs with nonempty original source intervals.

A zero-cut after insertion shares its source cluster with the following original
grapheme. Its glyph start/end may remain empty, while cluster_end includes that
grapheme. This preserves cursor access while display graphemes wrap a long inserted
side across lines and pages.

Display boundaries now replay Unicode 17 grapheme/line state for replacement
sides and the complete queued carry, including pending input. New joins can
widen cluster_start/end across original source positions (e.g. generated RI plus
original RI); they never expose positions within an original grapheme or generated
side. A cluster crossing ready/pending is deferred intact before remeasurement.
Format controls/selectors are hidden normally. Empty deletions have a distinct
private flag, omitted from public output, and do not enter Unicode/dictionary input.
Snapshots include all display states by value; no public record/API size changed.
Conditional compounds remain open; future
context verification is described in the following supplement.


### Display bidi after discretionary spelling changes (0.18 development)

Generated strings now participate in a mapped display analysis before shaping
and final visual ordering; mixed-direction visual subruns retain the original
source selection range, with direction-specific hit endpoints. No public record
size, symbol contract, ABI epoch or library schema changes. Private virtual
indices/flags never appear in installed SDK snapshots. Immutable history and
AUTO paragraph-base records survive checkpoints; ephemeral bidi views are rebuilt.
AUTO preflight ignores isolate contents and preserves current page/float geometry.
Its bounded two-base retry reports EXR_LIMIT for non-converging discretionary
layout. Providers must be deterministic and can be queried during preflight.
Installed JNI/Swift consumers verify actual Latin/Arabic/Han levels, source hits,
and leading neutral pages whose base changes after a later replacement.
Conditional compounds remain
open; future neutral/bracket context now uses the following proposal supplement.


### Stable display proposals across future edits (0.18 development)

Future spelling edits now participate before an affected row is published.
Risky contexts collect mapped display proposals and line boundaries, then replay
with that complete analysis before shaping. Acceptance requires every selected
line to match its proposal and both text/source mapping and line breaks to stay
unchanged. Up to eight proposals are allowed (EXR_LIMIT on non-convergence).
Formal replay rejects a changed provider/proposal with EXR_FORMAT before caching
the failed page. Deterministic providers can receive repeated queries.
Safe bidi boundaries keep ordinary mixed text bounded; actual preceding strong/
weak context is retained, and ES/CS/ET, NSM, brackets, controls and independent
AUTO B paragraphs are handled explicitly. Plans/prefixes count against the
16 MiB line/checkpoint payload; a 24 MiB temporary collector and ~64 MiB view cap
remain separate. Rebuilt views and shared immutable original bidi analyses avoid
copying complete text into every cursor/checkpoint. Copy/analysis work is charged
to the common work budget. No public API/record/ABI/schema changes.
JNI/Swift smoke verifies page-one plus signs at RTL level 1 even though the later
replacement that determines them is not on that page. Generated-side breaks and
explicit Unicode casing are covered below; conditional compounds, tall table-row
fragmentation and the broader VERSIONING.md roadmap remain open.


### Generated-side wrapping (0.18 development)

Transient grapheme identities separate display consumption from original source
affiliation. Committed after strings wrap with Unicode/ordinary dictionary and
emergency opportunities; their words can receive further spelling rewrites.
Mapped raw indices distinguish multiple edits at one source byte point. Original
selection ranges remain protected; no positions inside generated text become
original offsets. Public flags/boundaries contain no transient identities.
Before text plus the inserted hyphen remains a fitting left-line candidate: an
oversized unselected before string uses the existing original-text fallback.

Only private line-buffer state changes; installed record sizes, symbols, ABI 1
and schema 6 stay unchanged. Identities are copied in checkpoints, bounded and
charged through the existing glyph buffers; no parallel identity allocation or
new dependency is introduced. Original source affiliation can span more than one
page, including zero-cut insertions attached to the following original grapheme.

Pure-L insertion between adjacent L display scalars preserves strong context and
uses the existing fast path. Empty generated ranges refer to their following
original L anchor; other cases keep display proposal/analysis. The 1 MiB selected
and unselected insertion regression checks that ordinary text avoids repeated
whole-paragraph work without raising resource limits.


### Explicit native dictionary case policy (0.18 development)

The additive `exr_hyphenator_create_patterns_ex` symbol accepts LITERAL or WORD.
The legacy C constructor and existing Swift/JNI methods preserve literal behavior.
No public record size, ABI epoch (1), schema (6) or version change. The old JNI
native entry point remains present; a distinct entry point handles the explicit
policy, so older compiled Java consumers keep their calling contract. Providers
continue receiving original bytes and emitting literal discretionary strings.

WORD classifies original cased characters and applies Unicode 17 full mappings
to uniform lower/upper or initial-title words; mixed/uncased words remain literal.
Logical changed-word context includes unchanged prefix/suffix and both generated
sides, excluding the display hyphen. Standard Final_Sigma and tr/az/lt conditional
rules are included. Title preservation can extend end through an original retained
grapheme when moving/deleting the original initial; point is unchanged. Respect
the returned source ranges instead of assuming the dictionary cut stayed fixed.
Additional CLDR lexical tailoring can be supplied by host providers.

Generated text still shares the 128-scalar/512-byte cap, work/result budgets and
original selection affiliation. Case-sensitive display proposals, Unicode/shape
state, subsequent rematching and checkpoints use the existing common pipeline.
The compiled Unicode tables add no runtime component or dictionary download.
Installed C/C++ examples and two-page Swift/JNI smoke use the new policy while
retaining the preceding literal smoke checks.

Original inline window safety is classified once on demand in a cursor-local
cache; shared original bidi arrays remain immutable. Ordinary opens do not
classify this additional property. Temporary unmatched candidates can retain an accepted safe display
suffix instead of rescanning the whole source paragraph. Checkpoints rebuild
original safety and preserve the existing display prefix. The 1 MiB combining-
mark regression checks forward access, eviction, pixel-stable rewind and restored
checkpoints; work caps are unchanged.


Conditional compound stem reconstruction uses the existing C query/bitmap and
Swift/JNI pager calls. An explicit NEXTLEVEL dictionary can restore a left stem
for recursive matching without editing the original document. Only mapped whole
source intervals are returned; generated spelling has no invented interior source
positions. Only taking the corresponding line break applies its substitution.
Source grapheme minima, literal/WORD policy, 128-scalar/512-byte public result cap,
ABI 1 and schema 6 stay unchanged. Per-query conditional matching workspace and
owned stem strings are capped at 1 MiB. Installed C/C++ consumers verify recursive
breaks 2/4/7/9; Swift/JNI smoke checks the newly enabled source break on a real EPUB.


Tall table rows and connected rowspan groups now retain independent cell flow
cursors. Full lines/images cross pages without a shared canvas crop. Cell/grid
state and nested cursor allocations participate in checkpoint cloning and byte
accounting. Multi-column pages can overlap in their original source envelopes;
use actual glyph/cluster ranges for selection. The 128-float tree limit includes
cell cursors. Public C/Swift/JNI calls, record sizes, ABI 1 and schema 6 remain
compatible. Installed examples include a tall rowspan EPUB and use existing
pager calls; C++ also verifies checkpoint-based backward access.

Top/baseline groups probe one page before committing a tall row. Middle/bottom
alignment still needs full-height measurement, and auto-width tables still scan
full min/max-content input. Large-cell cost differences are recorded separately;
the performance report lists fixed, automatic and bottom-aligned costs separately.


RGB compositing adds size-tagged `exr_draw_sink_ex` and an optional `draw_ex`
tail to size-tagged `exr_fixed_input`. The original unversioned sink and fixed
render options keep their layouts. Existing providers still supply `draw`;
`exr_fixed_draw_ex` falls back to it with `sink.base`. Original annotation-capable
input prefixes remain accepted and have a compile-time ABI assertion.

For a host renderer, initialize `sink.struct_size`, retain the original callbacks
in `base`, and add blend plus paired begin/end layer callbacks. All callbacks use
`base.context`. A successful begin must be matched by end; commit=0 unwinds and
discards. A valid end consumes its layer even when reporting an error. PDF blend
consumers need the pair for isolated page content and Form/AP groups. The original
PDF draw entry rejects actual non-Normal blend paints and isolated Form groups.
Inspection consumers may skip primitives, but must acknowledge requested effects.

For built-in rendering no host migration is needed. Gray PDF output now uses an
RGB working image and converts at the end, subject to the existing 64 MiB RGB
bitmap ceiling. Isolated layers have a separate 64 MiB aggregate pixel budget;
combined fill/stroke uses two coverage masks charged to mask_budget. Callers
using a canvas directly can set the layer budget before entering layers. Layer
budget failure, cancellation or unbalanced scopes never returns a partial bitmap.
This is still 0.18.0 development, ABI 1 and schema 6.


Non-isolated RGB groups append optional `begin_group` to the size-tagged
`exr_draw_sink_ex`; all earlier prefixes remain accepted. Initialize the new
struct_size when recompiling. General begin is preferred; isolated requests
fall back to begin_layer, while non-isolated requests on an old consumer return
EXR_UNSUPPORTED. Either begin callback requires end_layer. The original sink,
fixed render options, ABI 1 and schema 6 retain their layouts/contracts.

Direct canvases can use exr_canvas_begin_group with flags=0 or
EXR_GROUP_ISOLATED, closing either with end_layer. Non-isolated groups reserve
24 bytes/pixel (RGBA8 plus five float channels), versus 4 for isolated layers;
both count against the aggregate 64 MiB default and the per-group 64 MiB cap.
The precision state remains private and is heap-stable across layer-stack growth.
No additional runtime component is introduced. The PDF Form/AP default I=false
now renders as non-isolated RGB; explicit CS on a non-isolated Form is malformed.
Knockout groups and graphics-state soft masks remain pending.

## Independent border sides and repeated table headers

`border-top/right/bottom/left` (width, colour and style) now reach blocks,
separate cells and collapsed grids. Uniform four-sided borders keep using
`exr_box.border_width`, `exr_box.border_color` and the DASHED/DOTTED/DOUBLE
flags, so existing drawing code is unchanged. When the four sides differ, the
layout appends one `EXR_BOX_BORDER` box per visible side instead of setting
`exr_box.border_width`; hosts that already paint collapsed-table border layers
handle them, while a host that only reads `border_width` must also draw border
boxes. No public record size, member offset, symbol, ABI epoch (1), schema (6) or
version changes. Table pagination also repeats leading `<thead>` rows at the top
of each continuation page; the extra repeated glyphs and boxes carry the header
source offsets.
## Mesh shadings 6/7 and DeviceCMYK groups

PDF mesh shadings types 6 (Coons patch) and 7 (tensor-product patch) now render
through the existing shading callback with the same bitmap-plus-matrix contract;
no callback or record changes. Transparency groups whose `/CS` is `DeviceCMYK`
are accepted: colours are converted with the engine's naive DeviceCMYK model and
the group composites in device RGB, so opaque content matches a CMYK-space
renderer but translucent overlaps may differ. Radial shadings with `/Extend`
now paint their extended colour into larger clips (a finite one-span margin per
side, like the axial path). No public symbol, record size, ABI epoch (1), schema
(6) or version changes.
## Canvas DeviceCMYK groups

`EXR_GROUP_CMYK` and `exr_canvas_path_cmyk` are additive: ABI epoch 1, schema 6
and the package version stay put. `exr_draw_sink_ex` gained one appended
`path_cmyk` callback; hosts that initialize `struct_size` to their own (older)
size keep working and simply leave it NULL. The canvas sink implements it, so PDF
DeviceCMYK groups now carry source components into the four-component buffer;
nested groups inherit the blend space and compound fill+stroke paths composite as
one CMYK element. Non-separable blend modes inside a CMYK group return
`EXR_UNSUPPORTED` instead of approximating.
## Package version 3.33.1

The current tree, header and installed config package report **3.33.1**
development. ABI epoch 1 and library schema 6 are unchanged: no exported
symbol, record layout, enum value or callback signature moves with this
renumbering. The complete historical size-based reclassification is in the
[changelog](../CHANGELOG.md); the previous 0.20.0 component split is now 3.33.0.
Select this package with `find_package(EXReader 3.33.1 EXACT
CONFIG REQUIRED)`. The 0.18.0 records (code commit `ec8d4a98`, DLL SHA-256,
CI run 39148719500 and the benchmark samples) keep their original number.

## 0.19.0 rendering corrections and license

The original EXReader code and fixtures now use MIT. Third-party notices retain
their own terms. Default and CI builds exclude FAAD2; explicitly enabling that
GPL codec produces a linked binary that cannot be distributed under MIT alone.
Existing releases retain the permissions already granted with them.

With ICC enabled, DeviceCMYK uses the complete bundled Argyll fallback profile;
ICC-disabled builds retain the documented simple device conversion. CMYK group
buffers blend native components, including subtractive separable and nonseparable
mode formulas. Earlier descriptions of RGB-only group blending and rejection of
all nonseparable CMYK modes above describe previous checkpoints. Images and
shadings still pass through RGBA in CMYK groups, losing original separations.
The 3.33.1 correction below supersedes the explicit RGB child issue.

Shading opacity, blend and soft masks now reach the painter, mesh interpolation
precedes color conversion, and Matte is undone before ICC conversion. These
corrections change affected pixels without changing public record layouts,
symbols, callback signatures, ABI1 or schema6. See AUDIT-2026-10-19.md for scope.

## Component linkage

`exreader.h` remains the full declaration umbrella. `exr/core.h` includes only the
reading core; the other public headers can each be included independently in C
and C++. The default compatibility shared library retains all 304 existing
exports. Static component consumers link `EXReader::exr_core`, `exr_audio`,
`exr_library`, `exr_pdf`, `exr_pdf_edit` or `exr_textindex`; these targets propagate
`EXR_STATIC` automatically. Choose either the compatibility shared library or the
static components within one process, so object ownership stays in one instance.

Component removal is an explicit build profile: an omitted library has no binary
or exported entry points in that profile. This differs from disabling a codec
inside an included component (for example AAC OFF still exposes the documented
unavailable-codec functions). Hosts discover installed components with CMake
`find_package(EXReader CONFIG REQUIRED COMPONENTS core audio)`; absent required
components fail configuration. The standard full build remains the ABI1
compatibility artifact.

Core and optional component release numbers are maintained in
`cmake/versions.cmake` and exposed by the corresponding public version macros and
installed CMake target `EXR_COMPONENT_VERSION` properties. Core and PDF reading are 3.33.1; the other components remain 3.33.0
after this fix and can be released independently. Release
numbers follow update size: very large updates increment the major number,
medium updates increment the minor number, and small bug fixes increment the
patch number. Incrementing major or minor resets the following numbers to zero.
ABI compatibility is tracked separately: this split preserves ABI1 core
signatures, records and ownership rules.

Static Windows components use the same MSVC runtime setting as the SDK build
(default `/MT`, `/MTd` for Debug). The installed component consumer examples use
that setting explicitly.

## 3.33.1 group colour spaces and knockout flags

PDF group `/K true` now enables knockout; false, null or omission selects a
normal group. Earlier implementation and fixture generation inverted this flag.
The 50-scene PDF inputs have been regenerated with the correct literal flags;
the independent Decimal pixel references and existing error tolerances remain.
Affected PDFs can change pixels while the public ABI remains epoch 1.

`EXR_GROUP_RGB` explicitly selects RGB in an isolated Gray/CMYK parent. An omitted
colour-space flag still inherits. `exr_canvas_begin_layer` follows its documented
isolated RGB contract. Child output converts at group commit, then group opacity,
blend and clipping apply in the parent's space. Parent native inks and space are
restored on both commit and discard. Conflicting space flags are invalid; switching
to RGB from Gray/CMYK without isolation is unsupported. PDF non-isolated forms with
an explicit `/CS` remain invalid under the existing contract. A custom `begin_group`
consumer must honour the RGB flag or reject it; legacy `begin_layer` supports the
isolated RGB fallback. No function signatures, exported symbols or record layouts
change. Images and shadings still lose original ink separations through RGBA.
