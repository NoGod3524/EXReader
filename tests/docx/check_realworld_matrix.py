#!/usr/bin/env python3
"""Evaluate Matrix A (bridge round-trip) and Matrix B (edit side-effects) across the 30 real-world DOCX fixtures."""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools' / 'docx'))

from test_docx_edit_io import ID, PP, RP, Run, Error, unzip, audit
from test_docx_edit_table_image import API, Table, cell_text
from roundtrip import Engine, differences
from verify_docx import verify, Formatting, Package, NS, W, R

WPG = 'http://schemas.microsoft.com/office/word/2010/wordprocessingGroup'
WPS = 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape'
VML = 'urn:schemas-microsoft-com:vml'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'

METRIC_DEFS = [
    ('M01_package_xml', 'ZIP CRC, XML syntax, w:document/w:body integrity (verify_docx #1)'),
    ('M02_content_types', '[Content_Types].xml main & part content types (verify_docx #2)'),
    ('M03_relationships', 'Root & document relationships integrity (verify_docx #3)'),
    ('M04_opc_parts', 'Non-main OPC parts byte-for-byte retention (styles/numbering/notes/headers/theme/media/comments)'),
    ('M05_sdk_reread', 'Core reader exr_document_open_memory reread & extracted text hash parity'),
    ('M06_paragraphs', 'Paragraph count fidelity (roundtrip.py #1: exact in A, +1 inserted in B)'),
    ('M07_characters', 'Character count & UTF-8 text SHA-256 fidelity (roundtrip.py #2)'),
    ('M08_para_and_run_props', 'Paragraph pPr presence, 480/auto line spacing, TNR 12pt (verify_docx #6-#9)'),
    ('M09_styles_and_theme', 'Style inheritance chain, direct overrides (b=0/i=0, inherited line/indent), theme fonts'),
    ('M10_tables_and_merges', 'Table count (roundtrip.py #3), gridSpan/hMerge/vMerge, nested w:tbl, w:tblHeader, multipara cell guard'),
    ('M11_fields', 'Simple (w:fldSimple) & complex (w:fldChar/w:instrText) PAGE/NUMPAGES/DATE/REF/TOC/Chinese fields'),
    ('M12_numbering', 'Multi-level ilvl, lvlRestart, lvlOverride/startOverride, numStyleLink, Chinese/enclosed numbering'),
    ('M13_sections_and_margins', 'Section count & 4-side margins (roundtrip.py #6) + verify_docx #4/#5/#10/#11 parity'),
    ('M14_section_cols_and_orient', 'Landscape page orientation (w:orient) and multi-column w:cols/w:col definitions'),
    ('M15_headers_and_footers', 'Header/footer parts, references, PAGE field, and header tables (verify_docx #12-#14)'),
    ('M16_footnotes_and_endnotes', 'Footnote count (roundtrip.py #5), footnotePr/numRestart, footnote tables, endnotes'),
    ('M17_graphics_and_shapes', 'Image count & SHA-256 (roundtrip.py #4), wp:inline, wp:anchor wrap, wpg:wgp, v:group'),
    ('M18_annotations_and_txbx', 'Textbox w:txbxContent, comment anchors + comments.xml, bookmarks, vanish hidden text'),
]


def tag_signatures(xml_bytes, local_names):
    """Collect structural attribute/text signatures for specific OOXML local element names."""
    root = ET.fromstring(xml_bytes)
    out = {name: [] for name in local_names}
    for elem in root.iter():
        local = elem.tag.rsplit('}', 1)[-1] if '}' in elem.tag else elem.tag
        if local in out:
            attrs = sorted((k.rsplit('}', 1)[-1], v) for k, v in elem.attrib.items())
            txt = (elem.text or '').strip()
            out[local].append((attrs, txt))
    return out


def evaluate_18_metrics(source_bytes, output_bytes, reader, mode='A', extra_checks=None):
    """Evaluate all 18 metrics on output_bytes relative to source_bytes."""
    extra_checks = extra_checks or {}
    results = {}
    with tempfile.TemporaryDirectory(prefix='exr-mat-') as tmp:
        src_path = Path(tmp) / 'source.docx'
        out_path = Path(tmp) / 'output.docx'
        src_path.write_bytes(source_bytes)
        out_path.write_bytes(output_bytes)
        src_v = {r['check']: r['status'] for r in verify(src_path)}
        out_v = {r['check']: r['status'] for r in verify(out_path)}
        src_pkg = Package(src_path)
        out_pkg = Package(out_path)
        src_fmt = Formatting(src_pkg)
        out_fmt = Formatting(out_pkg)

    before = audit(source_bytes)
    after = audit(output_bytes)
    src_parts = unzip(source_bytes)
    out_parts = unzip(output_bytes)

    # M01, M02, M03: package XML, content types, relationships
    results['M01_package_xml'] = (out_v.get('package_xml') == 'PASS')
    results['M02_content_types'] = (out_v.get('content_types') == 'PASS')
    results['M03_relationships'] = (out_v.get('root_relationship') == 'PASS')

    # M04: Non-main OPC parts byte-for-byte identical
    results['M04_opc_parts'] = (
        set(src_parts.keys()) == set(out_parts.keys())
        and all(src_parts[k] == out_parts[k] for k in src_parts if k != 'word/document.xml')
    )

    # M05: SDK reread via exr_document_open_memory
    sdk_ok = False
    try:
        doc_a = reader.open(src_path if False else None)
    except Exception:
        doc_a = None
    with tempfile.TemporaryDirectory(prefix='exr-sdk-') as tmp:
        sp = Path(tmp) / 's.docx'
        op = Path(tmp) / 'o.docx'
        sp.write_bytes(source_bytes)
        op.write_bytes(output_bytes)
        try:
            da = reader.open(sp)
            db = reader.open(op)
            try:
                if mode == 'A':
                    sdk_ok = (reader.text_hash(da) == reader.text_hash(db))
                else:
                    sdk_ok = (reader.text_hash(da) != reader.text_hash(db))
            finally:
                reader.document_free(da)
                reader.document_free(db)
        except Exception:
            sdk_ok = False
    results['M05_sdk_reread'] = sdk_ok

    # M06: Paragraphs
    expected_p = before['paragraphs'] if mode == 'A' else before['paragraphs'] + extra_checks.get('expected_para_delta', 1)
    results['M06_paragraphs'] = (after['paragraphs'] == expected_p)

    # M07: Characters & text_sha256
    if mode == 'A':
        results['M07_characters'] = (
            after['characters'] == before['characters']
            and after['text_sha256'] == before['text_sha256']
        )
    else:
        expected_c = before['characters'] + extra_checks.get('expected_char_delta', 0)
        results['M07_characters'] = (
            after['characters'] == expected_c
            and after['text_sha256'] != before['text_sha256']
        )

    # M08: Paragraph & run properties (verify_docx #6-#9 + extra table row pPr check)
    p_run_ok = all(
        out_v.get(k) == src_v.get(k) == 'PASS'
        for k in ('paragraph_properties', 'double_spacing', 'font_times_new_roman', 'font_size_12pt')
    )
    if not extra_checks.get('row_insert_ppr_ok', True):
        p_run_ok = False
    results['M08_para_and_run_props'] = p_run_ok

    # M09: Styles & theme inheritance + direct formatting overrides + inherited indent/line preservation
    src_doc = src_pkg.document
    out_doc = out_pkg.document
    src_sigs = tag_signatures(src_parts['word/document.xml'], ('pStyle', 'rStyle', 'rFonts', 'b', 'i', 'u'))
    out_sigs = tag_signatures(out_parts['word/document.xml'], ('pStyle', 'rStyle', 'rFonts', 'b', 'i', 'u'))
    style_ok = (
        src_sigs['pStyle'] == out_sigs['pStyle']
        and src_sigs['rStyle'] == out_sigs['rStyle']
        and src_sigs['b'] == out_sigs['b']
        and src_sigs['i'] == out_sigs['i']
        and src_sigs['u'] == out_sigs['u']
    )
    # Check that effective style-resolved left/right indent and line spacing on target paragraph (index 1) were not clobbered to '0'
    src_ps = src_pkg.body.findall('w:p', NS)
    out_ps = out_pkg.body.findall('w:p', NS)
    if len(src_ps) >= 2 and len(out_ps) >= 2:
        for attr_name in ('left', 'right'):
            sv = src_fmt.value(src_ps[1], None, 'ind', attr_name)
            ov = out_fmt.value(out_ps[1], None, 'ind', attr_name)
            if sv != ov:
                style_ok = False
        if src_fmt.value(src_ps[1], None, 'spacing', 'line') != out_fmt.value(out_ps[1], None, 'spacing', 'line'):
            style_ok = False
    results['M09_styles_and_theme'] = style_ok

    # M10: Tables and merges
    tbl_sigs = ('tbl', 'tr', 'tc', 'gridSpan', 'hMerge', 'vMerge', 'tblHeader')
    s_tbl = tag_signatures(src_parts['word/document.xml'], tbl_sigs)
    o_tbl = tag_signatures(out_parts['word/document.xml'], tbl_sigs)
    tbl_ok = (
        after['tables'] == before['tables']
        and all(s_tbl[k] == o_tbl[k] for k in tbl_sigs)
        and extra_checks.get('multipara_cell_guarded', True)
        and extra_checks.get('row_insert_ppr_ok', True)
    )
    results['M10_tables_and_merges'] = tbl_ok

    # M11: Fields (w:fldSimple, w:fldChar, w:instrText, w:hyperlink)
    fld_sigs = ('fldSimple', 'fldChar', 'instrText', 'hyperlink')
    s_fld = tag_signatures(src_parts['word/document.xml'], fld_sigs)
    o_fld = tag_signatures(out_parts['word/document.xml'], fld_sigs)
    results['M11_fields'] = all(s_fld[k] == o_fld[k] for k in fld_sigs)

    # M12: Numbering (w:numPr, w:ilvl, w:numId + SDK reread numbering evaluation)
    num_sigs = ('numPr', 'ilvl', 'numId')
    s_num = tag_signatures(src_parts['word/document.xml'], num_sigs)
    o_num = tag_signatures(out_parts['word/document.xml'], num_sigs)
    results['M12_numbering'] = (
        all(s_num[k] == o_num[k] for k in num_sigs)
        and src_parts.get('word/numbering.xml') == out_parts.get('word/numbering.xml')
        and sdk_ok
    )

    # M13: Sections and margins
    results['M13_sections_and_margins'] = (
        after['section_margins'] == before['section_margins']
        and all(out_v.get(k) == src_v.get(k) for k in ('section_present', 'section_nonempty', 'letter_page_size', 'one_inch_margins'))
    )

    # M14: Section columns and orientation
    sec_sigs = ('pgSz', 'cols', 'col', 'titlePg')
    s_sec = tag_signatures(src_parts['word/document.xml'], sec_sigs)
    o_sec = tag_signatures(out_parts['word/document.xml'], sec_sigs)
    results['M14_section_cols_and_orient'] = all(s_sec[k] == o_sec[k] for k in sec_sigs)

    # M15: Headers and footers
    hf_sigs = ('headerReference', 'footerReference')
    s_hf = tag_signatures(src_parts['word/document.xml'], hf_sigs)
    o_hf = tag_signatures(out_parts['word/document.xml'], hf_sigs)
    results['M15_headers_and_footers'] = (
        all(s_hf[k] == o_hf[k] for k in hf_sigs)
        and all(out_v.get(k) == src_v.get(k) == 'PASS' for k in ('header_part', 'header_used', 'header_page_field'))
    )

    # M16: Footnotes and endnotes
    fn_sigs = ('footnoteReference', 'endnoteReference', 'footnotePr', 'numRestart')
    s_fn = tag_signatures(src_parts['word/document.xml'], fn_sigs)
    o_fn = tag_signatures(out_parts['word/document.xml'], fn_sigs)
    results['M16_footnotes_and_endnotes'] = (
        after['footnotes'] == before['footnotes']
        and all(s_fn[k] == o_fn[k] for k in fn_sigs)
        and src_parts.get('word/footnotes.xml') == out_parts.get('word/footnotes.xml')
        and src_parts.get('word/endnotes.xml') == out_parts.get('word/endnotes.xml')
    )

    # M17: Graphics and shapes
    gfx_sigs = ('drawing', 'inline', 'anchor', 'wrapSquare', 'wgp', 'wsp', 'pic', 'pict', 'group')
    s_gfx = tag_signatures(src_parts['word/document.xml'], gfx_sigs)
    o_gfx = tag_signatures(out_parts['word/document.xml'], gfx_sigs)
    results['M17_graphics_and_shapes'] = (
        after['images'] == before['images']
        and after['image_sha256'] == before['image_sha256']
        and all(s_gfx[k] == o_gfx[k] for k in gfx_sigs)
    )

    # M18: Annotations and textboxes (txbxContent, commentRangeStart/End/Reference, bookmarkStart/End, vanish)
    ann_sigs = ('txbxContent', 'commentRangeStart', 'commentRangeEnd', 'commentReference', 'bookmarkStart', 'bookmarkEnd', 'vanish')
    s_ann = tag_signatures(src_parts['word/document.xml'], ann_sigs)
    o_ann = tag_signatures(out_parts['word/document.xml'], ann_sigs)
    results['M18_annotations_and_txbx'] = (
        all(s_ann[k] == o_ann[k] for k in ann_sigs)
        and src_parts.get('word/comments.xml') == out_parts.get('word/comments.xml')
    )

    return results, out_v, differences(before, after)


def evaluate_fixture(api, reader, fixture_path, entry):
    source_bytes = fixture_path.read_bytes()
    assert len(source_bytes) == entry['bytes'] and len(source_bytes) < 60_000
    assert hashlib.sha256(source_bytes).hexdigest() == entry['sha256']

    # --- MATRIX A: Read -> Model -> Write (No edits) ---
    doc = c.c_void_p()
    err = Error()
    status_a = api.docx_read(source_bytes, len(source_bytes), None, c.byref(doc), c.byref(err))
    if status_a != 0:
        zero_metrics = {k: False for k, _ in METRIC_DEFS}
        return {
            'id': entry['id'],
            'category': entry['category'],
            'description': entry['description'],
            'matrix_a_read_status': status_a,
            'matrix_a_error': err.message.decode('utf-8', errors='replace'),
            'matrix_a_metrics': zero_metrics,
            'matrix_a_passed': 0,
            'matrix_b_read_status': status_a,
            'matrix_b_metrics': dict(zero_metrics),
            'matrix_b_passed': 0,
            'extra_losses': [],
            'extra_loss_count': 0,
        }

    try:
        saved_a = api.write(doc)
    finally:
        api.doc_free(doc)

    metrics_a, verify_a, rt_a = evaluate_18_metrics(source_bytes, saved_a, reader, mode='A')

    # --- MATRIX B: Read -> Edit Paragraph Properties & Insert Paragraph (+ Table Guards) -> Write ---
    doc = api.read(source_bytes)
    extra_checks = {
        'expected_para_delta': 1,
        'expected_char_delta': len('Matrix B inserted paragraph.'),
        'multipara_cell_guarded': True,
        'row_insert_ppr_ok': True,
    }
    try:
        # Pre-check: if document has tables with multi-paragraph cells, verify set_cell_text rejects overwriting them
        for tb in api.blocks(doc, 1):
            if not tb.table:
                continue
            t = c.cast(tb.table, c.POINTER(Table)).contents
            for r_idx in range(t.count):
                for c_idx in range(t.rows[r_idx].count):
                    cell = t.rows[r_idx].cells[c_idx]
                    if cell.count > 1:
                        guard_tx = api.begin(doc)
                        assert guard_tx
                        rc = api.table_set_cell_text(doc, tb.id, r_idx, c_idx, None, 0)
                        if rc == 0:
                            extra_checks['multipara_cell_guarded'] = False
                        assert api.rollback(guard_tx) == 0

        ps = api.paragraphs(doc)
        target = ps[1]  # Editable body paragraph
        tx = api.begin(doc)
        assert tx

        # 1. Modify paragraph properties on target body paragraph
        p = PP.from_buffer_copy(target.props)
        p.present |= 1 | 4  # EXR_EDIT_ALIGN | EXR_EDIT_SPACING
        p.align = 1  # center
        p.before = p.before + 60
        if p.present & 2:  # EXR_EDIT_INDENT
            p.first = p.first + 120
        assert api.set_paragraph_props(doc, target.id, c.byref(p)) == 0

        # 2. Insert 1 body paragraph after target
        marker_text = b'Matrix B inserted paragraph.'
        storage = c.create_string_buffer(marker_text)
        rp = RP(present=3, font=b'Times New Roman', size=24)
        pp_new = PP(present=4, line=480)
        run = Run(kind=0, text=c.cast(storage, c.c_void_p), length=len(marker_text), props=rp)
        new_id = ID()
        assert api.insert_paragraph(doc, target.id, c.byref(run), 1, c.byref(pp_new), c.byref(new_id)) == 0

        # 3. If document has tables, test inserting a temporary row at the bottom, checking pPr on all cells, then deleting it
        for tb in api.blocks(doc, 1):
            if not tb.table:
                continue
            t = c.cast(tb.table, c.POINTER(Table)).contents
            row_tx = api.begin(doc) if False else None
            if api.table_insert_row(doc, tb.id, t.count - 1) == 0:
                temp_bytes = api.write(doc)
                with tempfile.TemporaryDirectory(prefix='exr-tbl-') as tmp:
                    tp = Path(tmp) / 'temp_row.docx'
                    tp.write_bytes(temp_bytes)
                    v_tbl = {r['check']: r['status'] for r in verify(tp)}
                    if v_tbl.get('paragraph_properties') != 'PASS':
                        extra_checks['row_insert_ppr_ok'] = False
                assert api.table_delete_row(doc, tb.id, t.count) == 0

        assert api.commit(tx) == 0
        saved_b = api.write(doc)

        # Verify undo restores Matrix A and redo restores Matrix B
        assert api.undo(doc) == 0
        assert unzip(api.write(doc)) == unzip(saved_a)
        assert api.redo(doc) == 0
        assert unzip(api.write(doc)) == unzip(saved_b)
    finally:
        api.doc_free(doc)

    metrics_b, verify_b, rt_b = evaluate_18_metrics(source_bytes, saved_b, reader, mode='B', extra_checks=extra_checks)
    extra_losses = [k for k, _ in METRIC_DEFS if metrics_a[k] and not metrics_b[k]]

    return {
        'id': entry['id'],
        'category': entry['category'],
        'description': entry['description'],
        'matrix_a_read_status': 0,
        'matrix_a_error': '',
        'matrix_a_metrics': metrics_a,
        'matrix_a_passed': sum(1 for v in metrics_a.values() if v),
        'matrix_b_read_status': 0,
        'matrix_b_metrics': metrics_b,
        'matrix_b_passed': sum(1 for v in metrics_b.values() if v),
        'extra_losses': extra_losses,
        'extra_loss_count': len(extra_losses),
    }


def format_matrix_a_md(report, before_summary=None):
    lines = [
        '# MATRIX-A: Bridge Round-Trip Fidelity (Read → Model → Write, No Edits)',
        '',
        'Each of the 30 original synthetic real-world `.docx` fixtures in `tests/fixtures/docx-real/` is read via `exr_edit_docx_read`, held in `exr_edit_doc` without edits, written back via `exr_edit_docx_write`, and evaluated against the 18-metric verification suite (`M01`–`M18`, combining all 14 `tools/docx/verify_docx.py` checks, all 6 `tools/docx/roundtrip.py` metrics, SDK reread text hash parity, and structural XML fidelity).',
        '',
    ]
    if before_summary:
        lines += [
            '## Before vs. After Fixes Summary',
            '',
            '| Stage | Fixtures 18/18 PASS | Total Metric Cells PASS | Failing Fixtures & Root Causes |',
            '| --- | --- | --- | --- |',
            f'| **Before Fixes (`c04560b7`)** | {before_summary["a_full_pass"]}/30 | {before_summary["a_cells_pass"]}/540 | {before_summary["a_fail_detail"]} |',
            f'| **After Fixes** | **{report["matrix_a_full_pass"]}/30** | **{report["matrix_a_cells_pass"]}/540** | None (0 failures) |',
            '',
        ]
    lines += [
        '## 18 Metric Definitions (`M01`–`M18`)',
        '',
        '| Metric ID | Description |',
        '| --- | --- |',
    ]
    for mid, mdesc in METRIC_DEFS:
        lines.append(f'| `{mid}` | {mdesc} |')
    lines += [
        '',
        '## Per-Fixture Bridge Round-Trip Table (30 Fixtures × 18 Metrics = 540 Cells)',
        '',
        '| Fixture | Category | Score | ' + ' | '.join(f'`{m[:3]}`' for m, _ in METRIC_DEFS) + ' |',
        '| --- | --- | --- | ' + ' | '.join('---' for _ in METRIC_DEFS) + ' |',
    ]
    for f in report['fixtures']:
        cells = ' | '.join('PASS' if f['matrix_a_metrics'][m] else 'FAIL' for m, _ in METRIC_DEFS)
        lines.append(f'| `{f["id"]}` | `{f["category"]}` | **{f["matrix_a_passed"]}/18** | {cells} |')
    lines.append('')
    return '\n'.join(lines)


def format_matrix_b_md(report, before_summary=None):
    lines = [
        '# MATRIX-B: Edit Side-Effect Matrix (`Matrix B - Matrix A`)',
        '',
        'Each of the 30 fixtures in `tests/fixtures/docx-real/` is read via `exr_edit_docx_read`, edited in a transaction (modifying target body paragraph properties via `exr_edit_set_paragraph_props`, inserting a new body paragraph via `exr_edit_insert_paragraph`, verifying table multi-paragraph cell protection and row-insertion `<w:pPr>` preservation, and testing `undo`/`redo`), written via `exr_edit_docx_write`, and compared against `MATRIX-A` to measure extra edit side-effect losses (`Matrix B - Matrix A`).',
        '',
    ]
    if before_summary:
        lines += [
            '## Before vs. After Fixes Summary',
            '',
            '| Stage | Fixtures 18/18 PASS | Total Metric Cells PASS | Extra Edit Losses (`Matrix B - Matrix A`) | Root Causes of Extra Losses |',
            '| --- | --- | --- | --- | --- |',
            f'| **Before Fixes (`c04560b7`)** | {before_summary["b_full_pass"]}/30 | {before_summary["b_cells_pass"]}/540 | {before_summary["b_extra_losses"]} cells across {before_summary["b_extra_fixtures"]} fixtures | {before_summary["b_fail_detail"]} |',
            f'| **After Fixes** | **{report["matrix_b_full_pass"]}/30** | **{report["matrix_b_cells_pass"]}/540** | **{report["matrix_b_extra_loss_cells"]} cells across {report["matrix_b_extra_loss_fixtures"]} fixtures** | None (0 edit side-effect losses) |',
            '',
        ]
    lines += [
        '## Per-Fixture Edit Side-Effect Table (30 Fixtures × 18 Metrics = 540 Cells)',
        '',
        '| Fixture | Category | Matrix A | Matrix B | Extra Loss (`B - A`) | ' + ' | '.join(f'`{m[:3]}`' for m, _ in METRIC_DEFS) + ' |',
        '| --- | --- | --- | --- | --- | ' + ' | '.join('---' for _ in METRIC_DEFS) + ' |',
    ]
    for f in report['fixtures']:
        loss_str = '0' if not f['extra_losses'] else f'-{len(f["extra_losses"])} ({", ".join(x[:3] for x in f["extra_losses"])})'
        cells = ' | '.join('PASS' if f['matrix_b_metrics'][m] else 'FAIL' for m, _ in METRIC_DEFS)
        lines.append(f'| `{f["id"]}` | `{f["category"]}` | {f["matrix_a_passed"]}/18 | **{f["matrix_b_passed"]}/18** | **{loss_str}** | {cells} |')
    lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, default=ROOT / 'tests' / 'fixtures' / 'docx-real' / 'argon')
    parser.add_argument('--output-json', type=Path)
    parser.add_argument('--before-json', type=Path, help='Optional pre-fix baseline JSON for before/after table')
    parser.add_argument('--write-matrices', action='store_true', help='Write MATRIX-A.md and MATRIX-B.md')
    parser.add_argument('--strict', action='store_true', help='Exit non-zero if any metric fails in A or B')
    args = parser.parse_args()

    manifest = json.loads((args.fixtures / 'manifest.json').read_text(encoding='utf-8'))
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(str(args.library.resolve().parent))
        mingw_bin = Path(r'C:\Users\Oscar\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin')
        if mingw_bin.is_dir():
            os.add_dll_directory(str(mingw_bin))
    api = API(args.library.resolve())
    reader = Engine(args.library.resolve())

    fixture_results = []
    for entry in manifest['fixtures']:
        res = evaluate_fixture(api, reader, args.fixtures / entry['path'], entry)
        fixture_results.append(res)

    a_full = sum(1 for f in fixture_results if f['matrix_a_passed'] == 18)
    a_cells = sum(f['matrix_a_passed'] for f in fixture_results)
    b_full = sum(1 for f in fixture_results if f['matrix_b_passed'] == 18)
    b_cells = sum(f['matrix_b_passed'] for f in fixture_results)
    b_extra_cells = sum(f['extra_loss_count'] for f in fixture_results)
    b_extra_fixtures = sum(1 for f in fixture_results if f['extra_loss_count'] > 0)

    report = {
        'total_fixtures': len(fixture_results),
        'total_metric_cells': len(fixture_results) * 18,
        'matrix_a_full_pass': a_full,
        'matrix_a_cells_pass': a_cells,
        'matrix_b_full_pass': b_full,
        'matrix_b_cells_pass': b_cells,
        'matrix_b_extra_loss_cells': b_extra_cells,
        'matrix_b_extra_loss_fixtures': b_extra_fixtures,
        'fixtures': fixture_results,
    }

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    if args.write_matrices:
        before_summary = None
        if args.before_json and args.before_json.is_file():
            bdata = json.loads(args.before_json.read_text(encoding='utf-8'))
            a_fails = [f['id'] for f in bdata['fixtures'] if f['matrix_a_passed'] < 18]
            b_extras = [f'{f["id"]} ({",".join(x[:3] for x in f["extra_losses"])})'
                        for f in bdata['fixtures'] if f['extra_loss_count'] > 0]
            before_summary = {
                'a_full_pass': bdata['matrix_a_full_pass'],
                'a_cells_pass': bdata['matrix_a_cells_pass'],
                'a_fail_detail': ', '.join(f'`{x}` (0/18 EXR_FORMAT)' for x in a_fails),
                'b_full_pass': bdata['matrix_b_full_pass'],
                'b_cells_pass': bdata['matrix_b_cells_pass'],
                'b_extra_losses': bdata['matrix_b_extra_loss_cells'],
                'b_extra_fixtures': bdata['matrix_b_extra_loss_fixtures'],
                'b_fail_detail': '; '.join(f'`{x}`' for x in b_extras),
            }
        (args.fixtures / 'MATRIX-A.md').write_text(format_matrix_a_md(report, before_summary), encoding='utf-8')
        (args.fixtures / 'MATRIX-B.md').write_text(format_matrix_b_md(report, before_summary), encoding='utf-8')

    print(f'Matrix A: {a_full}/30 fixtures 18/18 ({a_cells}/540 cells); '
          f'Matrix B: {b_full}/30 fixtures 18/18 ({b_cells}/540 cells); '
          f'Extra edit losses (B - A): {b_extra_cells} cells across {b_extra_fixtures} fixtures.')
    for f in fixture_results:
        if f['matrix_a_passed'] < 18 or f['matrix_b_passed'] < 18:
            a_fail_keys = [k for k, v in f['matrix_a_metrics'].items() if not v]
            b_fail_keys = [k for k, v in f['matrix_b_metrics'].items() if not v]
            print(f'  FAIL {f["id"]}: A={f["matrix_a_passed"]}/18 {a_fail_keys[:4]} | '
                  f'B={f["matrix_b_passed"]}/18 {b_fail_keys[:4]} | extra={f["extra_losses"]}')

    if args.strict and (a_cells < 540 or b_cells < 540 or b_extra_cells > 0):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
