#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independent Decimal shape/opacity probes for paths, text, groups and images."""
from decimal import Decimal as D, localcontext
import json
from generate_nested_group_fixtures import ROOT, write, MODES
from generate_mask_function_fixtures import stream
from pdf_group_reference import color, over

PRIMITIVES = ['path', 'text', 'group', 'shading', 'soft', 'explicit', 'key', 'compound']


def scene(name, isolated, shape, primitive, rate, ais=None, tail='', mode='Normal', backdrop=False):
    a = rate/255
    bodies = {
        'path': '0 0 16 16 re f', 'text': 'BT /Glyph 16 Tf (A) Tj ET',
        'group': '/Child Do', 'shading': '/Blue sh',
        'soft': '16 0 0 16 0 0 cm /Soft Do',
        'explicit': '16 0 0 16 0 0 cm /Explicit Do',
        'key': '16 0 0 16 0 0 cm /Key Do',
        'compound': '0 1 0 RG 8 w 5 5 6 6 re B',
    }
    resources = ('/ExtGState << /Paint << /ca %.12g /CA %.12g /AIS %s /BM /%s /SMask << /S /Alpha /G 6 0 R >> >> /Other << /AIS %s >> /Empty << >> /Null << /AIS null >> >> '
                 '/XObject << /Child 7 0 R /Soft 9 0 R /Explicit 10 0 R /Key 11 0 R >> '
                 '/Font << /Glyph 12 0 R >> /Shading << /Blue 14 0 R >>') % (a, a/2, ais or ('true' if shape else 'false'), mode, 'false' if shape else 'true')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R /Group << /S /Transparency /I true /CS /DeviceRGB >> /Resources << /XObject << /F 5 0 R >> >> >>',
        stream(('.2 .4 .6 rg 0 0 16 16 re f ' if backdrop else '')+'/F Do'),
        stream('1 0 0 rg 0 0 16 16 re f /Paint gs '+tail+' 0 0 1 rg '+bodies[primitive],
               '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /K true /I %s %s >> /Resources << %s >>' %
               ('true' if isolated else 'false', '/CS /DeviceRGB' if isolated else '', resources)),
        stream('/A gs 1 g 0 0 16 16 re f', '/Type /XObject /Subtype /Form /BBox [0 0 16 16] '
               '/Group << /S /Transparency /I true /CS /DeviceRGB >> /Resources << /ExtGState << /A << /ca %.12g >> >> >>' % (128/255)),
        stream('0 0 1 rg 0 0 16 16 re f', '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true /CS /DeviceRGB >> /Resources << >>'),
        b'null',
        stream(b'\0\0\xff\0\0\xff', '/Type /XObject /Subtype /Image /Width 2 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Interpolate true /SMask 15 0 R'),
        stream(b'\0\0\xff\0\0\xff', '/Type /XObject /Subtype /Image /Width 2 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Interpolate true /Mask 16 0 R'),
        stream(b'\xff\xff\xff\0\0\xff', '/Type /XObject /Subtype /Image /Width 2 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Interpolate true /Mask [255 255 255 255 255 255]'),
        b'<< /Type /Font /Subtype /Type3 /FontBBox [0 0 1000 1000] /FontMatrix [.001 0 0 .001 0 0] /CharProcs << /A 13 0 R >> /Encoding << /Type /Encoding /Differences [65 /A] >> /FirstChar 65 /LastChar 65 /Widths [1000] /Resources << >> >>',
        stream('1000 0 0 0 1000 1000 d1 0 0 1000 1000 re f'),
        b'<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [0 0 16 0] /Extend [true true] /Function << /FunctionType 2 /Domain [0 1] /C0 [0 0 1] /C1 [0 0 1] /N 1 >> >>',
        stream(b'\0\xff', '/Type /XObject /Subtype /Image /Width 2 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Interpolate true'),
        stream(b'\x80', '/Type /XObject /Subtype /Image /Width 2 /Height 1 /ImageMask true /BitsPerComponent 1 /Interpolate true'),
    ]
    return write(name, objects)


def main():
    rows = []
    with localcontext() as ctx:
        ctx.prec = 40
        for isolated in [False, True]:
            for shape in [False, True]:
                for primitive in PRIMITIVES:
                    for rate in [64, 128, 192]:
                        a = D(rate)/255;m = D(128)/255;f = D(1);green = D(0)
                        if primitive == 'compound':
                            stroke = a/2
                            if shape:
                                f = m*(stroke+(1-stroke)*a);alpha = f
                                green = m*stroke;blue = m*(1-stroke)*a
                            else:
                                alpha = m*stroke;green = alpha;blue = D(0)
                        else:
                            if primitive in ['soft', 'explicit', 'key']:
                                m = D(9)/16
                            alpha = a*m;blue = alpha
                            if shape:
                                f = alpha
                            elif primitive in ['explicit', 'key']:
                                f = m
                        pm = [1-f, green, blue, 1-f+alpha]
                        byte = lambda v: int(max(D(0), min(D(255), (v*255+D('.5')))))
                        name = 'alpha-source-%s-%s-%s-%d.pdf' % ('iso' if isolated else 'noniso', 'shape' if shape else 'opacity', primitive, rate)
                        rows.append({'file': name, 'sha256': scene(name, isolated, shape, primitive, rate),
                                     'probe_type': ('shape-' if shape else 'opacity-')+primitive,
                                     'premultiplied': list(map(byte, pm)),
                                     'white': [byte(v+1-pm[3]) for v in pm[:3]]+[255]})
    for shape in [False, True]:
        for state, tail in [('restore', 'q /Other gs Q'), ('retain', '/Empty gs'), ('null', '/Null gs')]:
            name = 'alpha-source-state-%s-%s.pdf' % ('shape' if shape else 'opacity', state)
            reference = next(row for row in rows if row['file'] == 'alpha-source-iso-%s-path-128.pdf' % ('shape' if shape else 'opacity'))
            rows.append({'file': name, 'sha256': scene(name, True, shape, 'path', 128, tail=tail),
                         'probe_type': 'state-'+state,
                         'premultiplied': reference['premultiplied'], 'white': reference['white']})
    with localcontext() as ctx:
        ctx.prec = 40
        for shape in [False, True]:
            for primitive in ['path', 'group']:
                for mode in MODES:
                    a = D(128)/255;m = a;alpha = a*m;f = alpha if shape else D(1)
                    painted = over(color([51, 102, 153, 255]), color([0, 0, 255]), alpha/f, mode)
                    result = [f*v+(1-f)*old for v, old in zip(painted, color([255, 0, 0, 255]))]
                    value = [int(max(D(0), min(D(255), v*255+D('.5')))) for v in result]
                    name = 'alpha-source-blend-%s-%s-%s.pdf' % ('shape' if shape else 'opacity', primitive, mode)
                    rows.append({'file': name, 'sha256': scene(name, False, shape, primitive, 128, mode=mode, backdrop=True),
                                 'probe_type': 'blend-'+('shape-' if shape else 'opacity-')+primitive,
                                 'premultiplied': value, 'white': value})
    rejected = []
    for i, value in enumerate(['1', '/true', '(true)', '[]']):
        name = 'alpha-source-bad-%d.pdf' % i
        rejected.append({'file': name, 'sha256': scene(name, True, False, 'path', 128, value)})
    (ROOT/'alpha-source-manifest.json').write_text(json.dumps({'scenes': rows, 'rejected': rejected}, indent=2)+'\n', encoding='utf-8')
    (ROOT/'alpha-source-oracle.bin').write_bytes(bytes(v for row in rows for key in ['premultiplied', 'white'] for v in row[key]))
    print('%d alpha-source scenes and %d rejected AIS values' % (len(rows), len(rejected)))


if __name__ == '__main__':
    main()
