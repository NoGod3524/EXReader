#!/usr/bin/env python3
"""Apply the acceptance edit batch to hash-pinned local real DOCX inputs."""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from xml.parsers import expat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_docx_edit_io import Bridge, Run, RP, PP, ID, unzip, audit, W


def opaque_hashes(xml):
    """Hash exact source slices, independently of model counts/serialization."""
    tags = ('tbl', 'drawing', 'pict', 'object', 'footnoteReference', 'endnoteReference')
    result = {tag: [] for tag in tags}
    stack = []
    parser = expat.ParserCreate(namespace_separator='|')

    def start(name, attrs):
        begin = at = parser.CurrentByteIndex
        quote = None
        while True:
            value = xml[at]
            if quote:
                if value == quote:
                    quote = None
            elif value in (34, 39):
                quote = value
            elif value == 62:
                break
            at += 1
        stack.append((begin, xml[at - 1] == 47))

    def end(name):
        begin, empty = stack.pop()
        if name.startswith(W + '|') and name.split('|')[-1] in result:
            at = parser.CurrentByteIndex
            finish = at if empty else xml.index(b'>', at) + 1
            result[name.split('|')[-1]].append(hashlib.sha256(xml[begin:finish]).hexdigest())

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.Parse(xml, True)
    return {tag: sorted(values) for tag, values in result.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    api = Bridge(args.library.resolve())
    report = dict(library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(), documents=[])
    for entry in json.loads(args.manifest.read_text(encoding='utf-8'))['documents']:
        source = (args.manifest.parent / entry['path']).resolve()
        data = source.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry['sha256']
        doc = api.read(data)
        try:
            ids = [p.id for p in api.paragraphs(doc)[:3]]
            assert len(ids) == 3
            pp = PP(present=7, align=3, first=720, after=120, line=480)
            tx = api.begin(doc)
            assert tx
            for block_id in ids:
                assert api.set_paragraph_props(doc, block_id, c.byref(pp)) == 0
            rp = RP(present=3, font=b'Times New Roman', size=24)
            markers = []
            for i in range(5):
                text = ('X1 bridge acceptance paragraph %d' % i).encode()
                markers.append(text.decode())
                storage = c.create_string_buffer(text)
                run = Run(text=c.cast(storage, c.c_void_p), length=len(text), props=rp)
                new_id = ID()
                assert api.insert_paragraph(doc, ids[0], c.byref(run), 1, c.byref(pp), c.byref(new_id)) == 0
            assert api.commit(tx) == 0
            edited = api.write(doc)
            before, after = audit(data), audit(edited)
            assert after['paragraphs'] == before['paragraphs'] + 5
            for key in ('tables', 'images', 'footnotes', 'section_margins', 'image_sha256'):
                assert before[key] == after[key], key
            a, b = unzip(data), unzip(edited)
            assert set(a) == set(b)
            assert all(a[n] == b[n] for n in a if n != 'word/document.xml')
            retained_xml = opaque_hashes(a['word/document.xml'])
            assert retained_xml == opaque_hashes(b['word/document.xml'])
            root = ET.fromstring(b['word/document.xml'])
            text = ''.join(n.text or '' for n in root.iter('{%s}t' % W))
            assert all(text.count(m) == 1 for m in markers)
            assert len(list(root.iter('{%s}sectPr' % W))) == len(before['section_margins'])
            reopened = api.read(edited)
            try:
                ps = api.paragraphs(reopened)
                # First source paragraph, five inserted paragraphs, next two
                # source paragraphs. Borrowed model IDs need not survive reload.
                changed = [ps[0], ps[6], ps[7]]
                assert all(p.props.present & 7 == 7 and p.props.first == 720 and
                           p.props.after == 120 and p.props.line == 480 and
                           p.props.align == 3 for p in changed)
                texts = [''.join(c.string_at(p.runs[i].text, p.runs[i].length).decode('utf-8')
                                 for i in range(p.count) if p.runs[i].kind == 0) for p in ps]
                assert all(texts.count(marker) == 1 for marker in markers)
            finally:
                api.doc_free(reopened)
            assert api.undo(doc) == 0
            assert audit(api.write(doc)) == before
            assert api.redo(doc) == 0
            assert audit(api.write(doc)) == after
            (args.output / (entry['id'] + '.docx')).write_bytes(edited)
            report['documents'].append(dict(id=entry['id'], source_sha256=entry['sha256'],
                status='PASS', inserted_paragraphs=5, modified_paragraphs=3,
                properties_verified_after_reopen=True, unchanged_opc_parts=len(a)-1,
                opaque_xml_bytes_unchanged=True, opaque_xml_sha256=retained_xml,
                section_count_before=len(before['section_margins']),
                section_count_after=len(after['section_margins']), before=before, after=after))
            print(entry['id'], '5 inserts + 3 property edits + reopen + undo/redo PASS', flush=True)
        finally:
            api.doc_free(doc)
    (args.output / 'edits.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
