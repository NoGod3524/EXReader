
#!/usr/bin/env python3
"""Graphics-state soft-mask scenes (ISO 32000-1 11.6.5.2).

The mask is a solid rectangle or a flat grey, so the expected pixel at every
probe is analytic: out = m * blend(backdrop, element) + (1 - m) * backdrop.
"""
# SPDX-License-Identifier: MIT
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/pdf-blend'
CELL = 16
MODES = ['Normal', 'Multiply', 'Screen', 'Darken']
BG = (255, 0, 0)
FG = (0, 255, 0)


def blend_channel(b, s, mode):
    if mode == 'Normal': return s
    if mode == 'Multiply': return b * s
    if mode == 'Screen': return b + s - b * s
    if mode == 'Darken': return min(b, s)
    raise ValueError(mode)


def cell_pixels(mask_fn, mode='Normal'):
    bg = tuple(v / 255 for v in BG)
    fg = tuple(v / 255 for v in FG)
    blended = tuple(blend_channel(b, s, mode) for b, s in zip(bg, fg))
    out = []
    for y in range(CELL):
        for x in range(CELL):
            m = mask_fn(x, y)
            out.append(tuple(m * v + (1 - m) * b for v, b in zip(blended, bg)))
    return out


def write_images(name, cells, width):
    alpha = bytearray(width * CELL * 4)
    white = bytearray(width * CELL * 4)
    for index, pixels in enumerate(cells):
        for y in range(CELL):
            for x in range(CELL):
                v = pixels[y * CELL + x]
                i = ((CELL - 1 - y) * width + index * CELL + x) * 4
                for k in range(3):
                    alpha[i + k] = white[i + k] = int(max(0, min(255, round(v[k] * 255))))
                alpha[i + 3] = white[i + 3] = 255
    (ROOT / (name + '-alpha.rgba')).write_bytes(bytes(alpha))
    (ROOT / (name + '-white.rgba')).write_bytes(bytes(white))
    (ROOT / (name + '.mask')).write_bytes(bytes([1]) * (width * CELL))


class PDF:
    def __init__(self, width, height):
        self.w, self.h = width, height
        self.objects = [b'', b'', b'', b'']
        self.forms = []
        self.page_res = []

    def add(self, body):
        self.objects.append(body)
        return len(self.objects)

    def form(self, body, bbox=b'[0 0 16 16]', group=b'/S /Transparency /I true', matrix=None):
        data = body.encode() if isinstance(body, str) else body
        extra = (b' /BBox ' + bbox if bbox else b'') + (b' /Matrix ' + matrix if matrix else b'')
        return self.add(b'<< /Type /XObject /Subtype /Form' + extra + b' /Group << ' + group +
                        b' >> /Resources << >> /Length ' + str(len(data)).encode() + b' >>\nstream\n' + data + b'\nendstream')

    def cell(self, mask_dict, content, mode='Normal', bbox=b'[0 0 16 16]'):
        gs = self.add(('<< /SMask ' + mask_dict + ' /BM /%s >>' % mode).encode())
        body = content.encode()
        return self.add(b'<< /Type /XObject /Subtype /Form /BBox ' + bbox + b' /Group << /S /Transparency /I true >> '
                        b'/Resources << /ExtGState << /GS1 %d 0 R >> >> ' % gs
                        + b'/Length ' + str(len(body)).encode() + b' >>\nstream\n' + body + b'\nendstream')

    def finish(self, name, content):
        data = content.encode()
        self.objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
        self.objects[1] = b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>'
        resources = ['/XObject << %s >>' % ' '.join('/Fm%d %d 0 R' % (i, o) for i, o in self.forms)]
        for category, entries in self.page_res:
            resources.append('/%s << %s >>' % (category, ' '.join('/%s %d 0 R' % (n, o) for n, o in entries)))
        self.objects[2] = ('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R '
                           '/Group << /S /Transparency /CS /DeviceRGB /I true >> /Resources << %s >> >>'
                           % (self.w, self.h, ' '.join(resources))).encode()
        self.objects[3] = b'<< /Length ' + str(len(data)).encode() + b' >>\nstream\n' + data + b'\nendstream'
        out = bytearray(b'%PDF-1.7\n%\x80\x81\x82\x83\n')
        offsets = [0]
        for i, obj in enumerate(self.objects, 1):
            offsets.append(len(out))
            out += ('%d 0 obj\n' % i).encode() + obj + b'\nendobj\n'
        xref = len(out)
        out += ('xref\n0 %d\n0000000000 65535 f \n' % len(offsets)).encode()
        for off in offsets[1:]:
            out += ('%010d 00000 n \n' % off).encode()
        out += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offsets), xref)).encode()
        (ROOT / (name + '.pdf')).write_bytes(bytes(out))
        return hashlib.sha256(bytes(out)).hexdigest()


def grid(name, specs):
    pdf = PDF(len(specs) * CELL, CELL)
    content = []
    for index, spec in enumerate(specs):
        mask = pdf.form(spec['mask'])
        cell = pdf.cell(spec['dict'](mask), spec['content'], spec.get('mode', 'Normal'))
        pdf.forms.append((index, cell))
        content.append('q 1 0 0 1 %d 0 cm /Fm%d Do Q' % (index * CELL, index))
    pdf.finish(name, '\n'.join(content))
    write_images(name, [cell_pixels(spec['expect'], spec.get('mode', 'Normal')) for spec in specs], len(specs) * CELL)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    shapes = [(0, 0, 16, 16), (0, 0, 8, 16), (8, 0, 16, 16), (4, 4, 12, 12)]
    alpha = []
    for mode in MODES:
        for x0, y0, x1, y1 in shapes:
            alpha.append({
                'mask': '1 1 1 rg %d %d %d %d re f' % (x0, 16 - y1, x1 - x0, y1 - y0),
                'dict': lambda m: '<< /S /Alpha /G %d 0 R >>' % m,
                'content': '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q',
                'mode': mode,
                'expect': (lambda a, b, c, d: (lambda x, y: 1.0 if a <= x < c and b <= y < d else 0.0))(x0, y0, x1, y1),
            })
    grid('softmask-alpha-grid', alpha)

    grey = [0, 64, 128, 192, 255]
    bcs = [None, (0.5, 0.5, 0.5), (1.0, 1.0, 1.0)]
    lum = []
    for bc in bcs:
        for level in grey:
            v = level / 255
            lum.append({
                'mask': '%g %g %g rg 0 0 16 16 re f' % (v, v, v),
                'dict': (lambda mv, bc=bc: '<< /S /Luminosity /G %d 0 R%s >>' % (
                    mv, '' if bc is None else ' /BC [%g %g %g]' % bc)),
                'content': '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q',
                'expect': (lambda v: (lambda x, y: v))(v),
            })
    lum.append({
        'mask': '0.5 0.5 0.5 rg 8 0 8 16 re f',
        'dict': lambda m: '<< /S /Luminosity /G %d 0 R /BC [0 0 0] >>' % m,
        'content': '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q',
        'expect': lambda x, y: 0.5 if x >= 8 else 0.0,
    })
    grid('softmask-luminosity-grid', lum)

    # Matrix: a 8-wide mask shifted by /Matrix [1 0 0 1 4 0] covers x 4..12.
    pdf = PDF(CELL, CELL)
    mask = pdf.form('1 1 1 rg 0 0 8 16 re f', bbox=b'[0 0 8 16]', matrix=b'[1 0 0 1 4 0]')
    cell = pdf.cell('<< /S /Alpha /G %d 0 R >>' % mask, '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q')
    pdf.forms.append((0, cell))
    pdf.finish('softmask-matrix', 'q 1 0 0 1 0 0 cm /Fm0 Do Q')
    # The mask moves to x 4..12, so the outer columns stay red.
    write_images('softmask-matrix', [cell_pixels(lambda x, y: 1.0 if 4 <= x < 12 else 0.0)], CELL)
    # BBox clips the mask form: content outside the box must not contribute.
    pdf = PDF(CELL, CELL)
    mask = pdf.form('1 1 1 rg 0 0 16 16 re f', bbox=b'[0 0 8 16]')
    cell = pdf.cell('<< /S /Alpha /G %d 0 R >>' % mask, '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q')
    pdf.forms.append((0, cell))
    pdf.finish('softmask-bbox', 'q 1 0 0 1 0 0 cm /Fm0 Do Q')
    write_images('softmask-bbox', [cell_pixels(lambda x, y: 1.0 if x < 8 else 0.0)], CELL)

    # Malformed dictionaries: each must be refused, never partially honoured.
    def bad(name, dict_for, mask_body='1 1 1 rg 0 0 16 16 re f', bbox=b'[0 0 16 16]'):
        pdf = PDF(CELL, CELL)
        mask = pdf.form(mask_body, bbox=bbox)
        text = dict_for(pdf, mask)
        cell = pdf.cell(text, '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q')
        pdf.forms.append((0, cell))
        pdf.finish(name, 'q 1 0 0 1 0 0 cm /Fm0 Do Q')

    bad('softmask-bad-0', lambda pdf, m: '%d 0 R' % pdf.add(b'42'))
    bad('softmask-bad-1', lambda pdf, m: '<< /S /Bad /G %d 0 R >>' % m)
    bad('softmask-bad-2', lambda pdf, m: '<< /S /Alpha >>')
    bad('softmask-bad-3', lambda pdf, m: '<< /S /Alpha /G %d 0 R >>' % pdf.add(b'42'))
    bad('softmask-bad-4', lambda pdf, m: '<< /S /Luminosity /G %d 0 R /BC [1 2] >>' % m)
    bad('softmask-bad-5', lambda pdf, m: '<< /S /Alpha /G %d 0 R /TR << /FunctionType 99 >> >>' % m)
    bad('softmask-bad-6', lambda pdf, m: '<< /S /Alpha /G %d 0 R >>' % m, bbox=None)
    bad('softmask-bad-7', lambda pdf, m: '<< /S /Alpha /G %d 0 R >>' % m, bbox=b'[16 0 0 16]')
    # Transfer function: luminance 0.5 with C0=0, C1=1, N=2 gives a 0.25 mask.
    pdf = PDF(CELL, CELL)
    mask = pdf.form('0.5 0.5 0.5 rg 0 0 16 16 re f')
    cell = pdf.cell('<< /S /Luminosity /G %d 0 R /TR << /FunctionType 2 /Domain [0 1] /C0 [0] /C1 [1] /N 2 >> >>' % mask,
                    '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q')
    pdf.forms.append((0, cell))
    pdf.finish('softmask-tr', 'q 1 0 0 1 0 0 cm /Fm0 Do Q')
    write_images('softmask-tr', [cell_pixels(lambda x, y: 0.25)], CELL)

    grid('softmask-qq', [{
        'mask': 'q Q',
        'dict': lambda m: '<< /S /Alpha /G %d 0 R >>' % m,
        'content': '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 8 16 re f Q 0 1 0 rg 8 0 8 16 re f',
        'expect': lambda x, y: 1.0 if x >= 8 else 0.0,
    }])
    # Device-grey group colour space: luminance is computed in the mask group's own CS.
    grey_pdf = PDF(CELL, CELL)
    grey_mask = grey_pdf.form('0.5 0.5 0.5 rg 0 0 16 16 re f', group=b'/S /Transparency /I true /CS /DeviceGray')
    grey_cell = grey_pdf.cell('<< /S /Luminosity /G %d 0 R /BC [0.5] >>' % grey_mask,
                              '1 0 0 rg 0 0 16 16 re f q /GS1 gs 0 1 0 rg 0 0 16 16 re f Q')
    grey_pdf.forms.append((0, grey_cell))
    grey_pdf.finish('softmask-gray', 'q 1 0 0 1 0 0 cm /Fm0 Do Q')
    write_images('softmask-gray', [cell_pixels(lambda x, y: 0.5)], CELL)

    # Nested: the mask is set on the page and applies to the form's composite, while
    # the form body starts with the default graphics state (ISO 32000-1 8.10.1).
    nested_pdf = PDF(CELL, CELL)
    nested_mask = nested_pdf.form('1 1 1 rg 0 0 8 16 re f')
    nested_gs = nested_pdf.add(('<< /SMask << /S /Alpha /G %d 0 R >> >>' % nested_mask).encode())
    nested_form = nested_pdf.form('1 0 0 rg 0 0 16 16 re f')
    nested_pdf.page_res.append(('ExtGState', [('GS1', nested_gs)]))
    nested_pdf.page_res.append(('XObject', [('Nest', nested_form)]))
    nested_pdf.finish('softmask-nested', '1 1 1 rg 0 0 16 16 re f q /GS1 gs /Nest Do Q')
    nested_pixels = []
    for y in range(CELL):
        for x in range(CELL):
            nested_pixels.append((1.0, 0.0, 0.0) if x < 8 else (1.0, 1.0, 1.0))
    write_images('softmask-nested', [nested_pixels], CELL)
    print('soft mask scenes written')


if __name__ == '__main__':
    main()
