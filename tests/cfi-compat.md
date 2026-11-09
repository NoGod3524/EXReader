# EPUB CFI compatibility

The grammar and public examples come from [W3C EPUB CFI 1.1](https://w3c.github.io/epub-specs/epub33/epubcfi/).
The implementation is original C; it reuses EXReader's existing retained DOM,
package routing and CFI point/range generation. No foliate-js implementation was copied.

## A. Parsing and serialization

`exr_cfi_parse` accepts wrapped CFIs and bare scheme data, independently of a book.
The lexer advances through step, indirection, terminal offset, assertion, escape,
parameter and range states. It handles ID assertions (including literal `@id`),
before/after text assertions, side bias, escaped reserved characters including `=`,
unknown extension parameters/CSV values, temporal and spatial offsets. Spatial
coordinates must be between 0 and 100. Unknown parameters survive serialization
and are ignored by DOM resolution. Ranges cannot carry side bias or have an
offset in the shared parent path. Range order is checked during document
resolution, after ID/text corrections.

Failures give `exr_cfi_diagnostic.code` plus an input UTF-8 byte position:
`SYNTAX=1`, `NUMBER=2`, `ESCAPE=3`, `ASSERTION=4`, `RANGE=5`, `ENCODING=6`,
`LIMIT=7`. General return values are `EXR_FORMAT`, `EXR_ENCODING` or `EXR_LIMIT`;
invalid API arguments use `EXR_ARGUMENT`. Input must be XML-valid UTF-8.
The canonical wrapped representation is limited to 65,536 bytes and 768 steps.
CFIs are raw scheme data; URI percent decoding belongs to the caller.

The opaque parsed value retains validated lexemes. `exr_cfi_serialize` preserves
the scheme data **byte for byte**, including assertion order and parameter order;
bare input gains `epubcfi(...)`. `exr_cfi_endpoints` expands ranges into PS and PE.
Temporal/spatial CFIs parse and serialize, but text anchor resolution returns an
explicit format error for those media locations.

## B. DOM and text offsets

`exr_document_cfi_point_at` and `exr_document_cfi_point_offset` map normalized UTF-8
byte boundaries to original XML text nodes with raw UTF-16 offsets. Node ranges
already contain visibility, paragraph breaks and cross-inline space folding;
the mapping replays each visible node's non-space scalars against those ranges.
Synthetic paragraph breaks map to text boundaries on their respective sides.
Thus generated CFIs contain real XML paths, with IDs and the original package
spine route, rather than offsets attached to an invented text-only DOM.

All normalized scalar boundaries round-trip, including both sides of inserted
spaces/newlines, trimmed whitespace, suppressed CJK spaces and non-BMP text.
Multiple raw whitespace boundaries can import to the same normalized boundary.
Surrogate interiors and UTF-8 interiors cannot become content anchors and fail
explicitly. Hidden/unprojected text fails. Mapping takes a retained DOM snapshot;
bounded chapter-reader views return `EXR_UNSUPPORTED`. An empty chapter maps to
the empty XML root child boundary. This adds no projection or layout mutations.

## C. Content anchors

The new layout APIs take the built-in indexed EPUB publication:

```c
exr_range_to_cfi(publication, &range, control, &cfi, &error);
exr_range_from_cfi(publication, cfi, control, &range, &error);
exr_anchor_to_cfi(publication, &anchor, control, &cfi, &error);
exr_anchor_from_cfi(publication, cfi, control, &anchor, &error);
```

Each endpoint is loaded independently, mapped through its raw DOM and routed
through the original OPF itemref. A cross-part range shares its package ancestor.
Import validates both endpoints; reversed ranges fail. Point CFIs import as
collapsed ranges. Missing/ambiguous anchors fail instead of choosing a fallback.
Custom/non-EPUB providers fail explicitly. Owned strings use `exr_free`; content
anchors use `exr_content_anchor_free`. Failures clear outputs. Cancellation is
propagated through mapping, routing and anchor capture.

Losslessness means exact equality of both `(part, normalized UTF-8 byte offset)`
endpoints and **every field** of content anchors captured by `exr_anchor_from_range`
in an unchanged publication. It does not mean retaining an imported foreign
CFI's lexical spelling after conversion to a content anchor: that API captures
the local canonical selector. Serialization of a parsed CFI retains its spelling.

## D. Reproduction and evidence

Final acceptance on 2026-11-08:

| Check | Result |
| --- | --- |
| Parse and invalid-input diagnostics | 63/63 (25 valid, 38 invalid) |
| Parse/serialize equivalence | 25/25; exact scheme data |
| Same-part anchor/range round trips | 100/100, 100% lossless |
| Cross-part ranges | 10/10, 100% lossless |
| 紅樓夢 positions | 20/20, identical landing points |
| Real-book layout regression | 19/19; 11,296 pages; 0 page-count/hash changes |
| Full ctest | 218/218; 212 existing + 6 new groups |

Six new ctest groups: `native-cfi-compat-{parse,invalid,mapping,roundtrip,cross,contracts}`.
The vectors include 13 W3C examples plus original assertions/escapes/extension/
range/invalid cases. Every prefix of every valid vector is also checked for
safe truncation handling. Mapping checks every normalized scalar boundary in
a mixed whitespace/inline/Chinese/emoji fixture, plus independent expected DOM
paths, foreign raw UTF-16 offsets, text-assertion correction and quoted end points.
Range sampling uses the deterministic seed `0x41ce2026`; failures count against
the denominator. Additional whole-part, collapsed-start/end and empty-chapter
cases are checked separately. The real-book run samples 20 positions across
紅樓夢's parts. Its actual positions and generated CFIs are retained in `real.txt`.

Build with full tests, tools, shared compatibility DLL and fuzz enabled. This
Windows configuration uses Release/GCC; audio/library/text-index/PDF/PDF-edit/JPX
are enabled; ICC, optional image codecs, MP3, AAC and PDF crypto are disabled.
The full CMake cache is retained with evidence. Before modifying implementation,
build baseline `b7bad7f0` with the same settings and save its DLL as `baseline.dll`.

```powershell
ctest --test-dir build/cfi --output-on-failure -j 4 > build/cfi/ctest-final.log
# Run once per DLL; use realbooks-before.json for baseline output, then
# realbooks-final.json with --baseline build/cfi/realbooks-before.json for candidate.
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json `
  --dll build/cfi/libexreader.dll --font C:/Users/Oscar/exr-deps/reader-font/Reader.otf `
  --layout tools/regress/layout.json --output build/cfi/realbooks-final.json `
  --baseline build/cfi/realbooks-before.json --source-revision cfi-working-tree --workers 4
python tests/collect_cfi_acceptance.py --build build/cfi
```

`cfi-acceptance-20261108.json` contains the seven acceptance results, source/DLL/
test/font hashes and content fingerprints. Its companion directory contains
per-range/per-position logs, layer checks, full ctest output, build configuration
and compressed per-page before/after pixel hashes. Books stay outside the repo.

Protected-tree registration: `include/exr/{document,layout}.h`,
`src/{cfi,cfi_syntax,cfi_offset,publication}.c`, `src/document_internal.h`, and
the new tests/evidence. `tools/layers.json` registers both new C files;
`CMakeLists.txt` only registers the six suites. No new private header, no
`examples/` changes, no workflow edits and no layout algorithm changes.
