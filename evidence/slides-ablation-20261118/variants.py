# SPDX-License-Identifier: MIT
"""Build bilateral drawing-class omissions for pages 1-10 of image-heavy-100.pdf.

Each edit is an incremental update of the original fixture. The same edited
file is opened by EXReader and PDF.js. Edits are byte-level regex substitutions
on the page content streams (as in the reference clip ablation) or deletions of
dictionary keys; nothing is re-serialized.
"""
import hashlib
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PDF = ROOT / 'tests/fixtures/pdf-large/image-heavy-100.pdf'
OUT = HERE / '_work'
PAGES = range(10)

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

# class -> (page-content (pattern, replacement), delete /SMask in ExtGState,
#           edit mask-group streams, expected page-content edits per 10 pages)
def mask_groups(writer):
    seen = {}
    for i in PAGES:
        for gs in writer.pages[i]['/Resources']['/ExtGState'].values():
            gs = gs.get_object()
            if '/SMask' in gs:
                group = gs['/SMask'].get_object()['/G'].get_object()
                seen[group.indirect_reference.idnum] = group
    return list(seen.values())

def ext_gstates(writer):
    seen = {}
    for i in PAGES:
        for gs in writer.pages[i]['/Resources']['/ExtGState'].values():
            gs = gs.get_object()
            if '/SMask' in gs:
                seen[gs.indirect_reference.idnum] = gs
    return list(seen.values())

CLASSES = {
    # name: dict(content=(regex, repl, expected), smask=bool, group_sh=bool)
    'image':        dict(content=(rb'/Image\d+ Do', b'', 28)),
    'shading':      dict(content=(rb'/P\d+ sh', b'', 10), group_sh=True),
    'shading-page': dict(content=(rb'/P\d+ sh', b'', 10)),
    'softmask':     dict(smask=True),
    'gradient':     dict(content=(rb'/P\d+ sh', b'', 10), smask=True),
    'path':         dict(content=(rb'(\r?\n)S(\r?\nQ)', rb'\1n\2', 20)),
    'glyph':        dict(content=(rb'\[[^\]]*\] TJ', b'', 42)),
    'clip':         dict(content=(rb'(\r?\n)W\* n', rb'\1n', 110)),
}
# Hook-only (EXR_ATTRIBUTION_SKIP) arms that exist for EXReader.
HOOK = {'image': 'image', 'shading': 'shading', 'softmask': 'softmask', 'path': 'path',
        'glyph': 'glyph', 'group': 'group'}

def build(name, spec, out):
    writer = PdfWriter(str(PDF), incremental=True)
    assert len(writer.pages) == 100
    edits = 0
    if 'content' in spec:
        pattern, repl, expected = spec['content']
        seen = set()
        for i in PAGES:
            stream = writer.pages[i]['/Contents']
            if stream.indirect_reference.idnum in seen:
                continue  # pages 6-10 share the content streams of pages 1-5
            seen.add(stream.indirect_reference.idnum)
            data, n = re.subn(pattern, repl, stream.get_data())
            stream.set_data(data)
            edits += n
        assert len(seen) == 5 and edits * 2 == expected, (name, len(seen), edits, expected)
        for i in PAGES:
            assert not re.search(pattern, writer.pages[i]['/Contents'].get_data())
    if spec.get('group_sh'):
        for group in mask_groups(writer):
            data, n = re.subn(rb'/P\d+ sh', b'', group.get_data())
            assert n == 1
            group.set_data(data)
    if spec.get('smask'):
        gstates = ext_gstates(writer)
        assert len(gstates) == 5
        for gs in gstates:
            del gs['/SMask']
    writer.write(out)
    with out.open('rb') as f:
        assert f.read(PDF.stat().st_size) == PDF.read_bytes()
    return edits

def main():
    OUT.mkdir(exist_ok=True)
    manifest = {}
    for name, spec in CLASSES.items():
        out = OUT / f'{name}.pdf'
        edits = build(name, spec, out)
        manifest[name] = dict(sha256=sha(out), content_edits=edits)
        print(name, edits, sha(out), flush=True)
    import json
    (HERE / 'variants.json').write_text(json.dumps(dict(fixture=sha(PDF), variants=manifest), indent=1))

if __name__ == '__main__':
    main()
