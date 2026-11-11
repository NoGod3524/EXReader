#!/usr/bin/env python3
"""Generate six original, deterministic OOXML fixtures using only the stdlib."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZipInfo, ZIP_STORED
import zlib

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
PIC = 'http://schemas.openxmlformats.org/drawingml/2006/picture'
FIXTURES = ('plain', 'heading', 'table', 'image', 'notes', 'sections')
FONT = '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/></w:rPr>'


def paragraph(text, properties='', extra=''):
    section_end = properties if properties.startswith('<w:sectPr>') else ''
    leading = '' if section_end else properties
    return (f'<w:p><w:pPr>{leading}<w:spacing w:line="480" w:lineRule="auto"/>{section_end}'
            f'</w:pPr><w:r>{FONT}<w:t>{escape(text)}</w:t></w:r>{extra}</w:p>')


def section(second=False, header=False):
    margins = (1080, 2160, 1800, 720) if second else (1440,) * 4
    reference = '<w:headerReference w:type="default" r:id="header"/>' if header else ''
    return (f'<w:sectPr>{reference}<w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar ' + ' '.join(f'w:{k}="{v}"' for k, v in zip(
                ('top', 'right', 'bottom', 'left'), margins)) +
            ' w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = b''.join(b'\0' + b''.join(bytes((24, 96, 160) if (x + y) % 2 else
                     (64, 192, 192)) for x in range(8)) for y in range(8))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 8, 8, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


def fixture(kind):
    parts = {}
    relationships = [('styles', 'styles', 'styles.xml')]
    overrides = [('document', 'document.main'), ('styles', 'styles')]
    extras = ['', '', '']
    properties = ['', '', '']
    if kind == 'heading':
        properties[0] = '<w:pStyle w:val="Heading1"/>'
    if kind == 'image':
        extras[1] = ('<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            '<wp:extent cx="76200" cy="76200"/><wp:docPr id="1" name="Original checker"/>'
            f'<a:graphic><a:graphicData uri="{PIC}"><pic:pic><pic:nvPicPr>'
            '<pic:cNvPr id="0" name="checker.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="image"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="76200" cy="76200"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
        relationships.append(('image', 'image', 'media/checker.png'))
        parts['word/media/checker.png'] = png()
    if kind == 'notes':
        extras[0] = '<w:r><w:footnoteReference w:id="1"/></w:r>'
        extras[2] = '<w:r><w:endnoteReference w:id="2"/></w:r>'
        for plural, singular, number in [('footnotes', 'footnote', 1), ('endnotes', 'endnote', 2)]:
            relationships.append((plural, plural, plural + '.xml'))
            overrides.append((plural, plural))
            parts['word/' + plural + '.xml'] = (
                f'<w:{plural} xmlns:w="{W}"><w:{singular} w:type="separator" w:id="-1">'
                f'<w:p><w:r><w:separator/></w:r></w:p></w:{singular}>'
                f'<w:{singular} w:id="{number}">' + paragraph('Original ' + singular + ' text.') +
                f'</w:{singular}></w:{plural}>')
    if kind == 'sections':
        properties[1] = section(header=True)
        relationships.append(('header', 'header', 'header1.xml'))
        overrides.append(('header1', 'header'))
        parts['word/header1.xml'] = (f'<w:hdr xmlns:w="{W}">' +
            paragraph('Original page ', extra='<w:fldSimple w:instr=" PAGE "><w:r>' + FONT +
                      '<w:t>1</w:t></w:r></w:fldSimple>') + '</w:hdr>')
    body = ''.join(paragraph(f'Original {kind} paragraph {i + 1}: alpha 中文 beta.', properties[i],
                             extras[i]) for i in range(3))
    if kind == 'table':
        body += '<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/></w:tblPr><w:tblGrid>'
        body += '<w:gridCol w:w="3000"/>' * 3 + '</w:tblGrid>'
        for row in range(3):
            body += '<w:tr>' + ''.join('<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/>'
                '</w:tcPr>' + paragraph(f'Original cell {row + 1},{col + 1}.') + '</w:tc>'
                for col in range(3)) + '</w:tr>'
        body += '</w:tbl>'
    body += section(second=kind == 'sections', header=kind == 'sections')
    parts['word/document.xml'] = (f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}" '
        f'xmlns:wp="{WP}" xmlns:pic="{PIC}"><w:body>{body}</w:body></w:document>')
    parts['word/styles.xml'] = (f'<w:styles xmlns:w="{W}"><w:docDefaults>'
        f'<w:rPrDefault>{FONT}</w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:line="480" '
        'w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
        '</w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:outlineLvl w:val="0"/></w:pPr>'
        '<w:rPr><w:b/></w:rPr></w:style></w:styles>')
    parts['_rels/.rels'] = (f'<Relationships xmlns="{REL}"><Relationship Id="main" '
        f'Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>')
    parts['word/_rels/document.xml.rels'] = (f'<Relationships xmlns="{REL}">' + ''.join(
        f'<Relationship Id="{ident}" Type="{R}/{relation}" Target="{target}"/>'
        for ident, relation, target in relationships) + '</Relationships>')
    parts['[Content_Types].xml'] = (f'<Types xmlns="{CT}"><Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>' + ''.join(
        f'<Override PartName="/word/{name}.xml" '
        f'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{mime}+xml"/>'
        for name, mime in overrides) + '</Types>')
    output = io.BytesIO()
    with ZipFile(output, 'w') as archive:
        for name, data in sorted(parts.items()):
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data.encode('utf-8') if isinstance(data, str) else data)
    return output.getvalue()


def generate():
    files, records = {}, []
    for kind in FIXTURES:
        data = fixture(kind)
        if len(data) >= 50_000:
            raise ValueError(f'{kind}: fixture size {len(data)} >= 50000')
        files[kind + '.docx'] = data
        records.append(dict(id=kind, path=kind + '.docx', bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), paragraphs=12 if kind == 'table' else 3,
            body_paragraphs=3, tables=int(kind == 'table'), images=int(kind == 'image'),
            footnotes=int(kind == 'notes'), endnotes=int(kind == 'notes'),
            sections=2 if kind == 'sections' else 1, headers=int(kind == 'sections')))
    files['manifest.json'] = (json.dumps(dict(license='MIT', origin='Original synthetic content; no external inputs.',
        fixtures=records), indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--check', action='store_true', help='Fail on missing/drifting committed bytes.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in generate().items():
        path = args.output / name
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                raise SystemExit(f'{name}: generated bytes differ; run {Path(__file__).name}')
        else:
            path.write_bytes(data)
        print(f'{name}: {len(data)} bytes' + (' reproducible' if args.check else ''))


if __name__ == '__main__':
    main()
