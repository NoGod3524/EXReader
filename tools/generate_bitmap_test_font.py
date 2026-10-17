#!/usr/bin/env python3
"""Original PNG/JPEG sbix strikes based on EXReader's own rectangle font."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from io import BytesIO
import hashlib
import zipfile
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
    files = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'OPS/book.opf': b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:exreader:original-color-fonts</dc:identifier><dc:title>Original Color Fonts</dc:title><dc:language>en</dc:language></metadata><manifest><item id="text" href="text.xhtml" media-type="application/xhtml+xml"/><item id="css" href="style.css" media-type="text/css"/><item id="bitmap" href="fonts/bitmap.ttf" media-type="font/ttf"/><item id="vector" href="fonts/color.ttf" media-type="font/ttf"/></manifest><spine><itemref idref="text"/></spine></package>',
        'OPS/text.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml"><head><link rel="stylesheet" href="style.css"/></head><body><p class="bitmap">&#x1f600;</p><p class="vector">&#x1f600;</p></body></html>',
        'OPS/style.css': b'@font-face{font-family:EXRBitmap;src:url(fonts/bitmap.ttf)}@font-face{font-family:EXRVector;src:url(fonts/color.ttf)}p{margin:0;font-size:100px;line-height:1}.bitmap{font-family:EXRBitmap}.vector{font-family:EXRVector}',
        'OPS/fonts/bitmap.ttf': path.read_bytes(),
        'OPS/fonts/color.ttf': (ROOT/'color.ttf').read_bytes(),
    }
    book = ROOT.parent/'color-fonts.epub'
    with zipfile.ZipFile(book,'w') as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_STORED if name=='mimetype' else zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    print(book.name,book.stat().st_size,hashlib.sha256(book.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
