#!/usr/bin/env python3
"""Generate mesh shading (types 6 and 7) pixel fixtures.

Each fixture is a 100x100 page with one 1x1-unit patch scaled to the page:
a planar Coons patch, a bulged tensor-product patch, and a planar Coons patch
painted in DeviceCMYK. Reference pixels in tests/test_pdf_shading_mesh7.c were
recorded from MuPDF 1.28.2; the CMYK case documents the engine's naive
DeviceCMYK conversion instead (no ICC profile is bundled yet).
"""
# SPDX-License-Identifier: MIT
import argparse
from pathlib import Path


def encode_patch(points, colors, tensor, cmyk):
    """One flag-0 patch: 12 boundary points, optional 4 interior, 4 corner colours."""
    data = bytearray([0])
    for x, y in points[:12]:
        data += bytes([x, y])
    if tensor:
        for x, y in points[12:16]:
            data += bytes([x, y])
    for colour in colors:
        data += bytes(colour)
    return data


def write_pdf(path, data, cmyk, shading_type):
    comps = 4 if cmyk else 3
    decode = "[0 1 0 1 " + " ".join(["0 1"] * comps) + "]"
    cs = "/DeviceCMYK" if cmyk else "/DeviceRGB"
    content = b"q 100 0 0 100 0 0 cm /Sh1 sh Q\n"
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] "
         b"/Resources << /Shading << /Sh1 5 0 R >> >> /Contents 4 0 R >>"),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
        (("<< /ShadingType %d /ColorSpace %s /BitsPerCoordinate 8 /BitsPerComponent 8 "
          "/BitsPerFlag 8 /Decode %s /Length %d >>") % (shading_type, cs, decode, len(data))).encode()
        + b"\nstream\n" + bytes(data) + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(bodies, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(bodies) + 1)
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(bodies) + 1, xref)
    Path(path).write_bytes(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path, help="tests/fixtures/pdf-color")
    args = parser.parse_args()

    square = [(0, 0), (0, 85), (0, 170), (0, 255),
              (85, 255), (170, 255), (255, 255),
              (255, 170), (255, 85), (255, 0),
              (170, 0), (85, 0)]
    interior = [(85, 85), (85, 170), (170, 170), (170, 85)]
    bulged = list(square) + list(interior)
    bulged[12] = (60, 60)      # pull the lower-left interior pole towards the corner
    bulged[13] = (40, 120)
    bulged[14] = (150, 150)
    bulged[15] = (120, 40)

    rgb_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    cmyk_colors = [(0, 255, 255, 0), (255, 0, 0, 0), (255, 255, 0, 0), (0, 0, 0, 0)]

    write_pdf(args.directory / "shading-mesh6.pdf",
              encode_patch(square, rgb_colors, False, False), False, 6)
    write_pdf(args.directory / "shading-mesh7.pdf",
              encode_patch(square + interior, rgb_colors, True, False), False, 7)
    write_pdf(args.directory / "shading-mesh7-bulge.pdf",
              encode_patch(bulged, rgb_colors, True, False), False, 7)
    write_pdf(args.directory / "shading-mesh7-cmyk.pdf",
              encode_patch(square + interior, cmyk_colors, True, True), True, 7)
    print("generated 4 mesh shading fixtures")


if __name__ == "__main__":
    main()
