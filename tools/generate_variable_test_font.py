#!/usr/bin/env python3
"""Original two-axis outlines, advances, GPOS deltas and rvrn conditions.

Developer-only fontTools; no external font outlines. Normal builds use the fixture.
"""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from tempfile import TemporaryDirectory
from fontTools.designspaceLib import DesignSpaceDocument, AxisDescriptor, SourceDescriptor, InstanceDescriptor
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.varLib import build
from fontTools.varLib.featureVars import addFeatureVariations


def master(weight, width):
    names = ['.notdef', 'space', 'A', 'V', 'A.alt', 'acute']
    advance = round(500 * width / 100 + (weight - 400) / 10)
    height = round(700 + (weight - 400) / 10)
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name != 'space':
            if name == 'acute':
                points = [(0, 0), (60, 80), (100, 80), (40, 0)]
            else:
                top = height - (150 if name == 'A.alt' else 0)
                points = [(20, 0), (advance - 30, 0), (advance - 30, top), (20, top)]
            pen.moveTo(points[0])
            for point in points[1:]:
                pen.lineTo(point)
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (0 if name == 'acute' else advance, 0) for name in names})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupVerticalMetrics({name: (1000 + (weight - 400) // 10, 100) for name in names})
    builder.setupVerticalHeader(ascent=500, descent=-500)
    builder.setupCharacterMap({32: 'space', 65: 'A', 86: 'V', 0x301: 'acute'})
    builder.setupNameTable(dict(familyName='EXR Variable Test', styleName='Regular',
                               uniqueFontIdentifier='EXR-Variable-Test', fullName='EXR Variable Test',
                               psName='EXRVariableTest', copyright='Copyright 2026 EXReader contributors; GPL-3.0-only'))
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=1000, usWinDescent=200)
    builder.setupPost()
    kern = round(-50 - (weight - 400) / 10 - (width - 100) / 10)
    anchor = round(advance / 2)
    addOpenTypeFeaturesFromString(builder.font, f'''
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        markClass acute <anchor 0 0> @TOP;
        feature kern {{ pos A V {kern}; pos A.alt V {kern}; }} kern;
        feature mark {{ pos base A <anchor {anchor} {height}> mark @TOP;
                        pos base A.alt <anchor {anchor} {height - 150}> mark @TOP; }} mark;
    ''')
    builder.font['head'].created = builder.font['head'].modified = 3800000000
    builder.font.recalcTimestamp = False
    return builder.font


def generate():
    with TemporaryDirectory(prefix='exreader-variable-') as temp:
        root = Path(temp)
        document = DesignSpaceDocument()
        for tag, name, minimum, default, maximum in [('wght', 'Weight', 100, 400, 900),
                                                      ('wdth', 'Width', 50, 100, 150)]:
            axis = AxisDescriptor()
            axis.tag, axis.name = tag, name
            axis.minimum, axis.default, axis.maximum = minimum, default, maximum
            if tag == 'wght':
                axis.map = [(100, 100), (400, 400), (650, 700), (900, 900)]
            else:
                axis.hidden = True
            document.addAxis(axis)
        for weight in (100, 400, 900):
            for width in (50, 100, 150):
                source = SourceDescriptor()
                source.path = str(root / f'{weight}-{width}.ttf')
                source.name = f'{weight}-{width}'
                source.location = {'Weight': weight, 'Width': width}
                source.familyName, source.styleName = 'EXR Variable Test', 'Regular'
                if weight == 400 and width == 100:
                    source.copyInfo = source.copyLib = source.copyFeatures = True
                master(weight, width).save(source.path)
                document.addSource(source)
        instance = InstanceDescriptor()
        instance.name, instance.familyName, instance.styleName = 'Heavy', 'EXR Variable Test', 'Heavy'
        instance.location = {'Weight': 900, 'Width': 100}
        document.addInstance(instance)
        font, _, _ = build(document)
        addFeatureVariations(font, [([{'wght': (.6, 1.0)}], {'A': 'A.alt'})], featureTag='rvrn')
        font['head'].created = font['head'].modified = 3800000000
        font.recalcTimestamp = False
        target = Path(__file__).resolve().parents[1] / 'tests/fixtures/fonts/variable.ttf'
        font.save(target)
        print(f'Generated original two-axis font ({target.stat().st_size} bytes).')


if __name__ == '__main__':
    generate()
