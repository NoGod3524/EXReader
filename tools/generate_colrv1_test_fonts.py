#!/usr/bin/env python3
"""Original COLR v1 paint-matrix font; fontTools is a developer-only dependency."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import hashlib
from fontTools.fontBuilder import FontBuilder
from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib.builder import buildVarStore, buildVarData, buildVarRegionList


def build_variable_font():
    """PaintVarSolid alpha 0.25 plus a +0.5 delta at wght=900."""
    order = ['.notdef', 'space', 'box', 'var_solid', 'static', 'var_translate']
    font = FontBuilder(1000, isTTF=True)
    font.setupGlyphOrder(order)
    font.setupCharacterMap({65: 'var_solid', 66: 'static'})
    font.setupGlyf({'.notdef': glyph((0, 0, 10, 10)), 'space': glyph(None),
                    'box': glyph((0, 0, 800, 800)), 'var_solid': glyph(None), 'static': glyph(None),
                    'var_translate': glyph(None)})
    font.setupHorizontalMetrics({n: (900, 0) for n in order})
    font.setupHorizontalHeader(ascent=900, descent=-100)
    font.setupOS2(sTypoAscender=900, sTypoDescender=-100, usWinAscent=1000, usWinDescent=200)
    font.setupNameTable({'familyName': 'EXReader COLRv1 Variable', 'styleName': 'Regular',
                         'uniqueFontIdentifier': 'EXReader-COLRv1-Variable',
                         'fullName': 'EXReader COLRv1 Variable Regular',
                         'psName': 'EXReaderCOLRv1Variable-Regular', 'version': 'Version 1.0'})
    font.setupPost(underlinePosition=-100, underlineThickness=50)
    font.setupMaxp()
    font.setupFvar([('wght', 100, 400, 900, 'Weight')],
                   [{'location': {'wght': 400}, 'stylename': 'Regular'}])
    regions = buildVarRegionList([{'wght': (0, 1, 1)}], ['wght'])
    store = buildVarStore(regions, [buildVarData([0], [[8192], [200], [0]])])
    var_paint = {'Format': ot.PaintFormat.PaintVarSolid, 'PaletteIndex': 0,
                 'Alpha': 0.25, 'VarIndexBase': 0}
    var_translate = {'Format': ot.PaintFormat.PaintVarTranslate,
                     'Paint': paint_glyph('box', solid(0)),
                     'dx': 0, 'dy': 0, 'VarIndexBase': 1}
    font.font['COLR'] = buildCOLR({
        'var_solid': paint_glyph('box', var_paint),
        'static': paint_glyph('box', solid(0, .25)),
        'var_translate': var_translate,
    }, version=1, glyphMap=font.font.getReverseGlyphMap(), varStore=store)
    font.font['CPAL'] = buildCPAL([PALETTE])
    font.font['head'].created = font.font['head'].modified = 2082844800
    font.font.recalcTimestamp = False
    path = ROOT / 'colrv1-var.ttf'
    font.font.save(path)
    print(path.name, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/fonts'

PALETTE = [
    (1, 0, 0, 1),      # 0 opaque red
    (0, 0, 1, 1),      # 1 opaque blue
    (0, 1, 0, .5),     # 2 half green
    (1, 1, 0, 1),      # 3 opaque yellow
    (0, 0, 0, 0),      # 4 transparent
]
STOPS_RB = [{'StopOffset': 0.0, 'PaletteIndex': 0, 'Alpha': 1.0},
            {'StopOffset': 0.5, 'PaletteIndex': 3, 'Alpha': 1.0},
            {'StopOffset': 1.0, 'PaletteIndex': 1, 'Alpha': 1.0}]
STOPS_ALPHA = [{'StopOffset': 0.0, 'PaletteIndex': 0, 'Alpha': 1.0},
               {'StopOffset': 1.0, 'PaletteIndex': 0, 'Alpha': .25}]


def glyph(bounds, curves=False):
    pen = TTGlyphPen(None)
    if bounds is None:
        return pen.glyph()
    x0, y0, x1, y1 = bounds
    if curves:
        # Circle-ish shape through four quadratic segments.
        cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
        pen.moveTo((cx + r, cy))
        pen.qCurveTo((cx + r, cy + r), (cx, cy + r))
        pen.qCurveTo((cx - r, cy + r), (cx - r, cy))
        pen.qCurveTo((cx - r, cy - r), (cx, cy - r))
        pen.qCurveTo((cx + r, cy - r), (cx + r, cy))
        pen.closePath()
        return pen.glyph()
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return pen.glyph()


def solid(index=0, alpha=1.0):
    return {'Format': ot.PaintFormat.PaintSolid, 'PaletteIndex': index, 'Alpha': alpha}


def paint_glyph(name, paint):
    return {'Format': ot.PaintFormat.PaintGlyph, 'Glyph': name, 'Paint': paint}


def linear(name, x0, y0, x1, y1, x2=None, y2=None, stops=None, extend='pad'):
    if x2 is None:
        # A perpendicular p2 gives the same colour axis as a projection while
        # avoiding the degenerate p2 == p0 basis that Skia 152 treats as a
        # solid first-stop fill.
        x2, y2 = x0 - (y1 - y0), y0 + (x1 - x0)
    return paint_glyph(name, {
        'Format': ot.PaintFormat.PaintLinearGradient,
        'ColorLine': {'Extend': extend, 'ColorStop': stops or STOPS_RB},
        'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})


def radial(name, c0, r0, c1, r1, stops=None, extend='pad'):
    return paint_glyph(name, {
        'Format': ot.PaintFormat.PaintRadialGradient,
        'ColorLine': {'Extend': extend, 'ColorStop': stops or STOPS_RB},
        'x0': c0[0], 'y0': c0[1], 'r0': r0,
        'x1': c1[0], 'y1': c1[1], 'r1': r1})


def sweep(name, center, start, end, stops=None, extend='pad'):
    return paint_glyph(name, {
        'Format': ot.PaintFormat.PaintSweepGradient,
        'ColorLine': {'Extend': extend, 'ColorStop': stops or STOPS_RB},
        'centerX': center[0], 'centerY': center[1],
        'startAngle': start, 'endAngle': end})


def wrap(fmt, child, **fields):
    paint = {'Format': fmt, 'Paint': child}
    paint.update(fields)
    return paint


SCENES = [
    # name, base paint, clip box
    ('solid', paint_glyph('box', solid(0)), None),
    ('solid_fg', paint_glyph('box', solid(0xFFFF)), None),
    ('solid_half', paint_glyph('box', solid(2)), None),
    ('layers', {'Format': ot.PaintFormat.PaintColrLayers, 'Layers': [
        paint_glyph('left', solid(0)), paint_glyph('right', solid(1))]}, None),
    ('layers_overlap', {'Format': ot.PaintFormat.PaintColrLayers, 'Layers': [
        paint_glyph('box', solid(0)), paint_glyph('inner', solid(1, .5))]}, None),
    ('linear', linear('box', 0, 0, 800, 0), None),
    ('linear_p2', linear('box', 0, 0, 800, 0, 0, 800), None),
    ('linear_shear', linear('box', 0, 0, 800, 0, 800, 800), None),
    ('linear_alpha', linear('box', 0, 0, 800, 0, stops=STOPS_ALPHA), None),
    ('linear_repeat', linear('box', 0, 0, 400, 0, stops=[
        {'StopOffset': 0.0, 'PaletteIndex': 0, 'Alpha': 1.0},
        {'StopOffset': 1.0, 'PaletteIndex': 1, 'Alpha': 1.0}], extend='repeat'), None),
    ('radial', radial('box', (400, 400), 0, (400, 400), 400), None),
    ('radial_offset', radial('box', (300, 400), 100, (500, 400), 300), None),
    ('sweep', sweep('box', (400, 400), 0, 360), None),
    ('translate', wrap(ot.PaintFormat.PaintTranslate, paint_glyph('box', solid(0)), dx=400, dy=0), None),
    ('scale', wrap(ot.PaintFormat.PaintScale, paint_glyph('box', solid(0)), scaleX=.5, scaleY=.5), None),
    ('scale_center', wrap(ot.PaintFormat.PaintScaleAroundCenter, paint_glyph('box', solid(0)),
                          scaleX=.5, scaleY=.5, centerX=400, centerY=400), None),
    ('scale_uniform', wrap(ot.PaintFormat.PaintScaleUniform, paint_glyph('box', solid(0)), scale=.5), None),
    ('rotate', wrap(ot.PaintFormat.PaintRotate, paint_glyph('left', solid(0)), angle=90), None),
    ('rotate_center', wrap(ot.PaintFormat.PaintRotateAroundCenter, paint_glyph('left', solid(0)),
                           angle=90, centerX=400, centerY=400), None),
    ('rotate_half', wrap(ot.PaintFormat.PaintRotateAroundCenter, paint_glyph('left', solid(0)),
                         angle=180, centerX=400, centerY=400), None),
    ('skew', wrap(ot.PaintFormat.PaintSkew, paint_glyph('box', solid(0)), xSkewAngle=45, ySkewAngle=0), None),
    ('skew_y', wrap(ot.PaintFormat.PaintSkew, paint_glyph('box', solid(0)), xSkewAngle=0, ySkewAngle=45), None),
    ('transform', wrap(ot.PaintFormat.PaintTransform, paint_glyph('box', solid(0)),
                       Transform={'xx': .5, 'yx': 0, 'xy': 0, 'yy': .5, 'dx': 100, 'dy': 100}), None),
    ('colr_glyph', {'Format': ot.PaintFormat.PaintColrGlyph, 'Glyph': 'solid'}, None),
    ('composite_normal', {'Format': ot.PaintFormat.PaintComposite,
                          'SourcePaint': paint_glyph('inner', solid(1)),
                          'CompositeMode': ot.CompositeMode.SRC_OVER,
                          'BackdropPaint': paint_glyph('box', solid(0))}, None),
    ('composite_multiply', {'Format': ot.PaintFormat.PaintComposite,
                            'SourcePaint': paint_glyph('inner', solid(3)),
                            'CompositeMode': ot.CompositeMode.MULTIPLY,
                            'BackdropPaint': paint_glyph('box', solid(1))}, None),
    ('composite_screen', {'Format': ot.PaintFormat.PaintComposite,
                          'SourcePaint': paint_glyph('inner', solid(1)),
                          'CompositeMode': ot.CompositeMode.SCREEN,
                          'BackdropPaint': paint_glyph('box', solid(0))}, None),
    ('composite_difference', {'Format': ot.PaintFormat.PaintComposite,
                              'SourcePaint': paint_glyph('inner', solid(3)),
                              'CompositeMode': ot.CompositeMode.DIFFERENCE,
                              'BackdropPaint': paint_glyph('box', solid(0))}, None),
    ('composite_luminosity', {'Format': ot.PaintFormat.PaintComposite,
                              'SourcePaint': paint_glyph('inner', solid(1)),
                              'CompositeMode': ot.CompositeMode.HSL_LUMINOSITY,
                              'BackdropPaint': paint_glyph('box', solid(0))}, None),
    ('composite_src', {'Format': ot.PaintFormat.PaintComposite,
                       'SourcePaint': paint_glyph('inner', solid(1)),
                       'CompositeMode': ot.CompositeMode.SRC,
                       'BackdropPaint': paint_glyph('box', solid(0))}, None),
    ('composite_clear', {'Format': ot.PaintFormat.PaintComposite,
                         'SourcePaint': paint_glyph('inner', solid(1)),
                         'CompositeMode': ot.CompositeMode.CLEAR,
                         'BackdropPaint': paint_glyph('box', solid(0))}, None),
    ('clipbox', paint_glyph('box', solid(0)), (100, 100, 700, 700)),
    ('clipbox_gradient', linear('box', 0, 0, 800, 0), (100, 100, 700, 700)),
    ('layer_gradient', {'Format': ot.PaintFormat.PaintColrLayers, 'Layers': [
        paint_glyph('left', solid(0)), radial('right', (600, 400), 0, (600, 400), 400)]}, None),
    ('cycle', {'Format': ot.PaintFormat.PaintColrGlyph, 'Glyph': 'cycle'}, None),
    ('palette_oob', paint_glyph('box', solid(9)), None),
    ('deep', None, None),
    ('many', None, None),
    ('outline_only', None, None),
    # Negative fixtures appended so existing glyph IDs stay stable.
    ('many_stops', None, None),
    ('missing_colr_glyph', {'Format': ot.PaintFormat.PaintColrGlyph, 'Glyph': 'box'}, None),
    ('bad_clipbox', paint_glyph('box', solid(0)), (700, 700, 100, 100)),
]

OUTLINE_GLYPHS = ['.notdef', 'space', 'box', 'inner', 'left', 'right', 'circle']
BASE_GLYPHS = [name for name, _, _ in SCENES]
ORDER = OUTLINE_GLYPHS + BASE_GLYPHS


def build_deep():
    paint = paint_glyph('box', solid(0))
    for _ in range(70):
        paint = wrap(ot.PaintFormat.PaintTranslate, paint, dx=0, dy=0)
    return paint


def build_many():
    layers = [paint_glyph('box', solid(0)) for _ in range(4200)]
    return {'Format': ot.PaintFormat.PaintColrLayers, 'Layers': layers}


def main():
    colors = {}
    boxes = {}
    for name, paint, clip in SCENES:
        if name == 'deep':
            paint = build_deep()
        elif name == 'many':
            paint = build_many()
        elif name == 'many_stops':
            stops = [{'StopOffset': i/256.0, 'PaletteIndex': i % 3, 'Alpha': 1.0}
                     for i in range(257)]
            paint = linear('box', 0, 0, 800, 0, stops=stops)
        elif name == 'outline_only':
            continue
        colors[name] = paint
        if clip:
            boxes[name] = clip

    font = FontBuilder(1000, isTTF=True)
    font.setupGlyphOrder(ORDER)
    cmap = {32: 'space'}
    for i, name in enumerate(BASE_GLYPHS):
        if name not in ('cycle', 'palette_oob', 'deep', 'many'):
            cmap[0x41 + i] = name
    font.setupCharacterMap(cmap)
    shapes = {name: glyph(None) for name in ORDER}
    shapes['box'] = glyph((0, 0, 800, 800))
    shapes['inner'] = glyph((200, 200, 600, 600))
    shapes['left'] = glyph((0, 0, 400, 800))
    shapes['right'] = glyph((400, 0, 800, 800))
    shapes['circle'] = glyph((0, 0, 800, 800), curves=True)
    font.setupGlyf(shapes)
    bounds = {name: (0, 0, 800, 800) for name in ORDER}
    bounds.update(space=None, inner=(200, 200, 600, 600), left=(0, 0, 400, 800),
                  right=(400, 0, 800, 800))
    font.setupHorizontalMetrics({name: (900, bounds[name][0] if bounds[name] else 0) for name in ORDER})
    font.setupHorizontalHeader(ascent=900, descent=-100)
    font.setupVerticalMetrics({name: (1000, 500) for name in ORDER})
    font.setupVerticalHeader(ascent=500, descent=-500)
    font.setupOS2(sTypoAscender=900, sTypoDescender=-100, usWinAscent=1000, usWinDescent=200)
    font.setupNameTable({'familyName': 'EXReader COLRv1 Matrix', 'styleName': 'Regular',
                         'uniqueFontIdentifier': 'EXReader-COLRv1-Matrix',
                         'fullName': 'EXReader COLRv1 Matrix Regular',
                         'psName': 'EXReaderCOLRv1Matrix-Regular', 'version': 'Version 1.0'})
    font.setupPost(underlinePosition=-100, underlineThickness=50)
    font.setupMaxp()
    font.font['COLR'] = buildCOLR(colors, version=1, glyphMap=font.font.getReverseGlyphMap(),
                                  clipBoxes=boxes)
    font.font['CPAL'] = buildCPAL([PALETTE])
    font.font['head'].created = font.font['head'].modified = 2082844800
    font.font.recalcTimestamp = False
    path = ROOT / 'colrv1.ttf'
    font.font.save(path)
    print(path.name, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
    build_variable_font()