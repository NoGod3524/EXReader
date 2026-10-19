#!/usr/bin/env python3
"""Original PDF glyph-selection/outline fixtures; fontTools is development-only."""
# SPDX-License-Identifier: MIT
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.cffLib import FDArrayIndex, FontDict, FDSelect

ROOT = Path(__file__).resolve().parents[1]/'tests/fixtures/fonts'


def build(cff=False, cid=False):
    names = ['.notdef', 'A', 'fi', 'Q', 'space']
    if cid:
        names = ['.notdef', 'cid00001', 'cid00042', 'cid00077', 'cid00099']
    units = 1000 if cff else 2000
    builder = FontBuilder(units, isTTF=not cff)
    builder.setupGlyphOrder(names)
    outlines = {}
    for index, name in enumerate(names):
        pen = T2CharStringPen(units//2, None) if cff else TTGlyphPen(None)
        factor = units/1000
        def p(x, y):
            return int(x*factor), int(y*factor)
        if index == 1:
            pen.moveTo(p(0, 0)); pen.lineTo(p(400, 0)); pen.lineTo(p(400, 600)); pen.lineTo(p(0, 600)); pen.closePath()
        elif index == 2:
            pen.moveTo(p(500, 0)); pen.lineTo(p(900, 0)); pen.lineTo(p(500, 600)); pen.closePath()
        elif index == 3:
            pen.moveTo(p(0, 0))
            if cff:
                pen.curveTo(p(0, 800), p(800, 800), p(800, 0))
            else:
                pen.qCurveTo(p(400, 1000), p(800, 0))
            pen.closePath()
        outlines[name] = pen.getCharString() if cff else pen.glyph()
    builder.setupHorizontalMetrics({n: (units//2, units//2 if i==2 else 0) for i,n in enumerate(names)})
    builder.setupHorizontalHeader(ascent=units, descent=0)
    builder.setupCharacterMap({32:names[4], 65:names[1], 81:names[3], 0xfb01:names[2]})
    builder.setupNameTable({'familyName':'EXR PDF Test', 'styleName':'Regular',
        'uniqueFontIdentifier':'EXRPDFTest', 'fullName':'EXR PDF Test', 'psName':'EXRPDFTest',
        'copyright':'Copyright 2026 EXReader contributors; MIT'})
    builder.setupOS2(sTypoAscender=units, sTypoDescender=0, usWinAscent=units, usWinDescent=0)
    builder.setupPost()
    if cff:
        builder.setupCFF('EXRPDFTest', {}, outlines, {})
        if cid:
            top = builder.font['CFF '].cff.topDictIndex[0]
            top.ROS = ('Adobe', 'Identity', 0)
            top.CIDCount = 100
            fd = FontDict(); fd.Private = top.Private
            top.FDArray = FDArrayIndex(); top.FDArray.append(fd)
            top.FDSelect = FDSelect(); top.FDSelect.gidArray = [0]*len(names)
            del top.Private
    else:
        builder.setupGlyf(outlines); builder.setupMaxp()
    builder.font['head'].created = builder.font['head'].modified = 3800000000
    builder.font.recalcTimestamp = False
    return builder.font


if __name__ == '__main__':
    font = build()
    font.save(ROOT/'pdf-names.ttf')
    font['post'].formatType = 3.0
    font.save(ROOT/'pdf-unicode.ttf')
    symbol = CmapSubtable.newSubtable(4)
    symbol.platformID, symbol.platEncID, symbol.language = 3, 0, 0
    symbol.cmap = {0xf041:'fi'}
    font['cmap'].tables = [symbol]
    font.save(ROOT/'pdf-symbol.ttf')
    build(cff=True).save(ROOT/'pdf-cubic.otf')
    build(cff=True, cid=True).save(ROOT/'pdf-cid.otf')
    print('Generated five original PDF outline fonts')
