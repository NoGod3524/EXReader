#!/usr/bin/env python3
"""X6 public-ABI acceptance, checked independently with ZIP/XML and #117 metrics."""
import argparse
import ctypes as c
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
import xml.etree.ElementTree as ET
import zlib

from test_docx_edit_io import Bridge, Block, Run, RP, ID, Error, package, repack, unzip, audit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/docx'))
from roundtrip import METRICS
from verify_docx import W, R, NS, REL

WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
NS.update(wp=WP, a=A)
MAX = c.c_size_t(-1).value

class Cell(c.Structure):
    _fields_ = [('id', ID), ('blocks', c.POINTER(Block)), ('count', c.c_size_t),
                ('unsupported', c.c_uint), ('xml', c.c_void_p), ('xml_size', c.c_size_t),
                ('changed', c.c_uint)]
class Row(c.Structure):
    _fields_ = [('id', ID), ('cells', c.POINTER(Cell)), ('count', c.c_size_t),
                ('xml', c.c_void_p), ('xml_size', c.c_size_t), ('source_index', c.c_size_t)]
class Table(c.Structure):
    _fields_ = [('rows', c.POINTER(Row)), ('count', c.c_size_t), ('columns', c.c_size_t),
                ('width', c.c_int32), ('borders', c.c_int), ('changed', c.c_uint),
                ('widths', c.POINTER(c.c_int32))]

class API(Bridge):
    def __init__(self, library):
        super().__init__(library)
        ptr, size = c.c_void_p, c.c_size_t
        for name, args in [
            ('table_insert_row', [ptr, ID, size]), ('table_delete_row', [ptr, ID, size]),
            ('table_set_cell_text', [ptr, ID, size, size, c.POINTER(Run), size]),
            ('table_set_width', [ptr, ID, c.c_int32]), ('table_set_borders', [ptr, ID, c.c_int]),
            ('delete_table', [ptr, ID]), ('delete_image', [ptr, ID]),
            ('insert_image', [ptr, ID, ptr, size, c.c_double, c.c_double, c.POINTER(ID)]),
            ('rollback', [ptr])]:
            f = getattr(self.dll, 'exr_edit_' + name)
            f.restype, f.argtypes = c.c_int, args
            setattr(self, name, f)
    def write(self, doc):
        data, size, error = c.c_void_p(), c.c_size_t(), Error()
        assert self.docx_write(doc, c.byref(data), c.byref(size), c.byref(error)) == 0, error.message
        try:
            result = c.string_at(data, size.value)
            for name, value in unzip(result).items():
                if name.endswith(('.xml', '.rels')):
                    ET.fromstring(value)
            return result
        finally:
            self.free(data)
    def blocks(self, doc, kind=None):
        return [self.block_at(doc, i).contents for i in range(self.block_count(doc))
                if kind is None or self.block_at(doc, i).contents.kind == kind]
    def table(self, doc):
        b = self.blocks(doc, 1)[0]
        assert b.table
        return b.id, c.cast(b.table, c.POINTER(Table)).contents
    def text(self, doc, tid, row, col, text):
        storage = c.create_string_buffer(text.encode())
        run = Run(text=c.cast(storage, c.c_void_p), length=len(text.encode()),
                  props=RP(present=3, font=b'Times New Roman', size=24))
        assert self.table_set_cell_text(doc, tid, row, col, c.byref(run), 1) == 0
    def image(self, doc, after, data, width, height):
        id = ID()
        assert self.insert_image(doc, after, data, len(data), width, height, c.byref(id)) == 0
        assert id.value
        return id.value

def png(width=1, height=1):
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + b'\x12\x34\x56' * width) * height)) + chunk(b'IEND', b''))

def paragraph(text='', extra=''):
    return ('<w:p><w:pPr><w:spacing w:line="480" w:lineRule="auto"/></w:pPr>'
            '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
            '<w:sz w:val="24"/></w:rPr><w:t>' + text + '</w:t></w:r>' + extra + '</w:p>')

def cell(text='', pr='', extra=''):
    return '<w:tc>' + ('<w:tcPr>' + pr + '</w:tcPr>' if pr else '') + paragraph(text) + extra + '</w:tc>'

def row(index):
    return '<w:tr>' + cell('A' + str(index)) + cell('B' + str(index)) + '</w:tr>'

DRAWING = '<w:r><w:drawing><a:blip r:embed="image1"/></w:drawing></w:r>'
SECT = ('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>')
GRID = '<w:tblGrid><w:gridCol w:w="2400"/><w:gridCol w:w="2400"/></w:tblGrid>'
MERGED = '<w:tr>' + cell('merged', '<w:gridSpan w:val="2"/>') + '</w:tr>'
NESTED = '<w:tbl><w:tr>' + cell('inner') + '</w:tr></w:tbl>'
SHADED = cell('shaded', '<w:shd w:fill="AABBCC"/>', NESTED + paragraph('tail'))

def fixture(kind='table'):
    first, extra, boundary = row(0), '', ''
    if kind == 'images':
        extra = paragraph('image neighbour', DRAWING)
    elif kind == 'notes':
        extra = paragraph('notes', '<w:r><w:footnoteReference w:id="1"/><w:endnoteReference w:id="2"/></w:r>')
    elif kind == 'sections':
        boundary = paragraph('section break').replace('</w:pPr>', SECT + '</w:pPr>')
        extra = paragraph('second section', DRAWING)
    elif kind == 'merged':
        first = MERGED
    elif kind == 'nested':
        first = '<w:tr>' + SHADED + cell('plain') + '</w:tr>'
    table = '<w:tbl x:keep="table"><w:tblPr><w:tblW w:w="4800" w:type="dxa"/></w:tblPr>' + GRID + first + row(1) + row(2) + '</w:tbl>'
    return package(body=paragraph('before') + table + boundary + extra + paragraph('after') + SECT)

def xml(data):
    return ET.fromstring(unzip(data)['word/document.xml'])

def media(data):
    return {n: v for n, v in unzip(data).items() if n.startswith('word/media/') and not n.endswith('/')}

def image_rels(data):
    raw = unzip(data).get('word/_rels/document.xml.rels')
    return [] if raw is None else [r for r in ET.fromstring(raw) if r.get('Type', '').endswith('/image')]

def dimensions(data):
    return [(int(e.get('cx')) / 12700, int(e.get('cy')) / 12700) for e in xml(data).findall('.//wp:extent', NS)]

def same_parts(a, b, changed=('word/document.xml',)):
    a, b = unzip(a), unzip(b)
    assert set(a) == set(b)
    assert all(a[n] == b[n] for n in a if n not in changed)

def shape(data):
    return [[len(r.findall('w:tc', NS)) for r in t.findall('w:tr', NS)]
            for t in xml(data).findall('.//w:tbl', NS)]

def cell_text(table, row_index, col):
    cell = table.rows[row_index].cells[col]
    return ''.join(c.string_at(cell.blocks[i].runs[j].text, cell.blocks[i].runs[j].length).decode()
                   for i in range(cell.count) for j in range(cell.blocks[i].count)
                   if cell.blocks[i].runs[j].kind == 0)

def run_group(group, api, output=None):
    report = {'group': group, 'status': 'PASS'}
    if group == 'table-roundtrip':
        report['fixtures'] = []
        for kind in ('table', 'images', 'notes', 'sections', 'merged', 'nested'):
            source = fixture(kind)
            doc = api.read(source)
            try:
                tid, t = api.table(doc)
                initial = t.count
                assert initial == 3 and t.columns == 2
                ids = [t.rows[i].id for i in range(t.count)]
                assert api.table_insert_row(doc, tid, initial - 1) == 0
                inserted = api.write(doc)
                reopened = api.read(inserted)
                try:
                    _, t = api.table(reopened)
                    assert t.count == initial + 1 and t.columns == 2
                    assert [t.rows[i].count for i in range(t.count)] == ([1, 2, 2, 2] if kind == 'merged' else [2] * 4)
                finally:
                    api.doc_free(reopened)
                assert api.table_delete_row(doc, tid, initial) == 0
                api.text(doc, tid, 1, 0, 'Z1')
                saved = api.write(doc)
                reopened = api.read(saved)
                try:
                    _, t = api.table(reopened)
                    assert t.count == initial and t.columns == 2 and cell_text(t, 1, 0) == 'Z1'
                    same_parts(saved, api.write(reopened))
                finally:
                    api.doc_free(reopened)
                _, t = api.table(doc)
                assert [t.rows[i].id for i in range(t.count)] == ids
                same_parts(source, saved)
                assert shape(source) == shape(saved)
                before, after = audit(source), audit(saved)
                assert all(before[k] == after[k] for k in METRICS)
                assert before['image_sha256'] == after['image_sha256']
                report['fixtures'].append(dict(id=kind, before=before, after=after,
                    row_counts=[initial, initial + 1, initial], columns=2, shape=shape(saved)))
                if output:
                    (output / (kind + '-source.docx')).write_bytes(source)
                    (output / (kind + '-edited.docx')).write_bytes(saved)
            finally:
                api.doc_free(doc)
    elif group == 'table-properties':
        # Both missing and existing tblPr/tblGrid; unmodelled properties/attributes survive.
        for bare in (False, True):
            parts = unzip(fixture())
            if bare:
                parts['word/document.xml'] = parts['word/document.xml'].replace(GRID.encode(), b'').replace(
                    b'<w:tblPr><w:tblW w:w="4800" w:type="dxa"/></w:tblPr>', b'')
            else:
                parts['word/document.xml'] = parts['word/document.xml'].replace(b'</w:tblPr>', b'<w:tblLayout w:type="fixed"/></w:tblPr>')
            doc = api.read(repack(parts))
            try:
                tid, _ = api.table(doc)
                assert api.table_set_width(doc, tid, 7200) == 0
                for value, name in ((0, 'nil'), (1, 'single'), (2, 'double')):
                    assert api.table_set_borders(doc, tid, value) == 0
                    saved = api.write(doc)
                    t = xml(saved).find('.//w:tbl', NS)
                    assert t.find('w:tblPr/w:tblW', NS).get('{%s}w' % W) == '7200'
                    assert len(t.find('w:tblGrid', NS)) == 2
                    assert [e.get('{%s}val' % W) for e in t.find('w:tblPr/w:tblBorders', NS)] == [name] * 6
                    assert list(t)[0].tag == '{%s}tblPr' % W and list(t)[1].tag == '{%s}tblGrid' % W
                    if not bare:
                        assert b'<w:tblLayout w:type="fixed"/>' in unzip(saved)['word/document.xml']
                        names = [n.tag.rsplit('}', 1)[-1] for n in t.find('w:tblPr', NS)]
                        assert names.index('tblW') < names.index('tblBorders') < names.index('tblLayout')
                    reopened = api.read(saved)
                    try:
                        _, t = api.table(reopened)
                        assert t.width == 7200 and t.borders == value
                    finally:
                        api.doc_free(reopened)
            finally:
                api.doc_free(doc)
        # Repeated identical rows and range markers must retain their source positions.
        marker = '<w:bookmarkStart w:id="9" w:name="between"/><!--row boundary-->'
        source = package(body='<w:tbl>' + GRID + row(0) + marker + row(0) + '<w:bookmarkEnd w:id="9"/>' + row(2) + '</w:tbl>' + SECT)
        doc = api.read(source)
        try:
            tid, _ = api.table(doc)
            assert unzip(api.write(doc))['word/document.xml'] == unzip(source)['word/document.xml']
            api.text(doc, tid, 2, 0, 'Z2')
            raw = unzip(api.write(doc))['word/document.xml']
            assert (row(0) + marker + row(0) + '<w:bookmarkEnd w:id="9"/>').encode() in raw
            assert api.table_delete_row(doc, tid, 0) == 0
            raw = unzip(api.write(doc))['word/document.xml']
            assert (marker + row(0) + '<w:bookmarkEnd w:id="9"/>').encode() in raw
        finally:
            api.doc_free(doc)
    elif group == 'table-preserve':
        report['protected_xml'] = []
        # Includes same-row neighbouring-cell edits, and a vertical merge chain.
        vertical = '<w:tr>' + cell('start', '<w:vMerge w:val="restart"/>') + cell('side0') + '</w:tr>'
        continuation = '<w:tr>' + cell('', '<w:vMerge/>') + cell('side1') + '</w:tr>'
        horizontal = '<w:tr>' + cell('h', '<w:hMerge w:val="restart"/>') + cell('', '<w:hMerge/>') + '</w:tr>'
        multipara = '<w:tr><w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>' + paragraph('P1') + paragraph('P2') + '</w:tc>' + cell('side') + '</w:tr>'
        for protected in (MERGED, '<w:tr>' + SHADED + cell('side') + '</w:tr>', vertical + continuation, horizontal, multipara):
            source = package(body='<w:tbl>' + GRID + protected + row(1) + row(2) + '</w:tbl>' + SECT)
            doc = api.read(source)
            try:
                tid, t = api.table(doc)
                target = t.count - 1
                api.text(doc, tid, target, 0, 'Z2')
                assert api.table_insert_row(doc, tid, target) == 0
                with_inserted = api.write(doc)
                assert all(p.find('w:pPr', NS) is not None for p in xml(with_inserted).findall('.//w:tc/w:p', NS))
                assert api.table_delete_row(doc, tid, target + 1) == 0
                saved = api.write(doc)
                assert protected.encode() in unzip(saved)['word/document.xml']
                assert api.table_set_cell_text(doc, tid, 0, 0, None, 0) != 0
                assert unzip(api.write(doc)) == unzip(saved)
                if protected == vertical + continuation:
                    assert api.table_insert_row(doc, tid, 0) != 0
                    assert api.table_delete_row(doc, tid, 0) != 0
                    assert api.table_delete_row(doc, tid, 1) != 0
                    api.text(doc, tid, 1, 1, 'changed side')
                    assert cell('', '<w:vMerge/>').encode() in unzip(api.write(doc))['word/document.xml']
                report['protected_xml'].append(protected)
                reopened = api.read(saved)
                api.doc_free(reopened)
            finally:
                api.doc_free(doc)
        style_cell = '<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Styled</w:t></w:r></w:p></w:tc>'
        styled_tbl = package(body='<w:tbl>' + GRID + '<w:tr>' + style_cell + style_cell + '</w:tr></w:tbl>' + SECT)
        doc = api.read(styled_tbl)
        try:
            tid, _ = api.table(doc)
            assert api.table_insert_row(doc, tid, 0) == 0
            saved = api.write(doc)
            assert all(p.find('w:pPr', NS) is not None for p in xml(saved).findall('.//w:tc/w:p', NS))
        finally:
            api.doc_free(doc)
    elif group == 'table-rows':
        doc = api.read(fixture())
        try:
            tid, _ = api.table(doc)
            assert api.table_insert_row(doc, tid, MAX) == 0
            assert api.table_delete_row(doc, tid, 2) == 0  # delete original row 1
            assert api.table_delete_row(doc, tid, 1) == 0  # delete original row 0
            saved = api.write(doc)
            reopened = api.read(saved)
            try:
                _, t = api.table(reopened)
                assert t.count == 2 and cell_text(t, 0, 0) == '' and cell_text(t, 1, 0) == 'A2'
            finally:
                api.doc_free(reopened)
            assert api.table_delete_row(doc, tid, 0) == 0
            assert api.table_delete_row(doc, tid, 0) != 0
        finally:
            api.doc_free(doc)
    elif group == 'table-new':
        p = Block()
        cells = (Cell * 2)(Cell(blocks=c.pointer(p), count=1), Cell())
        rows = (Row * 1)(Row(cells=cells, count=2))
        table = Table(rows=rows, count=1, columns=2, width=6000, borders=2)
        block = Block(kind=1, table=c.cast(c.pointer(table), c.c_void_p))
        doc = c.c_void_p()
        assert api.doc_create(None, 0, c.byref(block), 1, None, 0, None, c.byref(doc)) == 0
        try:
            tid, t = api.table(doc)
            assert len({tid, t.rows[0].id, t.rows[0].cells[0].id, t.rows[0].cells[1].id,
                        t.rows[0].cells[0].blocks[0].id}) == 5
            api.text(doc, tid, 0, 0, '新表 & < >')
            assert api.table_insert_row(doc, tid, 0) == 0
            saved = api.write(doc)
            assert all(tc.find('w:p', NS) is not None for tc in xml(saved).findall('.//w:tc', NS))
            reopened = api.read(saved)
            try:
                _, t = api.table(reopened)
                assert t.width == 6000 and t.borders == 2 and t.count == 2 and cell_text(t, 0, 0) == '新表 & < >'
            finally:
                api.doc_free(reopened)
        finally:
            api.doc_free(doc)
    elif group == 'history':
        source = fixture()
        doc = api.read(source)
        try:
            baseline = api.write(doc)
            tid, _ = api.table(doc)
            tx = api.begin(doc)
            assert tx
            assert api.table_insert_row(doc, tid, 1) == 0
            api.text(doc, tid, 2, 0, 'transaction')
            image = api.image(doc, tid, png(), 20, 30)
            assert api.table_set_width(doc, tid, 7000) == 0
            assert api.commit(tx) == 0
            edited = api.write(doc)
            assert api.undo(doc) == 0 and unzip(api.write(doc)) == unzip(baseline)
            assert api.redo(doc) == 0 and unzip(api.write(doc)) == unzip(edited)
            tx = api.begin(doc)
            assert api.delete_image(doc, image) == 0
            assert api.delete_table(doc, tid) == 0
            assert api.table_insert_row(doc, tid, 0) != 0
            assert api.commit(tx) != 0 and unzip(api.write(doc)) == unzip(edited)
            tx = api.begin(doc)
            assert api.delete_table(doc, tid) == 0
            assert api.rollback(tx) == 0 and unzip(api.write(doc)) == unzip(edited)
        finally:
            api.doc_free(doc)
    elif group in ('image-small', 'image-large'):
        w, h, width, height = (1, 1, 0.75, 0.75) if group == 'image-small' else (800, 600, 600.25, 450.5)
        payload, source = png(w, h), fixture()
        doc = api.read(source)
        try:
            baseline = api.write(doc)
            tid, _ = api.table(doc)
            image = api.image(doc, tid, payload, width, height)
            saved = api.write(doc)
            if group == 'image-small':
                # ZIP DOS timestamps tick every two seconds. Compare every byte.
                time.sleep(2.1)
                assert api.write(doc) == saved
                bad, rejected = b'text renamed to .png', ID(999)
                count = api.block_count(doc)
                assert api.insert_image(doc, 0, bad, len(bad), 10, 10, c.byref(rejected)) == 5
                assert not rejected.value and api.block_count(doc) == count
                assert api.write(doc) == saved
            assert dimensions(saved) == [(width, height)]
            assert media(source).items() <= media(saved).items()
            assert payload in media(saved).values()
            assert len(image_rels(saved)) == len(image_rels(source)) + 1
            types = ET.fromstring(unzip(saved)['[Content_Types].xml'])
            assert any(n.get('Extension') == 'png' and n.get('ContentType') == 'image/png' for n in types)
            reopened = api.read(saved)
            try:
                assert dimensions(api.write(reopened)) == [(width, height)]
                assert media(api.write(reopened)) == media(saved)
            finally:
                api.doc_free(reopened)
            assert api.delete_image(doc, image) == 0 and unzip(api.write(doc)) == unzip(baseline)
            report.update(pixel_dimensions=[w, h], point_dimensions=[width, height], emu=[round(width * 12700), round(height * 12700)])
            if output:
                (output / (group + '.docx')).write_bytes(saved)
        finally:
            api.doc_free(doc)
    elif group == 'image-delete':
        source = fixture('images')
        doc = api.read(source)
        try:
            p = next(p for p in api.paragraphs(doc) if any(p.runs[i].kind == 1 and b'drawing' in c.string_at(p.runs[i].xml, p.runs[i].xml_size) for i in range(p.count)))
            rid = next(p.runs[i].id for i in range(p.count) if p.runs[i].kind == 1)
            assert api.delete_image(doc, rid) == 0
            saved = api.write(doc)
            assert len(media(source)) == 1 and len(media(saved)) == 0 and not image_rels(saved)
            assert not xml(saved).findall('.//w:drawing', NS)
            assert 'image neighbour' in ''.join(xml(saved).itertext())
            assert api.undo(doc) == 0 and media(api.write(doc)) == media(source)
            assert api.redo(doc) == 0 and unzip(api.write(doc)) == unzip(saved)
            reopened = api.read(saved)
            api.doc_free(reopened)
            report.update(media_before=1, media_after=0, image_relationships_before=1, image_relationships_after=0)
            if output:
                (output / 'image-deleted.docx').write_bytes(saved)
        finally:
            api.doc_free(doc)
        # Mixed-content opaque runs retain text, run properties, and non-image drawings.
        mixed = ('<w:r><w:rPr><w:b/></w:rPr><w:t>mixed text</w:t>'
                 '<w:drawing><a:blip r:embed="image1"/></w:drawing>'
                 '<w:drawing><x:chart x:keep="yes"/></w:drawing></w:r>')
        doc = api.read(package(body=paragraph('before', mixed) + SECT))
        try:
            p = api.paragraphs(doc)[0]
            assert api.delete_image(doc, p.id) == 0
            raw = unzip(api.write(doc))['word/document.xml']
            assert b'<w:rPr><w:b/></w:rPr><w:t>mixed text</w:t>' in raw
            assert b'<w:drawing><x:chart x:keep="yes"/></w:drawing>' in raw
            assert not media(api.write(doc))
            assert api.delete_image(doc, p.id) != 0
        finally:
            api.doc_free(doc)
    elif group == 'image-shared':
        for header in (False, True):
            parts = unzip(package(body=paragraph('one', DRAWING) + paragraph('two', DRAWING) + SECT))
            if header:
                parts['word/_rels/header1.xml.rels'] = ('<Relationships xmlns="' + REL + '"><Relationship Id="header-image" Type="' + R + '/image" Target="media/image1.png"/></Relationships>').encode()
                parts['word/header1.xml'] = ('<w:hdr xmlns:w="' + W + '"/>').encode()
            doc = api.read(repack(parts))
            try:
                ids = [p.id for p in api.paragraphs(doc)]
                assert api.delete_image(doc, ids[0]) == 0
                assert len(media(api.write(doc))) == 1 and len(image_rels(api.write(doc))) == 1
                assert api.delete_image(doc, ids[1]) == 0
                saved = api.write(doc)
                assert len(media(saved)) == int(header) and not image_rels(saved)
            finally:
                api.doc_free(doc)
        # Distinct relationship IDs can share the same media part.
        source = package(body=paragraph('one', DRAWING) + paragraph('two', DRAWING.replace('image1', 'alias')) + SECT)
        parts = unzip(source)
        parts['word/_rels/document.xml.rels'] = parts['word/_rels/document.xml.rels'].replace(b'</Relationships>',
            ('<Relationship Id="alias" Type="' + R + '/image" Target="media/image1.png"/></Relationships>').encode())
        doc = api.read(repack(parts))
        try:
            ids = [p.id for p in api.paragraphs(doc)]
            assert api.delete_image(doc, ids[0]) == 0
            assert len(media(api.write(doc))) == 1 and len(image_rels(api.write(doc))) == 1
            assert api.delete_image(doc, ids[1]) == 0
            assert not media(api.write(doc)) and not image_rels(api.write(doc))
        finally:
            api.doc_free(doc)
    elif group == 'image-cell':
        # Image deletion must not reconstruct nested tables or shaded/merged properties.
        protected = '<w:tc><w:tcPr><w:gridSpan w:val="2"/><w:shd w:fill="ABCDEF"/></w:tcPr><!--before-->' + paragraph('keep text', DRAWING) + NESTED + '<!--after-->' + paragraph('tail') + '</w:tc>'
        source = package(body='<w:tbl>' + GRID + '<w:tr>' + protected + '</w:tr>' + row(1) + '</w:tbl>' + SECT)
        doc = api.read(source)
        try:
            _, t = api.table(doc)
            p = t.rows[0].cells[0].blocks[0]
            assert api.delete_image(doc, p.id) == 0
            saved = api.write(doc)
            raw = unzip(saved)['word/document.xml']
            assert NESTED.encode() in raw and b'<!--before-->' in raw and b'<!--after-->' in raw
            assert b'<w:gridSpan w:val="2"/><w:shd w:fill="ABCDEF"/>' in raw
            assert not media(saved) and not image_rels(saved) and not xml(saved).findall('.//w:drawing', NS)
            reopened = api.read(saved)
            api.doc_free(reopened)
        finally:
            api.doc_free(doc)
    elif group == 'table-delete':
        for shared in (False, True):
            source = package(body='<w:tbl>' + GRID + '<w:tr>' + cell('in table', extra=paragraph('', DRAWING)) + cell('side') + '</w:tr></w:tbl>'
                             + (paragraph('outside', DRAWING) if shared else paragraph('outside')) + SECT)
            doc = api.read(source)
            try:
                tid, _ = api.table(doc)
                assert api.delete_table(doc, tid) == 0
                saved = api.write(doc)
                assert not shape(saved) and len(media(saved)) == int(shared) and len(image_rels(saved)) == int(shared)
                assert api.undo(doc) == 0 and audit(api.write(doc)) == audit(source)
                assert api.redo(doc) == 0 and unzip(api.write(doc)) == unzip(saved)
                reopened = api.read(saved)
                api.doc_free(reopened)
            finally:
                api.doc_free(doc)
    elif group == 'errors':
        doc = api.read(fixture())
        try:
            tid, _ = api.table(doc)
            before = api.write(doc)
            for fn, args in [(api.table_insert_row, (tid, 3)), (api.table_delete_row, (tid, MAX)),
                             (api.table_set_cell_text, (tid, 0, 2, None, 0)),
                             (api.table_set_cell_text, (tid, 0, 0, None, 1)),
                             (api.table_set_width, (tid, 0)), (api.table_set_width, (tid, -1)),
                             (api.table_set_borders, (tid, 3)), (api.delete_image, (tid,)),
                             (api.delete_table, (0,))]:
                assert fn(doc, *args) != 0 and unzip(api.write(doc)) == unzip(before)
            bad = c.create_string_buffer(b'\xc0\x80')
            run = Run(text=c.cast(bad, c.c_void_p), length=2)
            assert api.table_set_cell_text(doc, tid, 0, 0, c.byref(run), 1) != 0
            for payload in (b'bad', png()[:20], b'\xff\xd8\xffbad'):
                id = ID(99)
                assert api.insert_image(doc, 0, payload, len(payload), 10, 10, c.byref(id)) != 0 and id.value == 0
            for width, height in [(0, 10), (-1, 10), (math.inf, 10), (math.nan, 10), (1e100, 10), (1e-20, 10)]:
                id = ID(99)
                assert api.insert_image(doc, 0, png(), len(png()), width, height, c.byref(id)) != 0 and not id.value
            assert unzip(api.write(doc)) == unzip(before)
        finally:
            api.doc_free(doc)
    elif group == 'image-package':
        # Empty models exercise base OPC creation; JPEG payloads remain byte-identical.
        jpeg = (Path(__file__).parent / 'fixtures/pdf-images/baseline.jpg').read_bytes()
        doc = c.c_void_p()
        assert api.doc_create(None, 0, None, 0, None, 0, None, c.byref(doc)) == 0
        try:
            api.image(doc, 0, jpeg, 12.5, 24.25)
            saved = api.write(doc)
            types = ET.fromstring(unzip(saved)['[Content_Types].xml'])
            assert any(n.get('Extension') == 'jpeg' and n.get('ContentType') == 'image/jpeg' for n in types)
            assert list(media(saved).values()) == [jpeg]
            reopened = api.read(saved)
            api.doc_free(reopened)
        finally:
            api.doc_free(doc)
        # A conflicting source MIME default needs a per-part Override, without rewriting it.
        parts = unzip(fixture())
        parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace(b'</Types>', b'<Default Extension="png" ContentType="application/octet-stream"/></Types>')
        doc = api.read(repack(parts))
        try:
            api.image(doc, 0, png(), 5, 6)
            saved = api.write(doc)
            types = ET.fromstring(unzip(saved)['[Content_Types].xml'])
            assert any(n.get('Extension') == 'png' and n.get('ContentType') == 'application/octet-stream' for n in types)
            assert any(n.get('PartName', '').startswith('/word/media/exr-image') and n.get('ContentType') == 'image/png' for n in types)
        finally:
            api.doc_free(doc)
        # OPC main-part names and Word namespace prefixes are not fixed.
        for strict in (False, True):
            source = package(body=paragraph('prefix') + '<w:tbl>' + GRID + row(0) + '</w:tbl>' + SECT, strict=strict, prefix='q')
            doc = api.read(source)
            try:
                tid, _ = api.table(doc)
                api.text(doc, tid, 0, 0, 'Z0')
                api.image(doc, tid, png(), 11, 22)
                saved = api.write(doc)
                word_ns = 'http://purl.oclc.org/ooxml/wordprocessingml/main' if strict else W
                root = xml(saved)
                assert len(list(root.iter('{' + word_ns + '}drawing'))) == 1
                if strict:
                    assert len(list(root.iter('{http://purl.oclc.org/ooxml/drawingml/main}blip'))) == 1
                    assert len(list(root.iter('{http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing}extent'))) == 1
                reopened = api.read(saved)
                api.doc_free(reopened)
            finally:
                api.doc_free(doc)
        # Removing linked images also removes their now-unused external relationships.
        parts = unzip(fixture('images'))
        parts['word/document.xml'] = parts['word/document.xml'].replace(b'r:embed="image1"', b'r:link="image1"')
        parts['word/_rels/document.xml.rels'] = parts['word/_rels/document.xml.rels'].replace(
            b'Target="media/image1.png"', b'Target="https://example.invalid/image.png" TargetMode="External"')
        doc = api.read(repack(parts))
        try:
            p = next(p for p in api.paragraphs(doc) if p.count > 1)
            assert api.delete_image(doc, p.id) == 0
            assert not image_rels(api.write(doc))
        finally:
            api.doc_free(doc)
        parts = unzip(fixture('images'))
        relocated = {}
        for name, value in parts.items():
            new_name = name.replace('word/', 'custom/').replace('document.xml', 'main.xml')
            if name in ('[Content_Types].xml', '_rels/.rels'):
                value = value.replace(b'word/document.xml', b'custom/main.xml')
            relocated[new_name] = value
        doc = api.read(repack(relocated))
        try:
            tid, _ = api.table(doc)
            api.image(doc, tid, png(), 8, 9)
            saved = api.write(doc)
            assert 'custom/main.xml' in unzip(saved) and 'custom/_rels/main.xml.rels' in unzip(saved)
            assert len([n for n in unzip(saved) if n.startswith('custom/media/')]) == 2
            reopened = api.read(saved)
            api.doc_free(reopened)
        finally:
            api.doc_free(doc)
    else:
        raise AssertionError(group)
    return report

GROUPS = ('table-roundtrip', 'table-properties', 'table-preserve', 'table-rows', 'table-new',
          'history', 'image-small', 'image-large', 'image-delete', 'image-shared', 'image-cell',
          'table-delete', 'errors', 'image-package')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('group', choices=GROUPS + ('all',))
    args = parser.parse_args()
    api = API(args.library.resolve())
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    report = {'library_sha256': hashlib.sha256(args.library.read_bytes()).hexdigest(), 'groups': []}
    for group in GROUPS if args.group == 'all' else [args.group]:
        report['groups'].append(run_group(group, api, args.output))
        print(group, 'PASS', flush=True)
    if args.output:
        (args.output / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    main()
