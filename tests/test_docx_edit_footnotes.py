#!/usr/bin/env python3
"""L14: public footnote edits, history and independent OPC/XML assertions."""
import argparse
import ctypes as c
from pathlib import Path
import xml.etree.ElementTree as ET

from test_docx_edit_e4 import E4, text
from test_docx_edit_e3 import source
from test_docx_edit_io import ID, package, unzip, repack
from test_docx_edit_table_image import cell


class Note(c.Structure):
    _fields_ = [('id', ID), ('paragraph_id', ID), ('run_index', c.c_size_t),
                ('number', c.c_size_t), ('text', c.c_void_p), ('size', c.c_size_t)]


class Footnotes(E4):
    def __init__(self, library):
        super().__init__(library)
        ptr, size = c.c_void_p, c.c_size_t
        for name, result, args in [
            ('count', size, [ptr]),
            ('at', c.c_int, [ptr, size, c.POINTER(Note)]),
            ('insert', c.c_int, [ptr, ID, size, size, ptr, size, c.POINTER(ID)]),
            ('set_text', c.c_int, [ptr, ID, ptr, size]),
            ('delete', c.c_int, [ptr, ID]),
        ]:
            fn = getattr(self.dll, 'exr_edit_footnote_' + name)
            fn.restype, fn.argtypes = result, args
            setattr(self, 'note_' + name, fn)

    def notes(self, doc):
        result = []
        for i in range(self.note_count(doc)):
            n = Note()
            assert self.note_at(doc, i, c.byref(n)) == 0
            result.append((n.id, n.paragraph_id, n.run_index, n.number,
                           c.string_at(n.text, n.size)))
        return result

    def insert_note(self, doc, pid, run, offset, value=b''):
        id_ = ID()
        assert self.note_insert(doc, pid, run, offset, value, len(value), c.byref(id_)) == 0
        assert id_.value
        return id_.value


def audit(api, doc, expected):
    parts = unzip(api.write(doc))
    body = ET.fromstring(parts['word/document.xml'])
    ns = body.tag[1:].split('}')[0]
    refs = body.findall('.//{%s}footnoteReference' % ns)
    assert [n.get('{%s}id' % ns) for n in refs] == [str(i + 1) for i in range(len(expected))]
    for ref in refs:
        run = next(r for r in body.iter('{%s}r' % ns) if ref in list(r))
        superscript = run.find('{%s}rPr/{%s}vertAlign' % (ns, ns))
        assert superscript is not None and superscript.get('{%s}val' % ns) == 'superscript'
    notes = ET.fromstring(parts['word/footnotes.xml'])
    def note_text(node):
        return ''.join(('\n' if n.tag == '{%s}br' % ns else
                        '\t' if n.tag == '{%s}tab' % ns else n.text or '')
                       for n in node.iter() if n.tag in
                       ('{%s}t' % ns, '{%s}br' % ns, '{%s}tab' % ns))
    actual = [(n.get('{%s}id' % ns), note_text(n))
              for n in notes if n.tag == '{%s}footnote' % ns
              and n.get('{%s}type' % ns, 'normal') == 'normal']
    assert actual == [(str(i + 1), value) for i, value in enumerate(expected)], actual
    rels = ET.fromstring(parts['word/_rels/document.xml.rels'])
    links = [r for r in rels if r.get('Type', '').endswith('/footnotes')]
    assert len(links) == 1 and links[0].get('Target') == 'footnotes.xml'
    types = ET.fromstring(parts['[Content_Types].xml'])
    assert any(t.get('PartName') == '/word/footnotes.xml' and
               t.get('ContentType', '').endswith('wordprocessingml.footnotes+xml') for t in types)
    reopened = api.read(api.write(doc))
    try:
        assert [n[3:] for n in api.notes(reopened)] == [
            (i + 1, value.encode()) for i, value in enumerate(expected)]
    finally:
        api.doc_free(reopened)
    return parts


def acceptance(api):
    for strict, prefix in [(False, 'w'), (False, 'q'), (True, 'w')]:
        parts = unzip(package(body='<w:p><w:r><w:rPr><w:b/></w:rPr>'
                              '<w:t>A中文B</w:t></w:r></w:p>', strict=strict, prefix=prefix))
        del parts['word/footnotes.xml']
        rels = ET.fromstring(parts['word/_rels/document.xml.rels'])
        for r in list(rels):
            if r.get('Type', '').endswith('/footnotes'):
                rels.remove(r)
        parts['word/_rels/document.xml.rels'] = ET.tostring(rels)
        doc = api.read(repack(parts))
        try:
            p = api.paragraphs(doc)[0]
            pid, original = p.id, text(p)
            first = api.insert_note(doc, pid, 0, 1)
            assert text(api.find_block(doc, pid).contents) == original
            assert api.note_set_text(doc, first, b'note1', 5) == 0
            p = api.find_block(doc, pid).contents
            second = api.insert_note(doc, pid, p.count, 0, b'note2 & <text>')
            saved = audit(api, doc, ['note1', 'note2 & <text>'])
            for name in ('word/endnotes.xml', 'custom/data.bin', 'word/styles.xml'):
                assert saved[name] == parts[name]
            assert api.note_delete(doc, first) == 0
            assert [(n[0], n[3]) for n in api.notes(doc)] == [(second, 1)]
            audit(api, doc, ['note2 & <text>'])
            assert api.undo(doc) == 0
            assert [n[0] for n in api.notes(doc)] == [first, second]
            assert api.redo(doc) == 0
            assert api.note_delete(doc, second) == 0
            assert api.note_count(doc) == 0
            reopened = api.read(api.write(doc))
            assert api.note_count(reopened) == 0
            assert text(api.paragraphs(reopened)[0]) == original
            api.doc_free(reopened)
            print(f'PASS insert/edit/reopen/delete/renumber/history (strict={strict}, prefix={prefix})')
        finally:
            api.doc_free(doc)


def cells_and_validation(api):
    doc = api.read(source('<w:tr>' + cell('A中文B') + cell('side') + '</w:tr>'))
    try:
        tid, _ = api.table(doc)
        pid = api.cell_paragraph(doc, tid, 0, 0, 0).contents.id
        saved = unzip(api.write(doc))
        # Split in the middle of a UTF-8 scalar must leave no dangling note.
        id_ = ID(99)
        assert api.note_insert(doc, pid, 0, 2, b'bad', 3, c.byref(id_)) == 1
        assert id_.value == 0 and api.note_count(doc) == 0
        assert unzip(api.write(doc)) == saved
        tx = api.begin(doc)
        first = api.insert_note(doc, pid, 0, 1, '注释\n第二行'.encode())
        p = api.find_block(doc, pid).contents
        second = api.insert_note(doc, pid, p.count, 0, b'second')
        assert api.commit(tx) == 0
        assert api.texts(doc, tid) == ['A中文B']
        assert text(api.cell_paragraph(doc, tid, 0, 1, 0).contents) == 'side'
        audit(api, doc, ['注释\n第二行', 'second'])
        assert api.undo(doc) == 0 and api.note_count(doc) == 0
        assert api.redo(doc) == 0 and [n[0] for n in api.notes(doc)] == [first, second]
        assert api.note_delete(doc, first) == 0
        audit(api, doc, ['second'])
        print('PASS table-cell refs, UTF-8 validation, grouped undo/redo and cell renumbering')
    finally:
        api.doc_free(doc)


def model_boundaries(api):
    doc = api.read(package(body='<w:p/>'))
    try:
        pid = api.paragraphs(doc)[0].id
        first = api.insert_note(doc, pid, 0, 0, b'alias')
        note = Note()
        assert api.note_at(doc, 0, c.byref(note)) == 0
        second = ID()
        # The input becomes invalid during the owning paragraph replacement.
        assert api.note_insert(doc, pid, 0, 0, note.text, note.size, c.byref(second)) == 0
        assert [(n[0], n[3], n[4]) for n in api.notes(doc)] == [
            (second.value, 1, b'alias'), (first, 2, b'alias')]
        assert api.note_set_text(doc, first, None, 0) == 0
        audit(api, doc, ['alias', ''])
        assert api.delete_block(doc, pid) == 0 and api.note_count(doc) == 0
        assert api.undo(doc) == 0 and [n[0] for n in api.notes(doc)] == [second.value, first]
        assert api.note_delete(doc, first) == 0
        assert api.note_delete(doc, second) == 0
        assert api.find_block(doc, pid).contents.count == 0
        note.id = 99
        assert api.note_at(doc, 0, c.byref(note)) == 1 and note.id == 0
        print('PASS empty paragraph, aliased input, insert before reference, clear text and block undo')
    finally:
        api.doc_free(doc)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    api = Footnotes(parser.parse_args().library.resolve())
    acceptance(api)
    cells_and_validation(api)
    model_boundaries(api)
