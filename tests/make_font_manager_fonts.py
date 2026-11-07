#!/usr/bin/env python3
"""Create the tiny original fonts used by the font manager test.

Developer-only: requires fontTools. Normal builds use the committed fixtures.
Every glyph is an original rectangle; no system or third-party outlines.
"""
# SPDX-License-Identifier: MIT
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection


def font(family, style, weight, cmap, localized=None):
    names = ['.notdef', 'space', 'box']
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    glyphs = {}
    for glyph in names:
        pen = TTGlyphPen(None)
        if glyph != 'space':
            pen.moveTo((60, -80))
            pen.lineTo((940, -80))
            pen.lineTo((940, 760))
            pen.lineTo((60, 760))
            pen.closePath()
        glyphs[glyph] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({g: (1000, 0) for g in names})
    builder.setupHorizontalHeader(ascent=880, descent=-120)
    builder.setupCharacterMap({cp: 'space' if cp == 32 else 'box' for cp in cmap})
    full = family + ' ' + style
    table = {'familyName': family, 'styleName': style, 'uniqueFontIdentifier': full,
             'fullName': full, 'psName': full.replace(' ', ''),
             'copyright': 'Copyright 2026 EXReader contributors; MIT'}
    builder.setupNameTable(table)
    if localized:  # Windows platform, Unicode BMP, zh-CN (0x0804).
        builder.font['name'].setName(localized, 1, 3, 1, 0x804)
    bold = style.startswith('Bold')
    italic = 'Italic' in style
    builder.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120,
                     usWeightClass=weight,
                     fsSelection=(0x20 if bold else 0) | (1 if italic else 0) |
                     (0x40 if not bold and not italic else 0))
    builder.font['head'].macStyle = (1 if bold else 0) | (2 if italic else 0)
    builder.setupPost()
    builder.setupMaxp()
    builder.font['head'].created = builder.font['head'].modified = 3800000000
    builder.font.recalcTimestamp = False
    return builder.font


if __name__ == '__main__':
    out = Path(__file__).resolve().parent / 'fixtures/font_manager'
    out.mkdir(parents=True, exist_ok=True)
    latin = [32] + list(range(0x21, 0x7f))
    font('EXR FM Latin Serif', 'Regular', 400, latin).save(out / 'latin-serif.ttf')
    # Serif: 一 中 文 紅 夢 、 。 ; lacks 樓 (U+6A13) on purpose.
    font('EXR FM CJK Serif', 'Regular', 400,
         [32, 0x4e00, 0x4e2d, 0x6587, 0x7d05, 0x5922, 0x3001, 0x3002],
         localized='测试宋体').save(out / 'cjk-serif.ttf')
    font('EXR FM CJK Sans', 'Regular', 400,
         [32, 0x4e00, 0x4e2d, 0x6587, 0x7d05, 0x5922, 0x6a13]).save(out / 'cjk-sans.ttf')
    # Bold-only extra coverage: 龍 (U+9F8D), for the same-family-other-style step.
    font('EXR FM CJK Serif', 'Bold', 700, [32, 0x4e00, 0x4e2d, 0x9f8d]).save(out / 'cjk-serif-bold.ttf')
    font('EXR FM CJK Serif', 'Italic', 400, [32, 0x4e2d, 0x03b1]).save(out / 'cjk-serif-italic.ttf')
    collection = TTCollection()
    collection.fonts = [font('EXR FM Latin Serif', 'Regular', 400, latin),
                        font('EXR FM CJK Serif', 'Regular', 400, [32, 0x4e2d])]
    collection.save(out / 'collection.ttc')
