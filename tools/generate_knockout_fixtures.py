
#!/usr/bin/env python3
"""Original knockout-group PDF scenes and an independent Decimal(40) reference.

The reference implements ISO 32000-1 11.4.5 on the same arithmetic as
pdf_group_reference.py: each element composites with the group's initial
backdrop and replaces the accumulated result inside its coverage. No external
renderer is required, so these scenes can be regenerated offline.
"""
# SPDX-License-Identifier: GPL-3.0-only
import hashlib, json, sys
from decimal import Decimal as D, localcontext
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pdf_group_reference import over, color  # noqa: E402

ROOT = HERE.parent / 'tests/fixtures/pdf-blend'
MODES = 'Normal Multiply Screen Overlay Darken Lighten ColorDodge ColorBurn HardLight SoftLight Difference Exclusion Hue Saturation Color Luminosity'.split()
CELL = 16
FG = (204, 77, 26)
BG = (51, 102, 153)
WHITE = (D(1), D(1), D(1))


def num(v):
    return '%.9f' % (v / 255)


def pdf_color(rgb, stroke=False):
    return ' '.join(num(v) for v in rgb) + (' RG' if stroke else ' rg')


class PDF:
    """Minimal page with one form XObject per cell, plus shared resources."""

    def __init__(self, width, height):
        self.w, self.h = width, height
        self.objects = [b'', b'', b'', b'']
        self.forms = []
        self.shared = []          # (name, object) entries shared by every form
        self.resources = {}       # resource name -> object number
        self.page_shared = []     # page-level resources

    def add(self, body):
        self.objects.append(body)
        return len(self.objects)

    def image(self, rgb):
        """A 1x1 DeviceRGB image, scalable to any rectangle without interpolation."""
        body = bytes(rgb)
        obj = self.add(b'<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceRGB '
                       b'/BitsPerComponent 8 /Length 3 >>\nstream\n' + body + b'\nendstream')
        self.resources['Im1'] = obj
        return obj

    def type3(self):
        """A Type3 font whose only glyph is a filled 1000x1000 square."""
        body = b'1000 0 d0 0 0 1000 1000 re f'
        proc = self.add(b'<< /Length ' + str(len(body)).encode() + b' >>\nstream\n' + body + b'\nendstream')
        font = self.add(('<< /Type /Font /Subtype /Type3 /FontBBox [0 0 1000 1000] '
                         '/FontMatrix [0.001 0 0 0.001 0 0] /CharProcs << /A %d 0 R >> '
                         '/Encoding << /Type /Encoding /Differences [65 /A] >> '
                         '/FirstChar 65 /LastChar 65 /Widths [1000] /Resources << >> >>' % proc).encode())
        self.resources['F1'] = font
        return font

    def nested(self, rgb):
        """A non-isolated group used as a nested element (alpha comes from the caller)."""
        body = ('%s 0 0 16 16 re f' % pdf_color(rgb)).encode()
        obj = self.add(b'<< /Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I false >> '
                       b'/Resources << >> '
                       + b'/Length ' + str(len(body)).encode() + b' >>\nstream\n' + body + b'\nendstream')
        self.resources['Nest'] = obj
        return obj

    def finish(self, path, content, background=None):
        ops = []
        if background is not None:
            ops.append(pdf_color(background) + ' 0 0 %d %d re f' % (self.w, self.h))
        ops.append(content)
        data = ('\n'.join(ops)).encode()
        self.objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
        self.objects[1] = ('<< /Type /Pages /Count 1 /Kids [3 0 R] >>').encode()
        resources = ' '.join('/Fm%d %d 0 R' % (i, obj) for i, obj in self.forms)
        self.objects[2] = ('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R '
                           '/Group << /S /Transparency /CS /DeviceRGB /I true >> /Resources << /XObject << %s >> >> >>'
                           % (self.w, self.h, resources)).encode()
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
        Path(path).write_bytes(bytes(out))
        return hashlib.sha256(bytes(out)).hexdigest()


def form(pdf, isolated, knockout, elements):
    """One form XObject: a transparency group containing the given elements.

    Elements are (rgb, alpha, mode, rect, kind) with kind in fill/text/image/nested.
    Rects use image coordinates (y down); PDF user space is y up.
    """
    gs, xobjects, fonts, ops = [], [], [], []
    for i, element in enumerate(elements):
        rgb, alpha, mode, rect = element[:4]
        kind = element[4] if len(element) > 4 else 'fill'
        name = 'GS%d' % i
        gs.append('/%s %d 0 R' % (name, pdf.add(('<< /BM /%s /ca %s /CA %s >>' % (mode, num(alpha), num(alpha))).encode())))
        x0, y0, x1, y1 = rect
        if kind == 'fill':
            ops.append('/%s gs %s %d %d %d %d re f' % (name, pdf_color(rgb), x0, CELL - y1, x1 - x0, y1 - y0))
        elif kind == 'text':
            ops.append('/%s gs %s BT /F1 16 Tf %d %d Td (A) Tj ET' % (name, pdf_color(rgb), x0, CELL - y1))
            fonts.append('/F1 %d 0 R' % pdf.resources['F1'])
        elif kind == 'image':
            ops.append('/%s gs q %d 0 0 %d %d %d cm /Im1 Do Q' % (name, x1 - x0, y1 - y0, x0, CELL - y1))
            xobjects.append('/Im1 %d 0 R' % pdf.resources['Im1'])
        elif kind == 'nested':
            ops.append('/%s gs q 1 0 0 1 %d %d cm /Nest Do Q' % (name, x0, CELL - y1))
            xobjects.append('/Nest %d 0 R' % pdf.resources['Nest'])
        else:
            raise ValueError(kind)
    body = '\n'.join(ops).encode()
    flags = '/I %s /K %s' % ('true' if isolated else 'false', 'false' if knockout else 'true')
    resources = '/ExtGState << %s >>' % ' '.join(gs)
    if xobjects:
        resources += ' /XObject << %s >>' % ' '.join(xobjects)
    if fonts:
        resources += ' /Font << %s >>' % ' '.join(fonts)
    extra = '/Group << /S /Transparency %s%s >> /Resources << %s >>' % (
        flags, '' if not isolated else ' /CS /DeviceRGB', resources)
    return pdf.add(b'<< /Type /XObject /Subtype /Form /BBox [0 0 %d %d] ' % (CELL, CELL) + extra.encode()
                   + b' /Length ' + str(len(body)).encode() + b' >>\nstream\n' + body + b'\nendstream')


def cell_pixel(back, elements, x, y, isolated, knockout):
    """Group result at one covered pixel; coverage is binary, no antialiasing."""
    with localcontext() as ctx:
        ctx.prec = 40
        initial = (D(0),) * 4 if isolated else back
        result = initial
        group_alpha = D(0)
        for element in elements:
            rgb, alpha, mode, rect = element[:4]
            if not (rect[0] <= x < rect[2] and rect[1] <= y < rect[3]):
                continue  # outside this element's coverage
            a = D(alpha) / 255
            if not a:
                continue  # fully transparent: paints nothing, knocks nothing out
            src = tuple(D(v) / 255 for v in rgb)
            if knockout:
                result = over(initial, src, a, mode)
                group_alpha = result[3]
            else:
                result = over(result, src, a, mode)
                group_alpha += a * (1 - group_alpha)
        if not group_alpha:
            return (D(0),) * 4
        straight = tuple((v - (1 - group_alpha) * b) / group_alpha for v, b in zip(result[:3], initial))
        return straight + (group_alpha,)


def expected_pixels(pdf_w, pdf_h, cells, isolated, knockout, background=None, mask=None):
    """Premultiplied (alpha) and straight-over-white byte images, per pixel."""
    alpha = bytearray(pdf_w * pdf_h * 4)
    white = bytearray(pdf_w * pdf_h * 4)
    back = (D(0),) * 4 if background is None else tuple(D(v) / 255 for v in background) + (D(1),)
    for index, (x0, y0, elements) in enumerate(cells):
        for y in range(CELL):
            for x in range(CELL):
                straight = cell_pixel(back, elements, x, y, isolated, knockout)
                a = straight[3]
                premul = tuple(v * a for v in straight[:3])
                comp = tuple(p + (1 - a) for p in premul)
                i = ((pdf_h - 1 - (y0 + y)) * pdf_w + (x0 + x)) * 4
                for k in range(3):
                    alpha[i + k] = int((premul[k] * 255).to_integral_value(rounding='ROUND_HALF_UP'))
                    white[i + k] = int((comp[k] * 255).to_integral_value(rounding='ROUND_HALF_UP'))
                alpha[i + 3] = int((a * 255).to_integral_value(rounding='ROUND_HALF_UP'))
                white[i + 3] = 255  # the white variant composites onto an opaque medium
    return bytes(alpha), bytes(white)


def build(name, cells, isolated, knockout, background=None, width=None, height=CELL, dest=None, mask=None):
    dest = Path(dest or ROOT)
    width = width or len(cells) * CELL
    pdf = PDF(width, height)
    # Shared resources must exist before the forms that reference them.
    made = set()
    for cell in cells:
        for element in cell[2]:
            kind = element[4] if len(element) > 4 else 'fill'
            if kind in made:
                continue
            if kind == 'text':
                pdf.type3()
            elif kind == 'image':
                pdf.image(element[0])
            elif kind == 'nested':
                pdf.nested(element[0])
            if kind != 'fill':
                made.add(kind)
    content = []
    for index, (x0, y0, elements) in enumerate(cells):
        obj = form(pdf, isolated, knockout, elements)
        pdf.forms.append((index, obj))
        content.append('q 1 0 0 1 %d %d cm /Fm%d Do Q' % (x0, y0, index))
    digest = pdf.finish(dest / (name + '.pdf'), '\n'.join(content), background)
    mask_bytes = bytearray(width * height)
    for index, (x0, y0, elements) in enumerate(cells):
        for y in range(CELL):
            for x in range(CELL):
                inside = mask(index, x, y) if mask else True
                if inside:
                    mask_bytes[(height - 1 - (y0 + y)) * width + (x0 + x)] = 1
    (dest / (name + '.mask')).write_bytes(bytes(mask_bytes))
    alpha, white = expected_pixels(width, height, cells, isolated, knockout, background)
    (dest / (name + '-alpha.rgba')).write_bytes(alpha)
    (dest / (name + '-white.rgba')).write_bytes(white)
    return digest


def scenes():
    """50 original scenes: 16 modes isolated, 16 non-isolated, 10 alpha/coverage,
    6 element kinds (text/image/nested) and 2 antialiased-edge cells."""
    out = {}
    cells = [(i * CELL, 0, [((255, 0, 0), 255, 'Normal', (0, 0, 16, 16), 'fill'),
                            (FG, 128, mode, (0, 0, 16, 16), 'fill')]) for i, mode in enumerate(MODES)]
    out['knockout'] = (cells, True, True, None, None)
    out['knockout-nonisolated'] = (cells, False, True, BG, None)
    shapes = []
    for row, alpha in enumerate((0, 64, 128, 192, 255)):
        shapes.append((row * 2 * CELL, 0, [((255, 0, 0), 255, 'Normal', (0, 0, 16, 16), 'fill'),
                                           (FG, alpha, 'Normal', (0, 0, 16, 16), 'fill')]))
        shapes.append(((row * 2 + 1) * CELL, 0, [((255, 0, 0), 255, 'Normal', (0, 0, 16, 16), 'fill'),
                                                 (FG, alpha, 'Normal', (0, 0, 8, 16), 'fill')]))
    out['knockout-shapes'] = (shapes, True, True, None, None)
    # Element kinds: text (Type3 square glyph), 1x1 image, nested group.
    kinds = [((10, 200, 40), 'text'), ((30, 60, 90), 'image'), ((200, 100, 0), 'nested')]
    elements = []
    for i, (rgb, kind) in enumerate(kinds):
        for j, mode in enumerate(('Normal', 'Multiply')):
            elements.append(((i * 2 + j) * CELL, 0, [((255, 0, 0), 255, 'Normal', (0, 0, 16, 16), 'fill'),
                                                     (rgb, 128, mode, (0, 0, 16, 16), kind)]))
    out['knockout-elements'] = (elements, True, True, None, None)
    # Antialiased edge: element offset by half a pixel; only interior pixels are sampled.
    edges = []
    for row in range(2):
        edges.append((row * CELL, 0, [((255, 0, 0), 255, 'Normal', (0, 0, 16, 16), 'fill'),
                                      (FG, 128, 'Normal', (2.5, 2.5, 13.5, 13.5), 'fill')]))
    out['knockout-edges'] = (edges, True, True, None, lambda index, x, y: 3 <= x <= 12 and 3 <= y <= 12)
    return out


def write_all(dest, update_manifest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    digests = {}
    for name, (cells, isolated, knockout, background, mask) in scenes().items():
        digests[name + '.pdf'] = build(name, cells, isolated, knockout, background, dest=dest, mask=mask)
    if not update_manifest:
        return digests
    manifest_path = ROOT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['sha256'].update(digests)
    manifest['knockout_scenes'] = [
        {'file': 'knockout.pdf', 'isolation': 'isolated', 'scenes': 16, 'reference': 'Decimal(40) ISO 32000-1 11.4.5'},
        {'file': 'knockout-nonisolated.pdf', 'isolation': 'non-isolated', 'scenes': 16, 'reference': 'Decimal(40) ISO 32000-1 11.4.5'},
        {'file': 'knockout-shapes.pdf', 'isolation': 'isolated', 'scenes': 10, 'reference': 'Decimal(40) ISO 32000-1 11.4.5'},
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return digests


def check():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        write_all(tmp, False)
        bad = []
        for name in scenes():
            for suffix in ('.pdf', '.mask', '-alpha.rgba', '-white.rgba'):
                produced = (Path(tmp) / (name + suffix)).read_bytes()
                committed = (ROOT / (name + suffix)).read_bytes()
                if produced != committed:
                    bad.append(name + suffix)
        if bad:
            raise SystemExit('knockout fixtures differ: ' + ', '.join(bad))
    print('knockout fixtures reproduce from the Decimal reference')


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='recompute and compare without writing')
    args = parser.parse_args()
    if args.check:
        check()
        return
    write_all(ROOT, True)
    print('knockout fixtures: 50 scenes, Decimal(40) reference, no external renderer')


if __name__ == '__main__':
    main()
