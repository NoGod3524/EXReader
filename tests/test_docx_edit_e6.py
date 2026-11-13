#!/usr/bin/env python3
"""M-E6: first-run insertion, cell paragraph insertion, atomic failures and IO."""
import argparse
import ctypes as c
from pathlib import Path
from tempfile import TemporaryDirectory

from test_docx_edit_e4 import E4, text
from test_docx_edit_e3 import source
from test_docx_edit_io import Block, ID, PP, RP, Run, package, unzip
from test_docx_edit_table_image import cell, paragraph, NESTED, SECT, xml


class E6(E4):
    def __init__(self, library):
        super().__init__(library)
        self.insert_run = self.dll.exr_edit_insert_run
        self.insert_run.restype = c.c_int
        self.insert_run.argtypes = [c.c_void_p, c.c_void_p, ID, c.c_size_t,
                                   c.c_void_p, c.c_size_t, c.POINTER(RP)]

    def insert(self, doc, pid, offset, value, props=None):
        tx = self.begin(doc)
        assert tx
        status = self.insert_run(doc, tx, pid, offset, value, len(value), props)
        assert self.commit(tx) == status
        return status


def acceptance(api, output):
    doc = api.read(source('<w:tr>' + cell('AB') + cell('side') + '</w:tr>'))
    try:
        tid, table = api.table(doc)
        assert table.count == table.columns == 2
        pid = api.cell_paragraph(doc, tid, 0, 0, 0).contents.id
        top_ids = [p.id for p in api.blocks(doc)]
        assert api.split_paragraph(doc, pid, 0, 1) == 0
        second = api.cell_paragraph(doc, tid, 0, 0, 1).contents.id
        assert api.set_run_text(doc, second, 0, b'B2', 2) == 0
        assert api.split_paragraph(doc, second, 1, 0) == 0
        third = api.cell_paragraph(doc, tid, 0, 0, 2).contents
        empty = third.id
        ids = [p.id for p in api.cell_blocks(doc, tid)]
        run_ids = [p.runs[0].id for p in api.cell_blocks(doc, tid)[:2]]
        assert api.texts(doc, tid) == ['A', 'B2', ''] and third.count == 0
        print('1 PASS Enter at end: paragraphs=3 text=A|B2|<empty>; third.run_count=0', flush=True)
        baseline = api.write(doc)
        assert api.insert(doc, empty, 0, b'X') == 0
        assert api.texts(doc, tid) == ['A', 'B2', 'X']
        assert [p.id for p in api.cell_blocks(doc, tid)] == ids
        assert [p.runs[0].id for p in api.cell_blocks(doc, tid)[:2]] == run_ids
        new_run = api.find_block(doc, empty).contents.runs[0].id
        assert new_run and new_run not in run_ids
        assert [p.id for p in api.blocks(doc)] == top_ids
        print('2 PASS insert_run(third,0,X,1,NULL)=EXR_OK; paragraphs=3 text=A|B2|X; IDs retained', flush=True)
        assert api.undo(doc) == 0 and api.write(doc) == baseline
        assert api.texts(doc, tid) == ['A', 'B2', '']
        assert api.find_block(doc, empty).contents.count == 0
        print('3 PASS undo once: paragraphs=3 text=A|B2|<empty>; third.run_count=0', flush=True)
        assert api.redo(doc) == 0
        assert api.find_block(doc, empty).contents.runs[0].id == new_run
        assert api.undo(doc) == 0
        new = ID(999)
        assert api.insert_paragraph(doc, second, None, 0, None, c.byref(new)) == 0
        assert new.value and new.value not in ids
        assert api.texts(doc, tid) == ['A', 'B2', '', '']
        assert [p.id for p in api.cell_blocks(doc, tid)] == ids[:2] + [new.value, empty]
        assert [p.runs[0].id for p in api.cell_blocks(doc, tid)[:2]] == run_ids
        assert text(api.table_cell_block_at(doc, tid, 0, 1, 0).contents) == 'side'
        assert [p.id for p in api.blocks(doc)] == top_ids
        print('4 PASS insert_paragraph(after second)=EXR_OK; paragraphs=4 text=A|B2|<empty>|<empty>; siblings retained', flush=True)
        assert api.undo(doc) == 0 and api.write(doc) == baseline
        assert api.redo(doc) == 0
        assert api.insert(doc, new.value, 0, '中'.encode()) == 0
        assert api.insert(doc, empty, 0, b'X') == 0
        path = output / 'edited-2x2.docx'
        path.write_bytes(api.write(doc))
        nodes = xml(path.read_bytes()).findall('.//{*}tbl/{*}tr/{*}tc')[0].findall('{*}p')
        assert [''.join(p.itertext()) for p in nodes] == ['A', 'B2', '中', 'X']
        reopened = api.read(path.read_bytes())
        try:
            new_tid, _ = api.table(reopened)
            assert api.texts(reopened, new_tid) == ['A', 'B2', '中', 'X']
            last = api.cell_paragraph(reopened, new_tid, 0, 0, 3).contents.id
            assert api.split_paragraph(reopened, last, 1, 0) == 0
            tail = api.cell_paragraph(reopened, new_tid, 0, 0, 4).contents.id
            assert api.insert(reopened, tail, 0, b'Y') == 0
        finally:
            api.doc_free(reopened)
    finally:
        api.doc_free(doc)


def top_level(api):
    doc = c.c_void_p()
    seed = Block()
    assert api.doc_create(None, 0, c.byref(seed), 1, None, 0, None, c.byref(doc)) == 0
    try:
        pid = api.paragraphs(doc)[0].id
        assert api.find_block(doc, pid).contents.count == 0
        before = api.write(doc)
        assert api.insert(doc, pid, 0, b'first') == 0
        assert text(api.find_block(doc, pid).contents) == 'first'
        assert api.undo(doc) == 0 and api.write(doc) == before
        assert api.redo(doc) == 0
        new = ID()
        assert api.insert_paragraph(doc, pid, None, 0, None, c.byref(new)) == 0
        assert api.insert(doc, new.value, 0, b'next') == 0
        assert [text(p) for p in api.paragraphs(doc)] == ['first', 'next']
        reopened = api.read(api.write(doc))
        try:
            assert [text(p) for p in api.paragraphs(reopened)] == ['first', 'next']
        finally:
            api.doc_free(reopened)
        print('5 PASS new document first zero-run paragraph + insert_paragraph empty: insert_run=EXR_OK; undo/redo + write/read', flush=True)
    finally:
        api.doc_free(doc)


def invalid(api):
    doc = api.read(source('<w:tr><w:tc><w:p/></w:tc>' + cell('side') + '</w:tr>'))
    other = api.read(package(body='<w:p/>' + SECT))
    try:
        tid, _ = api.table(doc)
        pid = api.cell_paragraph(doc, tid, 0, 0, 0).contents.id
        baseline = api.write(doc)
        bad_props = RP(present=128)
        cases = [(pid, 1, b'X', 1, None), (pid, c.c_size_t(-1).value, b'X', 1, None),
                 (pid, 0, b'', 0, None), (pid, 0, None, 1, None), (pid, 0, None, 0, None),
                 (0, 0, b'X', 1, None), (pid, 0, b'\xc0\x80', 2, None),
                 (pid, 0, b'\x01', 1, None), (pid, 0, b'\x00', 1, None),
                 (pid, 0, b'X', 1, c.byref(bad_props)),
                 (pid, 0, b'X', c.c_size_t(-1).value, None)]
        for args in cases:
            tx = api.begin(doc)
            assert api.insert_run(doc, tx, *args) == 1
            assert api.write(doc) == baseline
            assert api.insert_run(doc, tx, pid, 0, b'Y', 1, None) == 1
            assert api.commit(tx) == 1 and api.write(doc) == baseline
        for index in (0, 1, c.c_size_t(-1).value):
            assert api.set_run_text(doc, pid, index, b'X', 1) == 1
            assert api.write(doc) == baseline
        assert api.insert_run(None, None, pid, 0, b'X', 1, None) == 1
        assert api.insert_run(doc, None, pid, 0, b'X', 1, None) == 1
        foreign = api.begin(other)
        assert foreign
        assert api.insert_run(doc, foreign, pid, 0, b'X', 1, None) == 1
        tx = api.begin(doc)
        assert api.insert_run(doc, foreign, pid, 0, b'X', 1, None) == 1
        assert api.commit(tx) == 1
        assert api.rollback(foreign) == 0
        # A failed insertion also rolls back earlier successful commands in the tx.
        tx = api.begin(doc)
        assert api.insert_run(doc, tx, pid, 0, b'X', 1, None) == 0
        assert api.insert_run(doc, tx, pid, 2, b'Y', 1, None) == 1
        assert api.commit(tx) == 1 and api.write(doc) == baseline
        assert api.find_block(doc, pid).contents.count == 0
        print('6 PASS out-of-range/empty/NULL/invalid UTF-8/XML/props/tx=EXR_ARGUMENT; write bytes identical; set_run_text zero-run stays EXR_ARGUMENT', flush=True)
    finally:
        api.doc_free(other)
        api.doc_free(doc)


def boundaries(api):
    for strict, prefix in ((False, 'w'), (True, 'q')):
        doc = api.read(package(body='<w:tbl><w:tr><w:tc><w:p/>' + paragraph('tail')
                               + '</w:tc>' + cell('side') + '</w:tr></w:tbl>' + SECT,
                               strict=strict, prefix=prefix))
        try:
            tid, _ = api.table(doc)
            first, tail = [p.id for p in api.cell_blocks(doc, tid)]
            before = api.write(doc)
            props = RP(present=4, bold=1)
            tx = api.begin(doc)
            assert api.insert_run(doc, tx, first, 0, '字&<>'.encode(), 6, c.byref(props)) == 0
            assert api.rollback(tx) == 0 and api.write(doc) == before
            assert api.insert(doc, first, 0, b'A', c.byref(props)) == 0
            original_id = api.find_block(doc, first).contents.runs[0].id
            # Insert before, between and after runs, including aliased text/props.
            assert api.insert(doc, first, 0, b'B') == 0
            p = api.find_block(doc, first).contents
            tx = api.begin(doc)
            assert api.insert_run(doc, tx, first, 1, p.runs[1].text, p.runs[1].length,
                                  c.byref(p.runs[1].props)) == 0
            assert api.commit(tx) == 0
            assert api.insert(doc, first, 3, '字&<>'.encode()) == 0
            p = api.find_block(doc, first).contents
            assert text(p) == 'BAA字&<>' and p.count == 4
            assert p.runs[2].id == original_id and p.runs[1].props.bold == p.runs[2].props.bold == 1
            assert p.runs[0].props.present == p.runs[3].props.present == 0
            # Nonempty cell paragraph insertion accepts aliased runs and props.
            new = ID()
            assert api.insert_paragraph(doc, first, p.runs, p.count, c.byref(p.props), c.byref(new)) == 0
            assert api.texts(doc, tid) == ['BAA字&<>', 'BAA字&<>', 'tail']
            assert api.cell_paragraph(doc, tid, 0, 0, 2).contents.id == tail
            assert api.undo(doc) == 0 and api.redo(doc) == 0
            reopened = api.read(api.write(doc))
            try:
                new_tid, _ = api.table(reopened)
                assert api.texts(reopened, new_tid) == ['BAA字&<>', 'BAA字&<>', 'tail']
                p = api.cell_paragraph(reopened, new_tid, 0, 0, 0).contents
                assert p.runs[1].props.bold == p.runs[2].props.bold == 1
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
            pid = api.cell_blocks(doc, tid)[0].id
            before = api.write(doc)
            assert api.insert(doc, pid, 0, b'X') == 11
            new = ID(999)
            assert api.insert_paragraph(doc, pid, None, 0, None, c.byref(new)) == 11
            assert new.value == 0 and api.write(doc) == before
        finally:
            api.doc_free(doc)
    # Opaque top-level neighbors remain intact and keep their run IDs.
    doc = api.read(package(body=paragraph('A', '<w:bookmarkStart w:id="1" w:name="mark"/>') + SECT))
    try:
        p = api.paragraphs(doc)[0]
        pid, count = p.id, p.count
        opaque = [(r.id, c.string_at(r.xml, r.xml_size)) for r in p.runs[:count] if r.kind == 1]
        assert opaque
        assert api.insert(doc, pid, 1, b'B') == 0
        assert api.insert(doc, pid, count + 1, b'C') == 0
        p = api.find_block(doc, pid).contents
        assert [(r.id, c.string_at(r.xml, r.xml_size)) for r in p.runs[:p.count] if r.kind == 1] == opaque
        assert b'w:bookmarkStart' in unzip(api.write(doc))['word/document.xml']
    finally:
        api.doc_free(doc)
    print('extra PASS offsets/alias/props/rollback/redo/strict namespace; protected cells refused; top-level opaque neighbors retained', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    api = E6(args.library.resolve())
    with TemporaryDirectory() as temp:
        output = args.output or Path(temp)
        output.mkdir(parents=True, exist_ok=True)
        acceptance(api, output)
        top_level(api)
        invalid(api)
        print('7 PASS file write/read: paragraphs=4 text=A|B2|中|X; reopened Enter + typing succeeds', flush=True)
        boundaries(api)
