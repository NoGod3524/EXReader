#!/usr/bin/env python3
"""M-E4: addressable cell blocks, isolated run edits, history and DOCX persistence."""
import argparse
import ctypes as c
from pathlib import Path
from tempfile import TemporaryDirectory

from test_docx_edit_e3 import E3, source
from test_docx_edit_io import Block, ID, package, unzip
from test_docx_edit_table_image import cell, paragraph, GRID, NESTED, SECT, xml


class E4(E3):
    def __init__(self, library):
        super().__init__(library)
        ptr, size = c.c_void_p, c.c_size_t
        for name, result, args in [
            ('find_block', c.POINTER(Block), [ptr, ID]),
            ('set_run_text', c.c_int, [ptr, ID, size, ptr, size]),
            ('table_cell_block_count', size, [ptr, ID, size, size]),
            ('table_cell_block_at', c.POINTER(Block), [ptr, ID, size, size, size])]:
            fn = getattr(self.dll, 'exr_edit_' + name)
            fn.restype, fn.argtypes = result, args
            setattr(self, name, fn)

    def cell_blocks(self, doc, tid, row=0, col=0):
        return [self.table_cell_block_at(doc, tid, row, col, i).contents
                for i in range(self.table_cell_block_count(doc, tid, row, col))]

    def texts(self, doc, tid):
        return [text(p) for p in self.cell_blocks(doc, tid)]


def text(p):
    return b''.join(c.string_at(p.runs[i].text, p.runs[i].length)
                    for i in range(p.count) if p.runs[i].kind == 0).decode()


def acceptance(api, output):
    data = source('<w:tr>' + cell('AB') + cell('side') + '</w:tr>')
    (output / 'source-2x2.docx').write_bytes(data)
    doc = api.read(data)
    try:
        tid, table = api.table(doc)
        assert table.count == table.columns == 2
        top_ids = [p.id for p in api.blocks(doc)]
        pid = api.cell_paragraph(doc, tid, 0, 0, 0).contents.id
        assert api.split_paragraph(doc, pid, 0, 1) == 0
        assert api.texts(doc, tid) == ['A', 'B']
        ps = api.cell_blocks(doc, tid)
        ids = [p.id for p in ps]
        run_ids = [p.runs[0].id for p in ps]
        assert [p.id for p in api.blocks(doc)] == top_ids
        assert not api.table_cell_block_at(doc, tid, 0, 0, 2)
        assert all(api.find_block(doc, p.id).contents.id == p.id for p in ps)
        print('1 PASS 2x2 Enter: paragraphs=2 text=A|B; cell count/at enumerates both; top-level unchanged', flush=True)
        found = api.find_block(doc, ids[1])
        assert found and text(found.contents) == 'B'
        assert c.addressof(found.contents) == c.addressof(api.cell_paragraph(doc, tid, 0, 0, 1).contents)
        print('2 PASS find_block(second id) != NULL text=B', flush=True)
        assert api.set_run_text(doc, ids[1], 0, b'B2', 2) == 0
        assert api.texts(doc, tid) == ['A', 'B2']
        assert [p.id for p in api.cell_blocks(doc, tid)] == ids
        assert [p.runs[0].id for p in api.cell_blocks(doc, tid)] == run_ids
        assert text(api.table_cell_block_at(doc, tid, 0, 1, 0).contents) == 'side'
        print('3 PASS set_run_text(second, B2)=EXR_OK paragraphs=2 text=A|B2; sibling/run IDs retained', flush=True)
        assert api.undo(doc) == 0 and api.texts(doc, tid) == ['A', 'B']
        print('4 PASS undo once: paragraphs=2 text=A|B', flush=True)
        assert api.redo(doc) == 0 and api.texts(doc, tid) == ['A', 'B2']
        path = output / 'edited-2x2.docx'
        path.write_bytes(api.write(doc))
        nodes = xml(path.read_bytes()).findall('.//{*}tbl/{*}tr/{*}tc')[0].findall('{*}p')
        assert [''.join(p.itertext()) for p in nodes] == ['A', 'B2']
        reopened = api.read(path.read_bytes())
        try:
            new_tid, _ = api.table(reopened)
            assert api.texts(reopened, new_tid) == ['A', 'B2']
            p = api.cell_blocks(reopened, new_tid)[1]
            assert text(api.find_block(reopened, p.id).contents) == 'B2'
            assert api.set_run_text(reopened, p.id, 0, b'B3', 2) == 0
            assert api.texts(reopened, new_tid) == ['A', 'B3']
        finally:
            api.doc_free(reopened)
        print('5 PASS redo + file write/read: paragraphs=2 text=A|B2; reopened paragraph remains editable', flush=True)
    finally:
        api.doc_free(doc)
    doc = api.read(package(body=paragraph('ordinary') + SECT))
    try:
        p = api.paragraphs(doc)[0]
        pid, rid = p.id, p.runs[0].id
        assert text(api.find_block(doc, pid).contents) == 'ordinary'
        assert api.set_run_text(doc, pid, 0, b'ordinary2', 9) == 0
        assert api.block_count(doc) == 1 and text(api.find_block(doc, pid).contents) == 'ordinary2'
        assert api.find_block(doc, pid).contents.runs[0].id == rid
        assert api.undo(doc) == 0 and text(api.find_block(doc, pid).contents) == 'ordinary'
        print('6 PASS top-level find_block/set_run_text/undo: ordinary -> ordinary2 -> ordinary; count=1 IDs stable', flush=True)
    finally:
        api.doc_free(doc)


def boundaries(api):
    for strict, prefix in ((False, 'w'), (True, 'q')):
        doc = api.read(package(body='<w:tbl>' + GRID + '<w:tr><w:tc>'
                              + '<!--before-->' + paragraph('one') + '<!--middle-->' + paragraph('中') + paragraph('three') + '<!--after-->'
                              + '</w:tc>' + cell('side') + '</w:tr></w:tbl>' + SECT,
                              strict=strict, prefix=prefix))
        try:
            tid, _ = api.table(doc)
            ps = api.cell_blocks(doc, tid)
            pid = ps[1].id
            baseline = unzip(api.write(doc))
            tx = api.begin(doc)
            assert tx
            # Queries must not latch a failure in the active transaction.
            for args in ((None, tid, 0, 0), (doc, 0, 0, 0), (doc, tid, 99, 0), (doc, tid, 0, 99)):
                assert api.table_cell_block_count(*args) == 0
                assert not api.table_cell_block_at(*args, 0)
            assert not api.find_block(None, pid) and not api.find_block(doc, 0)
            assert not api.find_block(doc, ps[1].runs[0].id)
            # Input aliases a sibling's borrowed text.
            assert api.set_run_text(doc, pid, 0, ps[0].runs[0].text, ps[0].runs[0].length) == 0
            assert api.texts(doc, tid) == ['one', 'one', 'three']
            assert api.commit(tx) == 0
            assert api.undo(doc) == 0 and unzip(api.write(doc)) == baseline
            tx = api.begin(doc)
            assert api.set_run_text(doc, pid, 0, b'x', 1) == 0
            assert api.set_run_text(doc, pid, 99, b'x', 1) == 1
            assert api.set_run_text(doc, pid, 0, b'y', 1) == 1
            assert api.commit(tx) == 1 and unzip(api.write(doc)) == baseline
            tx = api.begin(doc)
            assert api.set_run_text(doc, pid, 0, None, 0) == 0
            assert api.texts(doc, tid) == ['one', '', 'three']
            assert api.rollback(tx) == 0 and unzip(api.write(doc)) == baseline
            for bad in (b'\xc0\x80', b'\x00', b'\x01'):
                assert api.set_run_text(doc, pid, 0, bad, len(bad)) == 1
                assert unzip(api.write(doc)) == baseline
            assert api.set_run_text(doc, pid, 0, '字'.encode(), 3) == 0
            saved = api.write(doc)
            raw = unzip(saved)['word/document.xml']
            assert all(marker in raw for marker in (b'<!--before-->', b'<!--middle-->', b'<!--after-->'))
            reopened = api.read(saved)
            try:
                new_tid, _ = api.table(reopened)
                assert api.texts(reopened, new_tid) == ['one', '字', 'three']
            finally:
                api.doc_free(reopened)
        finally:
            api.doc_free(doc)
    for protected in (cell('merged', '<w:gridSpan w:val="2"/>'),
                      cell('vertical', '<w:vMerge w:val="restart"/>'),
                      cell('shaded', '<w:shd w:fill="AABBCC"/>'),
                      cell('nested', extra=NESTED),
                      cell('opaque', extra='<w:r><w:drawing/></w:r>')):
        doc = api.read(source('<w:tr>' + protected + cell('side') + '</w:tr>'))
        try:
            tid, _ = api.table(doc)
            original = unzip(api.write(doc))
            ps = api.cell_blocks(doc, tid)
            assert ps and api.find_block(doc, ps[0].id)
            assert not api.cell_paragraph(doc, tid, 0, 0, 0)
            assert api.set_run_text(doc, ps[0].id, 0, b'x', 1) == 11
            assert unzip(api.write(doc)) == original
            assert all(api.find_block(doc, p.id) for p in ps)
        finally:
            api.doc_free(doc)
    print('extra PASS imported multi-paragraph cells; alias/UTF-8/clear; failed tx/rollback; strict namespace; merged/shaded/nested/opaque protected', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    api = E4(args.library.resolve())
    with TemporaryDirectory() as temp:
        output = args.output or Path(temp)
        output.mkdir(parents=True, exist_ok=True)
        acceptance(api, output)
        boundaries(api)
