#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate byte-reproducible PPTX M4 text fixtures (stdlib, ZIP_STORED)."""
import argparse
from html import escape
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

HERE = Path(__file__).resolve().parent
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
SLIDE = 'ppt/slides/slide1.xml'


def run(text='Hello', attributes='', properties=''):
    return f'<a:r><a:rPr {attributes}>{properties}</a:rPr><a:t>{escape(text)}</a:t></a:r>'


def paragraph(runs=None, attributes='', properties=''):
    return f'<a:p><a:pPr {attributes}>{properties}</a:pPr>{run() if runs is None else runs}</a:p>'


def shape(paragraphs=None, box=(40, 40, 400, 240), body='wrap="square" anchor="t" lIns="127000" tIns="127000" rIns="127000" bIns="127000"',
          autofit='', lst='', placeholder='', number=1):
    x, y, width, height = (round(value * 12700) for value in box)
    ph = f'<p:ph type="{placeholder}"/>' if placeholder else ''
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="M4 {number}"/><p:cNvSpPr txBox="1"/>'
            f'<p:nvPr>{ph}</p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
            f'<a:ext cx="{width}" cy="{height}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
            '</a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>'
            f'<p:txBody><a:bodyPr {body}>{autofit}</a:bodyPr><a:lstStyle>{lst}</a:lstStyle>'
            f'{paragraph() if paragraphs is None else paragraphs}</p:txBody></p:sp>')


def package(shapes=None, default='', master='', master_path='ppt/slideMasters/slideMaster1.xml'):
    shapes = shape() if shapes is None else shapes
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>',
        '_rels/.rels': f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{R}/officeDocument" Target="ppt/presentation.xml"/></Relationships>',
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}">'
            '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="9144000" cy="6858000"/>'
            f'<p:defaultTextStyle>{default}</p:defaultTextStyle></p:presentation>',
        'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{R}/slide" Target="slides/slide1.xml"/></Relationships>',
        SLIDE: f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="0" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
            f'{shapes}</p:spTree></p:cSld></p:sld>',
        'ppt/theme/theme1.xml': f'<a:theme xmlns:a="{A}" name="M4"><a:themeElements><a:clrScheme name="M4">'
            '<a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
            '</a:clrScheme></a:themeElements></a:theme>',
    }
    if master:
        parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace('</Types>',
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            f'<Override PartName="/{master_path}" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/></Types>')
        parts['ppt/presentation.xml'] = parts['ppt/presentation.xml'].replace('<p:sldIdLst>',
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="master"/></p:sldMasterIdLst><p:sldIdLst>')
        parts['ppt/_rels/presentation.xml.rels'] = parts['ppt/_rels/presentation.xml.rels'].replace('</Relationships>',
            f'<Relationship Id="master" Type="{R}/slideMaster" Target="/{master_path}"/></Relationships>')
        parts['ppt/slides/_rels/slide1.xml.rels'] = (f'<Relationships xmlns="{REL}"><Relationship Id="layout" '
            f'Type="{R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>')
        parts['ppt/slideLayouts/slideLayout1.xml'] = f'<p:sldLayout xmlns:p="{P}"><p:cSld><p:spTree/></p:cSld></p:sldLayout>'
        parts['ppt/slideLayouts/_rels/slideLayout1.xml.rels'] = (f'<Relationships xmlns="{REL}"><Relationship Id="master" '
            f'Type="{R}/slideMaster" Target="/{master_path}"/></Relationships>')
        parts[master_path] = (f'<p:sldMaster xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree/></p:cSld>'
            f'<p:txStyles>{master}</p:txStyles></p:sldMaster>')
    return archive(parts)


def archive(parts):
    output = BytesIO()
    with ZipFile(output, 'w') as target:
        for name, data in sorted(parts.items()):
            entry = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            entry.compress_type, entry.create_system, entry.external_attr = ZIP_STORED, 3, 0o600 << 16
            target.writestr(entry, data.encode('utf-8') if isinstance(data, str) else data)
    return output.getvalue()


def cases():
    explicit = lambda size, **kwargs: package(shape(paragraph(run('Hello', f'sz="{size * 100}"')), **kwargs))
    result = {
        'hello': package(shape(paragraph(run('Hello', 'sz="1800"'), 'algn="ctr"'))),
        **{f'size{size}': explicit(size) for size in (12, 24, 48)},
        'master28': package(shape(placeholder='body'), master='<p:bodyStyle><a:lvl1pPr><a:defRPr sz="2800"/></a:lvl1pPr></p:bodyStyle>'),
        'regular': package(shape(paragraph(run('IIIIIIII', 'sz="4800" b="0"')))),
        'bold': package(shape(paragraph(run('IIIIIIII', 'sz="4800" b="1"')))),
        'cjk': package(shape(paragraph(run('中文测试', 'sz="2800"', '<a:latin typeface="Segoe UI"/><a:ea typeface="SimHei"/>')))),
        'cjk-fallback': package(shape(paragraph(run('中文测试', 'sz="2800"', '<a:latin typeface="Segoe UI"/><a:ea typeface="Segoe UI"/>')))),
        'missing-glyph': package(shape(paragraph(run('\u0378', 'sz="2800"', '<a:latin typeface="Segoe UI"/>')))),
        'missing-font': package(shape(paragraph(run('Hello', 'sz="1800"', '<a:latin typeface="M4 Missing Font"/>')))),
        'wrap': package(shape(paragraph(run('word ' * 40, 'sz="1800"')), box=(40, 40, 200, 440))),
        'numbered': package(shape(''.join(paragraph(run('Item', 'sz="2400"'), 'marL="381000" indent="-381000"',
                                                  '<a:buAutoNum type="arabicPeriod"/>') for _ in range(3)))),
        'autofit': explicit(48, autofit='<a:normAutofit fontScale="62500" lnSpcReduction="0"/>'),
        'breaks': package(shape(paragraph(run('First', 'sz="1800"') + '<a:br/>' + run('Second', 'sz="1800"')))),
    }
    bad = result['size24']
    with ZipFile(BytesIO(bad)) as source:
        parts = {name: source.read(name) for name in source.namelist()}
    # Invalid UTF-8 is inside one a:t; a sibling run must survive intact.
    parts[SLIDE] = parts[SLIDE].replace(b'<a:t>Hello</a:t>', b'<a:t>bad\xfftext</a:t></a:r><a:r><a:rPr sz="2400"/><a:t>Good</a:t>')
    result['invalid-utf8'] = archive(parts)
    return result


def generate(check=False):
    for name, data in cases().items():
        path = HERE / f'{name}.pptx'
        if check:
            assert path.read_bytes() == data, path
        else:
            path.write_bytes(data)
        print(f'{name}: deterministic OPC ZIP_STORED {len(data)} bytes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    generate(parser.parse_args().check)
