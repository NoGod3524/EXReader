#!/usr/bin/env python3
"""Generate separate, labelled fixed-page resolver inputs only in Actions."""
import os
from pathlib import Path
import sys

def pdf(path, text):
    stream = ('BT /F1 12 Tf 36 720 Td (' + text + ') Tj ET').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 3000 800] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    data = bytearray(b'%PDF-1.7\n'); offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data)); data += f'{index} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref = len(data); data += f'xref\n0 {len(offsets)}\n'.encode() + b'0000000000 65535 f \n'
    for offset in offsets[1:]: data += f'{offset:010d} 00000 n \n'.encode()
    data += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    path.write_bytes(data)

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
    context = 'A' * 40 + ' UniqueSelectionTarget ' + 'B' * 40
    pdf(root / 'AnchorSource.pdf', context)
    pdf(root / 'AnchorMissing.pdf', context.replace('UniqueSelectionTarget', 'DifferentText'))
    pdf(root / 'AnchorAmbiguous.pdf', context + ' ' * 40 + context)

if __name__ == '__main__': main()
