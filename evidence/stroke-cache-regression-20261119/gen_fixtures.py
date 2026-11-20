"""Adversarial single-page PDFs for the stroke/path coverage cache (1200 x 900 pt, rendered at scale 1 -> 1200 px).

Hand-assembled objects; no third-party PDF library. Each case repeats one stroke matrix many times
at whole-pixel offsets (so the cache admits, inserts and replays) while varying one other input.
Usage: python -I gen_fixtures.py OUTDIR
"""
import sys, zlib
from pathlib import Path

W, H = 1200, 900
# Curve with a corner, in user units relative to the tile origin.
PATH = "0 0 m 30 -38 62 44 96 -6 c 118 30 l"
CLOSED = "0 0 m 34 -30 70 30 96 -4 c 92 40 l 6 44 l h"
BLENDS = ["Normal", "Multiply", "Screen", "Overlay", "Darken", "Lighten", "ColorDodge", "ColorBurn",
          "HardLight", "SoftLight", "Difference", "Exclusion", "Hue", "Saturation", "Color", "Luminosity"]


def tiles(cols=8, rows=6, x0=40, y0=820, dx=140, dy=140):
    for r in range(rows):
        for c in range(cols):
            yield r * cols + c, x0 + c * dx, y0 - r * dy


def backdrop():
    # Coloured bands so alpha and blend modes have something to act on.
    out = []
    for i, rgb in enumerate(["0.95 0.85 0.55", "0.55 0.8 0.9", "0.85 0.55 0.75", "0.4 0.7 0.45"]):
        out.append(f"{rgb} rg 0 {i * 225} {W} 225 re f")
    return "\n".join(out)


STYLE = "0.12 0.31 0.66 RG 0.82 0.38 0.23 rg 6 w 1 j 0 J"


def case_clip():
    s = [backdrop(), STYLE]
    for i, x, y in tiles():
        cw, ch = 30 + (i * 17) % 90, 20 + (i * 29) % 70
        s.append(f"q {x + (i * 7) % 40} {y - 50 + (i * 11) % 30} {cw} {ch} re W n "
                 f"1 0 0 1 {x} {y} cm {PATH} S Q")
        s.append(f"q {x} {y - 70 + (i * 13) % 50} {40 + (i * 23) % 80} 60 re W n "
                 f"1 0 0 1 {x} {y - 60} cm {CLOSED} B Q")
    return s, {}


def case_alpha():
    alphas = [1, .9, .75, .6, .5, .4, .3, .2, .1, .05, .02, 0.996]
    gs = {f"G{k}": f"<< /Type /ExtGState /CA {a} /ca {alphas[-1 - k]} >>" for k, a in enumerate(alphas)}
    s = [backdrop(), STYLE]
    for i, x, y in tiles():
        k = i % len(alphas)
        s.append(f"q /G{k} gs 1 0 0 1 {x} {y} cm {PATH} S Q")
        s.append(f"q /G{k} gs 1 0 0 1 {x} {y - 60} cm {CLOSED} B Q")
    return s, gs


def case_width():
    widths = ["6", "6", "6", "1", "2", "6.5", "6.000001", "12", "0.5", "6", "9", "6"]
    s = [backdrop(), STYLE]
    for i, x, y in tiles():
        w = widths[i % len(widths)]
        s.append(f"q {w} w 1 0 0 1 {x} {y} cm {PATH} S Q")
        s.append(f"q {w} w 1 0 0 1 {x} {y - 60} cm {CLOSED} B Q")
    return s, {}


def case_blend():
    gs = {f"B{k}": f"<< /Type /ExtGState /BM /{m} /CA 0.85 /ca 0.7 >>" for k, m in enumerate(BLENDS)}
    s = [backdrop(), STYLE]
    for i, x, y in tiles():
        k = i % len(BLENDS)
        s.append(f"q /B{k} gs 1 0 0 1 {x} {y} cm {PATH} S Q")
        s.append(f"q /B{k} gs 1 0 0 1 {x} {y - 60} cm {CLOSED} B Q")
    return s, gs


def case_matrix_epsilon():
    # Three identical tiles admit+insert+replay, then each linear term moves by 1e-6, then back.
    variants = ["1 0 0 1", "1 0 0 1", "1 0 0 1", "1.000001 0 0 1", "1 0.000001 0 1", "1 0 0.000001 1",
                "1 0 0 1.000001", "1 0 0 1", "0.999999 0 0 0.999999", "1 0 0 1", "1.000001 0 0 1", "1 0 0 1"]
    s = [backdrop(), STYLE]
    for i, x, y in tiles():
        v = variants[i % len(variants)]
        s.append(f"q 1 0 0 1 {x} {y} cm {v} 0 0 cm {PATH} S Q")
        s.append(f"q 1 0 0 1 {x} {y - 60} cm {v} 0 0 cm {CLOSED} B Q")
    return s, {}


def case_clip_change():
    # Stroke, narrow the clip, stroke again with the same matrix, restore, stroke again.
    s = [backdrop(), STYLE]
    for i, x, y in tiles():
        s.append(f"q 1 0 0 1 {x} {y} cm {PATH} S "
                 f"q {(i * 9) % 50} -50 {30 + (i * 13) % 70} 70 re W n {PATH} S "
                 f"0 -10 60 40 re W n 0.9 0.1 0.1 RG {PATH} S Q {PATH} S Q")
        s.append(f"q 1 0 0 1 {x} {y - 60} cm {CLOSED} B q 10 -20 {20 + (i * 5) % 60} 60 re W n {CLOSED} B Q Q")
    return s, {}


def case_matrix_validation():
    # PDF-reachable form of the skipped inverse check. CTM linear part 0.001 is identical in all tiles;
    # tiles 1-3 translate by 0 (inverse in range), tile 4 by 10500 so inverse(CTM).e = -1.05e7 (> 1e7):
    # an uncached render rejects the page with "Invalid or singular canvas stroke matrix".
    s = [backdrop(), STYLE]
    pts = [(650.25, 300.5), (720.25, 260.5), (780.25, 340.5), (840.25, 300.5)]
    def path(tx):
        p = [(round((x - tx) * 1000, 6), round(y * 1000, 6)) for x, y in pts]
        return f"{p[0][0]} {p[0][1]} m {p[1][0]} {p[1][1]} {p[2][0]} {p[2][1]} {p[3][0]} {p[3][1]} c"
    for tx in (0, 0, 0):
        s.append(f"q 0.001 0 0 0.001 0 0 cm 6000 w {path(0)} S Q")
    s.append(f"q 0.001 0 0 0.001 10500 0 cm 6000 w {path(10500)} S Q")
    return s, {}


def case_hairline():
    # PDF 0 w is a one-device-pixel hairline; 0.0000000000001 w is a near-invisible stroke.
    s = [backdrop(), "0.1 0.1 0.1 RG"]
    for i, x, y in tiles():
        w = "0.0000000000001" if i % 6 < 3 else "0"
        s.append(f"q {w} w 1 0 0 1 {x} {y} cm {PATH} S Q")
    return s, {}


CASES = {
    "01_clip": case_clip, "02_alpha": case_alpha, "03_width": case_width, "04_blend": case_blend,
    "05_matrix_epsilon": case_matrix_epsilon, "06_clip_change": case_clip_change,
    "07_matrix_validation": case_matrix_validation, "08_hairline": case_hairline,
}


def pdf(content: str, extgstates: dict) -> bytes:
    stream = zlib.compress(content.encode("ascii"))
    gs = " ".join(f"/{k} {v}" for k, v in extgstates.items())
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Contents 4 0 R "
         f"/Resources << /ExtGState << {gs} >> >> >>").encode("ascii"),
        f"<< /Length {len(stream)} /Filter /FlateDecode >>\nstream\n".encode("ascii") + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii")
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    return bytes(out)


def main():
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    for name, fn in CASES.items():
        lines, gs = fn()
        (outdir / f"{name}.pdf").write_bytes(pdf("\n".join(lines) + "\n", gs))
        print(f"{name}.pdf ops={len(lines)}")


if __name__ == "__main__":
    main()
