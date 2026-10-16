# Unicode 17 bidirectional conformance data

`BidiTest.txt` and `BidiCharacterTest.txt` are the complete, unmodified Unicode
17.0.0 files. The first supplies 490,846 property sequences, expanding to 770,241
paragraph-direction cases. The second supplies 91,707 explicit-character cases.
`tests/test_bidi.c` checks all 861,948 cases against their levels and visual order.

The corpora cover UAX #9 through L2; they do not test font shaping or glyph drawing.
Additional native tests cover UTF-8 ranges, embedded NUL, multiple paragraphs,
line-slice L1, inherited defaults, overflow and long sequences.

`python tools/generate_bidi.py --download --check` verifies the pinned source
SHA-256 values and reproduces `src/bidi_data.h`. Normal builds use committed data
without Python or downloads. Source URLs and hashes are in the generator.

These Unicode data files use the Unicode-3.0 license in
`../unicode/LICENSE.txt`.
