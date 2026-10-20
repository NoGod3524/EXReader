#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Function-based shadings and bounded per-component function bundles."""
from pathlib import Path
import hashlib
import json
import re
import pymupdf
from generate_render_audit_fixtures import pdf, stream
from generate_pdf_shading_mesh7_fixture import encode_patch

ROOT = Path(__file__).resolve().parent.parent/'tests/fixtures/pdf-color'


def main():
    rows = [];rejected = [];oracle = bytearray()

    def add(shading, functions, expected, kind, content=b'/Sh sh', status=0):
        name = 'shading-function-%d.pdf' % (len(rows)+len(rejected))
        pdf(ROOT/name, b'1 0 0 -1 0 16 cm '+content, shading, functions, media_box=b'0 0 16 16')
        row = {'file': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest()}
        index = int(name.split('-')[-1][:-4])
        if status:
            row['status'] = status;rejected.append(row);oracle.extend([index, status, 0, 0, 0, 0]);return
        white = expected if expected[3] else [255]*4
        row.update(probe=[8, 8], probe_type=kind, rgba=expected, premultiplied=expected, white=white)
        rows.append(row);oracle.extend([index, 0, *white])

    calc = stream(b'/FunctionType 4 /Domain [0 1 0 1] /Range [0 1 0 1 0 1]', b'{ 0 }')
    base = b'<< /ShadingType 1 /ColorSpace /DeviceRGB /Matrix [16 0 0 16 0 0] /Function 6 0 R '
    add(base+b'>>', (calc,), [135, 135, 0, 255], 'function2d-default')
    add(base+b'/Domain [0 1 0 1] >>', (calc,), [135, 135, 0, 255], 'function2d-domain')
    add(base+b'/Domain null >>', (calc,), [135, 135, 0, 255], 'function2d-null')
    sampled = stream(b'/FunctionType 0 /Domain [0 1 0 1] /Range [0 1 0 1 0 1] /Size [2 2] /BitsPerSample 8',
                     bytes([0, 0, 0, 255, 0, 0, 0, 255, 0, 255, 255, 0]))
    add(base+b'>>', (sampled,), [135, 135, 0, 255], 'function2d-sampled')
    scalar_domains = [stream(b'/FunctionType 4 /Domain [0 1 0 1] /Range [0 1]', source)
                      for source in [b'{ exch pop }', b'{ pop }', b'{ pop pop .25 }']]
    add(base.replace(b'6 0 R', b'[6 0 R 7 0 R 8 0 R]')+b'>>', tuple(scalar_domains), [135, 135, 64, 255], 'function2d-array')
    calc_nonunit = stream(b'/FunctionType 4 /Domain [-1 1 2 4] /Range [0 1 0 1 0 1]', b'{ 2 sub 2 div exch 1 add 2 div exch .25 }')
    add(base.replace(b'[16 0 0 16 0 0]', b'[8 0 0 8 8 -16]')+b'/Domain [-1 1 2 4] >>',
        (calc_nonunit,), [135, 135, 64, 255], 'function2d-nonunit')
    add(base.replace(b'[16 0 0 16 0 0]', b'[0 16 -16 0 16 0]')+b'>>', (calc,), [135, 120, 0, 255], 'function2d-rotated')

    constant = lambda value: ('<< /FunctionType 2 /Domain [0 1] /C0 [%s] /C1 [%s] /N 1 >>' % (value, value)).encode()
    ramp = b'<< /FunctionType 2 /Domain [0 1] /C0 [0] /C1 [1] /N 1 >>'
    components = (ramp, constant('.25'), constant('.75'))
    for kind in [2, 3]:
        coords = '[0 0 16 0]' if kind==2 else '[0 0 0 0 0 16]'
        shading = ('<< /ShadingType %d /ColorSpace /DeviceRGB /Coords %s /Function [6 0 R 7 0 R 8 0 R] >>' % (kind, coords)).encode()
        add(shading, components, [135 if kind==2 else 192, 64, 191, 255], 'component-array-%d' % kind)

    square = [(0, 0), (0, 85), (0, 170), (0, 255), (85, 255), (170, 255), (255, 255),
              (255, 170), (255, 85), (255, 0), (170, 0), (85, 0)]
    interior = [(85, 85), (85, 170), (170, 170), (170, 85)]
    for kind in [4, 5, 6, 7]:
        if kind==4:
            data = b''.join(bytes([0, x, y, 128]) for x, y in [(0, 0), (255, 0), (0, 255)])
        elif kind==5:
            data = b''.join(bytes([x, y, 128]) for x, y in [(0, 0), (255, 0), (0, 255), (255, 255)])
        else:
            data = encode_patch(square+(interior if kind==7 else []), [(128,)]*4, kind==7, False)
        fields = ('/ShadingType %d /ColorSpace /DeviceRGB /BitsPerCoordinate 8 /BitsPerComponent 8 /BitsPerFlag 8 '
                  '/Decode [0 1 0 1 0 1] /Function [6 0 R 7 0 R 8 0 R] ' % kind).encode()
        if kind==5: fields+=b'/VerticesPerRow 2 '
        add(stream(fields, data), components, [128, 64, 191, 255], 'component-array-%d' % kind,
            content=b'32 0 0 32 0 0 cm /Sh sh')

    # Two further component bundles per shading type: scalar Gray and a mixed
    # calculator/sampled/stitching RGB bundle. Use the already generated source
    # dictionaries so geometry and stream packing remain identical.
    sampled_constant = stream(b'/FunctionType 0 /Domain [0 1] /Range [0 1] /Size [2] /BitsPerSample 8', bytes([64, 64]))
    stitched = (b'<< /FunctionType 3 /Domain [0 1] /Functions [<< /FunctionType 2 /Domain [0 1] '
                b'/C0 [.75] /C1 [.75] /N 1 >>] /Bounds [] /Encode [0 1] >>')
    invert = stream(b'/FunctionType 4 /Domain [0 1] /Range [0 1]', b'{ 1 exch sub }')
    original = list(rows[7:13])
    for row in original:
        with pymupdf.open(ROOT/row['file']) as source:
            kind = int(source.xref_get_key(5, 'ShadingType')[1])
            dictionary = source.xref_object(5, compressed=True).encode()
            # Obtain the original raw stream without retaining /Length from its
            # serialized dictionary. All fixtures here use unfiltered streams.
            raw = source.xref_stream(5) if kind>=4 else None
        dictionary = dictionary.replace(b'/Function[6 0 R 7 0 R 8 0 R]', b'/Function[6 0 R]')
        dictionary = dictionary.replace(b'/ColorSpace/DeviceRGB', b'/ColorSpace/DeviceGray')
        if raw is not None:
            dictionary = re.sub(rb'/Length\s*\d+', b'', dictionary)
            gray_shading = stream(dictionary[2:-2], raw)
        else: gray_shading = dictionary
        value = row['rgba'][0]
        add(gray_shading, (ramp,), [value]*3+[255], 'component-gray-%d' % kind,
            content=b'32 0 0 32 0 0 cm /Sh sh' if kind>=4 else b'/Sh sh')
        dictionary = dictionary.replace(b'/Function[6 0 R]', b'/Function[6 0 R 7 0 R 8 0 R]')
        dictionary = dictionary.replace(b'/ColorSpace/DeviceGray', b'/ColorSpace/DeviceRGB')
        mixed = stream(dictionary[2:-2], raw) if raw is not None else dictionary
        add(mixed, (invert, sampled_constant, stitched), [255-value, 64, 191, 255], 'component-mixed-%d' % kind,
            content=b'32 0 0 32 0 0 cm /Sh sh' if kind>=4 else b'/Sh sh')
        for functions in [b'[]', b'[6 0 R null 8 0 R]']:
            bad = dictionary.replace(b'/Function[6 0 R 7 0 R 8 0 R]', b'/Function'+functions)
            add(stream(bad[2:-2], raw) if raw is not None else bad, components, None, 'bad-components-%d' % kind,
                content=b'32 0 0 32 0 0 cm /Sh sh' if kind>=4 else b'/Sh sh', status=5)

    for field in [b'/Domain [0 1]', b'/Domain [0 1 0 1 2]', b'/Domain [1 0 0 1]', b'/Matrix [1 0 0 1 0]', b'/Matrix /Bad']:
        # Replace Matrix when testing it; duplicate keys would obscure the fixture.
        badbase = base.replace(b'/Matrix [16 0 0 16 0 0] ', b'') if field.startswith(b'/Matrix') else base
        add(badbase+field+b' >>', (calc,), None, 'bad', status=5)
    for functions, extra, status in [(b'[]', components, 5), (b'[6 0 R 7 0 R]', components, 5),
                                      (b'[6 0 R 7 0 R 8 0 R 6 0 R 7 0 R]', components, 6),
                                      (b'[6 0 R null 8 0 R]', components, 5),
                                      (b'[6 0 R 7 0 R 8 0 R]', (b'<< /FunctionType 2 /Domain [0 1] /C0 [0 0] /C1 [1 1] /N 1 >>', *components[1:]), 5)]:
        bad = b'<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [0 0 16 0] /Function '+functions+b' >>'
        add(bad, extra, None, 'bad-array', status=status)

    large_scalar = stream(b'/FunctionType 0 /Domain [0 1] /Range [0 1] /Size [524288] /BitsPerSample 8', bytes([128])*524288)
    add(b'<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [0 0 16 0] /Function [6 0 R 6 0 R 6 0 R] >>',
        (large_scalar,), None, 'aggregate-function-budget', status=6)
    add(base.replace(b'/Function 6 0 R', b'/Function [6 0 R 7 0 R 8 0 R]')+b'>>',
        (b'[6 0 R]', *scalar_domains[1:]), None, 'recursive-component-array', status=5)
    for kind in [1, 2, 3]:
        coords = b'' if kind==1 else (b'/Coords [0 0 16 0] ' if kind==2 else b'/Coords [0 0 0 0 0 16] ')
        add(b'<< /ShadingType %d /ColorSpace [/Indexed /DeviceRGB 1 <000000FFFFFF>] ' % kind+coords+b'/Function 6 0 R >>',
            (calc if kind==1 else ramp,), None, 'invalid-indexed-shading', status=5)

    add(base.replace(b'[16 0 0 16 0 0]', b'[16 4 8 16 0 0]')+b'>>', (calc,), [77, 116, 0, 255], 'function2d-shear')
    add(base+b'/BBox [0 0 4 4] >>', (calc,), [0]*4, 'function2d-bbox')
    add(base+b'/Domain [0 0 0 1] >>', (calc,), [0]*4, 'function2d-empty-domain')
    add(base.replace(b'[16 0 0 16 0 0]', b'[0 0 0 16 0 0]')+b'>>', (calc,), [0]*4, 'function2d-singular')
    add(base+b'>>', (ramp,), None, 'function2d-wrong-input-dimension', status=5)
    bad_calculator = stream(b'/FunctionType 4 /Domain [0 1 0 1] /Range [0 1 0 1 0 1]', b'{ 0 div }')
    add(base+b'>>', (bad_calculator,), None, 'function2d-evaluation-error', status=5)

    ink_function = stream(b'/FunctionType 4 /Domain [0 1 0 1] /Range [0 1 0 1 0 1 0 1]', b'{ pop pop .25 .5 .75 .125 }')
    ink_name = 'shading-function-inks.pdf'
    pdf(ROOT/ink_name, b'/Sh sh', base.replace(b'/DeviceRGB', b'/DeviceCMYK')+b'>>', (ink_function,), media_box=b'0 0 16 16')

    (ROOT/'shading-function-oracle.bin').write_bytes(oracle)
    (ROOT/'shading-function-manifest.json').write_text(json.dumps({'scenes': rows, 'rejected': rejected,
        'native_inks': {'file': ink_name, 'sha256': hashlib.sha256((ROOT/ink_name).read_bytes()).hexdigest(), 'cmyk': [64, 128, 191, 32]}}, indent=2)+'\n', encoding='utf-8')
    print('%d function/array scenes, %d rejected inputs' % (len(rows), len(rejected)))


if __name__=='__main__':
    main()
