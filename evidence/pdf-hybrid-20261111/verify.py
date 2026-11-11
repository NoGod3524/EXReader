"""Reproduce the baseline failure, fixture inventory and independent pixel comparison.

Run from the repository root: python evidence/pdf-hybrid-20261111/verify.py
Uses the existing MinGW Release build/h; baseline output stays under build/.
"""
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build/h'
OUT = Path(__file__).resolve().parent
TEMP = ROOT / 'build/hybrid-validation'
BASE = 'f9df237713c9ad36d0cf6bb10df6b58fbc30ccff'


def save(name, value):
    data = ('[\n' + ',\n'.join(json.dumps(row, ensure_ascii=False) for row in value) + '\n]'
            if name == 'inventory.json' else json.dumps(value, indent=2, ensure_ascii=False))
    (OUT / name).write_text(data + '\n', encoding='utf-8')


def baseline():
    TEMP.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(['git', 'show', BASE + ':src/pdf_objects.c'], cwd=ROOT)
    original = TEMP / 'pdf_objects.c'
    original.write_bytes(source)
    target = 'CMakeFiles/exr_pdf_objects.dir/src/pdf_objects.c.obj'
    command = subprocess.check_output(['ninja', '-t', 'commands', target], cwd=BUILD, text=True).splitlines()[-1]
    args = [a.replace('\\"', '"') for a in shlex.split(command, posix=False)]
    obj = TEMP / 'pdf_objects.c.obj'
    for flag, value in [('-o', obj), ('-MF', TEMP / 'baseline.d'), ('-MT', obj), ('-c', original)]:
        args[args.index(flag) + 1] = str(value)
    args += ['-I' + str(ROOT / 'src')]
    subprocess.run(args, cwd=BUILD, check=True)
    ninja = (BUILD / 'build.ninja').read_text()
    block = next(b for b in ninja.split('\n\n') if b.startswith('build libexreader.dll libexreader.dll.a:'))
    inputs = block.splitlines()[0].split(' C_SHARED_LIBRARY_LINKER__exreader_Release ', 1)[1].split(' |')[0].split()
    assert target in inputs
    inputs[inputs.index(target)] = str(obj).replace('\\', '/')
    libs = re.search(r'^  LINK_LIBRARIES = (.*)$', block, re.M)[1].split()
    # The explicit baseline object precedes archives, so its implementation is used.
    dll = TEMP / 'libexreader.dll'
    response = TEMP / 'baseline.rsp'
    response.write_text('\n'.join('"' + p + '"' for p in inputs + libs))
    subprocess.run([args[0], '-O3', '-DNDEBUG', '-shared', '-static-libgcc', '-static',
                    'exreader.def', '-o', str(dll), '@' + str(response)], cwd=BUILD, check=True)
    return dll


class Error(C.Structure):
    _fields_ = [('code', C.c_int), ('message', C.c_char * 256)]


class Bitmap(C.Structure):
    _fields_ = [('width', C.c_uint32), ('height', C.c_uint32), ('stride', C.c_uint32),
                ('pixels', C.POINTER(C.c_ubyte)), ('channels', C.c_uint32)]


def load(path):
    dll = C.CDLL(str(path))
    dll.exr_fixed_open.argtypes = [C.c_char_p, C.c_void_p, C.POINTER(C.c_void_p), C.POINTER(Error)]
    dll.exr_fixed_pages.argtypes = [C.c_void_p, C.POINTER(C.c_size_t)]
    dll.exr_fixed_pages.restype = C.c_void_p
    dll.exr_fixed_render.argtypes = [C.c_void_p, C.c_size_t, C.c_double, C.c_void_p, C.POINTER(Bitmap), C.POINTER(Error)]
    dll.exr_bitmap_free.argtypes = [C.POINTER(Bitmap)]
    dll.exr_fixed_free.argtypes = [C.c_void_p]
    return dll


def open_pdf(dll, path):
    doc, error = C.c_void_p(), Error()
    status = dll.exr_fixed_open(str(path).encode('utf-8'), None, C.byref(doc), C.byref(error))
    count = C.c_size_t()
    if not status:
        dll.exr_fixed_pages(doc, C.byref(count))
    return doc, dict(status=status, pages=count.value, message=error.message.decode('utf-8', 'replace'))


def render(dll, doc, page):
    import numpy as np
    bitmap, error = Bitmap(), Error()
    status = dll.exr_fixed_render(doc, page, 1., None, C.byref(bitmap), C.byref(error))
    try:
        assert status == 0 and bitmap.pixels, (page, status, error.message)
        data = np.frombuffer(C.string_at(bitmap.pixels, bitmap.stride * bitmap.height), dtype=np.uint8)
        return data.reshape(bitmap.height, bitmap.stride)[:, :bitmap.width * bitmap.channels].reshape(
            bitmap.height, bitmap.width, bitmap.channels).copy()
    finally:
        dll.exr_bitmap_free(C.byref(bitmap))


def main():
    import numpy as np
    import pymupdf
    from PIL import Image
    old = load(baseline())
    current_path = BUILD / 'libexreader.dll'
    new = load(current_path)
    deck = ROOT / 'tests/fixtures/pdf-ppt/deck.pdf'
    doc, result = open_pdf(old, deck)
    save('baseline-probe.json', result)
    assert result['status'] == 5 and not doc, result
    print('baseline deck assertion is red:', result, flush=True)
    assertion_exe = TEMP / 'exreader-pdf-hybrid-test.exe'
    assertion_exe.write_bytes((BUILD / assertion_exe.name).read_bytes())
    red = subprocess.run([str(assertion_exe), str(ROOT / 'tests/fixtures')], capture_output=True, text=True)
    (OUT / 'baseline-assertion.txt').write_text(red.stdout + red.stderr, encoding='utf-8')
    assert red.returncode == 1 and 'Invalid PDF cross-reference stream' in red.stderr

    files = subprocess.check_output(['git', 'ls-files', '*.pdf'], cwd=ROOT, text=True).splitlines()
    inventory = []
    for name in files:
        data = (ROOT / name).read_bytes()
        table = bool(re.search(rb'(?m)^xref\s', data))
        stream = bool(re.search(rb'/Type\s*/XRef\b', data))
        kind = 'hybrid' if table and stream else 'stream' if stream else 'table' if table else 'other'
        row = dict(path=name, kind=kind, xrefstm=bool(re.search(rb'/XRefStm\b', data)))
        for label, dll in [('before', old), ('after', new)]:
            doc, result = open_pdf(dll, ROOT / name)
            row[label] = result
            dll.exr_fixed_free(doc)
        inventory.append(row)
    save('inventory.json', inventory)
    changed = [r['path'] for r in inventory if r['before'] != r['after']]
    assert changed == ['tests/fixtures/pdf-ppt/deck.pdf'], changed
    print('inventory complete:', len(inventory), flush=True)

    started = time.perf_counter()
    doc, result = open_pdf(new, deck)
    assert result['status'] == 0 and result['pages'] == 15, result
    result.update(rendered=0, failures=0, first_paint_ms=None)
    comparisons = []
    with pymupdf.open(deck) as reference:
        assert reference.page_count == 15
        for page in range(15):
            pixels = render(new, doc, page)
            if page == 0:
                result['first_paint_ms'] = round((time.perf_counter() - started) * 1000, 3)
            result['rendered'] += 1
            pix = reference[page].get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=True)
            expected = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            # Composite both RGBA images over white before comparing RGB.
            def white(a):
                a = a.astype(np.float64)
                return np.rint(a[:, :, :3] + 255 - a[:, :, 3:4]).clip(0, 255).astype(np.uint8)
            # EXReader returns straight RGBA; MuPDF returns premultiplied RGBA.
            actual = np.rint(pixels[:, :, :3] * (pixels[:, :, 3:4].astype(float) / 255) +
                             255 - pixels[:, :, 3:4]).clip(0, 255).astype(np.uint8)
            expected = white(expected)
            assert actual.shape == expected.shape, (actual.shape, expected.shape)
            delta = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
            comparisons.append(dict(page=page + 1, width=pix.width, height=pix.height,
                                    mean_absolute_error=round(float(delta.mean()), 6),
                                    max_error=int(delta.max()),
                                    pixels_differ_percent=round(float(np.any(delta, axis=2).mean() * 100), 6)))
            if page < 3:
                for label, image in [('exreader', actual), ('reference', expected)]:
                    Image.fromarray(image).save(TEMP / f'{label}-{page + 1}.png')
            print('rendered page', page + 1, comparisons[-1], flush=True)
    new.exr_fixed_free(doc)
    result['dll_sha256'] = hashlib.sha256(current_path.read_bytes()).hexdigest()
    result['deck_sha256'] = hashlib.sha256(deck.read_bytes()).hexdigest()
    save('deck-probe.json', result)
    save('pixels.json', dict(reference='PyMuPDF', version=pymupdf.VersionBind, scale=1, pages=comparisons))

    # Exercise unchanged traditional/stream rendering byte-for-byte against baseline.
    unchanged = []
    for name in ['tests/fixtures/pdf-graphics.pdf', 'tests/fixtures/pdf-xref-stream.pdf', 'tests/fixtures/pdf-hybrid.pdf']:
        if not (ROOT / name).exists():
            continue
        left, a = open_pdf(old, ROOT / name)
        right, b = open_pdf(new, ROOT / name)
        assert a == b, (name, a, b)
        if a['status'] == 0:
            for page in range(a['pages']):
                x, y = render(old, left, page), render(new, right, page)
                assert np.array_equal(x, y), (name, page)
                unchanged.append(dict(path=name, page=page + 1, sha256=hashlib.sha256(x.tobytes()).hexdigest()))
        old.exr_fixed_free(left)
        new.exr_fixed_free(right)
    save('unchanged-pixels.json', unchanged)
    print('deck:', result, flush=True)


if __name__ == '__main__':
    main()
