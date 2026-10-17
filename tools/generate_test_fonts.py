#!/usr/bin/env python3
"""Create tiny original rectangle fonts for deterministic fallback tests.

Developer-only: requires fontTools. Normal builds use the committed fixtures.
No system fonts or third-party font outlines are copied.
"""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0


def font(name, cmap, width, ascent, descent, kern):
    names = ['.notdef', 'space', 'A', 'V', 'a', 'acute', 'beta']
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    glyphs = {}
    for glyph in names:
        pen = TTGlyphPen(None)
        if glyph != 'space':
            if glyph == 'acute':
                pen.moveTo((0, 750))
                pen.lineTo((150, 900))
                pen.lineTo((250, 900))
                pen.lineTo((100, 750))
            else:
                pen.moveTo((50, -descent // 2))
                pen.lineTo((width - 50, -descent // 2))
                pen.lineTo((width - 50, ascent - 100))
                pen.lineTo((50, ascent - 100))
            pen.closePath()
        glyphs[glyph] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({g: (0 if g == 'acute' else width, 0) for g in names})
    builder.setupHorizontalHeader(ascent=ascent, descent=-descent)
    builder.setupCharacterMap(cmap)
    builder.setupNameTable({'familyName': name, 'styleName': 'Regular',
                            'uniqueFontIdentifier': name, 'fullName': name,
                            'psName': name.replace(' ', ''),
                            'copyright': 'Copyright 2026 EXReader contributors; GPL-3.0-only'})
    builder.setupOS2(sTypoAscender=ascent, sTypoDescender=-descent,
                    usWinAscent=ascent, usWinDescent=descent)
    builder.setupPost()
    builder.setupMaxp()
    if kern:
        table = newTable('kern')
        table.version = 0
        subtable = KernTable_format_0()
        subtable.version, subtable.coverage = 0, 1
        subtable.kernTable = {('A', 'V'): kern}
        table.kernTables = [subtable]
        builder.font['kern'] = table
    builder.font['head'].created = builder.font['head'].modified = 3800000000
    builder.font.recalcTimestamp = False
    return builder.font


if __name__ == '__main__':
    directory = Path(__file__).resolve().parents[1] / 'tests/fixtures/fonts'
    directory.mkdir(parents=True, exist_ok=True)
    primary = font('EXR Test Primary', {32: 'space', 65: 'A', 86: 'V', 97: 'a'},
                   500, 800, 200, -100)
    fallback = font('EXR Test Fallback',
                    {32: 'space', 65: 'A', 86: 'V', 97: 'a', 0x301: 'acute',
                     0x7532: 'V', 0x4e59: 'beta', 0x1f600: 'beta'},
                    900, 1200, 400, -300)
    marks = font('EXR Test Marks', {0x301: 'acute', 0x3b2: 'beta'}, 700, 1000, 300, 0)
    oversize = font('EXR Test Oversize', {65: 'A'}, 32000, 32000, 0, 0)
    for filename, data in [('primary.ttf', primary), ('fallback.ttf', fallback), ('marks.ttf', marks), ('oversize.ttf', oversize)]:
        data.save(directory / filename)
    collection = TTCollection()
    collection.fonts = [primary, fallback]
    collection.save(directory / 'collection.ttc')
    print('Generated four original test fonts and a two-face collection.')
