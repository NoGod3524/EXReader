#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Original scalar transfer functions and image-mask precedence probes."""
import json
from generate_nested_group_fixtures import ROOT, write, stream as text_stream


def stream(body, attrs=''):
    if isinstance(body, str):
        return text_stream(body, attrs)
    return ('<< %s /Length %d >>\nstream\n' % (attrs, len(body))).encode()+body+b'\nendstream'


def scene(name, kind, alpha, function=None, image=None):
    luminosity = kind == 'luminosity'
    mask_body = ('%.12g g ' % (alpha/255) if luminosity else '/A gs 1 g ')+'0 0 16 16 re f'
    tr = '/TR 7 0 R' if function else ''
    body = '/M gs '+('16 0 0 16 0 0 cm /Im Do' if image else '0 0 1 rg 0 0 16 16 re f')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R /Resources << /ExtGState << /M 5 0 R >> /XObject << /Im 8 0 R >> >> >>',
        stream(body),
        ('<< /SMask << /S /%s /G 6 0 R %s >> >>' % ('Luminosity' if luminosity else 'Alpha', tr)).encode(),
        stream(mask_body, '/Type /XObject /Subtype /Form /BBox [0 0 16 16] '
               '/Group << /S /Transparency /I true /CS /DeviceRGB >> '
               '/Resources << /ExtGState << /A << /ca %.12g >> >> >>' % (alpha/255)),
        function or b'null',
    ]
    if image:
        own = {'none': '', 'soft': '/SMask 9 0 R', 'explicit': '/Mask 10 0 R',
               'key-visible': '/Mask [255 255 0 0 0 0]',
               'key-hidden': '/Mask [0 0 0 0 255 255]',
               'both': '/SMask 9 0 R /Mask [0 0 0 0 255 255]'}[image]
        objects.extend([
            stream(b'\0\0\xff', '/Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 '+own),
            stream(b'\x80', '/Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8'),
            stream(b'\0', '/Type /XObject /Subtype /Image /Width 1 /Height 1 /ImageMask true /BitsPerComponent 1'),
        ])
    return write(name, objects)


def main():
    functions = {
        'sampled': stream(b'\xff\0', '/FunctionType 0 /Domain [0 1] /Range [0 1] /Size [2] /BitsPerSample 8'),
        'exponential': b'<< /FunctionType 2 /Domain [0 1] /C0 [1] /C1 [0] /N 1 >>',
        'stitching': b'<< /FunctionType 3 /Domain [0 1] /Range [0 1] /Functions [<< /FunctionType 2 /Domain [0 1] /C0 [1] /C1 [.5] /N 1 >> << /FunctionType 2 /Domain [0 1] /C0 [.5] /C1 [0] /N 1 >>] /Bounds [.5] /Encode [0 1 0 1] >>',
        'calculator': stream('{ 1 exch sub }', '/FunctionType 4 /Domain [0 1] /Range [0 1]'),
        'identity': b'/Identity',
        'domain': b'<< /FunctionType 2 /Domain [0 .5] /Range [.1 .4] /C0 [0] /C1 [1] /N 1 >>',
        'square': b'<< /FunctionType 2 /Domain [0 1] /C0 [0] /C1 [1] /N 2 >>',
    }
    rows = []
    for kind in ['alpha', 'luminosity']:
        for function, data in functions.items():
            for alpha in [64, 128, 192]:
                name = 'mask-function-%s-%s-%d.pdf' % (kind, function, alpha)
                a = alpha/255
                m = a if function == 'identity' else min(.4, max(.1, min(.5, a))) if function == 'domain' else a*a if function == 'square' else 1-a
                # Raster results are rounded to an 8-bit mask before application.
                m = int(m*255+.5)
                rows.append({'file': name, 'sha256': scene(name, kind, alpha, data),
                             'premultiplied': [0, 0, m, m], 'white': [255-m, 255-m, 255, 255]})
    for image in ['none', 'soft', 'explicit', 'key-visible', 'key-hidden', 'both']:
        for alpha in [64, 128, 192]:
            name = 'mask-function-image-%s-%d.pdf' % (image, alpha)
            m = alpha if image == 'none' else 128 if image in ['soft', 'both'] else 0 if image == 'key-hidden' else 255
            rows.append({'file': name, 'sha256': scene(name, 'alpha', alpha, image=image),
                         'probe_type': 'image-mask-'+image,
                         'premultiplied': [0, 0, m, m], 'white': [255-m, 255-m, 255, 255]})
    for kind in ['alpha', 'luminosity']:
        for geometry in ['rotated-inside', 'rotated-outside', 'outside-zero', 'outside-inverse', 'knockout', 'nonisolated']:
            name = 'mask-function-%s-%s.pdf' % (kind, geometry)
            bbox = '[32 32 40 40]' if geometry.startswith('outside-') else '[0 0 8 8]' if geometry.startswith('rotated-') else '[0 0 16 16]'
            matrix = '[1 1 -1 1 8 0]' if geometry == 'rotated-inside' else '[1 1 -1 1 2 2]' if geometry == 'rotated-outside' else '[1 0 0 1 0 0]'
            group = '/S /Transparency /I false /CS /DeviceRGB' if geometry == 'nonisolated' else '/S /Transparency /I true /CS /DeviceRGB'+(' /K true' if geometry == 'knockout' else '')
            bc = '/BC [.5 .5 .5]' if kind == 'luminosity' and geometry == 'nonisolated' else ''
            tr = '/TR << /FunctionType 2 /Domain [0 1] /C0 [1] /C1 [0] /N 1 >>' if geometry == 'outside-inverse' else ''
            body = '/A gs 1 g -64 -64 128 128 re f'
            m = 128
            if geometry == 'knockout':
                body = '/A gs 1 g 0 0 16 16 re f /B gs 1 g 0 0 16 16 re f';m = 64
            if geometry == 'nonisolated' and kind == 'luminosity':
                body = '/Multiply gs 1 0 0 rg 0 0 16 16 re f';m = 38
            if geometry in ['rotated-outside', 'outside-zero']:
                m = 0
            if geometry == 'outside-inverse':
                m = 255
            objects = [
                b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
                b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R /Resources << /ExtGState << /M 5 0 R >> >> >>',
                stream('/M gs 0 0 1 rg 0 0 16 16 re f'),
                ('<< /SMask << /S /%s /G 6 0 R %s %s >> >>' % ('Alpha' if kind == 'alpha' else 'Luminosity', bc, tr)).encode(),
                stream(body, '/Type /XObject /Subtype /Form /BBox %s /Matrix %s /Group << %s >> '
                       '/Resources << /ExtGState << /A << /ca %.12g >> /B << /ca %.12g >> /Multiply << /BM /Multiply >> >> >>' % (bbox, matrix, group, 128/255, 64/255)),
            ]
            rows.append({'file': name, 'sha256': write(name, objects), 'probe_type': 'mask-geometry-'+geometry,
                         'premultiplied': [0, 0, m, m], 'white': [255-m, 255-m, 255, 255]})
    invalid = {
        'name': b'/Bogus', 'scalar': b'42',
        'outputs': b'<< /FunctionType 2 /Domain [0 1] /C0 [0 0] /C1 [1 1] /N 1 >>',
        'domain': b'<< /FunctionType 2 /Domain [1 0] /N 1 >>',
        'cycle': b'<< /FunctionType 3 /Domain [0 1] /Functions [7 0 R] /Bounds [] /Encode [0 1] >>',
        'calculator': stream('{ pop pop }', '/FunctionType 4 /Domain [0 1] /Range [0 1]'),
        'samples': stream(b'', '/FunctionType 0 /Domain [0 1] /Range [0 1] /Size [2] /BitsPerSample 8'),
        'missing-type': b'<< /Domain [0 1] >>',
    }
    rejected = []
    for kind, data in invalid.items():
        name = 'mask-function-bad-'+kind+'.pdf'
        rejected.append({'file': name, 'sha256': scene(name, 'alpha', 128, data)})
    (ROOT/'mask-function-manifest.json').write_text(json.dumps({'scenes': rows, 'rejected': rejected}, indent=2)+'\n', encoding='utf-8')
    (ROOT/'mask-function-oracle.bin').write_bytes(bytes(v for row in rows for key in ['premultiplied', 'white'] for v in row[key]))
    print('%d valid and %d rejected mask function/image precedence probes' % (len(rows), len(rejected)))


if __name__ == '__main__':
    main()
