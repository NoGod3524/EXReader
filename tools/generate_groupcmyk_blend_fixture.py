#!/usr/bin/env python3
"""Generate a DeviceCMYK transparency-group fixture with translucent fills.

The isolated group paints rich black (C=M=Y=1, K=1) at 50% alpha, then white at
50% alpha. Blended in DeviceCMYK the result is (1/3,1/3,0,1/3) at alpha 0.75,
which over white is (128,128,191); RGB compositing would give (191,191,191).
"""
# SPDX-License-Identifier: MIT
import argparse
from pathlib import Path

CONTENT = b"q /Fm0 Do Q\n"
FORM = b"/GS0 gs 1 1 0 1 k 0 0 16 16 re f 0 0 0 0 k 0 0 16 16 re f\n"


def write_pdf(path):
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] "
         b"/Resources << /XObject << /Fm0 5 0 R >> >> /Contents 4 0 R >>"),
        b"<< /Length %d >>\nstream\n" % len(CONTENT) + CONTENT + b"endstream",
        (b"<< /Type /XObject /Subtype /Form /BBox [0 0 16 16] "
         b"/Group << /S /Transparency /CS /DeviceCMYK /I true >> "
         b"/Resources << /ExtGState << /GS0 << /ca 0.5 /CA 0.5 >> >> >> /Length %d >>\nstream\n" % len(FORM)
         + FORM + b"endstream"),
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path, help="tests/fixtures/pdf-color")
    args = parser.parse_args()
    write_pdf(args.directory / "groupcmyk-blend.pdf")
    print("generated groupcmyk-blend.pdf")
