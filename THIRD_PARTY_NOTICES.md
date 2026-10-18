# Native C dependencies

EXReader's own C sources are GPL-3.0-only. Third-party code keeps its original license.

## PDF calculator command names

The compatibility command names in `src/pdf_calculator.c` follow PDF 32000-1,
table 42, and the PostScript Language Reference, third edition, section 1.5.
Copyright 1985-1999 Adobe Systems Incorporated. All rights reserved.
Adobe permits use of the copyrighted command list to write compatible programs
and interpreters, with an appropriate copyright notice. The calculator
implementation is original EXReader C code; no Adobe interpreter code is included.
PostScript is a registered trademark of Adobe Systems Incorporated.

| Component | Pinned source | License | Use |
| --- | --- | --- | --- |
| FreeType | VER-2-14-1, freetype/freetype | FreeType License OR GPL-2.0-only; FreeType License selected | Font loading, glyph metrics and rasterization |
| Expat | R_2_9_0, libexpat/libexpat | MIT | XML parsing with external entity resolution disabled |
| miniz | 3.1.2, richgel999/miniz | MIT | ZIP containers and decompression |
| SQLite | 3.54.0 amalgamation, sqlite.org | Public domain | Local bookshelf and annotations |
| stb_image | 2c980bb59875b0d32144a71867fbdebb2f77cd20, nothings/stb | MIT OR public domain; MIT selected | PNG/JPEG decoding only |
| LittleCMS | lcms2.19.1, mm2/Little-CMS | MIT | Optional ICCBased profile-to-sRGB conversion; EXR_ENABLE_ICC |

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

`src/indic_data.h` additionally derives full script tags, Indic syllabic/positional
categories and canonical combining classes from pinned Unicode 17
`Scripts.txt`, `PropertyValueAliases.txt`, `IndicSyllabicCategory.txt`,
`IndicPositionalCategory.txt` and `UnicodeData.txt`. Reproduce and check using
`python tools/generate_indic.py --download --check`; the same Unicode-3.0
notice applies.

## Original font fixtures and development tools

`tests/fixtures/fonts`, `tests/fixtures/shaping` and `tests/fixtures/indic` contain original geometric
glyphs and OpenType rules, GPL-3.0-only, copyright 2026 EXReader contributors.
Their generators use fontTools during development. The committed fonts require
neither fontTools nor Python at build or runtime.

HarfBuzz 14.6.0, accessed through the development-only uharfbuzz 0.56.3 package,
was used as an independent oracle for selected fixture glyphs and anchor values.
HarfBuzz and fontTools are not linked into or distributed as part of the native
engine.

## MOBI format reference

HUFF/CDIC field semantics were checked against the GPLv3 KindleUnpack project's
[`lib/mobi_uncompress.py`](https://github.com/kevinhendricks/KindleUnpack/blob/2efebb372258cdcbd1478da6e5f843c97504ebb5/lib/mobi_uncompress.py),
by the KindleUnpack developers. EXReader implements the decoding, bounded dictionary cache,
cycle detection and record handling in C in `src/huff.c` and `src/formats.c`, under GPL-3.0-only.


KF8 INDX/TAGX, FDST and skeleton/fragment semantics were checked against
[`lib/mobi_index.py`](https://github.com/kevinhendricks/KindleUnpack/blob/2efebb372258cdcbd1478da6e5f843c97504ebb5/lib/mobi_index.py)
and [`lib/mobi_k8proc.py`](https://github.com/kevinhendricks/KindleUnpack/blob/2efebb372258cdcbd1478da6e5f843c97504ebb5/lib/mobi_k8proc.py)
of the same GPLv3 project. EXReader's bounded C reconstruction is in `src/kf8.c`.


KF8 resource URI and FONT field semantics were also checked against
[`lib/mobi_html.py`](https://github.com/kevinhendricks/KindleUnpack/blob/2efebb372258cdcbd1478da6e5f843c97504ebb5/lib/mobi_html.py)
and [`lib/kindleunpack.py`](https://github.com/kevinhendricks/KindleUnpack/blob/2efebb372258cdcbd1478da6e5f843c97504ebb5/lib/kindleunpack.py).
FONT zlib streams use the existing miniz dependency; all resource handling remains native C.


KF8 NCX tag meanings and hierarchy fields were checked against
[`lib/mobi_ncx.py`](https://github.com/kevinhendricks/KindleUnpack/blob/2efebb372258cdcbd1478da6e5f843c97504ebb5/lib/mobi_ncx.py).
NCX/CNCX validation, hierarchy checks and resource construction are implemented in C.


Declared hybrid EXTH 121 boundaries and header-relative section indexes were checked against
[`lib/mobi_split.py`](https://github.com/kevinhendricks/KindleUnpack/blob/2efebb372258cdcbd1478da6e5f843c97504ebb5/lib/mobi_split.py)
and `lib/mobi_header.py` at the same revision. Shared resources are borrowed from the original
record directory; EXReader does not call the reference splitter or create an intermediate book.


## PDF font facts

`src/pdf_font_data.h` contains static encoding, glyph-name/Unicode and standard
14 width facts. Adobe Glyph List and ITC Zapf Dingbats Glyph List are from
[adobe-type-tools/agl-aglfn](https://github.com/adobe-type-tools/agl-aglfn/tree/4036a9ca80a62f64f9de4f7321a9a045ad0ecfd6),
Copyright 2002-2019 Adobe, BSD-3-Clause. Their complete notice is retained in
`licenses/adobe-glyph-list.txt`.

Encoding vectors and standard-font metric facts are extracted from
[PDF.js encodings.js and metrics.js](https://github.com/mozilla/pdf.js/tree/81525fd446779f0a29003cf06e3ba33751954826/src/core),
Copyright 2012 Mozilla Foundation, Apache-2.0. The full license is retained in
`licenses/pdfjs.txt`. Both notices are installed in the SDK license directory.

`python tools/generate_pdf_fonts.py --download --check` verifies the pinned
source SHA-256 hashes and reproduces the committed tables and notices. It parses
only static facts; downloaded JavaScript is never executed. Normal C builds
require neither Python nor network access. PDF interpretation, font mapping and
raster algorithms remain EXReader's own C implementation.


## Optional MP3 decoder

`EXR_ENABLE_MP3=ON` (default) builds the CC0-1.0 `minimp3.h` codec from
[lieff/minimp3](https://github.com/lieff/minimp3/tree/ea99364f61c14656440e8d77e9c233ccf3124633),
commit `ea99364f61c14656440e8d77e9c233ccf3124633`. The source archive is pinned
to SHA-256 `5628166eb82a9bb581317918a334c317a2c0a30278bb14a20381307976768f34`.
Only the core C header is compiled; the upstream test audio, player and
`minimp3_ex` full-file index are not part of the SDK. The complete upstream CC0
license is installed at `share/exreader/licenses/minimp3/LICENSE`.

EXReader's source callbacks, tag bounds, Xing/LAME trimming, bounded decoder-state
checkpoints, ownership and cancellation are implemented in `src/mp3.c`; MP3
synthesis itself uses minimp3. Disabling the component avoids its source download
and codec footprint while retaining API symbols with availability reporting.

## Optional AAC decoder

`EXR_ENABLE_AAC=ON` builds FAAD2 from
[knik0/faad2](https://github.com/knik0/faad2/tree/521d105979795b887ea11e1f36565e97a8fbfc53),
commit `521d105979795b887ea11e1f36565e97a8fbfc53`, archive SHA-256
`9284bd9c5ef998f636b233055f4d988aadf0d5a97acdb3109bcb9d4e3c7cfdd8`.
FAAD2 is Copyright (C) 2003-2005 M. Bakker, Nero AG, licensed under GPL-2.0-or-later;
EXReader distributes this combination under GPL-3.0-only.
Code from FAAD2 is copyright (c) Nero AG, www.nero.com.
The full upstream COPYING and copyright notice are installed under
`share/exreader/licenses/faad2`. Only the floating-point codec is built, without
the CLI, DRM or fixed-point variants. This component defaults to OFF and is not
downloaded when disabled. ADTS source access, validation, ownership, cancellation
and exact bounded replay are EXReader C code; AAC synthesis uses FAAD2.
