"""Byte-compare active RGBA of every page between two EXReader DLLs loaded in one process.

usage: python -X utf8 verify_pixels.py A.dll B.dll out.json
"""
import ctypes as c, hashlib, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from benchmark_pdf_blend import Bitmap, Error
from benchmark_pdf_rect import Page

CASES = [
    ('pptx-20', 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf', [600, 1200, 2400]),
    ('deck', 'tests/fixtures/pdf-ppt/deck.pdf', [600, 1200]),
    ('word-5', 'tests/fixtures/pdf-hybrid-real/word-5.pdf', [600, 1200]),
    ('real-mixed-120', 'tests/fixtures/pdf-large/real-mixed-120.pdf', [1200]),
    ('image-heavy-100', 'tests/fixtures/pdf-large/image-heavy-100.pdf', [1200]),
    ('vector-heavy-100', 'tests/fixtures/pdf-large/vector-heavy-100.pdf', [1200]),
]


def load(path):
    os.add_dll_directory(str(Path(path).resolve().parent))
    e = c.CDLL(str(Path(path).resolve()))
    e.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    e.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    e.exr_fixed_pages.restype = c.POINTER(Page)
    e.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
    e.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    e.exr_fixed_free.argtypes = [c.c_void_p]
    return e


def rows(b):
    return b''.join(c.string_at(b.pixels + y * b.stride, b.width * 4) for y in range(b.height))


def main():
    a, b, out = load(sys.argv[1]), load(sys.argv[2]), Path(sys.argv[3])
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    report = {'library_a_sha256': sha(sys.argv[1]), 'library_b_sha256': sha(sys.argv[2]), 'cases': []}
    for name, rel, widths in CASES:
        err = Error(); docs = []
        for e in (a, b):
            d = c.c_void_p(); assert e.exr_fixed_open(str(ROOT / rel).encode(), None, c.byref(d), c.byref(err)) == 0
            docs.append(d)
        n = c.c_size_t(); pages = a.exr_fixed_pages(docs[0], c.byref(n))
        for w in widths:
            compared = different = 0; bad_pages = []
            for i in range(n.value):
                g = pages[i].geometry; bw = g.bounds[3] - g.bounds[1] if g.rotation % 180 else g.bounds[2] - g.bounds[0]
                scale = w / (bw * g.unit_scale); px = []
                for e, d in zip((a, b), docs):
                    bm = Bitmap(); assert e.exr_fixed_render(d, i, scale, None, c.byref(bm), c.byref(err)) == 0, err.message
                    assert bm.width == w and bm.channels == 4
                    px.append(rows(bm)); e.exr_bitmap_free(c.byref(bm))
                assert len(px[0]) == len(px[1])
                compared += len(px[0]) // 4
                if px[0] != px[1]:
                    diff = sum(px[0][k:k + 4] != px[1][k:k + 4] for k in range(0, len(px[0]), 4))
                    different += diff; bad_pages.append([i + 1, diff])
            row = {'fixture': name, 'width': w, 'pages': n.value, 'compared_pixels': compared,
                   'different_pixels': different, 'different_pages': bad_pages}
            print(row, flush=True); report['cases'].append(row)
        for e, d in zip((a, b), docs): e.exr_fixed_free(d)
    report['compared_pixels'] = sum(r['compared_pixels'] for r in report['cases'])
    report['different_pixels'] = sum(r['different_pixels'] for r in report['cases'])
    out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print('total', report['compared_pixels'], 'different', report['different_pixels'])
    return 1 if report['different_pixels'] else 0


sys.exit(main())
