#!/usr/bin/env python3
"""Original rectangles and triangles for vertical metrics/orientation tests.

Developer-only fontTools; normal builds use the committed fonts.
"""
# SPDX-License-Identifier: MIT
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString


def font(kind):
    names = [".notdef", "space", "latin", "acute", "cjk", "angle", "comma", "dash",
             "angle.vert", "comma.vert", "angle.vrt2", "comma.vrt2"]
    b = FontBuilder(1000, isTTF=True)
    b.setupGlyphOrder(names)
    glyphs = {}
    for i, name in enumerate(names):
        p = TTGlyphPen(None)
        if name != "space":
            if name == "acute":
                points = [(0, 700), (200, 850), (240, 850), (40, 700)]
            elif name == "latin":
                points = [(50, -100), (450, -100), (300, 600)]
            elif name.startswith("angle."):
                points = [(40, 100), (100 + i * 25, 100), (100 + i * 25, 250), (40, 250)]
            else:
                points = [(40, -100), (440, -100), (440, 700), (40, 700)]
            p.moveTo(points[0])
            for point in points[1:]: p.lineTo(point)
            p.closePath()
        glyphs[name] = p.glyph()
    b.setupGlyf(glyphs)
    b.setupHorizontalMetrics({name: (0 if name == "acute" else 600, 0) for name in names})
    b.setupHorizontalHeader(ascent=800, descent=-200)
    b.setupVerticalMetrics({name: (1000, 100) for name in names})
    b.setupVerticalHeader(ascent=800, descent=-200)
    b.setupCharacterMap({32: "space", 65: "latin", 0x301: "acute", 0x7532: "cjk",
                         0x3008: "angle", 0x3001: "comma", 0x2010: "dash", 45: "dash"})
    family = "EXR Vertical " + kind
    b.setupNameTable({"familyName": family, "styleName": "Regular", "uniqueFontIdentifier": family,
                      "fullName": family, "psName": family.replace(" ", ""),
                      "copyright": "Copyright 2026 EXReader contributors; MIT"})
    b.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=900, usWinDescent=200)
    b.setupPost()
    b.setupMaxp()
    if kind != "plain":
        features = "languagesystem DFLT dflt; languagesystem hani dflt;\n"
        features += "feature vert { sub angle by angle.vert; sub comma by comma.vert; } vert;\n"
        if kind == "vrt2":
            features += "feature vrt2 { sub angle by angle.vrt2; sub comma by comma.vrt2; } vrt2;\n"
        features += "feature vkrn { pos cjk cjk <0 0 0 100>; } vkrn;\n"
        addOpenTypeFeaturesFromString(b.font, features)
    b.font["head"].created = b.font["head"].modified = 3800000000
    b.font.recalcTimestamp = False
    return b.font


if __name__ == "__main__":
    directory = Path(__file__).resolve().parents[1] / "tests/fixtures/fonts"
    for kind in ("plain", "vert", "vrt2"):
        font(kind).save(directory / f"vertical-{kind}.ttf")
    print("Generated three original vertical test fonts.")
