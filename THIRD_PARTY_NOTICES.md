# Native C dependencies

EXReader's own C sources are MIT. Third-party code keeps its original license.

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
| Argyll fallback CMYK profile | Graeme Gill; full 961,644-byte ICC, zlib embedded | Public domain; original notice in licenses/default-cmyk-profile.txt | Default DeviceCMYK and inverse conversion when EXR_ENABLE_ICC is enabled |
| LittleCMS | lcms2.19.1, mm2/Little-CMS | MIT | Optional ICCBased profile-to-sRGB conversion; EXR_ENABLE_ICC |
| Mbed TLS crypto subset | mbedtls-3.6.7, Mbed-TLS/mbedtls | Apache-2.0 OR GPL-2.0-or-later; Apache-2.0 selected | Optional PDF MD5/SHA-256/384/512 and AES-CBC/ECB; EXR_ENABLE_PDF_CRYPTO |

CMake verifies every source archive using the SHA-256 values in cmake/deps.cmake. CSS matching, Unicode boundary and bidirectional algorithms, OpenType GSUB/GPOS processing, line breaking, pagination, image placement, table layout, pixel compositing, document positions, the document model and format extraction are EXReader C code. FreeType supplies font access, glyph metrics and rasterization; stb_image supplies decoded image pixels. License texts are included in the installed SDK under share/exreader/licenses.

The old JavaScript framework and reader are retained in Git history and their respective reader branches. They are not linked into this native engine.

The legacy ARC4 key schedule and byte loop in `src/pdf_crypto.c` adapt
`library/arc4.c` from Mbed TLS **mbedtls-2.28.10**, Copyright The Mbed TLS
Contributors, under Apache-2.0. Context handling and cancellation are adapted
for EXReader; this code is used only to read legacy PDF R2-4. Both the full
Mbed TLS license text and this modification notice accompany installed SDKs.
The other cryptographic primitives are built from the pinned 3.6.7 source.
No TLS/network, certificate parser, random-number generator or encryption writer
is included in EXReader's selected component.

`src/pdf_saslprep_data.h` contains Unicode 3.2 mapping, normalization, combining,
composition and stringprep properties generated from Python's frozen UCD and
RFC 4013 tables by `tools/generate_saslprep.py`. The Unicode-3.0 license in
`tests/fixtures/unicode/LICENSE.txt` applies to these data. No Python code is
linked into the SDK. Original security fixtures under `tests/fixtures/pdf-crypto`
are generated with independent pypdf/cryptography development tools.

The private four-component JPEG adapter in `src/images.c` adapts row reconstruction
from stb_image's `load_jpeg_image`, using the pinned decoder's entropy, IDCT,
upsampling and YCbCr routines. This adapted portion retains stb_image's MIT
license (Copyright (c) 2017 Sean Barrett); the complete notice is distributed in
the stb license file alongside the SDK. PDF Decode, masking and color-space
conversion are applied after component reconstruction.

```text
Copyright (c) 2017 Sean Barrett
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Unicode data

The compact C property tables in `src/unicode_data.h` are derived from the
Unicode Character Database 17.0.0: `GraphemeBreakProperty.txt`, `emoji-data.txt`
(`Extended_Pictographic`), `DerivedCoreProperties.txt` (`InCB`) and
`LineBreak.txt`. The unmodified official `GraphemeBreakTest.txt` corpus is
included in `tests/fixtures/unicode`. These data and their derived tables use
the **Unicode-3.0** license, separate from EXReader's MIT code.
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
glyphs and OpenType rules, MIT, copyright 2026 EXReader contributors.
The root MIT grant also covers these original assets when an older embedded
font name or archived fixture manifest still carries its previous license label.
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
cycle detection and record handling in C in `src/huff.c` and `src/formats.c`, under MIT.


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
Enabling this component produces a GPL-covered linked combination; that binary
cannot be distributed under MIT alone. The default build and CI leave it disabled.
EXReader's original adapter source remains available under MIT.
Code from FAAD2 is copyright (c) Nero AG, www.nero.com.
The full upstream COPYING and copyright notice are installed under
`share/exreader/licenses/faad2`. Only the floating-point codec is built, without
the CLI, DRM or fixed-point variants. This component defaults to OFF and is not
downloaded when disabled. ADTS source access, validation, ownership, cancellation
and exact bounded replay are EXReader C code; AAC synthesis uses FAAD2.


## Hyphenation Unicode data and external test dictionaries

`src/hyphen_unicode_data.h` derives full case folding and L/M/N category ranges
from Unicode 17.0.0 `CaseFolding.txt` and `UnicodeData.txt`, under **Unicode-3.0**.
The same Unicode copyright/license installed above applies. Reproduce with
`python tools/generate_hyphen_unicode.py --download --check`; the generator pins
both source SHA-256 values. No language dictionary is bundled with the SDK.
The original weighted patterns in `examples/hyphen.c` are EXReader MIT
sample code, not a complete natural-language dictionary.

`tools/check_hyphen_reference.py` is an optional development check against a
separate Pyphen 0.17.2 installation. Pyphen and its language dictionaries are not
linked, copied into the SDK or required for builds. Each external dictionary
retains its own license; consult its `README_hyph_*.txt` and Pyphen package
license before redistribution. Recorded oracle results contain hashes/counts,
not dictionary data. English US COMPOUND minimum metadata is explicitly removed
for the portable-pattern comparison; this is not validation of compound rules.

`tests/fixtures/shaping/hyphen.ttf` derives only from EXReader's original rectangle
shaping fixture, adding an original hyphen outline and a test f/hyphen GPOS pair.
It is generated by `tools/generate_hyphen_layout_fixtures.py`, MIT.

## Unicode 17 canonical normalization data

`src/normalize_data.h` derives canonical decomposition, canonical combining
classes and composition pairs from Unicode 17.0.0 UnicodeData.txt and
CompositionExclusions.txt. Algorithmic Hangul decomposition/composition is in
EXReader's C code. Unicode-3.0 covers the derived data and the original official
`tests/fixtures/unicode/NormalizationTest.txt`; its license is already included
in the SDK. The generator pins all inputs by SHA-256 and uses the Python standard
library, not the host Python Unicode version. Reproduce with
`python tools/generate_normalize_unicode.py --download --check`.
These Unicode 17 data do not replace PDF SASLprep's mandated Unicode 3.2 tables.

`tools/check_hyphen_compound.py` has an independent literal-overlay development
oracle. It can additionally compare with a caller-supplied libhyphen build and
its official substring preprocessor. Neither libhyphen, its Perl script nor its
patterns are linked into or distributed with EXReader. External dictionaries
retain their separate data licenses; raw input hashes and explicit reference
preprocessing are recorded in verification output.


`tools/check_hyphen_replacements.py` contains an independent literal-overlay
oracle for discretionary replacement records. Its optional Pyphen comparison
uses an unmodified external Catalan dictionary and records its hash/counts.
The external Hungarian dictionary's malformed rules are explicitly rejected,
not edited and counted as successful input. Neither dictionary nor Pyphen is
shipped or linked. The installed example uses EXReader's original synthetic
patterns and no natural-language dictionary payload.


## Unicode 17 full case data

`src/case_unicode_data.h` and `tests/fixtures/unicode/CaseMappingTest.txt` derive
default full lower/title/upper mappings and contextual properties from Unicode
17.0.0 `UnicodeData.txt`, `SpecialCasing.txt`, `DerivedCoreProperties.txt` and
`PropList.txt`, under **Unicode-3.0**. The generator pins each official input SHA-256:
`python tools/generate_case_unicode.py --download --check`. The existing installed
Unicode license applies. Contextual conversion and the explicit native dictionary
case policy are EXReader C code; no ICU library is linked. An optional test compares
results against Node's system ICU through Intl. Node/ICU are test tools only.


`tools/check_hyphen_conditional.py` uses EXReader's original generated patterns
and an independent source-span model for conditional compound matching. Optional
external libhyphen comparison uses its caller-supplied substring preprocessor.
Neither the external library nor preprocessor is linked or shipped. Explicit
zero-cut insertion, protected source mapping and bounded full restored stems
are verified against the independent model; external comparison is restricted
to the documented common semantics. No external pattern text is copied.
