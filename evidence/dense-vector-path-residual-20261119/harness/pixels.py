# SPDX-License-Identifier: MIT
"""Compare active RGBA bytes of every page for two DLLs over the parity matrix."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'evidence'/'slides-gradient-20261118'))
from paired_sweep import NativeDocument, digest_file, pixels_different

F = ROOT/'tests/fixtures'
LARGE = [(f'pdf-large/{n}.pdf', 1200) for n in ('image-heavy-100', 'real-mixed-120', 'vector-heavy-100')]
SMALL = [('pdf-hybrid-real/pptx-20.pdf', w) for w in (600, 1200, 2400)] \
      + [('pdf-ppt/deck.pdf', w) for w in (600, 1200)] \
      + [('pdf-hybrid-real/word-5.pdf', w) for w in (600, 1200)]
a, b, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
res = {'a_sha256': digest_file(a), 'b_sha256': digest_file(b), 'cells': [], 'totals': {}}
for group, cells in (('large', LARGE), ('small', SMALL)):
    px = diff = 0
    for pdf, width in cells:
        da, db = NativeDocument(a, F/pdf, width), NativeDocument(b, F/pdf, width)
        cell = {'pdf': pdf, 'width': width, 'pdf_sha256': digest_file(F/pdf), 'pages': len(da.scales),
                'pixels': 0, 'differing_pixels': 0, 'mismatched_pages': []}
        for p in range(len(da.scales)):
            ra, rb = da.render(p, True, None)[1], db.render(p, True, None)[1]
            cell['pixels'] += len(ra)*width
            if ra != rb:
                cell['mismatched_pages'].append(p+1)
                cell['differing_pixels'] += pixels_different(ra, rb)
        da.close(); db.close()
        px += cell['pixels']; diff += cell['differing_pixels']; res['cells'].append(cell)
        print(pdf, width, cell['pixels'], cell['differing_pixels'], flush=True)
    res['totals'][group] = {'pixels': px, 'differing_pixels': diff}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res, indent=1)+'\n')
print(res['totals'], flush=True)
