#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Original clip-wide shading scenes and a Decimal subpixel reference."""
from decimal import Decimal as D, localcontext
from pathlib import Path
import hashlib
import json
from generate_render_audit_fixtures import pdf, stream

ROOT = Path(__file__).resolve().parent.parent/'tests/fixtures/pdf-color'


def parameter(kind, coords, x, y, extend):
    if kind == 2:
        dx, dy = coords[2]-coords[0], coords[3]-coords[1]
        roots = [((x-coords[0])*dx+(y-coords[1])*dy)/(dx*dx+dy*dy)]
    else:
        dx, dy, dr = [coords[i+3]-coords[i] for i in range(3)]
        ox, oy = x-coords[0], y-coords[1]
        a = dx*dx+dy*dy-dr*dr
        b = -2*(ox*dx+oy*dy+coords[2]*dr)
        c = ox*ox+oy*oy-coords[2]*coords[2]
        if not a:
            roots = [-c/b] if b else []
        elif b*b-4*a*c < 0:
            roots = []
        else:
            disc = (b*b-4*a*c).sqrt()
            roots = [(-b-disc)/(2*a), (-b+disc)/(2*a)]
        roots = [t for t in roots if coords[2]+t*dr >= 0]
    roots = [t for t in roots if (t >= 0 or extend[0]) and (t <= 1 or extend[1])]
    return max(roots) if roots else None


def main():
    rows = [];oracle = bytearray()
    cases = [
        (2, '0 0 .01 0'), (2, '100 0 101 0'), (2, '0 100000 16 100000'),
        (3, '0 0 0 0 0 .01'), (3, '100 100 20 100 100 10'),
        (3, '0 8.5 .01 1 8.5 .01'), (3, '0 8.5 20 1 8.5 20'),
    ]
    identity = [D(1), D(0), D(0), D(1), D(0), D(0)]

    def add(kind, text, extend, matrix=identity, alpha=D(1), bbox=None, appearance=False, group=False):
        index = len(rows);name = 'shading-extent-%d.pdf' % index
        coords = list(map(D, text.split()))
        fields = '/ShadingType %d /ColorSpace /DeviceGray /Coords [%s] /Extend [%s %s] /Function 6 0 R' % (
            kind, text, *('true' if v else 'false' for v in extend))
        if bbox: fields += ' /BBox [%s]' % ' '.join(map(str, bbox))
        shading = ('<< '+fields+' >>').encode()
        function = b'<< /FunctionType 2 /Domain [0 1] /C0 [0] /C1 [1] /N 1 >>'
        transform = (' '.join(map(str, matrix))+' cm ').encode()
        resources = ('/ExtGState << /A << /ca %s >> >>' % alpha).encode()
        content = transform+b'/A gs /Sh sh'
        extras = [function];page_extra = b''
        if group:
            extras.append(stream(b'/Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I true /K true /CS /DeviceRGB >> '
                                 b'/Resources << /Shading << /Sh 5 0 R >> '+resources+b' >>', content))
            resources = b'/XObject << /G 7 0 R >>';content = b'/G Do'
        if appearance:
            extras.append(stream(b'/Subtype /Form /BBox [0 0 16 16] /Resources << /Shading << /Sh 5 0 R >> '+resources+b' >>', content))
            page_extra = b'/Annots [<< /Type /Annot /Subtype /Square /Rect [0 0 16 16] /AP << /N 7 0 R >> >>]';content = b''
        pdf(ROOT/name, b'1 0 0 -1 0 16 cm '+content, shading, extras, resources, page_extra, b'0 0 16 16')
        a, b, c, d, tx, ty = matrix;det = a*d-b*c
        expected = bytearray()
        for y in range(16):
            for x in range(16):
                total = D(0);coverage = D(0)
                for sx, sy in [(D('.25'), D('.25')), (D('.75'), D('.25')), (D('.25'), D('.75')), (D('.75'), D('.75'))]:
                    px, py = D(x)+sx-tx, D(y)+sy-ty
                    u, v = (d*px-c*py)/det, (-b*px+a*py)/det
                    t = parameter(kind, coords, u, v, extend)
                    if bbox and not (bbox[0] <= u <= bbox[2] and bbox[1] <= v <= bbox[3]): t = None
                    if t is not None:
                        total += max(D(0), min(D(1), t))/4;coverage += D('.25')
                value = int((total/coverage if coverage else 0)*255+D('.5'))
                opacity = int(coverage*alpha*255+D('.5'))
                expected.extend([value if opacity else 0]*3+[opacity])
        oracle.extend(expected)
        raw = list(expected[(8*16+8)*4:(8*16+8)*4+4]);premul = [(v*raw[3]+127)//255 for v in raw[:3]]+[raw[3]]
        white = [(v*raw[3]+255*(255-raw[3])+127)//255 for v in raw[:3]]+[255]
        rows.append(dict(file=name, sha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),
                         probe=[8, 8], probe_type='clip-wide-%d' % kind, rgba=raw, premultiplied=premul, white=white,
                         kind=kind, coords=text, extend=extend, matrix=list(map(str, matrix)), alpha=str(alpha),
                         appearance=appearance, group=group, rgba_sha256=hashlib.sha256(expected).hexdigest()))

    with localcontext() as ctx:
        ctx.prec = 80
        for kind, coords in cases:
            for extend in [(False, False), (True, False), (False, True), (True, True)]:
                add(kind, coords, extend)
        for kind, coords in [cases[0], cases[3]]:
            add(kind, coords, (True, True), [D(0), D(2), D(-2), D(0), D(16), D(0)])
            add(kind, coords, (True, True), [D(1), D('.25'), D('.5'), D(1), D(0), D(0)])
            add(kind, coords, (True, True), alpha=D('.25'))
            add(kind, coords, (True, True), bbox=list(map(D, [4, 4, 12, 12])))
            add(kind, coords, (True, True), appearance=True)
            add(kind, coords, (True, True), group=True)
    (ROOT/'shading-extent-oracle.rgba').write_bytes(oracle)
    (ROOT/'shading-extent-manifest.json').write_text(json.dumps(dict(scenes=rows), indent=2)+'\n', encoding='utf-8')
    print('%d clip-wide shading scenes; %d reference pixels' % (len(rows), len(oracle)//4))


if __name__ == '__main__':
    main()
