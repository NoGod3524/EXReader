#!/usr/bin/env python3
"""Combined X1/X6 workflow, using original generated text and PNG bytes."""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from test_docx_edit_io import ID, PP, RP, Run, package, repack, unzip, audit
from test_docx_edit_table_image import API, png, paragraph, row, GRID, SECT, DRAWING, xml, shape, media, dimensions
from verify_docx import NS


def text(block):
    return ''.join(c.string_at(r.text, r.length).decode() for r in block.runs[:block.count] if r.kind == 0)


def x5_roundtrips(api):
    folder = Path(__file__).parent / 'fixtures/docx-edit'
    results = []
    for entry in json.loads((folder / 'manifest.json').read_text())['fixtures']:
        source = (folder / entry['path']).read_bytes()
        assert len(source) == entry['bytes']
        assert hashlib.sha256(source).hexdigest() == entry['sha256']
        before = audit(source)
        for key in ('paragraphs', 'tables', 'images', 'footnotes'):
            assert before[key] == entry[key]
        assert len(before['section_margins']) == entry['sections']
        doc = api.read(source)
        try:
            assert len(api.paragraphs(doc)) == entry['body_paragraphs']
            saved = api.write(doc)
            original_parts, saved_parts = unzip(source), unzip(saved)
            assert original_parts.keys() == saved_parts.keys()
            assert all(saved_parts[k] == v for k, v in original_parts.items() if k != 'word/document.xml')
            # Moved section boundaries carry inherited namespace declarations.
            assert ET.tostring(xml(saved)) == ET.tostring(xml(source))
        finally:
            api.doc_free(doc)
        reopened = api.read(saved)
        try:
            assert audit(api.write(reopened)) == before
        finally:
            api.doc_free(reopened)
        results.append(dict(id=entry['id'], status='PASS', structure=before))
    return results


def run(api, folder):
    fixtures = x5_roundtrips(api)
    # One package exercises paragraph, table, image, notes and section IO together.
    body = ''.join(paragraph(t) for t in ('before', 'keep one', 'keep two', 'split target', 'delete target'))
    body += '<w:tbl>' + GRID + ''.join(row(i) for i in range(3)) + '</w:tbl>'
    body += paragraph('image neighbour', DRAWING)
    body += paragraph('notes', '<w:r><w:footnoteReference w:id="1"/></w:r>')
    body += paragraph('section boundary').replace('</w:pPr>', SECT + '</w:pPr>')
    body += paragraph('after') + SECT
    body = body.replace('<w:pPr>', '<w:pPr><w:ind w:left="720" w:right="120" w:firstLine="360"/>')
    parts = unzip(package(body=body))
    parts['word/media/image1.png'] = png()
    source = repack(parts)
    (folder / 'source.docx').write_bytes(source)
    before = audit(source)
    assert [before[k] for k in ('paragraphs', 'tables', 'images', 'footnotes')] == [15, 1, 1, 1], before
    assert len(before['section_margins']) == 2
    steps = []
    doc = api.read(source)

    def step(name, paragraphs, rows=3, images=0):
        assert len(api.paragraphs(doc)) == paragraphs
        assert len(api.blocks(doc, 1)) == 1
        assert api.table(doc)[1].count == rows
        assert len(api.blocks(doc, 4)) == images
        count = c.c_size_t()
        api.sections(doc, c.byref(count))
        assert count.value == 2
        steps.append(dict(step=name, status='PASS', model_paragraphs=paragraphs,
                          tables=1, rows=rows, inserted_image_blocks=images, sections=2))

    try:
        original = {text(b): b.id for b in api.paragraphs(doc)}
        step('open/assert structure (XML: 15 paragraphs, 1 table, 1 image, 1 footnote, 2 sections)', 9)
        anchor = original['before']
        for i in range(5):
            value = ('Y4 inserted %d' % i).encode()
            storage = c.create_string_buffer(value)
            r = Run(text=c.cast(storage, c.c_void_p), length=len(value),
                    props=RP(present=3, font=b'Times New Roman', size=24))
            new_id = ID()
            assert api.insert_paragraph(doc, anchor, c.byref(r), 1, None, c.byref(new_id)) == 0
            anchor = new_id.value
        step('insert 5 paragraphs', 14)
        changed = {}
        for i, name in enumerate(('before', 'keep one', 'keep two')):
            p = PP.from_buffer_copy(next(b for b in api.paragraphs(doc) if b.id == original[name]).props)
            p.present |= 3
            p.align, p.left, p.right, p.first = i + 1, 900 + i * 100, 120, 360
            assert api.set_paragraph_props(doc, original[name], c.byref(p)) == 0
            changed[name] = (i + 1, 900 + i * 100)
        step('change 3 paragraph properties', 14)
        assert api.split_paragraph(doc, original['split target'], 0, 6) == 0
        step('split 1 paragraph', 15)
        assert api.delete_block(doc, original['delete target']) == 0
        step('delete 1 paragraph', 14)
        tid, table = api.table(doc)
        assert api.table_insert_row(doc, tid, table.count - 1) == 0
        api.text(doc, tid, 3, 0, 'Y4 row A')
        api.text(doc, tid, 3, 1, 'Y4 row B')
        step('insert 1 table row', 14, 4)
        image = png(3, 2)
        api.image(doc, anchor, image, 72, 48)
        step('insert 1 PNG (72 x 48 points)', 14, 4, 1)
        saved = api.write(doc)
    finally:
        api.doc_free(doc)

    output = folder / 'edited.docx'
    output.write_bytes(saved)
    reopened = api.read(output.read_bytes())
    try:
        paragraphs = {text(b): b for b in api.paragraphs(reopened)}
        assert all('Y4 inserted %d' % i in paragraphs for i in range(5))
        assert 'split ' in paragraphs and 'target' in paragraphs and 'delete target' not in paragraphs
        for name, (align, left) in changed.items():
            p = paragraphs[name].props
            assert (p.align, p.left, p.right, p.first, p.line) == (align, left, 120, 360, 480)
        for name in ('split ', 'target', 'image neighbour', 'notes', 'section boundary', 'after'):
            p = paragraphs[name]
            assert (p.props.left, p.props.right, p.props.first, p.props.line) == (720, 120, 360, 480)
        for p in paragraphs.values():
            for r in p.runs[:p.count]:
                if r.kind == 0:
                    assert (r.props.font, r.props.size) == (b'Times New Roman', 24)
        assert api.table(reopened)[1].count == 4
        steps.append(dict(step='save/reopen: all edits + font/size/line/indent', status='PASS'))
        # A second write after reopen must retain every metric and package part.
        assert unzip(api.write(reopened)) == unzip(saved)
    finally:
        api.doc_free(reopened)

    after = audit(saved)
    assert after['paragraphs'] == before['paragraphs'] + 5 + 1 - 1 + 2 + 1
    assert after['tables'] == before['tables'] == 1
    assert after['images'] == before['images'] + 1 == 2
    assert after['footnotes'] == before['footnotes'] == 1
    assert after['section_margins'] == before['section_margins']
    assert shape(saved) == [[2, 2, 2, 2]]
    root = xml(saved)
    assert [list(r.itertext()) for r in root.findall('.//w:tbl/w:tr', NS)[:3]] == [
        list(r.itertext()) for r in xml(source).findall('.//w:tbl/w:tr', NS)]
    assert [''.join(n.itertext()) for n in root.findall('.//w:tbl/w:tr', NS)][-1] == 'Y4 row AY4 row B'
    new_parts = unzip(saved)
    for name, value in parts.items():
        if name not in ('word/document.xml', 'word/_rels/document.xml.rels', '[Content_Types].xml'):
            assert new_parts[name] == value, name
    assert image in media(saved).values() and dimensions(saved) == [(72, 48)]
    steps.append(dict(step='independent ZIP/XML: expected counts, row text, notes/sections/parts, exact PNG/dimensions', status='PASS'))
    return dict(status='PASS', x5_fixtures=fixtures, steps=steps, before=before, after=after,
                formatting=dict(font='Times New Roman', size_half_points=24, line=480,
                                changed_left_indents=[900, 1000, 1100], preserved_left_indent=720,
                                right_indent=120, first_line_indent=360),
                source_sha256=hashlib.sha256(source).hexdigest(), output_sha256=hashlib.sha256(saved).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='exr-y4-') as temporary:
        folder = args.output or Path(temporary)
        folder.mkdir(parents=True, exist_ok=True)
        report = run(API(args.library.resolve()), folder)
        (folder / 'e2e.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
