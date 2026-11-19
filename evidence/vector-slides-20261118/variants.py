# SPDX-License-Identifier: MIT
"""Incremental bilateral PDF omissions, adapted from the slides ablation."""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / '_work'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


# Byte-local edits preserve the original streams except for the omitted operator.
# 'n' terminates the path without painting. 'S' and 'f*' retain one half of 'B*'.
CLASSES = {
    'image': (rb'/Image\d+\s+Do\b', b'', {b'Do': None}),
    'shading': (rb'/P\d+\s+sh\b', b'', {b'sh': None}),
    'shading-page': (rb'/P\d+\s+sh\b', b'', {b'sh': None}),
    'path': (rb'(?<=\s)(?:S|f\*?)(?=\s|$)', b'n', {b'S': b'n', b'f': b'n', b'f*': b'n'}),
    'fill': (rb'(?<=\s)f\*?(?=\s|$)', b'n', {b'f': b'n', b'f*': b'n'}),
    'stroke': (rb'(?<=\s)S(?=\s|$)', b'n', {b'S': b'n'}),
    'glyph': (rb'\[[^\[\]]*\]\s+TJ\b', b'', {b'TJ': None}),
    'clip': (rb'(?<=\s)W\*?(?=\s+n(?:\s|$))', b'', {b'W': None, b'W*': None}),
}


def mask_sources(doc, p):
    for operands, op in p.get_contents().operations:
        if op == b'gs':
            owner = p['/Resources']['/ExtGState'][operands[0]].get_object()
            if '/SMask' in owner and owner['/SMask'] != '/None':
                yield 'state', owner, owner['/SMask']['/G'].get_object()
        if op == b'Do':
            owner = p['/Resources']['/XObject'][operands[0]].get_object()
            assert owner['/Subtype'] == '/Image', 'nested Form requires its own audit'
            if '/SMask' in owner:
                yield 'image', owner, None


def audit(doc, page_indices):
    rows = []
    for i in page_indices:
        p = doc.pages[i]
        ops = Counter(op.decode() for _, op in p.get_contents().operations)
        for kind, _, group in mask_sources(doc, p):
            ops[kind + '_mask_use'] += 1
            if group is not None:
                ops['mask_sh'] += sum(op == b'sh' for _, op in ContentStream(group, doc).operations)
                ops['mask_group'] += group['/Group']['/S'] == '/Transparency'
                assert not any(op == b'Do' for _, op in ContentStream(group, doc).operations)
        ops['page_group'] = int('/Group' in p)
        rows.append(dict(page=i + 1, ops=dict(ops)))
    return rows


def edit_stream(doc, stream, name):
    pattern, replacement, operators = CLASSES[name]
    before = ContentStream(stream, doc).operations
    contents, count = re.subn(pattern, replacement, stream.get_data())
    expected = [(operands, operators.get(op, op)) for operands, op in before
                if operators.get(op, op) is not None]
    assert count == sum(op in operators for _, op in before), (name, count)
    if count:
        stream.set_data(contents)
        assert ContentStream(stream, doc).operations == expected, name
    return count


def build(pdf, pages, name, out):
    writer = PdfWriter(str(pdf), incremental=True)
    masks = {(kind, owner.indirect_reference.idnum): (owner, group)
             for i in pages for kind, owner, group in mask_sources(writer, writer.pages[i])}
    page_edits = mask_edits = 0
    if name == 'softmask':
        for owner, _ in masks.values():
            del owner['/SMask']
        mask_edits = len(masks)
    elif name == 'page-group':
        for i in pages:
            if '/Group' in writer.pages[i]:
                del writer.pages[i]['/Group']
                page_edits += 1
    else:
        streams = {writer.pages[i]['/Contents'].indirect_reference.idnum: writer.pages[i]['/Contents']
                   for i in pages}
        if name == 'identity':
            for stream in streams.values():
                before = ContentStream(stream, writer).operations
                stream.set_data(stream.get_data() + b'\n')
                assert ContentStream(stream, writer).operations == before
        elif name != 'shading-mask':
            page_edits = sum(edit_stream(writer, stream, name) for stream in streams.values())
        if name in ('shading', 'shading-mask'):
            groups = {group.indirect_reference.idnum: group for _, group in masks.values() if group is not None}
            mask_edits = sum(edit_stream(writer, group, 'shading') for group in groups.values())
    assert name == 'identity' or page_edits or mask_edits, name
    writer.write(out)
    with out.open('rb') as f:
        assert f.read(pdf.stat().st_size) == pdf.read_bytes()
    edited = PdfReader(out)
    assert len(edited.pages) == len(writer.pages)
    assert out.stat().st_size > pdf.stat().st_size
    return dict(sha256=sha(out), unique_page_edits=page_edits, unique_mask_edits=mask_edits,
                after=audit(edited, pages))


def main():
    pdf = ROOT / 'tests/fixtures/pdf-large' / (sys.argv[1] + '.pdf')
    first, last = map(int, sys.argv[2:4])
    pages = range(first - 1, last)
    OUT.mkdir(exist_ok=True)
    manifest = dict(fixture=sha(pdf), before=audit(PdfReader(pdf), pages), variants={})
    for name in sys.argv[4:]:
        out = OUT / f'{pdf.stem}-{name}.pdf'
        result = build(pdf, pages, name, out)
        manifest['variants'][name] = result
        print(name, {k: v for k, v in result.items() if k != 'after'}, flush=True)
    data = json.dumps(manifest, separators=(',', ':')) + '\n'
    (HERE / f'{pdf.stem}-operator-audit.json').write_text(data, encoding='utf-8')


if __name__ == '__main__':
    main()
