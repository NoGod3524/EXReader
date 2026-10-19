#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Original PDF regressions for graphics state and mesh record decoding."""
from pathlib import Path
import argparse


def stream(dictionary, data):
    return b'<< ' + dictionary + b' /Length %d >>\nstream\n' % len(data) + data + b'\nendstream'


def pdf(path, content, shading, extras=(), resources=b'', page_extra=b''):
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Contents 4 0 R '
               b'/Resources << /Shading << /Sh 5 0 R >> ' + resources + b' >> ' + page_extra + b' >>',
               stream(b'', content), shading, *extras]
    out = bytearray(b'%PDF-1.7\n'); offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out)); out += b'%d 0 obj\n' % i + obj + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % len(offsets)
    out += b''.join(b'%010d 00000 n \n' % x for x in offsets[1:])
    out += b'trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offsets), xref)
    path.write_bytes(out)


def packed(parts):
    bits = ''.join(f'{v:0{n}b}' for v, n in parts)
    bits += '0' * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, 'big')


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    axial = (b'<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [0 0 100 0] '
             b'/Function << /FunctionType 2 /Domain [0 1] /C0 [1 0 0] /C1 [1 0 0] /N 1 >> >>')
    pdf(root/'shading-alpha.pdf', b'/GS gs /Sh sh', axial,
        resources=b'/ExtGState << /GS << /ca 0.25 >> >>')
    pdf(root/'shading-blend.pdf', b'0 1 0 rg 0 0 100 100 re f /GS gs /Sh sh', axial,
        resources=b'/ExtGState << /GS << /BM /Multiply >> >>')
    mask = stream(b'/Type /XObject /Subtype /Form /BBox [0 0 100 100] '
                  b'/Group << /S /Transparency /CS /DeviceRGB /I true >> '
                  b'/Resources << /ExtGState << /A << /ca 0.25 >> >> >>',
                  b'/A gs 1 g 0 0 100 100 re f')
    pdf(root/'shading-mask.pdf', b'/GS gs /Sh sh', axial, (mask,),
        b'/ExtGState << /GS << /SMask << /S /Alpha /G 6 0 R >> >> >>')
    gray_image=stream(b'/Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8',bytes((255,0,0))*4)
    gray_form=stream(b'/Type /XObject /Subtype /Form /BBox [0 0 100 100] /Group << /S /Transparency /CS /DeviceGray /I true >> /Resources << /XObject << /Im 7 0 R >> >>',b'100 0 0 100 0 0 cm /Im Do')
    pdf(root/'gray-image.pdf',b'/Fm Do',axial,(gray_form,gray_image),b'/XObject << /Fm 6 0 R >>')
    inks=b'/A gs 1 1 0 1 k 0 0 100 100 re f 0 0 0 0 k 0 0 100 100 re f'
    group=b'/Group << /S /Transparency /CS /DeviceCMYK /I true >>'
    pdf(root/'page-cmyk.pdf',inks,axial,resources=b'/ExtGState << /A << /ca 0.5 >> >>',page_extra=group)
    appearance=stream(b'/Type /XObject /Subtype /Form /BBox [0 0 100 100] '+group+
                      b' /Resources << /ExtGState << /A << /ca 0.5 >> >> >>',inks)
    pdf(root/'appearance-cmyk.pdf',b'',axial,(appearance,),
        page_extra=b'/Annots [<< /Type /Annot /Subtype /Square /Rect [0 0 100 100] /AP << /N 6 0 R >> >>]')
    def mesh(name, kind, data, cs=b'/DeviceRGB', extra=b'', decode=b'[0 1 0 1 0 1 0 1 0 1]'):
        dictionary = (b'/ShadingType %d /ColorSpace ' % kind + cs +
                      b' /BitsPerCoordinate 8 /BitsPerComponent 8 /Decode ' + decode +
                      (b' /VerticesPerRow 2' if kind == 5 else b' /BitsPerFlag 2') + extra)
        pdf(root/name, b'100 0 0 100 0 0 cm /Sh sh', stream(dictionary, data),
            resources=b'/ColorSpace << /Alias /DeviceRGB >>')
    def vertex(flag, point, color, lattice=False):
        return packed(([] if lattice else [(flag, 2)]) + [(v, 8) for v in (*point, *color)])
    vertices = [(0, (0, 0), (255, 0, 0)), (0, (255, 0), (0, 255, 0)),
                (0, (0, 255), (0, 0, 255)), (1, (255, 255), (255, 255, 255)),
                (2, (255, 128), (255, 0, 255))]
    mesh('mesh4-continue.pdf', 4, b''.join(vertex(*v) for v in vertices))
    mesh('mesh4-alias.pdf', 4, b''.join(vertex(*v) for v in vertices[:3]), cs=b'/Alias')
    lattice = [(0, (0, 0), (255, 0, 0)), (0, (255, 0), (0, 255, 0)),
               (0, (0, 255), (0, 0, 255)), (0, (255, 255), (255, 255, 255))]
    mesh('mesh5.pdf', 5, b''.join(vertex(*v, lattice=True) for v in lattice))
    mesh('mesh5-incomplete.pdf', 5, b''.join(vertex(*v, lattice=True) for v in lattice[:3]))
    mesh('mesh-function-gray.pdf', 4,
         b''.join(vertex(0, p, (128,)) for p in ((0, 0), (255, 0), (0, 255))),
         cs=b'/DeviceGray', decode=b'[0 1 0 1 0 1]',
         extra=b' /Function << /FunctionType 2 /Domain [0 1] /C0 [0] /C1 [1] /N 2 >>')
    square = [(0, 0), (0, 85), (0, 170), (0, 255), (85, 255), (170, 255),
              (255, 255), (255, 170), (255, 85), (255, 0), (170, 0), (85, 0)]
    patches = []
    for right, color in ((False, (255, 0, 0)), (True, (0, 0, 255))):
        points = [(128 + x//2 if right else x//2, y) for x, y in square]
        patches.extend([(0, 2)] + [(v, 8) for p in points for v in p] +
                       [(v, 8) for _ in range(4) for v in color])
    mesh('mesh6-packed.pdf', 6, packed(patches))
    # /SMask recursion must be bounded instead of exhausting the C stack.
    recursive = stream(b'/Type /XObject /Subtype /Form /BBox [0 0 100 100] '
                       b'/Group << /S /Transparency /CS /DeviceRGB /I true >> '
                       b'/Resources << /ExtGState << /Again << /SMask << /S /Alpha /G 6 0 R >> >> >> >>',
                       b'/Again gs 1 g 0 0 100 100 re f')
    pdf(root/'mask-cycle.pdf', b'/GS gs /Sh sh', axial, (recursive,),
        b'/ExtGState << /GS << /SMask << /S /Alpha /G 6 0 R >> >> >>')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    main(parser.parse_args().directory)
