#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independent 18-metric oracle and separate no-op/edit matrices; never calls export_text."""
import argparse
import ctypes as c
import difflib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'tests'))
# Reuse the established ABI declarations, not the product's XML decoder.
from test_docx_edit_io import Bridge, Block, Run, Part, Section, PP, RP, ID, unzip
import generate

# Load #117 by file name so the independent metric implementation is explicit.
sys.path.insert(0, str(ROOT / 'tools/docx'))
spec = importlib.util.spec_from_file_location('original_117', ROOT / 'tools/docx/roundtrip.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)

METRICS = original.METRICS + ('text_sha256', 'image_sha256', 'opc_parts', 'relationships',
    'tables_xml', 'fields_xml', 'numbering_styles_theme', 'sections_xml', 'notes_xml',
    'drawings_xml', 'annotations_xml', 'main_xml')
assert len(METRICS) == 18


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def parse(data):
    return ET.fromstring(data, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))


def tree(n):
    tag = '#comment' if n.tag is ET.Comment else '#pi' if n.tag is ET.ProcessingInstruction else n.tag
    return [tag, sorted(n.attrib.items()), n.text or '', n.tail or '', [tree(child) for child in n]]


def measure(path):
    # Exactly the unmodified #117 six metrics and its two content hashes.
    result = original.metrics(path)
    parts = unzip(Path(path).read_bytes())
    roots = {name: parse(data) for name, data in parts.items() if name.endswith('.xml') or name.endswith('.rels')}
    main = roots['word/document.xml']
    def selected(tags):
        tags = {('{' + generate.NS[prefix] + '}' + name) for prefix, name in tags}
        return digest([(name, tree(n)) for name, root in sorted(roots.items()) for n in root.iter() if n.tag in tags])
    result.update(
        opc_parts={name: digest(data) for name, data in sorted(parts.items()) if name != 'word/document.xml'},
        relationships={name: digest(tree(root)) for name, root in sorted(roots.items()) if name.endswith('.rels')},
        tables_xml=selected([('w', 'tbl')]),
        fields_xml=selected([('w', 'fldSimple'), ('w', 'instrText'), ('w', 'fldChar')]),
        numbering_styles_theme={name: digest(data) for name, data in sorted(parts.items()) if name in
            ('word/numbering.xml', 'word/styles.xml', 'word/theme/theme1.xml', 'word/settings.xml')},
        sections_xml=selected([('w', 'sectPr')]),
        notes_xml={name: digest(data) for name, data in sorted(parts.items()) if name in ('word/footnotes.xml', 'word/endnotes.xml')},
        drawings_xml=selected([('w', 'drawing'), ('w', 'pict'), ('mc', 'AlternateContent')]),
        annotations_xml=selected([('w', 'commentRangeStart'), ('w', 'commentRangeEnd'), ('w', 'commentReference'),
            ('w', 'bookmarkStart'), ('w', 'bookmarkEnd'), ('w', 'vanish'), ('w', 'webHidden')]),
        main_xml=digest(tree(main)))
    assert set(result) == set(METRICS)
    return result


def flat(n, path=''):
    item = tree(n)
    path += '/' + str(item[0])
    result = {path: item[:4]}
    for i, child in enumerate(n):
        result.update(flat(child, path + f'[{i}]'))
    return result


def main_changes(expected, actual):
    a, b = flat(parse(expected)), flat(parse(actual))
    return [dict(path=p, expected=a.get(p), actual=b.get(p)) for p in sorted(a.keys() | b.keys()) if a.get(p) != b.get(p)]


def expected_parts(source, edited):
    parts = unzip(source)
    if edited:
        before, after = generate.MARKER.encode(), generate.escape(generate.REPLACEMENT).encode()
        assert parts['word/document.xml'].count(before) == 1
        parts['word/document.xml'] = parts['word/document.xml'].replace(before, after)
    return parts


class RealBridge(Bridge):
    def __init__(self, library):
        super().__init__(library)
        self.set_text = getattr(self.dll, 'exr_edit_set_run_text', None)
        if self.set_text:
            self.set_text.restype = c.c_int
            self.set_text.argtypes = [c.c_void_p, ID, c.c_size_t, c.c_void_p, c.c_size_t]

    def target(self, doc):
        found = []
        for block in self.paragraphs(doc):
            for i, run in enumerate(block.runs[:block.count]):
                if run.kind == 0 and c.string_at(run.text, run.length).decode() == generate.MARKER:
                    found.append((block, i))
        assert len(found) == 1, 'one editable body-text target required'
        return found[0]

    def change(self, doc, legacy_snapshot=False):
        block, index = self.target(doc)
        storage = c.create_string_buffer(generate.REPLACEMENT.encode())
        if not legacy_snapshot:
            assert self.set_text, 'public exr_edit_set_run_text is missing'
            assert self.set_text(doc, block.id, index, storage, len(storage.value)) == 0
            return doc, 'public exr_edit_set_run_text'
        # The original bridge has no text command. A deep-copied seeded snapshot
        # expresses exactly the same one-run change, retaining IDs, XML and parts.
        blocks = (Block * self.block_count(doc))(*(self.block_at(doc, i).contents for i in range(self.block_count(doc))))
        runs = (Run * block.count)(*block.runs[:block.count])
        runs[index].text, runs[index].length = c.cast(storage, c.c_void_p), len(storage.value)
        for b in blocks:
            if b.id == block.id:
                b.runs = runs
        ns, np, out = c.c_size_t(), c.c_size_t(), c.c_void_p()
        sections, parts = self.sections(doc, c.byref(ns)), self.parts(doc, c.byref(np))
        assert self.doc_create(sections, ns.value, blocks, len(blocks), parts, np.value, None, c.byref(out)) == 0
        self.doc_free(doc)
        return out, 'legacy public seed snapshot (no text command in #125)'


def validate_fixture(item):
    path = HERE / item['path']
    data = path.read_bytes()
    assert digest(data) == item['sha256'] and len(data) == item['bytes'] and len(data) < 60*1024
    parts = unzip(data)
    roots = {name: parse(value) for name, value in parts.items() if name.endswith('.xml') or name.endswith('.rels')}
    main = roots['word/document.xml']
    assert main.findall(item['feature'], generate.NS), (item['id'], item['feature'])
    assert main.findall('.//w:tbl', generate.NS) and main.findall('.//wp:inline', generate.NS)
    assert sum((n.text or '') == generate.MARKER for n in main.iter('{' + generate.W + '}t')) == 1
    assert len(main.findall('.//w:p', generate.NS)) >= 12
    # Package references are resolved independently, including header/footer and notes.
    for name, root in roots.items():
        if not name.endswith('.rels'):
            continue
        import posixpath
        owner_dir = '' if name == '_rels/.rels' else name.rsplit('/_rels/', 1)[0]
        for rel in root:
            if rel.get('TargetMode') == 'External':
                continue
            target = rel.get('Target')
            assert target and posixpath.normpath(posixpath.join(owner_dir, target)) in parts, (name, target)
    if item['id'].startswith('04-'):
        assert len(main.findall('.//w:tr', generate.NS)) >= 89
    if item['id'].startswith('21-'):
        assert roots['word/footnotes.xml'].findall('.//w:tbl', generate.NS)
    if item['id'].startswith('29-'):
        assert roots['word/header1.xml'].findall('.//w:tbl', generate.NS)
    return data


def run_case(api, item, mode, folder, legacy_snapshot=False):
    folder.mkdir(parents=True, exist_ok=True)
    source = validate_fixture(item)
    expected = expected_parts(source, mode == 'edited')
    oracle = folder / 'expected.docx'
    oracle.write_bytes(generate.pack(expected))
    before, wanted = measure(HERE / item['path']), measure(oracle)
    record = dict(id=item['id'], mode=mode, source_sha256=digest(source), before=before, expected=wanted)
    doc = api.read(source)
    try:
        if mode == 'edited':
            doc, record['edit_method'] = api.change(doc, legacy_snapshot)
        saved = api.write(doc)
        output = folder / 'actual.docx'
        output.write_bytes(saved)
        actual_parts = unzip(saved)
        actual = measure(output)
        record['actual'] = actual
        record['metrics'] = {key: dict(before=before[key], expected=wanted[key], actual=actual[key],
            status='PASS' if wanted[key] == actual[key] else 'FAIL',
            **(dict(delta=actual[key]-before[key], unexpected_delta=actual[key]-wanted[key]) if isinstance(actual[key], int) else {})) for key in METRICS}
        record['passed'] = sum(row['status'] == 'PASS' for row in record['metrics'].values())
        record['failed_metrics'] = [key for key in METRICS if actual[key] != wanted[key]]
        record['changed_part_payloads'] = [name for name in sorted(expected.keys() | actual_parts.keys()) if expected.get(name) != actual_parts.get(name)]
        record['payloads_exact'] = not record['changed_part_payloads']
        record['main_changes'] = main_changes(expected['word/document.xml'], actual_parts['word/document.xml'])
        record['output_sha256'] = digest(saved)
        reopened = api.read(saved)
        try:
            resaved = unzip(api.write(reopened))
            record['second_write_stable'] = actual_parts == resaved
        finally:
            api.doc_free(reopened)
        record['status'] = 'PASS' if record['passed'] == 18 and record['payloads_exact'] and record['second_write_stable'] else 'FAIL'
    finally:
        api.doc_free(doc)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--case')
    parser.add_argument('--mode', choices=('noop', 'edited'))
    parser.add_argument('--legacy-snapshot', action='store_true', help='record original #125 using an otherwise identical model snapshot')
    args = parser.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    cases = [item for item in manifest['documents'] if args.case in (None, item['id'])]
    assert cases and (args.case is None or len(cases) == 1)
    modes = [args.mode] if args.mode else ['noop', 'edited']
    api = RealBridge(args.library.resolve(strict=True))
    with tempfile.TemporaryDirectory() as tmp:
        output = args.output or Path(tmp)
        output.mkdir(parents=True, exist_ok=True)
        report = dict(library_sha256=digest(args.library.read_bytes()), metrics=list(METRICS),
            original_117_metrics=list(original.METRICS), fixture_count=len(cases), matrices={mode: [] for mode in modes})
        for item in cases:
            for mode in modes:
                try:
                    row = run_case(api, item, mode, output / item['id'] / mode, args.legacy_snapshot)
                except Exception as exc:
                    row = dict(id=item['id'], mode=mode, status='ERROR', passed=0, error=type(exc).__name__ + ': ' + repr(exc), failed_metrics=list(METRICS))
                report['matrices'][mode].append(row)
                print(item['id'], mode, row['status'], str(row['passed']) + '/18', ','.join(row.get('failed_metrics', [])), row.get('error', ''), flush=True)
        report['summary'] = {mode: dict(passed=sum(row['passed'] for row in rows), total=18*len(rows),
            payload_exact=sum(row.get('payloads_exact', False) for row in rows),
            failed_documents=sum(row['status'] != 'PASS' for row in rows)) for mode, rows in report['matrices'].items()}
        if len(modes) == 2:
            report['edit_side_effects'] = []
            for noop, edited in zip(report['matrices']['noop'], report['matrices']['edited']):
                base = {digest(v) for v in noop.get('main_changes', [])}
                extra = [v for v in edited.get('main_changes', []) if digest(v) not in base]
                report['edit_side_effects'].append(dict(id=noop['id'],
                    noop_failed_metrics=noop['failed_metrics'], edited_failed_metrics=edited['failed_metrics'],
                    additional_failed_metrics=sorted(set(edited['failed_metrics']) - set(noop['failed_metrics'])),
                    additional_main_changes=extra))
        (output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(report['summary']), flush=True)
        return int(any(row['status'] != 'PASS' for rows in report['matrices'].values() for row in rows))


if __name__ == '__main__':
    sys.exit(main())
