# Content range acceptance

`exr_text_position` counts normalized UTF-8 **bytes within a publication part**.
`exr_text_range` is half open and ordered by publication directory index. It can
cross pages and parts. It contains no page numbers or pixel positions.

`exr_anchor_from_range()` captures two owned endpoint selectors. Each carries a
stable part ID/path, the text size and FNV-1a revision, and 32 Unicode scalars of
context on each side. The revision is deterministic modulo 2^64; hosts must
preserve all 64 bits when storing it (for example as a hexadecimal string).
Unchanged text uses the saved offset after checking its context. Edited text
uses `exr_anchor_resolve_ex()`; missing or equally strong matches return
MISSING/AMBIGUOUS with all range fields SIZE_MAX. Part reordering is supported;
IDs must retain their meaning across editions. Duplicate IDs are disambiguated
by path; duplicate ID/path pairs reject capture. Repeated text in an unchanged
part is covered by the revision check. This revision is a change detector, not a
cryptographic identity or an authenticity check.

Character expansion uses Unicode graphemes, including combining sequences and
ZWJ emoji. Word and sentence policies are specified in `include/exr/layout.h`;
word selection has no dictionary segmentation and sentence selection has no
abbreviation inference. Expansion loads only endpoint parts. Mapping likewise
loads endpoint snapshots and scans each for its revision; it does not require
layout. `exr_hit_test()` takes a layout and its publication part index, and uses
page-local coordinates with y down. Hits return caret cluster edges. Images and
coordinates outside text lines return SIZE_MAX.

The host owns serialization, highlight drawing and annotation UI.

## Reproduce

The five `native-content-*` ctests run synthetic, deterministic data and bundled
fonts on every full native test build:

```sh
ctest --test-dir build/anchors -R native-content --output-on-failure
```

Run the same executable on a real EPUB and real fonts:

```sh
build/anchors/exreader-content-ranges-test measure BOOK.epub NotoSerifSC-VF.ttf Reader.otf
```

The driver chooses the first two parts larger than 10,000 normalized bytes. Its
LCG seed is `0x41ce2026`. It samples Unicode scalar boundaries, including point
bookmarks, short ranges and cross-part ranges (20/200 mapping samples and
10/100 reflow samples). Successful roundtrip means FOUND and **both** endpoint
part indices and offsets equal the original; missing, ambiguous and error cases
are failures in the denominator. Each reflow stage builds a fresh layout and
loads fresh part documents. Book CSS/embedded fonts are disabled for these
measurements so the requested sizes and fonts actually take effect. Intermediate
stages also check every range. The three reported rates compare the final state
against the originally captured 17px/1280x800 ranges. Page movements at intermediate
stages prove the layout actually changed. The expansion suite separately checks
EOF and cross-part exclusive ends at offset zero.

The independent positioned hit fixture has ten samples in each category: body,
line start, line end, punctuation, image. Additional checks cover image/text
overlap, RTL, vertical text, invalid pages, NaN and outside-line coordinates.

The 19-book rendering regression uses `tools/regress/run_realbooks.py` before and
after the change, with identical configuration and font. It compares every page's
visible RGBA-row SHA-256, page count, dimensions and glyph count. No book text or
rendered pages are committed. `anchor-acceptance-20261107.json` records the measured
results, input hashes and per-book page-hash fingerprints; `ANCHOR-OUT.txt` records
the work and commands.
