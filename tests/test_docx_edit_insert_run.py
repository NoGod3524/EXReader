#!/usr/bin/env python3
"""Insert the first run without replacing its paragraph or sibling cell content."""
import argparse
import ctypes as c
from pathlib import Path
from test_docx_edit_e4 import E4, text
from test_docx_edit_io import ID, RP, Run, unzip
from test_docx_edit_e3 import source
from test_docx_edit_table_image import cell


def check(api):
    fn = api.dll.exr_edit_insert_run
    fn.restype = c.c_int
    fn.argtypes = [c.c_void_p, c.c_void_p, ID, c.c_size_t,
                   c.c_void_p, c.c_size_t, c.POINTER(RP)]
    doc = api.read(source('<w:tr>' + cell('AB') + cell('side') + '</w:tr>'))
    try:
        tid, _ = api.table(doc)
        first = api.cell_paragraph(doc, tid, 0, 0, 0).contents.id
        assert api.split_paragraph(doc, first, 1, 0) == 0
        empty = api.cell_paragraph(doc, tid, 0, 0, 1).contents.id
        assert api.find_block(doc, empty).contents.count == 0
        assert api.set_run_text(doc, empty, 0, b'X', 1) == 1
        assert fn(doc, None, empty, 0, b'X', 1, None) == 1
        tx = api.begin(doc)
        props = RP(present=4, bold=1)
        assert fn(doc, tx, empty, 0, b'X', 1, c.byref(props)) == 0
        assert api.set_run_text(doc, empty, 0, b'XY', 2) == 0
        assert api.commit(tx) == 0
        assert api.texts(doc, tid) == ['AB', 'XY']
        assert api.undo(doc) == 0 and api.texts(doc, tid) == ['AB', '']
        assert api.redo(doc) == 0 and api.texts(doc, tid) == ['AB', 'XY']
        p = api.find_block(doc, empty).contents
        assert p.id == empty and p.runs[0].props.bold == 1
        # Aliased text and props survive replacing the table's backing storage.
        tx = api.begin(doc)
        old_run = p.runs[0].id
        assert fn(doc, tx, empty, 0, p.runs[0].text, 2, c.byref(p.runs[0].props)) == 0
        assert api.commit(tx) == 0
        p = api.find_block(doc, empty).contents
        assert text(p) == 'XYXY' and p.runs[1].id == old_run
        assert p.runs[0].id != old_run
        saved = unzip(api.write(doc))
        tx = api.begin(doc)
        assert fn(doc, tx, empty, 2, b'Z', 1, None) == 0
        assert fn(doc, tx, empty, 99, b'!', 1, None) == 1
        assert api.commit(tx) == 1 and unzip(api.write(doc)) == saved
        tx = api.begin(doc)
        assert fn(doc, tx, empty, 0, b'\xff', 1, None) == 1
        assert api.commit(tx) == 1
        # Paragraph insertion/deletion in a cell preserves all siblings.
        added = ID()
        assert api.insert_paragraph(doc, empty, None, 0, None, c.byref(added)) == 0
        assert api.texts(doc, tid) == ['AB', 'XYXY', '']
        assert api.delete_block(doc, added.value) == 0
        assert api.texts(doc, tid) == ['AB', 'XYXY']
        reopened = api.read(api.write(doc))
        try:
            new_tid, _ = api.table(reopened)
            assert api.texts(reopened, new_tid) == ['AB', 'XYXY']
            assert text(api.cell_paragraph(reopened, new_tid, 0, 1, 0).contents) == 'side'
        finally:
            api.doc_free(reopened)
        print('PASS insert_run: zero-run / sibling text / atomic undo-redo / aliased input / fresh IDs / failed transaction rollback / invalid UTF-8 / cell paragraph insert-delete / DOCX reopen')
    finally:
        api.doc_free(doc)
    protected = api.read(source('<w:tr><w:tc><w:tcPr><w:shd w:fill="FF0000"/></w:tcPr><w:p/></w:tc>' + cell('side') + '</w:tr>'))
    try:
        tid, _ = api.table(protected)
        pid = api.table_cell_block_at(protected, tid, 0, 0, 0).contents.id
        tx = api.begin(protected)
        assert fn(protected, tx, pid, 0, b'X', 1, None) == 11
        assert api.commit(tx) == 11
        print('PASS protected cell: EXR_UNSUPPORTED; transaction rolled back')
    finally:
        api.doc_free(protected)
    # Imported multi-paragraph cells exercise both sides of an empty paragraph,
    # including retained paragraph properties and an earlier patched text edit.
    data = source('<w:tr><w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'
                  '<w:p><w:r><w:t>left</w:t></w:r></w:p>'
                  '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr></w:p>'
                  '<w:p><w:r><w:t>right</w:t></w:r></w:p></w:tc>' + cell('side') + '</w:tr>')
    doc = api.read(data)
    try:
        tid, _ = api.table(doc)
        ids = [p.id for p in api.cell_blocks(doc, tid)]
        assert api.set_run_text(doc, ids[0], 0, b'LEFT', 4) == 0
        tx = api.begin(doc)
        assert fn(doc, tx, ids[1], 0, b'X', 1, None) == 0
        assert api.commit(tx) == 0
        assert api.texts(doc, tid) == ['LEFT', 'X', 'right']
        assert [p.id for p in api.cell_blocks(doc, tid)] == ids
        assert b'pStyle' in unzip(api.write(doc))['word/document.xml']
        reopened = api.read(api.write(doc))
        try:
            new_tid, _ = api.table(reopened)
            assert api.texts(reopened, new_tid) == ['LEFT', 'X', 'right']
        finally:
            api.doc_free(reopened)
        assert api.undo(doc) == 0 and api.texts(doc, tid) == ['LEFT', '', 'right']
        print('PASS imported [LEFT|empty|right]: insert X preserves both neighbors, IDs, pStyle, previous patch and DOCX reopen; undo restores empty')
    finally:
        api.doc_free(doc)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    check(E4(parser.parse_args().library.resolve()))
