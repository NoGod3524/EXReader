#!/usr/bin/env python3
"""M-E3 public API acceptance: cell splits, transactional grid widths, ZIP/XML audit."""
import argparse
import ctypes as c
from pathlib import Path

from test_docx_edit_io import Block, ID, package, unzip
from test_docx_edit_table_image import API, Table, GRID, SECT, cell, row, xml


class E3(API):
    def __init__(self, library):
        super().__init__(library)
        self.cell_paragraph = self.dll.exr_edit_table_cell_paragraph
        self.cell_paragraph.restype = c.POINTER(Block)
        self.cell_paragraph.argtypes = [c.c_void_p, ID, c.c_size_t, c.c_size_t, c.c_size_t]
        self.column_width = self.dll.exr_edit_table_set_column_width
        self.column_width.restype = c.c_int
        self.column_width.argtypes = [c.c_void_p, c.c_void_p, ID, c.c_size_t, c.c_int32]

    def state(self, doc):
        block = self.blocks(doc, 1)[0]
        t = c.cast(block.table, c.POINTER(Table)).contents
        return [t.widths[i] if t.widths else t.width // t.columns for i in range(t.columns)], t.width

    def set_width(self, doc, tid, column, width):
        tx = self.begin(doc)
        assert tx
        assert self.column_width(doc, tx, tid, column, width) == 0
        assert self.commit(tx) == 0


def source(first=None, grid=GRID):
    return package(body='<w:tbl><w:tblPr><w:tblW w:w="4800" w:type="dxa"/></w:tblPr>'
                   + grid + (row(0) if first is None else first) + row(1) + '</w:tbl>' + SECT)


def check_xml(api, doc, expected):
    data = api.write(doc)
    root = xml(data)
    ns = {'w': root.tag[1:].split('}')[0]}
    attr = '{%s}w' % ns['w']
    table = root.find('.//w:tbl', ns)
    widths = [int(n.get(attr)) for n in table.findall('w:tblGrid/w:gridCol', ns)]
    total = int(table.find('w:tblPr/w:tblW', ns).get(attr))
    assert (widths, total) == expected == api.state(doc)
    reopened = api.read(data)
    try:
        assert api.state(reopened) == expected
        assert api.state(reopened) == api.state(doc)
    finally:
        api.doc_free(reopened)
    return data


def acceptance(api, output):
    data = source()
    if output:
        output.mkdir(parents=True, exist_ok=True)
        (output / 'source-2x2.docx').write_bytes(data)
    doc = api.read(data)
    try:
        tid, t = api.table(doc)
        assert t.count == t.columns == 2
        p = api.cell_paragraph(doc, tid, 0, 0, 0).contents
        pid, rid, count = p.id, p.runs[0].id, t.rows[0].cells[0].count
        top_count = api.block_count(doc)
        tx = api.begin(doc)
        assert tx and api.split_paragraph(doc, pid, 0, 1) == 0 and api.commit(tx) == 0
        _, t = api.table(doc)
        assert t.rows[0].cells[0].count == count + 1
        assert api.block_count(doc) == top_count
        print('1 PASS 2x2 DOCX cell(0,0) split=EXR_OK cell.blocks=1->2')
        left = api.cell_paragraph(doc, tid, 0, 0, 0).contents
        right = api.cell_paragraph(doc, tid, 0, 0, 1).contents
        assert left.id == pid and left.runs[0].id == rid and right.id != pid
        assert c.string_at(left.runs[0].text) == b'A' and c.string_at(right.runs[0].text) == b'0'
        assert not api.cell_paragraph(doc, tid, 0, 0, 2)
        assert [left.id, right.id] == [t.rows[0].cells[0].blocks[i].id for i in range(2)]
        print('2 PASS cell_paragraph[0,1]=[A,0]; both belong to cell(0,0); index=2 NULL')
        assert api.undo(doc) == 0 and not api.cell_paragraph(doc, tid, 0, 0, 1)
        assert api.redo(doc) == 0 and api.cell_paragraph(doc, tid, 0, 0, 1).contents.id == right.id
        api.set_width(doc, tid, 0, 3000)
        check_xml(api, doc, ([3000, 2400], 5400))
        print('3 PASS set_column_width(0,3000) gridCol=[3000,2400] tblW=5400')
        api.set_width(doc, tid, 1, 2600)
        check_xml(api, doc, ([3000, 2600], 5600))
        print('4 PASS set_column_width(1,2600) gridCol=[3000,2600] tblW=5600')
        assert api.undo(doc) == 0
        check_xml(api, doc, ([3000, 2400], 5400))
        print('5 PASS undo gridCol=[3000,2400] tblW=5400')
        saved = check_xml(api, doc, ([3000, 2400], 5400))
        if output:
            path = output / 'edited-2x2.docx'
            path.write_bytes(saved)
            saved = path.read_bytes()
        reopened = api.read(saved)
        try:
            assert api.state(reopened) == api.state(doc) == ([3000, 2400], 5400)
            new_tid, _ = api.table(reopened)
            assert api.cell_paragraph(reopened, new_tid, 0, 0, 1)
            assert not api.cell_paragraph(reopened, new_tid, 0, 0, 2)
            assert api.split_paragraph(reopened, api.cell_paragraph(reopened, new_tid, 0, 0, 1).contents.id, 0, 0) == 0
        finally:
            api.doc_free(reopened)
        print('6 PASS file write/read gridCol[0]=3000 gridCol[1]=2400 tblW=5400; memory/XML/reopened equal')
        before = unzip(api.write(doc))
        tx = api.begin(doc)
        assert api.column_width(doc, tx, tid, 99, 1000) == 1
        assert unzip(api.write(doc)) == before and api.commit(tx) == 1
        assert unzip(api.write(doc)) == before
        print('7 PASS column=99 EXR_ARGUMENT(1); model unchanged; failed commit rolled back')
        assert api.redo(doc) == 0
        check_xml(api, doc, ([3000, 2600], 5600))
    finally:
        api.doc_free(doc)


def boundaries(api):
    # Multiple paragraphs, empty placeholders, namespace variants and protected cells.
    for first in ('<w:tr><w:tc><w:p/><w:p/></w:tc>' + cell('side') + '</w:tr>',
                  '<w:tr><w:tc><w:p/></w:tc>' + cell('side') + '</w:tr>'):
        for strict, prefix in ((False, 'w'), (True, 'q')):
            body = unzip(source(first))['word/document.xml'].decode().split('<w:body>')[1].split('</w:body>')[0]
            doc = api.read(package(body=body, strict=strict, prefix=prefix))
            try:
                tid, t = api.table(doc)
                count = t.rows[0].cells[0].count
                pid = api.cell_paragraph(doc, tid, 0, 0, 0).contents.id
                assert api.split_paragraph(doc, pid, 0, 0) == 0
                assert api.cell_paragraph(doc, tid, 0, 0, count)
                api.set_width(doc, tid, 0, 3000)
                check_xml(api, doc, ([3000, 2400], 5400))
            finally:
                api.doc_free(doc)
    doc = api.read(source())
    try:
        tid, _ = api.table(doc)
        for args in ((doc, tid, 99, 0, 0), (doc, tid, 0, 99, 0), (doc, 0, 0, 0, 0), (None, tid, 0, 0, 0)):
            assert not api.cell_paragraph(*args)
        original = unzip(api.write(doc))
        pid = api.cell_paragraph(doc, tid, 0, 0, 0).contents.id
        tx = api.begin(doc)
        assert api.split_paragraph(doc, pid, 0, 1) == 0
        assert api.column_width(doc, tx, tid, 0, 3000) == 0
        assert api.rollback(tx) == 0 and unzip(api.write(doc)) == original
        tx = api.begin(doc)
        assert not api.cell_paragraph(doc, tid, 99, 0, 0)
        assert api.split_paragraph(doc, pid, 0, 1) == 0
        assert api.column_width(doc, tx, tid, 0, 3000) == 0
        assert api.column_width(doc, tx, tid, 99, 1000) == 1
        assert api.column_width(doc, tx, tid, 1, 2600) == 1
        assert api.commit(tx) == 1 and unzip(api.write(doc)) == original
        for width, status in ((0, 1), (-1, 1), (2147483647, 6)):
            tx = api.begin(doc)
            result = api.column_width(doc, tx, tid, 0, width)
            assert result == status, result
            assert api.commit(tx) == result and unzip(api.write(doc)) == original
        assert api.column_width(doc, None, tid, 0, 3000) == 1
        other = api.read(source())
        try:
            wrong_tx = api.begin(other)
            assert api.column_width(doc, wrong_tx, tid, 0, 3000) == 1
            assert api.rollback(wrong_tx) == 0
        finally:
            api.doc_free(other)
        assert api.table_set_width(doc, tid, 7200) == 0
        assert api.state(doc) == ([2400, 2400], 7200)
    finally:
        api.doc_free(doc)
    for first in ('<w:tr>' + cell('merged', '<w:gridSpan w:val="2"/>') + '</w:tr>',
                  '<w:tr>' + cell('shaded', '<w:shd w:fill="AABBCC"/>') + cell('side') + '</w:tr>',
                  '<w:tr>' + cell('opaque', extra='<w:r><w:drawing/></w:r>') + cell('side') + '</w:tr>'):
        doc = api.read(source(first))
        try:
            tid, t = api.table(doc)
            assert not api.cell_paragraph(doc, tid, 0, 0, 0)
            assert api.split_paragraph(doc, t.rows[0].cells[0].blocks[0].id, 0, 0) == 11
        finally:
            api.doc_free(doc)
    doc = api.read(source('<w:tr>' + cell('A中B') + cell('side') + '</w:tr>'))
    try:
        tid, _ = api.table(doc)
        pid = api.cell_paragraph(doc, tid, 0, 0, 0).contents.id
        before = unzip(api.write(doc))
        assert api.split_paragraph(doc, pid, 0, 2) == 1 and unzip(api.write(doc)) == before
        assert api.split_paragraph(doc, pid, 0, 4) == 0
        assert c.string_at(api.cell_paragraph(doc, tid, 0, 0, 0).contents.runs[0].text) == 'A中'.encode()
    finally:
        api.doc_free(doc)
    doc = api.read(source(grid=''))
    try:
        tid, _ = api.table(doc)
        api.set_width(doc, tid, 0, 3000)
        check_xml(api, doc, ([3000, 2400], 5400))
    finally:
        api.doc_free(doc)
    doc = api.read(source('<w:tr><w:tc/>' + cell('side') + '</w:tr>'))
    try:
        tid, _ = api.table(doc)
        assert not api.cell_paragraph(doc, tid, 0, 0, 0)
    finally:
        api.doc_free(doc)
    custom_grid = GRID.replace('<w:tblGrid>', '<w:tblGrid x:keep="grid"><!--grid comment-->').replace(
        '<w:gridCol w:w="2400"/>', '<w:gridCol x:keep="col" w:w="2400"/>')
    doc = api.read(source(grid=custom_grid))
    try:
        tid, _ = api.table(doc)
        tx = api.begin(doc)
        assert api.column_width(doc, tx, tid, 0, 3000) == 0
        assert api.column_width(doc, tx, tid, 1, 2600) == 0
        assert api.commit(tx) == 0
        raw = unzip(check_xml(api, doc, ([3000, 2600], 5600)))['word/document.xml']
        assert b'x:keep="grid"' in raw and raw.count(b'x:keep="col"') == 2 and b'<!--grid comment-->' in raw
        assert api.undo(doc) == 0 and api.state(doc) == ([2400, 2400], 4800)
        assert api.redo(doc) == 0
    finally:
        api.doc_free(doc)
    print('extra PASS split undo/redo; rollback; empty/multiple paragraphs; strict/alternate namespace; invalid tx/width; overflow; legacy table width')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    api = E3(args.library.resolve())
    acceptance(api, args.output)
    boundaries(api)
