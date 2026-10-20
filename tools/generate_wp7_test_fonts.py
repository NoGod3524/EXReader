#!/usr/bin/env python3
"""Generate the original WP7 synthetic fonts (rectangles, MIT).

Each font uses only glyphs derived from the fixed WP7 corpus and simple,
script-appropriate OpenType features.  They are deliberately independent of
Noto and are used to prove that reordering and feature staging do not depend
on one vendor's lookups.
"""
# SPDX-License-Identifier: MIT
from pathlib import Path
import sys

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

from wp7_sequences import CASES, INDIC, THAI_C, THAI_M, KHMER_C, KHMER_M, MYANMAR_C, MYANMAR_M

ROOT = Path(__file__).resolve().parents[1] / "tests/fixtures/wp7/fonts"


def name(cp):
    if cp == 0x20:
        return "space"
    if cp == 0x200C:
        return "zwnj"
    if cp == 0x200D:
        return "zwj"
    return "u%04X" % cp


def scalars(tag):
    values = set(ord(ch) for text in CASES[tag] for ch in text)
    values.discard(0x20)
    values.discard(0x2C)
    values.add(0x20)
    values.add(0x200C)
    values.add(0x200D)
    return sorted(values)


def spec(tag):
    if tag in INDIC:
        v = INDIC[tag]
        return dict(base=v["cons"], matra=v["mat"], marks=v["marks"],
                    virama=v["virama"], ra=v["ra"], ya=v["cons"][10], ha=v["cons"][-1],
                    ma=v["cons"][8], ssa=v["cons"][15], ta=v["cons"][6],
                    nukta=(0x09BC if tag == "beng" else (0x0CBC if tag == "knda" else (0x0D3C if tag == "mlym" else 0))),
                    script={"beng": "bng2", "taml": "tml2", "telu": "tel2", "knda": "knd2", "mlym": "mlm2"}[tag],
                    old={"beng": "beng", "taml": "taml", "telu": "telu", "knda": "knda", "mlym": "mlym"}[tag])
    if tag == "thai":
        return dict(base=THAI_C, matra=THAI_M, marks=[0x0E31,0x0E34,0x0E35,0x0E36,0x0E37,0x0E47,0x0E48,0x0E49,0x0E4A,0x0E4B,0x0E4C,0x0E4D],
                    virama=0, ra=0, ya=0, ha=0, ma=0, ssa=0, ta=0, nukta=0, script="thai", old=None)
    if tag == "khmr":
        return dict(base=KHMER_C, matra=KHMER_M, marks=[0x17C6,0x17C7,0x17C8,0x17C9,0x17CA,0x17CB,0x17CC,0x17CE,0x17CF,0x17D0,0x17D1,0x17D3],
                    virama=0x17D2, ra=0x179A, ya=KHMER_C[10], ha=KHMER_C[-1], ma=KHMER_C[8],
                    ssa=KHMER_C[15], ta=KHMER_C[6], nukta=0, script="khmr", old=None)
    if tag == "mymr":
        return dict(base=MYANMAR_C, matra=MYANMAR_M,
                    marks=[0x1036,0x1037,0x1038,0x103B,0x103C,0x103D,0x103E,0x103A,0x1039],
                    virama=0x1039, ra=0x1004, ya=MYANMAR_C[10], ha=MYANMAR_C[-1], ma=MYANMAR_C[8],
                    ssa=MYANMAR_C[15], ta=MYANMAR_C[6], nukta=0, script="mym2", old="mymr")
    raise KeyError(tag)


def make_font(tag):
    sp = spec(tag)
    values = set(scalars(tag))
    values.update(sp["base"])
    values.update(sp["matra"])
    values.update(sp["marks"])
    # Canonical split-matra components that the shaper emits before cmap lookup.
    values.update([0x09C7,0x09BE,0x09D7,0x0BBE,0x0BC6,0x0BC7,0x0BD7,0x0C46,0x0C56,
                   0x0CBF,0x0CC2,0x0CC6,0x0CD5,0x0CD6,0x0D3E,0x0D46,0x0D47,0x0D57])
    for key in ("virama", "ra", "ya", "ha", "ma", "ssa", "ta", "nukta"):
        if sp[key]:
            values.add(sp[key])
    values = sorted(values)
    base = sp["base"]
    extras = []
    for cp in base[:4]:
        extras += [name(cp) + ".half", name(cp) + ".locl"]
    extras += ["rakar", "reph", "reph.final", "preYa", "postHa", "aboveMa", "kssa", "qa", "kta",
               "kinzi", "mr", "mw", "mh", "ml", "baseAA", "coeng.sub"]
    extras = list(dict.fromkeys(extras))
    order = [".notdef"] + [name(cp) for cp in values] + extras
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    glyphs = {}
    widths = {}
    for index, glyph in enumerate(order):
        pen = TTGlyphPen(None)
        if glyph == ".notdef" or glyph == "space":
            width = 250 if glyph == "space" else 600
        elif glyph.endswith(".half") or glyph.endswith(".locl"):
            width = 300
        elif glyph in ("rakar", "reph", "reph.final", "kinzi", "mr", "mw", "mh", "ml"):
            width = 0
        elif glyph in ("kssa", "kta", "baseAA", "coeng.sub"):
            width = 700
        elif glyph in ("preYa", "postHa", "aboveMa", "qa"):
            width = 250
        elif glyph in ("zwj", "zwnj"):
            width = 0
        else:
            cp = int(glyph[1:], 16) if glyph.startswith("u") else 0
            if tag == "thai":
                zero = cp == 0x0E31 or 0x0E34 <= cp <= 0x0E37 or cp == 0x0E47 or cp >= 0x0E4D
            elif tag == "khmr":
                zero = cp >= 0x17C6
            elif tag == "mymr":
                zero = cp >= 0x1036
            else:
                zero = cp in sp["marks"]
            width = 0 if zero or cp == sp["virama"] or cp in (0x200C, 0x200D) else (200 if cp in sp["matra"] else 600)
        widths[glyph] = width
        if glyph not in (".notdef", "space", "zwj", "zwnj"):
            right = max(60, width - 40)
            height = 400 + (index % 7) * 30
            pen.moveTo((20, 0)); pen.lineTo((right, 0)); pen.lineTo((right, height)); pen.lineTo((20, height)); pen.closePath()
        glyphs[glyph] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({g: (widths[g], 0) for g in order})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupCharacterMap({cp: name(cp) for cp in values})
    builder.setupNameTable(dict(familyName="EXR WP7 " + tag, styleName="Regular",
        uniqueFontIdentifier="EXR-WP7-" + tag, fullName="EXR WP7 " + tag,
        psName="EXRWP7" + tag, copyright="Copyright 2026 EXReader contributors; MIT"))
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=1000, usWinDescent=200)
    builder.setupPost()
    def n(cp):
        return name(cp)
    marks = [n(cp) for cp in sp["marks"] if n(cp) in order]
    bases = [n(cp) for cp in base if n(cp) in order]
    v = n(sp["virama"]) if sp["virama"] else None
    lines = []
    lines.append("languagesystem %s dflt;" % sp["script"])
    if sp["old"]:
        lines.append("languagesystem %s dflt;" % sp["old"])
    if marks:
        lines.append("@MARK = [%s];" % " ".join(marks))
    if bases:
        lines.append("@BASE = [%s];" % " ".join(bases))
        lines.append("table GDEF { GlyphClassDef @BASE, , @MARK, ; } GDEF;")
    # Indic and Myanmar basic forms.  Only create rules whose glyphs exist.
    if sp["virama"] and sp["ra"] and "rakar" in order:
        lines.append("feature rphf { sub %s %s by reph; } rphf;" % (n(sp["ra"]), v))
        lines.append("feature blwf { sub %s %s by rakar; } blwf;" % (v, n(sp["ra"])))
        if n(sp["ra"]) + ".half" in order:
            lines.append("feature half { sub %s %s by %s; } half;" % (n(sp["ra"]), v, n(sp["ra"]) + ".half"))
    if sp["virama"] and sp["ya"] and "preYa" in order:
        lines.append("feature pref { sub %s %s by preYa; } pref;" % (v, n(sp["ya"])))
    if sp["virama"] and sp["ha"] and "postHa" in order:
        lines.append("feature pstf { sub %s %s by postHa; } pstf;" % (v, n(sp["ha"])))
    if sp["virama"] and sp["ma"] and "aboveMa" in order:
        lines.append("feature abvf { sub %s %s by aboveMa; } abvf;" % (v, n(sp["ma"])))
    if sp["virama"] and sp["ssa"] and "kssa" in order:
        lines.append("feature akhn { sub %s %s %s by kssa; } akhn;" % (n(base[0]), v, n(sp["ssa"])))
    if sp["nukta"] and "qa" in order:
        lines.append("feature nukt { sub %s %s by qa; } nukt;" % (n(base[0]), n(sp["nukta"])))
    if sp["virama"] and len(base) > 3 and "kta" in order:
        lines.append("feature cjct { sub %s.half %s by kta; } cjct;" % (n(base[0]), n(base[3])))
    if sp["virama"]:
        lines.append("feature half { sub %s %s by %s.half; } half;" % (n(base[0]), v, n(base[0])))
    for cp in base[:3]:
        g = n(cp)
        if g + ".half" in order and sp["virama"]:
            lines.append("feature half { sub %s %s by %s.half; } half;" % (g, v, g))
        if g + ".locl" in order:
            lines.append("feature locl { sub %s by %s.locl; } locl;" % (g, g))
    if sp["matra"]:
        m = n(sp["matra"][1])
        if m + ".init" in order:
            lines.append("feature init { sub %s by %s.init; } init;" % (m, m))
    if "reph" in order:
        lines.append("feature abvs { sub reph by reph.final; } abvs;")
    if tag == "khmr":
        lines.append("feature pref { sub %s %s by rakar; } pref;" % (v, n(sp["ra"])))
        for cp in base[:3]:
            lines.append("feature blwf { sub %s %s by %s.half; } blwf;" % (v, n(cp), n(cp)))
        lines.append("feature pstf { sub %s %s by postHa; } pstf;" % (v, n(sp["ha"])))
        lines.append("feature clig { sub %s %s by baseAA; } clig;" % (n(base[0]), n(sp["matra"][0])))
    if tag == "mymr":
        lines.append("feature rphf { sub %s %s %s by kinzi; } rphf;" % (n(sp["ra"]), n(0x103A), v))
        lines.append("feature blwf { sub %s %s by coeng.sub; } blwf;" % (v, n(base[0])))
        lines.append("feature pstf { sub %s %s by coeng.sub; } pstf;" % (v, n(base[1])))
    if marks and bases:
        lines.append("markClass [%s] <anchor 0 0> @TOP;" % " ".join(marks))
        lines.append("markClass [%s] <anchor 0 0> @BOTTOM;" % " ".join(marks))
        lines.append("feature abvm { pos base [%s] <anchor 300 700> mark @TOP; } abvm;" % " ".join(bases[:8]))
        lines.append("feature blwm { pos base [%s] <anchor 250 -100> mark @BOTTOM; } blwm;" % " ".join(bases[:8]))
        lines.append("feature mark { pos base [%s] <anchor 300 700> mark @TOP; } mark;" % " ".join(bases[:8]))
        lines.append("feature mkmk { pos mark [%s] <anchor 100 200> mark @TOP; } mkmk;" % " ".join(marks))
    addOpenTypeFeaturesFromString(builder.font, "\n".join(lines))
    builder.font["head"].created = builder.font["head"].modified = 3800000000
    builder.font.recalcTimestamp = False
    ROOT.mkdir(parents=True, exist_ok=True)
    target = ROOT / (tag + "-synthetic.ttf")
    builder.font.save(target)
    print("generated", target, target.stat().st_size)


if __name__ == "__main__":
    tags = sys.argv[1:] or list(CASES)
    for tag in tags:
        make_font(tag)
