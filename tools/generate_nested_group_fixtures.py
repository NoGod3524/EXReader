#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Nested knockout/source-alpha regressions and Decimal(40) interior probes."""
from decimal import Decimal as D, localcontext
import hashlib
import json
from pathlib import Path
from pdf_group_reference import group, over, color

ROOT = Path(__file__).resolve().parent.parent / 'tests/fixtures/pdf-blend'
MODES = 'Normal Multiply Screen Overlay Darken Lighten ColorDodge ColorBurn HardLight SoftLight Difference Exclusion Hue Saturation Color Luminosity'.split()


def stream(body, attrs=''):
    body = body.encode()
    return ('<< %s /Length %d >>\nstream\n' % (attrs, len(body))).encode() + body + b'\nendstream'


def write(name, objects):
    data = bytearray(b'%PDF-1.7\n');offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data));data += ('%d 0 obj\n' % i).encode()+obj+b'\nendobj\n'
    xref = len(data)
    data += ('xref\n0 %d\n0000000000 65535 f \n' % len(offsets)).encode()
    for offset in offsets[1:]:
        data += ('%010d 00000 n \n' % offset).encode()
    data += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offsets), xref)).encode()
    (ROOT/name).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def gs(alpha, mode='Normal'):
    return '<< /ca %.12g /BM /%s >>' % (alpha/255, mode)


def main():
    rows = [];oracle = bytearray()
    for isolated in [False, True]:
        for child_isolated in [False, True]:
            for background_alpha in [64, 192]:
                for mode in MODES:
                    name = 'nested-%03d.pdf' % len(rows)
                    outer = '/S /Transparency /K true /I ' + ('true /CS /DeviceRGB' if isolated else 'false')
                    inner = '/S /Transparency /I ' + ('true /CS /DeviceRGB' if child_isolated else 'false')
                    sha = write(name, [
                        b'<< /Type /Catalog /Pages 2 0 R >>',
                        b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
                        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R /Group << /S /Transparency /I true /CS /DeviceRGB >> '
                        b'/Resources << /XObject << /F 5 0 R >> /ExtGState << /B '+gs(background_alpha).encode()+b' /G '+gs(160, mode).encode()+b' >> >> >>',
                        stream('/B gs .2 .4 .6 rg 0 0 16 16 re f /G gs /F Do'),
                        stream('/A gs 1 0 0 rg 0 0 16 16 re f /G gs /C Do',
                               '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << %s >> '
                               '/Resources << /ExtGState << /A %s /G %s >> /XObject << /C 6 0 R >> >>' % (outer, gs(192), gs(128))),
                        stream('/A gs 0 0 1 rg 0 0 16 16 re f /B gs 0 1 0 rg 0 0 16 16 re f',
                               '/Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << %s >> '
                               '/Resources << /ExtGState << /A %s /B %s >> >>' % (inner, gs(64, 'Multiply'), gs(128, 'Screen'))),
                    ])
                    with localcontext() as ctx:
                        ctx.prec = 40
                        back = tuple(v*D(background_alpha)/255 for v in color((51, 102, 153)))+(D(background_alpha)/255,)
                        child = lambda bg: group(bg, [(color((0, 0, 255)), D(64)/255, 'Multiply'),
                                                      (color((0, 255, 0)), D(128)/255, 'Screen')], isolated=child_isolated)
                        src, alpha = group(back, [(color((255, 0, 0)), D(192)/255, 'Normal'), (child, D(128)/255, 'Normal')],
                                           isolated=isolated, knockout=True)
                        result = over(back, src, alpha*D(160)/255, mode)
                        byte = lambda v: max(0, min(255, int((v*255).to_integral_value(rounding='ROUND_HALF_UP'))))
                        expected = list(map(byte, result))
                        white = [byte(v+1-result[3]) for v in result[:3]]+[255]
                    oracle.extend(expected+white)
                    rows.append({'file': name, 'sha256': sha, 'isolated': isolated, 'child_isolated': child_isolated,
                                 'background_alpha': background_alpha, 'mode': mode,
                                 'premultiplied': expected, 'white': white})
    (ROOT/'nested-oracle.bin').write_bytes(oracle)
    (ROOT/'nested-manifest.json').write_text(json.dumps({'reference': 'Decimal(40), source alpha excludes initial backdrop',
                                                       'scenes': rows}, indent=2)+'\n', encoding='utf-8')
    print('Generated %d nested group scenes' % len(rows))


if __name__ == '__main__':
    main()
