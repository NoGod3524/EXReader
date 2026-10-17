#!/usr/bin/env python3
"""Original COLR v0/CPAL rectangles; fontTools is a developer-only dependency."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import hashlib
from fontTools.fontBuilder import FontBuilder
from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/fonts'
ORDER = ['.notdef', 'space', 'color', 'red', 'blue', 'foreground', 'plain',
         'tooMany', 'huge', 'hugeColor', 'exact256']


def rectangle(bounds):
    pen = TTGlyphPen(None)
    if bounds:
        x0, y0, x1, y1 = bounds
        pen.moveTo((x0, y0))
        pen.lineTo((x1, y0))
        pen.lineTo((x1, y1))
        pen.lineTo((x0, y1))
        pen.closePath()
    return pen.glyph()


def main():
    font = FontBuilder(1000, isTTF=True)
    font.setupGlyphOrder(ORDER)
    font.setupCharacterMap({32: 'space', 65: 'color', 66: 'plain', 67: 'exact256',
                            68: 'tooMany', 69: 'hugeColor', 0x1f600: 'color'})
    bounds = {name: (0, 0, 800, 800) for name in ORDER}
    bounds.update(space=None, red=(0, 0, 600, 600), blue=(200, 200, 800, 800),
                  foreground=(300, 300, 500, 500), huge=(0, 0, 32000, 32000))
    font.setupGlyf({name: rectangle(bounds[name]) for name in ORDER})
    font.setupHorizontalMetrics({name: (900, bounds[name][0] if bounds[name] else 0) for name in ORDER})
    font.setupHorizontalHeader(ascent=900, descent=-100)
    font.setupVerticalMetrics({name: (1000, 100) for name in ORDER})
    font.setupVerticalHeader(ascent=500, descent=-500)
    font.setupOS2(sTypoAscender=900, sTypoDescender=-100, yStrikeoutPosition=300,
                  yStrikeoutSize=50, usWinAscent=32000, usWinDescent=100)
    font.setupNameTable({'familyName': 'EXReader Original Color', 'styleName': 'Regular',
                        'uniqueFontIdentifier': 'EXReader-Color-v1',
                        'fullName': 'EXReader Original Color Regular',
                        'psName': 'EXReaderOriginalColor-Regular', 'version': 'Version 1.0'})
    font.setupPost(underlinePosition=-100, underlineThickness=50)
    font.setupMaxp()
    font.font['COLR'] = buildCOLR({
        'color': [('red', 0), ('blue', 1), ('foreground', 0xffff)],
        'tooMany': [('red', 0)] * 257,
        'hugeColor': [('huge', 0)],
        'exact256': [('red', 2)] * 255 + [('foreground', 0xffff)],
    }, version=0, glyphMap=font.font.getReverseGlyphMap())
    font.font['CPAL'] = buildCPAL([
        [(1, 0, 0, 1), (0, 0, 1, .5), (1, 1, 1, 0)],
        [(1, 1, 0, 1), (0, 1, 1, .25), (1, 1, 1, 0)],
    ])
    font.font['head'].created = font.font['head'].modified = 2082844800
    font.font.recalcTimestamp = False
    path = ROOT / 'color.ttf'
    font.font.save(path)
    print(path.name, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
