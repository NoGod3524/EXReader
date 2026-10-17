#!/usr/bin/env python3
"""Original PNG/JPEG sbix strikes based on EXReader's own rectangle font."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from io import BytesIO
import hashlib
from PIL import Image
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.sbixGlyph import Glyph
from fontTools.ttLib.tables.sbixStrike import Strike

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/fonts'


def png(size, colors):
    image = Image.new('RGBA', (size, size))
    image.putdata([colors[x >= size//2] for y in range(size) for x in range(size)])
    result = BytesIO()
    image.save(result, format='PNG')
    return result.getvalue()


def main():
    font = TTFont(ROOT/'color.ttf', recalcTimestamp=False)
    del font['COLR'], font['CPAL']
    font['sbix'] = newTable('sbix')
    font['sbix'].version = font['sbix'].flags = 1
    font['sbix'].strikes = {}
    for ppem, size, colors in [
        (10, 8, [(255, 0, 0, 255), (255, 255, 0, 128)]),
        (20, 16, [(0, 255, 0, 255), (0, 0, 255, 128)]),
    ]:
        strike = Strike(ppem=ppem, resolution=72)
        strike.glyphs = {name: Glyph(glyphName=name) for name in font.getGlyphOrder()}
        for name in ['color', 'foreground', 'red' if ppem==10 else 'blue']:
            strike.glyphs[name] = Glyph(glyphName=name, graphicType='png ',
                                       originOffsetX=ppem//10, originOffsetY=-ppem//5,
                                       imageData=png(size, colors))
        for name, target in [('tooMany', 'color'), ('exact256', 'tooMany'), ('hugeColor', 'hugeColor')]:
            strike.glyphs[name] = Glyph(glyphName=name, graphicType='dupe',
                                       referenceGlyphName=target, originOffsetX=99, originOffsetY=99)
        jpeg = BytesIO()
        Image.new('RGB',(size,size),(128,64,192)).save(jpeg,format='JPEG',quality=95)
        strike.glyphs['.notdef'] = Glyph(glyphName='.notdef', graphicType='jpg ',imageData=jpeg.getvalue())
        font['sbix'].strikes[ppem] = strike
    path = ROOT/'bitmap.ttf'
    font.save(path)
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
