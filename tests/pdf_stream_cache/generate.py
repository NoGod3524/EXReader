#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CI-only bounded fixtures: aggregate streams exceed cache, each page fits."""
import sys
from pathlib import Path
import zlib


def pdf(path, count, payload_size):
    objects = [b'', b'<< /Type /Catalog /Pages 2 0 R >>']
    kids = ' '.join(f'{3 + i * 2} 0 R' for i in range(count))
    objects.append(f'<< /Type /Pages /Kids [{kids}] /Count {count} >>'.encode())
    for i in range(count):
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 8 8] /Resources << >> /Contents {4 + i * 2} 0 R >>'.encode())
        # One long comment exercises the decoded buffer without rendering work
        # proportional to its size. Different real drawing commands per page.
        paint = b'0 g 0 0 4 8 re f\n' if i % 2 == 0 else b'0 g 4 0 4 8 re f\n'
        content = b'%' + b'x' * payload_size + b'\n' + paint
        compressed = zlib.compress(content)
        objects.append(f'<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n'.encode() + compressed + b'\nendstream')
    data, offsets = bytearray(b'%PDF-1.7\n'), [0]
    for number, obj in enumerate(objects[1:], 1):
        offsets.append(len(data))
        data.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
    start = len(data)
    data.extend(f'xref\n0 {len(objects)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    path.write_bytes(data)


root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
pdf(root / 'many-pages.pdf', 24, 6 * 1024 * 1024)
pdf(root / 'oversized-page.pdf', 1, 64 * 1024 * 1024)
