#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""PPTX public ABI acceptance, plus mutated OPC safety/ordering regressions."""
import argparse
import ctypes as C
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent / 'fixtures/pptx-skeleton'
MANIFEST = json.loads((HERE / 'manifest.json').read_text())
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
MAIN = 'ppt/presentation.xml'
RELS = 'ppt/_rels/presentation.xml.rels'


class Error(C.Structure):
    _fields_ = [('code', C.c_int), ('message', C.c_char * 256)]


class Geometry(C.Structure):
    _fields_ = [('bounds', C.c_double * 4), ('unit_scale', C.c_double),
                ('rotation', C.c_uint), ('y_down', C.c_uint)]


class Page(C.Structure):
    _fields_ = [('id', C.c_char_p), ('label', C.c_char_p), ('geometry', Geometry)]


class Bitmap(C.Structure):
    _fields_ = [('width', C.c_uint32), ('height', C.c_uint32), ('stride', C.c_uint32),
                ('pixels', C.c_void_p), ('channels', C.c_uint32)]


def mutate(data, changes):
    out = BytesIO()
    with ZipFile(BytesIO(data)) as src, ZipFile(out, 'w', ZIP_DEFLATED) as dst:
        for name in src.namelist():
            value = changes.get(name, src.read(name))
            if value is not None:
                dst.writestr(name, value)
    return out.getvalue()


class Engine:
    def __init__(self, library):
        self.directory = os.add_dll_directory(str(library.parent)) if os.name == 'nt' else None
        self.lib = C.CDLL(str(library))
        specs = {
            'exr_fixed_open': ([C.c_char_p, C.c_void_p, C.POINTER(C.c_void_p), C.POINTER(Error)], C.c_int),
            'exr_fixed_open_memory': ([C.c_int, C.c_void_p, C.c_size_t, C.c_void_p, C.POINTER(C.c_void_p), C.POINTER(Error)], C.c_int),
            'exr_fixed_pages': ([C.c_void_p, C.POINTER(C.c_size_t)], C.POINTER(Page)),
            'exr_fixed_render': ([C.c_void_p, C.c_size_t, C.c_double, C.c_void_p, C.POINTER(Bitmap), C.POINTER(Error)], C.c_int),
            'exr_fixed_free': ([C.c_void_p], None),
            'exr_bitmap_free': ([C.POINTER(Bitmap)], None),
        }
        for name, (args, result) in specs.items():
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, result

    def check(self, data, pages=None, dimensions=(720, 540), code=0, message='', labels=None, suffix='.pptx'):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ('幻灯片' + suffix)
            path.write_bytes(data)
            for mode in ('file', 'memory'):
                doc, error = C.c_void_p(), Error()
                if mode == 'file':
                    status = self.lib.exr_fixed_open(str(path).encode(), None, C.byref(doc), C.byref(error))
                else:
                    # EXR_PPTX 在 EXR_PPT 合入后是 9（EXR_PPT=8）；不要写死到别处
                    EXR_PPTX = 11
                    status = self.lib.exr_fixed_open_memory(EXR_PPTX, data, len(data), None, C.byref(doc), C.byref(error))
                text = error.message.decode()
                assert status == code and error.code == code, (mode, status, text)
                assert message in text, (message, text)
                print(f'{mode}: status={status} message={text!r}')
                if code:
                    assert not doc.value
                    continue
                try:
                    count = C.c_size_t()
                    directory = self.lib.exr_fixed_pages(doc, C.byref(count))
                    assert count.value == pages, (count.value, pages)
                    for i in range(count.value):
                        page = directory[i]
                        assert tuple(page.geometry.bounds) == (0, 0, *dimensions)
                        assert page.geometry.unit_scale == 1 and page.geometry.y_down == 1
                        if labels is not None:
                            assert page.label.decode() == labels[i]
                        bitmap = Bitmap()
                        status = self.lib.exr_fixed_render(doc, i, 1, None, C.byref(bitmap), C.byref(error))
                        assert status == 0, (status, error.message)
                        try:
                            assert (bitmap.width, bitmap.height, bitmap.channels) == (*dimensions, 4)
                            assert C.string_at(bitmap.pixels, bitmap.stride * bitmap.height) == b'\xff' * (bitmap.stride * bitmap.height)
                        finally:
                            self.lib.exr_bitmap_free(C.byref(bitmap))
                    # Empty decks and skipped pages still reject an out-of-range render.
                    bitmap = Bitmap()
                    assert self.lib.exr_fixed_render(doc, count.value, 1, None, C.byref(bitmap), C.byref(error)) == 1
                    assert not bitmap.pixels
                finally:
                    self.lib.exr_fixed_free(doc)


def run(engine, group):
    if group in {Path(e['file']).stem for e in MANIFEST}:
        e = next(e for e in MANIFEST if Path(e['file']).stem == group)
        engine.check((HERE / e['file']).read_bytes(), e['pages'], (e['cx'] / 12700, e['cy'] / 12700))
        print(f"{group}: engine={e['pages']} python-pptx={e['pages']}")
        return
    data = (HERE / 'layouts.pptx').read_bytes()
    with ZipFile(BytesIO(data)) as zip_file:
        presentation, relationships = zip_file.read(MAIN), zip_file.read(RELS)
    if group == 'errors':
        engine.check(data[:len(data)//2], code=5, message='truncated')
        engine.check(mutate(data, {MAIN: None}), code=5, message='PPTX part missing: ppt/presentation.xml')
        engine.check(mutate(data, {MAIN: b'<broken>'}), code=5, message=MAIN)
        engine.check(mutate(data, {'[Content_Types].xml': None}), code=5, message='content type missing')
        engine.check(mutate(data, {RELS: relationships.replace(b'Id="rId1"', b'Id="rId2"')}), code=5, message='Duplicate')
    elif group == 'defaults':
        import re
        for replacement in (b'', b'<p:sldSz cx="0" cy="0"/>', b'<p:sldSz cx="-1" cy="6858000"/>'):
            changed = re.sub(rb'<p:sldSz\b[^>]*/>', replacement, presentation)
            engine.check(mutate(data, {MAIN: changed}), 5)
    elif group == 'missing':
        engine.check(mutate(data, {'ppt/slides/slide2.xml': None}), 4, message='skipped 1',
                     labels=[f'ppt/slides/slide{i}.xml' for i in (1, 3, 4, 5)])
        engine.check(mutate(data, {RELS: None}), 0, message='skipped 5')
        engine.check(mutate(data, {'ppt/slides/slide1.xml': None,
                                  'ppt/slides/slide2.xml': None}), 3, message='skipped 2')
    elif group == 'order':
        import xml.etree.ElementTree as ET
        tree = ET.fromstring(presentation)
        slides = tree.find(f'{{{P}}}sldIdLst')
        slides[:] = list(reversed(slides))
        engine.check(mutate(data, {MAIN: ET.tostring(tree)}), 5,
                     labels=[f'ppt/slides/slide{i}.xml' for i in range(5, 0, -1)])
        absolute = relationships.replace(b'Target="slides/', b'Target="/ppt/slides/')
        engine.check(mutate(data, {RELS: absolute}), 5)
        unsafe = relationships.replace(b'Target="slides/slide1.xml"', b'Target="https://example.com/slide.xml"')
        engine.check(mutate(data, {RELS: unsafe}), 4, message='skipped 1')
    elif group == 'detection':
        engine.check(data, 5, suffix='.bin')
        engine.check(data, 5, suffix='.PPTX')
        changed = mutate(data, {'[Content_Types].xml': b'<Types>application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml</Types>'})
        engine.check(changed, code=5, message='content type missing')
    elif group == 'limit':
        for member in (b'[Content_Types].xml', b'ppt/slides/slide1.xml'):
            changed = bytearray(data)
            start = 0
            while True:
                start = changed.index(b'PK\x01\x02', start)
                name_size = struct.unpack_from('<H', changed, start + 28)[0]
                if changed[start + 46:start + 46 + name_size] == member:
                    break
                start += 4
            struct.pack_into('<I', changed, start + 24, 128 * 1024 * 1024 + 1)
            engine.check(bytes(changed), code=6, message='128 MiB')
    else:
        raise AssertionError(group)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('group')
    args = parser.parse_args()
    run(Engine(args.library.resolve()), args.group)

