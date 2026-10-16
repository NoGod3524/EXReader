# Native C dependencies

EXReader's own C sources are GPL-3.0-only. Third-party code keeps its original license.

| Component | Pinned source | License | Use |
| --- | --- | --- | --- |
| FreeType | VER-2-14-1, freetype/freetype | FreeType License OR GPL-2.0-only; FreeType License selected | Font loading, glyph metrics and rasterization |
| Expat | R_2_9_0, libexpat/libexpat | MIT | XML parsing with external entity resolution disabled |
| miniz | 3.1.2, richgel999/miniz | MIT | ZIP containers and decompression |
| SQLite | 3.54.0 amalgamation, sqlite.org | Public domain | Local bookshelf and annotations |
| stb_image | 2c980bb59875b0d32144a71867fbdebb2f77cd20, nothings/stb | MIT OR public domain; MIT selected | PNG/JPEG decoding only |

CMake verifies every source archive using the SHA-256 values in cmake/deps.cmake. CSS matching, Unicode boundary and bidirectional algorithms, OpenType GSUB/GPOS processing, line breaking, pagination, image placement, table layout, pixel compositing, document positions, the document model and format extraction are EXReader C code. FreeType supplies font access, glyph metrics and rasterization; stb_image supplies decoded image pixels. License texts are included in the installed SDK under share/exreader/licenses.

The old JavaScript framework and reader are retained in Git history and their respective reader branches. They are not linked into this native engine.

## Unicode data

The compact C property tables in `src/unicode_data.h` are derived from the
Unicode Character Database 17.0.0: `GraphemeBreakProperty.txt`, `emoji-data.txt`
(`Extended_Pictographic`), `DerivedCoreProperties.txt` (`InCB`) and
`LineBreak.txt`. The unmodified official `GraphemeBreakTest.txt` corpus is
included in `tests/fixtures/unicode`. These data and their derived tables use
the **Unicode-3.0** license, separate from EXReader's GPL-3.0-only code.
The full copyright and permission notice is in
`tests/fixtures/unicode/LICENSE.txt` and the installed SDK's licenses directory.

Reproduce the tables with `python tools/generate_unicode.py --download`, or
verify them with `python tools/generate_unicode.py --download --check`.
The generator records the official source URLs and verifies fixed SHA-256
hashes before using any downloaded bytes. Ordinary C builds use the committed
header without Python or network access. The original property files remain
in the ignored `build/unicode-cache` directory.

The 0.12 bidirectional tables in `src/bidi_data.h` use Unicode 17.0.0
`extracted/DerivedBidiClass.txt`, `BidiBrackets.txt` and `BidiMirroring.txt`.
The complete, unmodified `BidiTest.txt` and `BidiCharacterTest.txt` corpora are
included in `tests/fixtures/bidi`. Reproduce or verify these tables and data with
`python tools/generate_bidi.py --download --check`; the generator pins the official
Unicode URLs and each input's SHA-256 value.

The joining/script tables in `src/shaping_data.h` use Unicode 17.0.0
`extracted/DerivedJoiningType.txt` and the Latin / Arabic entries of `Scripts.txt`.
`python tools/generate_shaping.py --download --check` verifies the official source
hashes and reproduces the committed header. All these additional Unicode files
and derived tables use the same **Unicode-3.0** license, whose full notice is
`tests/fixtures/unicode/LICENSE.txt` and is installed with the SDK.

## Original font fixtures and development tools

`tests/fixtures/fonts` and `tests/fixtures/shaping` contain original geometric
glyphs and OpenType rules, GPL-3.0-only, copyright 2026 EXReader contributors.
Their generators use fontTools during development. The committed fonts require
neither fontTools nor Python at build or runtime.

HarfBuzz 14.6.0, accessed through the development-only uharfbuzz 0.56.3 package,
was used as an independent oracle for selected fixture glyphs and anchor values.
HarfBuzz and fontTools are not linked into or distributed as part of the native
engine.
