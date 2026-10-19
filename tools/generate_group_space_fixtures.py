#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small original PDFs separating group flags from blending colour spaces."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'tests/fixtures/pdf-color'


def stream(body, attributes=''):
    body = body.encode('ascii')
    return ('<< %s /Length %d >>\nstream\n' % (attributes, len(body))).encode() + body + b'\nendstream'


def write(name, objects):
    data = bytearray(b'%PDF-1.7\n')
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += ('%d 0 obj\n' % index).encode() + obj + b'\nendobj\n'
    xref = len(data)
    data += ('xref\n0 %d\n0000000000 65535 f \n' % len(offsets)).encode()
    for offset in offsets[1:]:
        data += ('%010d 00000 n \n' % offset).encode()
    data += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offsets), xref)).encode()
    (ROOT / name).write_bytes(data)


def scene(name, child_flags, body, placement='form', nested=False, cmyk=True, parent_space=None):
    parent_space = parent_space or ('DeviceCMYK' if cmyk else 'DeviceRGB')
    parent_flags = '/S /Transparency /I true /CS /' + parent_space
    background = '.2 .4 .6 .1 k 0 0 16 16 re f\n' if cmyk else ''
    page_extra = ('/Group << %s >>' % parent_flags) if placement == 'page' else ''
    page_content = background + '/Child Do' if placement == 'page' else '/Parent Do'
    if placement.startswith('appearance'):
        page_extra += ' /Annots [8 0 R]'
        page_content = ''
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        ('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R %s '
         '/Resources << /XObject << /Parent 5 0 R /Child 6 0 R >> >> >>' % page_extra).encode(),
        stream(page_content),
        stream(background + '/Child Do', '/Type /XObject /Subtype /Form /BBox [0 0 16 16] '
               '/Group << %s >> /Resources << /XObject << /Child 6 0 R >> >>' % parent_flags),
        stream('/Nested Do' if nested else body,
               '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency %s >> '
               '/Resources << /ExtGState << /A << /ca .5 >> >> /XObject << /Nested 7 0 R >> >>' % child_flags),
        stream(body, '/Type /XObject /Subtype /Form /BBox [0 0 16 16] '
               '/Group << /S /Transparency /I true >> /Resources << /ExtGState << /A << /ca .5 >> >> >>'),
        ('<< /Type /Annot /Subtype /Stamp /Rect [0 0 16 16] /AP << /N %d 0 R >> >>' %
         (6 if placement=='appearance-direct' else 5)).encode(),
    ]
    write(name, objects)


def main():
    body = '1 0 0 rg 0 0 16 16 re f /A gs 0 0 1 rg 0 0 16 16 re f'
    for name, flag in [('true', '/K true'), ('false', '/K false'), ('default', ''), ('null', '/K null'), ('bad', '/K 1')]:
        scene('group-k-' + name + '.pdf', '/I true /CS /DeviceRGB ' + flag, body, cmyk=False)
    body = '/A gs 0 0 0 rg 0 0 16 16 re f 1 1 1 rg 0 0 16 16 re f'
    for placement in ['form', 'page', 'appearance']:
        scene('mixed-rgb-' + placement + '.pdf', '/I true /CS /DeviceRGB', body, placement)
    scene('mixed-rgb-nested.pdf', '/I true /CS /DeviceRGB', body, nested=True)
    scene('mixed-rgb-inherit.pdf', '/I true', body)
    scene('mixed-rgb-nonisolated.pdf', '/I false /CS /DeviceRGB', body)
    scene('mixed-rgb-bad-space.pdf', '/I true /CS /Missing', body)
    scene('mixed-rgb-appearance-direct.pdf', '/I true /CS /DeviceRGB', body, 'appearance-direct')
    scene('mixed-rgb-gray-parent.pdf', '/I true /CS /DeviceRGB', body.replace('0 0 0 rg', '1 0 0 rg'),
          cmyk=False, parent_space='DeviceGray')


if __name__ == '__main__':
    main()
