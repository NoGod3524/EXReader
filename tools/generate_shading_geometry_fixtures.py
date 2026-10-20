#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Original radial-root and temporary shading-rectangle regressions."""
from decimal import Decimal as D, localcontext
from pathlib import Path
import hashlib
import json
from generate_render_audit_fixtures import pdf, stream
from generate_pdf_shading_mesh7_fixture import encode_patch

ROOT = Path(__file__).resolve().parent.parent/'tests/fixtures/pdf-color'


def main():
    rows = [];oracle = bytearray()
    function = b'<< /FunctionType 2 /Domain [0 1] /C0 [0] /C1 [1] /N 1 >>'

    def add(shading, probes, content=b'/Sh sh', extras=(function,), resources=b'', kind='bbox', transparent=False):
        name = 'shading-geometry-%d.pdf' % len(rows)
        pdf(ROOT/name, b'1 0 0 -1 0 16 cm '+content, shading, extras, resources, media_box=b'0 0 16 16')
        for x, y, gray, tolerance in probes:
            rgba = [gray]*3+[255]
            oracle.extend([len(rows), x, y, *rgba, tolerance])
        x, y, gray, tolerance = probes[0]
        rgba = [gray]*3+[255]
        rows.append({'file': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),
                     'probe': [x, y], 'probe_type': kind, 'rgba': [0]*4 if transparent else rgba, 'premultiplied': [0]*4 if transparent else rgba,
                     'white': rgba, 'tolerance': tolerance, 'additional_probes': probes[1:]})

    def radial(coords, extend, gray, prefix=b'', tolerance=3, kind='radial-root', transparent=False):
        shading = ('<< /ShadingType 3 /ColorSpace /DeviceGray /Coords [%s] /Extend [%s] /Function 6 0 R >>' % (coords, extend)).encode()
        add(shading, [(8, 8, gray, tolerance)], prefix+b'/Sh sh', kind=kind, transparent=transparent)

    radial('0 8.5 4 16 8.5 4', 'false false', 199)  # Larger of two in-range roots: .78125.
    radial('0 8.5 10 16 8.5 10', 'true false', 0)  # Negative root survives; positive root is outside.
    radial('0 8.5 10 16 8.5 10', 'false true', 255)
    radial('0 8.5 10 16 8.5 10', 'false false', 255, tolerance=0, transparent=True)
    radial('0 8.5 0 16 8.5 16', 'false false', 68)  # Linear cone equation.
    radial('8.5 8.5 0 8.5 8.5 0', 'true true', 255, tolerance=0, transparent=True)
    radial('8.5 8.5 12 8.5 8.5 4', 'false true', 255)
    with localcontext() as ctx:
        ctx.prec = 60
        gray = int(((D('8.5')**2*2).sqrt()/16*255+D('.5')))
    radius = '16'+'0'*200+'.0'
    small = '0.'+'0'*199+'1'
    radial('0 0 0 0 0 '+radius, 'false false', gray,
           (small+' 0 0 '+small+' 0 0 cm ').encode(), kind='scaled-large-radial')

    axial = b'<< /ShadingType 2 /ColorSpace /DeviceGray /Coords [0 0 16 0] /Function 6 0 R '
    for box, prefix in [('4 4 12 12', b''), ('12 12 4 4', b''), ('4 4 12 12', b'1 .25 .5 1 0 0 cm '),
                        ('4 4 12 12', b'0 1 -1 0 16 0 cm '), ('4 4 4 12', b'')]:
        value = 135 if not prefix else (77 if prefix.startswith(b'1 ') else 135)
        if box=='4 4 4 12': value=255
        add(axial+('/BBox [%s] >>' % box).encode(), [(8, 8, value, 3), (1, 1, 255, 0)], prefix+b'/Sh sh', transparent=box=='4 4 4 12')
    add(axial+b'/BBox [4 4 12 12] >>', [(8, 8, 0, 0), (1, 1, 0, 0)], b'/Sh sh 0 g 0 0 100 100 re f')
    add(axial+b'/BBox [4 4 12 12] /Background [0] >>', [(8, 8, 135, 1), (1, 1, 255, 0)])

    square = [(0, 0), (0, 85), (0, 170), (0, 255), (85, 255), (170, 255), (255, 255),
              (255, 170), (255, 85), (255, 0), (170, 0), (85, 0)]
    interior = [(85, 85), (85, 170), (170, 170), (170, 85)]
    for kind in [4, 5, 6, 7]:
        if kind==4:
            data = b''.join(bytes([0, x, y, 0]) for x, y in [(0, 0), (255, 0), (0, 255)])
        elif kind==5:
            data = b''.join(bytes([x, y, 0]) for x, y in [(0, 0), (255, 0), (0, 255), (255, 255)])
        else:
            data = encode_patch(square+(interior if kind==7 else []), [(0,)]*4, kind==7, False)
        fields = ('/ShadingType %d /ColorSpace /DeviceGray /BitsPerCoordinate 8 /BitsPerComponent 8 '
                  '/BitsPerFlag 8 /Decode [0 1 0 1 0 1] /BBox [0 0 .04 .04] ' % kind).encode()
        if kind==5: fields+=b'/VerticesPerRow 2 '
        add(stream(fields, data), [(8, 8, 255, 0), (1, 1, 0, 3)], b'100 0 0 100 0 0 cm /Sh sh', extras=(), transparent=True)

    bad = []
    for i, bbox in enumerate(['/Bad', '[0 0 4]', '[0 0 4 4 5]', '[0 false 4 4]']):
        name = 'shading-geometry-bad-%d.pdf' % i
        pdf(ROOT/name, b'/Sh sh', axial+('/BBox %s >>' % bbox).encode(), (function,), media_box=b'0 0 16 16')
        bad.append({'file': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest()})
    (ROOT/'shading-geometry-oracle.bin').write_bytes(oracle)
    (ROOT/'shading-geometry-manifest.json').write_text(json.dumps({'scenes': rows, 'rejected': bad}, indent=2)+'\n', encoding='utf-8')
    print('%d geometry scenes, %d probes, %d rejected inputs' % (len(rows), len(oracle)//8, len(bad)))


if __name__=='__main__':
    main()
