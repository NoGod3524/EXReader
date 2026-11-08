#!/usr/bin/env python3
"""Create tests/fixtures/fonts/latin-hyphen.ttf: original 500-unit rectangles for
ASCII letters, space, apostrophe, hyphen-minus and U+2010 (built-in hyphenation tests).

Developer-only: requires fontTools. Normal builds use the committed fixture.
"""
# SPDX-License-Identifier: MIT
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

if __name__ == '__main__':
    codes = [32, 39, 45, 0x2010] + list(range(65, 91)) + list(range(97, 123))
    names = ['.notdef'] + ['uni%04X' % c for c in codes]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name not in ('uni0020',):
            pen.moveTo((50, -100)); pen.lineTo((450, -100)); pen.lineTo((450, 700)); pen.lineTo((50, 700))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({n: (500, 0) for n in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap({c: 'uni%04X' % c for c in codes})
    name = 'EXR Test Latin Hyphen'
    builder.setupNameTable({'familyName': name, 'styleName': 'Regular', 'uniqueFontIdentifier': name,
                            'fullName': name, 'psName': name.replace(' ', ''),
                            'copyright': 'Copyright 2026 EXReader contributors; MIT'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost(); builder.setupMaxp()
    builder.font['head'].created = builder.font['head'].modified = 3800000000
    builder.font.recalcTimestamp = False
    builder.font.save(Path(__file__).resolve().parents[1] / 'tests/fixtures/fonts/latin-hyphen.ttf')
