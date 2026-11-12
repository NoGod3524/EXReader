#!/usr/bin/env python3
"""Original rectangles for text-combine-upright tests: 600-unit digits (ink 50..550 x 0..700),
a 300-unit period, an em-wide ideograph with native vertical metrics.

Developer-only fontTools; normal builds use the committed font.
"""
# SPDX-License-Identifier: MIT
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def font(punctuation=False):
    digits = ["d%d" % i for i in range(10)]
    names = [".notdef", "space", "period", "cjk", "stop"] + digits
    if punctuation:
        names.append('opening.vert')
    b = FontBuilder(1000, isTTF=True)
    b.setupGlyphOrder(names)
    boxes = {"period": (80, 0, 220, 140), "cjk": (40, -100, 960, 800), "stop": (100, 0, 400, 300),
             'opening.vert': (100, 0, 400, 300)}
    glyphs, advance = {}, {}
    for name in names:
        p = TTGlyphPen(None)
        if name != "space":
            x0, y0, x1, y1 = boxes.get(name, (50, 0, 550, 700))
            p.moveTo((x0, y0)); p.lineTo((x0, y1)); p.lineTo((x1, y1)); p.lineTo((x1, y0)); p.closePath()
        glyphs[name] = p.glyph()
        advance[name] = 300 if name == "period" else 1000 if name in ("cjk", "stop", ".notdef", 'opening.vert') else 600
    b.setupGlyf(glyphs)
    b.setupHorizontalMetrics({n: (advance[n], 0) for n in names})
    b.setupHorizontalHeader(ascent=800, descent=-200)
    b.setupVerticalMetrics({n: (1000, 600 if n == 'opening.vert' else 100) for n in names})
    b.setupVerticalHeader(ascent=800, descent=-200)
    cmap = {32: "space", 46: "period", 0x7532: "cjk", 0x3002: "stop"}
    cmap.update({48 + i: digits[i] for i in range(10)})
    if punctuation:
        # Original tall rectangles deliberately make half-em vertical advances
        # overlap. Compact stops retain a safe trailing half-em of blank space.
        cmap.update({0xff01: 'd1', 0xff1f: 'd2', 0x2026: 'period', 0x300c: 'period'})
    b.setupCharacterMap(cmap)
    family = "EXR Vertical Punctuation" if punctuation else "EXR Combine"
    b.setupNameTable({"familyName": family, "styleName": "Regular", "uniqueFontIdentifier": family,
                      "fullName": family, "psName": family.replace(' ', ''),
                      "copyright": "Copyright 2026 EXReader contributors; MIT"})
    b.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=900, usWinDescent=200)
    b.setupPost()
    b.setupMaxp()
    if punctuation:
        from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
        addOpenTypeFeaturesFromString(b.font,
            'languagesystem DFLT dflt; feature vert { sub period by opening.vert; } vert;')
    b.font["head"].created = b.font["head"].modified = 3800000000
    b.font.recalcTimestamp = False
    return b.font


if __name__ == "__main__":
    directory = Path(__file__).resolve().parents[1] / "tests/fixtures/fonts"
    font().save(directory / "combine.ttf")
    font(punctuation=True).save(directory / "vertical-punctuation.ttf")
    print("Generated the original text-combine-upright test font.")
