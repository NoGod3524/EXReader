#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate deterministic M3 OPC decks using only the Python standard library."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import struct
from zipfile import ZipFile, ZipInfo, ZIP_STORED
import zlib

HERE = Path(__file__).resolve().parent
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
THEME = dict(dk1='102030', lt1='F1F2F3', dk2='203040', lt2='D1D2D3',
             accent1='12A65B', accent2='C23A55', accent3='3579BD', accent4='A05BCA',
             accent5='29ADC5', accent6='E5A336', hlink='2255DD', folHlink='8844AA')


def png(width, height, pixel):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    raw = b''.join(b'\0' + b''.join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw, 0)) + chunk(b'IEND', b''))


def shape(fill, box=(40, 40, 400, 80), number=1):
    x, y, w, h = (round(v * 12700) for v in box)
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="M3 {number}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>{fill}<a:ln><a:noFill/></a:ln>'
            '</p:spPr></p:sp>')


def gradient(stops=((0, 'FF0000'), (100000, '0000FF')), angle=0):
    items = ''.join(f'<a:gs pos="{pos}"><a:srgbClr val="{rgb}"/></a:gs>' for pos, rgb in stops)
    return f'<a:gradFill><a:gsLst>{items}</a:gsLst><a:lin ang="{angle}" scaled="0"/></a:gradFill>'


def package(shapes, media=None):
    theme = ''.join(f'<a:{name}><a:srgbClr val="{rgb}"/></a:{name}>' for name, rgb in THEME.items())
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>',
        '_rels/.rels': f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{R}/officeDocument" Target="ppt/presentation.xml"/></Relationships>',
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="9144000" cy="6858000"/></p:presentation>',
        'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{R}/slide" Target="slides/slide1.xml"/><Relationship Id="rId2" Type="{R}/theme" Target="theme/theme1.xml"/></Relationships>',
        'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="0" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
            f'{shapes}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>',
        'ppt/slides/_rels/slide1.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="img1" Type="{R}/image" Target="../media/image1.png"/></Relationships>',
        'ppt/theme/theme1.xml': f'<a:theme xmlns:a="{A}" name="M3"><a:themeElements><a:clrScheme name="M3">{theme}</a:clrScheme></a:themeElements></a:theme>',
    }
    if media is not None:
        parts['ppt/media/image1.png'] = media
    out = BytesIO()
    with ZipFile(out, 'w') as archive:
        for name, data in sorted(parts.items()):
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type, info.create_system, info.external_attr = ZIP_STORED, 3, 0o600 << 16
            archive.writestr(info, data)
    return out.getvalue()


def generate(check=False):
    stretch = '<a:blipFill><a:blip r:embed="img1"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>'
    tile = '<a:blipFill><a:blip r:embed="img1"/><a:tile/></a:blipFill>'
    schemes = dict(THEME, tx1=THEME['dk1'], bg1=THEME['lt1'], tx2=THEME['dk2'], bg2=THEME['lt2'])
    cases = {
        'image': package(shape(stretch, (40, 40, 120, 80)), png(120, 80, lambda x, y: (0, 255, 0))),
        'stretch': package(shape(stretch, (40, 40, 400, 50)), png(100, 50, lambda x, y: (0, 255, 0))),
        'tile': package(shape(tile, (40, 40, 240, 60)), png(40, 40, lambda x, y: (255, 0, 0) if x < 20 else (0, 0, 255))),
        'gradient': package(shape(gradient())),
        'theme': package(''.join(shape(f'<a:solidFill><a:schemeClr val="{name}"/></a:solidFill>',
                                      (20 + i % 4 * 150, 20 + i // 4 * 100, 120, 70), i + 1)
                                 for i, name in enumerate(schemes))),
        'alpha': package(shape('<a:solidFill><a:srgbClr val="FF0000"><a:alpha val="50000"/></a:srgbClr></a:solidFill>')),
    }
    for name, data in cases.items():
        path = HERE / (name + '.pptx')
        if check:
            assert path.read_bytes() == data, path
        else:
            path.write_bytes(data)
        print(f'{name}: deterministic OPC {len(data)} bytes')
    text = json.dumps(schemes, indent=2) + '\n'
    if check:
        assert (HERE / 'theme.json').read_text() == text
    else:
        (HERE / 'theme.json').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    generate(parser.parse_args().check)

