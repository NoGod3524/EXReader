#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Original CMYK ink-preservation scenes; no reference pixels from the renderer."""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import zlib
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent / 'tests/fixtures/pdf-color'
INKS = [(180, 120, 80, 90), (0, 0, 0, 200), (128, 128, 128, 0)]


def stream(data, attrs=''):
    if isinstance(data, str):
        data = data.encode('ascii')
    return ('<< %s /Length %d >>\nstream\n' % (attrs, len(data))).encode() + data + b'\nendstream'


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
    return hashlib.sha256(data).hexdigest()


def scene(name, kind, inks, mode='Normal', variant=''):
    cs = '/DeviceCMYK'
    colour = ' '.join('%.12g' % (v / 255) for v in inks)
    resources = '/ExtGState << /A << /ca .5 /BM /%s >> >> ' % mode
    group = '/Group << /S /Transparency /I true /CS /DeviceCMYK >>'
    base = '.2 .4 .6 .1 k 0 0 16 16 re f /A gs '
    mask = stream(bytes([128]), '/Type /XObject /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 /ColorSpace /DeviceGray')
    if kind == 'image':
        samples, bpc, extra, width, height = bytes(inks), 8, '', 1, 1
        if variant == 'decode':
            samples = bytes(255-v for v in inks)
            extra = '/Decode [1 0 1 0 1 0 1 0]'
        elif variant == '16':
            samples = b''.join(bytes([v, v]) for v in inks)
            bpc = 16
        elif variant in ('mask', 'matte'):
            extra = '/SMask 7 0 R'
            if variant == 'matte':
                mask = stream(bytes([128]), '/Type /XObject /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 '
                              '/ColorSpace /DeviceGray /Matte [.2 .3 .4 .1]')
        elif variant == 'jpeg':
            buf = BytesIO()
            Image.new('CMYK', (1, 1), inks).save(buf, format='JPEG', quality=100, subsampling=0)
            samples = buf.getvalue()
            # Adobe CMYK JPEG stores inverted samples; PDF Decode performs
            # the inversion independently of its APP14 marker.
            extra = '/Filter /DCTDecode /Decode [1 0 1 0 1 0 1 0]'
        elif variant == 'key':
            extra = '/Mask [' + ' '.join('%d %d' % (v, v) for v in inks) + ']'
        elif variant == 'bad-decode':
            extra = '/Decode [0 1 0 1]'
        elif variant == 'bad-mask':
            extra = '/SMask 7 0 R'
            mask = stream(b'\x00\x00\x00', '/Type /XObject /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 /ColorSpace /DeviceRGB')
        elif variant == 'bad-intent':
            extra = '/Intent 9 0 R'
        elif variant == 'budget':
            width = height = 4096
            samples = zlib.compress(bytes(width*height*4), 9)
            extra = '/Filter /FlateDecode /SMask 7 0 R'
        obj = stream(samples, '/Type /XObject /Subtype /Image /Width %d /Height %d /BitsPerComponent %d /ColorSpace %s %s' % (width, height, bpc, cs, extra))
        resources += '/XObject << /I 6 0 R >>'
        body = base + 'q 16 0 0 16 0 0 cm /I Do Q'
    else:
        function = '/Function << /FunctionType 2 /Domain [0 1] /C0 [%s] /C1 [%s] /N 1 >>' % (colour, colour)
        if kind in ('axial', 'radial'):
            coords = '[0 0 16 0]' if kind == 'axial' else '[8 8 0 8 8 16]'
            obj = ('<< /ShadingType %d /ColorSpace %s /Coords %s /Extend [false false] %s >>' %
                   (2 if kind == 'axial' else 3, cs, coords, function)).encode()
        else:
            typ = int(kind[-1])
            attrs = '/ShadingType %d /ColorSpace %s /BitsPerCoordinate 8 /BitsPerComponent 8 /Decode [0 16 0 16 0 1 0 1 0 1 0 1]' % (typ, cs)
            if typ in (4, 5):
                points = [(0, 0), (255, 0), (0, 255)] + ([(255, 255)] if typ == 5 else [])
                data = b''.join((b'\0' if typ == 4 else b'') + bytes(p) + bytes(inks) for p in points)
                attrs += ' /BitsPerFlag 8' if typ == 4 else ' /VerticesPerRow 2'
            else:
                points = [(0, 0), (0, 85), (0, 170), (0, 255), (85, 255), (170, 255),
                          (255, 255), (255, 170), (255, 85), (255, 0), (170, 0), (85, 0)]
                if typ == 7:
                    points += [(85, 85), (85, 170), (170, 170), (170, 85)]
                data = b'\0' + b''.join(bytes(p) for p in points) + bytes(inks)*4
                attrs += ' /BitsPerFlag 8'
            obj = stream(data, attrs)
        resources += '/Shading << /S 6 0 R >>'
        body = base + '/S sh'
    page_group = group if variant == 'page' else ''
    annots = '/Annots [8 0 R]' if variant == 'appearance' else ''
    page_content = body if variant == 'page' else '' if annots else '/F Do'
    page_resources = resources.replace('/I 6 0 R', '/I 6 0 R /F 5 0 R') if kind == 'image' else resources + ' /XObject << /F 5 0 R >>'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        ('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R %s %s '
         '/Resources << %s >> >>' % (page_group, annots, page_resources)).encode(),
        stream(page_content),
        stream(body, '/Type /XObject /Subtype /Form /BBox [0 0 16 16] %s /Resources << %s >>' % (group, resources)),
        obj, mask,
        b'<< /Type /Annot /Subtype /Stamp /Rect [0 0 16 16] /AP << /N 5 0 R >> >>',
    ]
    if variant == 'bad-intent':
        objects.append(b'9 0 R')
    return write(name, objects)


def main():
    manifest = {}
    for kind in ['image', 'axial', 'radial', 'mesh4', 'mesh5', 'mesh6', 'mesh7']:
        for i, inks in enumerate(INKS):
            for mode in ['Normal', 'Multiply', 'Screen']:
                name = 'native-%s-%d-%s.pdf' % (kind, i, mode.lower())
                manifest[name] = scene(name, kind, inks, mode)
    for variant in ['decode', '16', 'mask', 'matte', 'jpeg', 'key', 'page', 'appearance', 'bad-decode', 'bad-mask', 'bad-intent', 'budget']:
        name = 'native-image-' + variant + '.pdf'
        manifest[name] = scene(name, 'image', INKS[0], variant=variant)
    (ROOT / 'native-ink-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print('Generated %d native ink PDFs' % len(manifest))


if __name__ == '__main__':
    main()
