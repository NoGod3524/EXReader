# SPDX-License-Identifier: MIT
"""Record source object identities, clip recipes, and routes without timing."""
import argparse
import gzip
import json
from pathlib import Path

from pypdf import PdfReader
from capture import Document, ROOT


def main(dll, out):
    pdf = ROOT / 'tests/fixtures/pdf-large/image-heavy-100.pdf'
    reader = PdfReader(pdf)
    doc = Document(dll, pdf, 1200, 0)
    rows = []
    try:
        for i in range(70, 100):
            page = reader.pages[i]
            ops = page.get_contents().operations
            refs = page['/Resources']['/XObject']
            images = [refs.raw_get(o[0]).idnum for o, op in ops if op == b'Do']
            clips = [[str(v) for v in ops[j-1][0]]
                     for j, (_, op) in enumerate(ops) if op in (b'W', b'W*')]
            row = doc.render(i, True)
            rows.append(dict(page=i+1, images=images, clips=clips,
                             probes=[p[9:] for p in row['probe']],
                             pixels=row['pixels'], rgba=row['rgba']))
    finally:
        doc.close()
    out.write_bytes(gzip.compress(json.dumps(rows).encode(), mtime=0))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('dll', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    main(args.dll, args.out)
