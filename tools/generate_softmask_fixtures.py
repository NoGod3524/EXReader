
#!/usr/bin/env python3
"""Original graphics-state soft-mask fixtures (ISO 32000-1 11.6.5.2)."""
# SPDX-License-Identifier: GPL-3.0-only
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/pdf-blend'


def build(name, objects, page_extra, content):
    body = content.encode()
    objects = dict(objects)
    objects[4] = b'<< /Length ' + str(len(body)).encode() + b' >>\nstream\n' + body + b'\nendstream'
    out = bytearray(b'%PDF-1.7\n')
    offsets = {}
    for i in sorted(objects):
        offsets[i] = len(out)
        out += str(i).encode() + b' 0 obj\n' + objects[i] + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 ' + str(len(objects) + 1).encode() + b'\n0000000000 65535 f \n'
    for i in sorted(objects):
        out += ('%010d 00000 n \n' % offsets[i]).encode()
    out += b'trailer\n<< /Size ' + str(len(objects) + 1).encode() + b' /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'
    (ROOT / (name + '.pdf')).write_bytes(bytes(out))
    return hashlib.sha256(bytes(out)).hexdigest()


def form(body, bbox=b'[0 0 16 16]'):
    data = body.encode()
    return b'<< /Type /XObject /Subtype /Form /BBox ' + bbox + b' /Group << /S /Transparency /I true >> /Resources << >> /Length ' + str(len(data)).encode() + b' >>\nstream\n' + data + b'\nendstream'


def page(extra_resources):
    return (b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R '
            b'/Group << /S /Transparency /CS /DeviceRGB /I true >> /Resources << /ExtGState << ' + extra_resources + b' >> >> >>')


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    # Alpha: the mask form paints an opaque left half, so only that half keeps the green fill.
    objects = {
        1: b'<< /Type /Catalog /Pages 2 0 R >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: page(b'/GS1 5 0 R'),
        5: b'<< /SMask << /S /Alpha /G 6 0 R >> >>',
        6: form('1 1 1 rg 0 0 8 16 re f'),
    }
    build('softmask-alpha', objects, b'', '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q')
    # Luminosity: the same mask but interpreted as luminance with a zero backdrop.
    objects[5] = b'<< /SMask << /S /Luminosity /G 6 0 R >> >>'
    build('softmask-luminosity', objects, b'', '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q')
    # Explicit /None restores full painting.
    objects[5] = b'<< /SMask /None >>'
    build('softmask-none', objects, b'', '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q')
    print('soft mask fixtures written')


if __name__ == '__main__':
    main()
