"""Direct active-RGBA comparison of the six acceptance fixtures, at every page."""
import ctypes as c
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from benchmark_pdf_blend import Bitmap, Error
from benchmark_pdf_rect import Page
from bench_firstscreen import sha256


def load(path):
    path = Path(path).resolve()
    directory = os.add_dll_directory(str(path.parent))
    lib = c.CDLL(str(path))
    lib.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    lib.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    lib.exr_fixed_pages.restype = c.POINTER(Page)
    lib.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
    lib.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    lib.exr_fixed_free.argtypes = [c.c_void_p]
    return lib, directory


def main():
    a, b, output = sys.argv[1:]
    libs = [load(a), load(b)]
    result = {'library_a_sha256': sha256(a), 'library_b_sha256': sha256(b), 'comparison': 'direct RGBA byte equality; differing pixels counted', 'cases': []}
    fixtures = [('tests/fixtures/pdf-large/' + name + '.pdf', [1200]) for name in ['real-mixed-120', 'image-heavy-100', 'vector-heavy-100']]
    fixtures += [('tests/fixtures/pdf-hybrid-real/pptx-20.pdf', [600, 1200, 2400]), ('tests/fixtures/pdf-ppt/deck.pdf', [600, 1200]), ('tests/fixtures/pdf-hybrid-real/word-5.pdf', [600, 1200])]
    error = Error()

    def check(status):
        if status:
            raise RuntimeError(error.message.decode(errors='replace'))

    for pdf, widths in fixtures:
        docs, pages = [], []
        try:
            for lib, _ in libs:
                doc, count = c.c_void_p(), c.c_size_t()
                check(lib.exr_fixed_open(os.fsencode(pdf), None, c.byref(doc), c.byref(error)))
                docs.append(doc)
                pages.append(lib.exr_fixed_pages(doc, c.byref(count)))
                if len(docs) == 1:
                    expected = count.value
                assert count.value == expected
            for width in widths:
                row = {'fixture': pdf, 'width': width, 'pages': [], 'pixels': 0, 'different_pixels': 0}
                for page in range(expected):
                    bitmaps = [Bitmap(), Bitmap()]
                    try:
                        for side in ([0, 1] if page % 2 == 0 else [1, 0]):
                            geometry = pages[side][page].geometry
                            native = geometry.bounds[3] - geometry.bounds[1] if geometry.rotation % 180 else geometry.bounds[2] - geometry.bounds[0]
                            check(libs[side][0].exr_fixed_render(docs[side], page, width / (native * geometry.unit_scale), None, c.byref(bitmaps[side]), c.byref(error)))
                        x, y = bitmaps
                        assert (x.width, x.height, x.channels) == (y.width, y.height, y.channels) and x.channels == 4
                        different = 0
                        for line in range(x.height):
                            left = c.string_at(x.pixels + line * x.stride, x.width * 4)
                            right = c.string_at(y.pixels + line * y.stride, y.width * 4)
                            if left != right:
                                different += sum(left[i:i+4] != right[i:i+4] for i in range(0, len(left), 4))
                        pixels = x.width * x.height
                        row['pages'].append({'page': page + 1, 'pixels': pixels, 'different_pixels': different})
                        row['pixels'] += pixels
                        row['different_pixels'] += different
                    finally:
                        for (lib, _), bitmap in zip(libs, bitmaps):
                            lib.exr_bitmap_free(c.byref(bitmap))
                result['cases'].append(row)
                Path(output).write_text(json.dumps(result, indent=2) + '\n')
                print(Path(pdf).stem, width, row['pixels'], row['different_pixels'], flush=True)
        finally:
            for (lib, _), doc in zip(libs, docs):
                lib.exr_fixed_free(doc)
    result['large_pixels'] = sum(row['pixels'] for row in result['cases'] if '/pdf-large/' in row['fixture'])
    result['small_pixels'] = sum(row['pixels'] for row in result['cases'] if '/pdf-large/' not in row['fixture'])
    assert result['large_pixels'] == 353143200 and result['small_pixels'] == 111897000
    assert all(row['different_pixels'] == 0 for row in result['cases'])
    Path(output).write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
