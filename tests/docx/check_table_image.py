#!/usr/bin/env python3
"""Edit tables in #117's three hash-pinned real inputs; retain all 18 metrics."""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_docx_edit_table_image import API, Table, cell_text, shape, same_parts, unzip, audit
from roundtrip import differences

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    api = API(args.library.resolve())
    report = dict(library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(), documents=[])
    for entry in json.loads(args.manifest.read_text(encoding='utf-8-sig'))['documents']:
        source = (args.manifest.parent / entry['path']).resolve().read_bytes()
        assert hashlib.sha256(source).hexdigest() == entry['sha256']
        doc = api.read(source)
        try:
            baseline = api.write(doc)
            candidates = []
            for index, block in enumerate(api.blocks(doc, 1)):
                if not block.table:
                    continue
                t = c.cast(block.table, c.POINTER(Table)).contents
                for row in range(t.count):
                    for col in range(t.rows[row].count):
                        cell = t.rows[row].cells[col]
                        if not cell.unsupported and cell.count == 1 and cell_text(t, row, col):
                            candidates.append((block.id, index, row, col, t.count, t.columns, cell_text(t, row, col)))
            if candidates:
                tid, index, row, col, rows, columns, text = candidates[0]
            else:
                # The Minitab source shades every cell. Its original cells stay
                # protected; edit a new row, delete it, and persist a width edit.
                block = next(b for b in api.blocks(doc, 1) if b.table)
                t = c.cast(block.table, c.POINTER(Table)).contents
                tid, index, row, col, rows, columns, text = block.id, 0, t.count, 0, t.count, t.columns, ''
                original_width = t.width
            tx = api.begin(doc)
            assert tx and api.table_insert_row(doc, tid, rows - 1) == 0
            added = api.write(doc)
            reopened = api.read(added)
            try:
                t = c.cast(api.blocks(reopened, 1)[index].table, c.POINTER(Table)).contents
                assert t.count == rows + 1 and t.columns == columns
            finally:
                api.doc_free(reopened)
            # Same code-point length keeps #117's character metric comparable;
            # the independent text hash must change to prove the edit persisted.
            replacement = (('Z' if text[0] != 'Z' else 'Y') + text[1:]) if text else 'X6 temporary row'
            api.text(doc, tid, row, col, replacement)
            assert api.table_delete_row(doc, tid, rows) == 0
            if not candidates:
                assert api.table_set_width(doc, tid, original_width + 20) == 0
            assert api.commit(tx) == 0
            saved = api.write(doc)
            reopened = api.read(saved)
            try:
                t = c.cast(api.blocks(reopened, 1)[index].table, c.POINTER(Table)).contents
                assert t.count == rows and t.columns == columns
                if candidates:
                    assert cell_text(t, row, col) == replacement
                else:
                    assert t.width == original_width + 20
                assert audit(api.write(reopened)) == audit(saved)
            finally:
                api.doc_free(reopened)
            assert shape(source) == shape(saved)
            same_parts(source, baseline)
            same_parts(source, saved)
            before, plain, edited = audit(source), audit(baseline), audit(saved)
            unchanged_rows, edited_rows = differences(before, plain), differences(before, edited)
            assert all(r['status'] == 'PASS' for r in unchanged_rows + edited_rows)
            assert before['image_sha256'] == edited['image_sha256']
            assert (before['text_sha256'] != edited['text_sha256']) == bool(candidates)
            assert unzip(baseline)['word/document.xml'] != unzip(saved)['word/document.xml']
            assert api.undo(doc) == 0 and unzip(api.write(doc)) == unzip(baseline)
            assert api.redo(doc) == 0 and unzip(api.write(doc)) == unzip(saved)
            for suffix, data in [('baseline', baseline), ('edited', saved)]:
                (args.output / (entry['id'] + '-' + suffix + '.docx')).write_bytes(data)
            record = dict(id=entry['id'], source_sha256=entry['sha256'],
                          edited_sha256=hashlib.sha256(saved).hexdigest(), status='PASS',
                          selected_table=index, selected_cell=[row, col],
                          row_counts=[rows, rows + 1, rows], columns=columns,
                          unchanged_metrics=unchanged_rows, edited_metrics=edited_rows,
                          media_bytes_unchanged=True, non_main_parts_unchanged=len(unzip(source)) - 1,
                          persistent_edit='cell text' if candidates else 'table width; temporary row cell edited before deletion',
                          original_cells_protected_or_empty=not candidates,
                          text_change_verified=bool(candidates), reopen_and_undo_redo=True)
            report['documents'].append(record)
            print(entry['id'], 'baseline 6/6; edited 6/6; reopen + undo/redo PASS', flush=True)
        finally:
            api.doc_free(doc)
    report['baseline_passed'] = sum(r['status'] == 'PASS' for d in report['documents'] for r in d['unchanged_metrics'])
    report['edited_passed'] = sum(r['status'] == 'PASS' for d in report['documents'] for r in d['edited_metrics'])
    report['metric_total'] = len(report['documents']) * 6
    assert report['metric_total'] == 18 and report['baseline_passed'] == report['edited_passed'] == 18
    (args.output / 'real-corpus.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    main()
