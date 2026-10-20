#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Original non-unit shading domains and malformed numeric/array fields."""
from decimal import Decimal as D
from pathlib import Path
import hashlib
import json
from generate_render_audit_fixtures import pdf
from generate_mask_function_fixtures import stream

ROOT = Path(__file__).resolve().parent.parent/'tests/fixtures/pdf-color'


def main():
    u = D('8.5')/16
    linear = b'<< /FunctionType 2 /Domain [0 1] /C0 [0] /C1 [1] /N 1 >>'
    huge = '1'+'0'*300+'.0'
    cases = [
        ('[2 4]', b'<< /FunctionType 2 /Domain [2 4] /C0 [-1] /C1 [-.5] /N 1 >>', u),
        ('[-1 1]', stream('{ 1 add 2 div }', '/FunctionType 4 /Domain [-1 1] /Range [0 1]'), u),
        ('[10 20]', stream('{ 10 sub 10 div }', '/FunctionType 4 /Domain [10 20] /Range [0 1]'), u),
        (None, linear, u), ('[0 1]', linear, u), ('[-1 2]', linear, -1+3*u),
        ('[%s %s]' % (huge, huge), linear, D(1)),
        ('[5 5]', stream('{ 10 div }', '/FunctionType 4 /Domain [0 10] /Range [0 1]'), D('.5')),
        ('null', linear, u),
    ]
    rows = [];oracle = bytearray()
    for i, (domain, function, value) in enumerate(cases):
        name = 'shading-domain-%d.pdf' % i
        shading = ('<< /ShadingType 2 /ColorSpace /DeviceGray /Coords [0 0 16 0] /Function 6 0 R %s >>' % ('/Domain '+domain if domain else '')).encode()
        pdf(ROOT/name, b'/Sh sh', shading, (function,))
        byte = int(max(D(0), min(D(255), value*255+D('.5'))))
        expected = [byte, byte, byte, 255];oracle.extend(expected)
        rows.append({'file': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), 'probe': [8, 8],
                     'probe_type': 'axial-ramp-sampling', 'rgba': expected,
                     'premultiplied': expected, 'white': expected})
    base = '<< /ShadingType %s /ColorSpace /DeviceGray /Coords %s /Function 6 0 R %s >>'
    invalid = [('2.5', '[0 0 16 0]', ''), (huge, '[0 0 16 0]', ''), ('/Two', '[0 0 16 0]', ''),
               ('2', '[0 0 16 0]', '/Domain [0]'), ('2', '[0 0 16 0]', '/Domain [0 1 2]'),
               ('2', '[0 0 16 0]', '/Domain [1 0]'), ('2', '[0 0 16 0]', '/Domain /Bad'),
               ('2', '[0 0 16 0]', '/Extend [true]'), ('2', '[0 0 16 0]', '/Extend [true false false]'),
               ('2', '[0 0 16 0]', '/Extend false'), ('2', '[0 0 16 0 8]', '')]
    rejected = []
    for i, params in enumerate(invalid):
        name = 'shading-domain-bad-%d.pdf' % i
        pdf(ROOT/name, b'/Sh sh', (base % params).encode(), (linear,))
        rejected.append({'file': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest()})
    (ROOT/'shading-domain-oracle.bin').write_bytes(oracle)
    (ROOT/'shading-domain-manifest.json').write_text(json.dumps({'scenes': rows, 'rejected': rejected}, indent=2)+'\n', encoding='utf-8')
    print('%d domain scenes and %d malformed shading inputs' % (len(rows), len(rejected)))


if __name__ == '__main__':
    main()
