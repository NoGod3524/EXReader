#!/usr/bin/env python3
"""M-E5 image acceptance through the public ABI, with independent ZIP/XML checks."""
import argparse
import ctypes as c
import re
import struct
from pathlib import Path
import xml.etree.ElementTree as ET

from test_docx_edit_io import Block, ID, package, repack, unzip
from test_docx_edit_table_image import API, png, paragraph, SECT, WP, A


class Image(c.Structure):
    _fields_ = [('data', c.c_void_p), ('size', c.c_size_t),
                ('width', c.c_int64), ('height', c.c_int64), ('jpeg', c.c_uint),
                ('format', c.c_uint), ('anchor', ID), ('offset', c.c_size_t)]


class Bitmap(c.Structure):
    _fields_ = [('width', c.c_uint32), ('height', c.c_uint32),
                ('stride', c.c_uint32), ('pixels', c.c_void_p), ('channels', c.c_uint32)]


def bmp():
    return (b'BM' + struct.pack('<IHHI', 58, 0, 0, 54)
            + struct.pack('<IiiHHIIiiII', 40, 1, 1, 1, 24, 0, 4, 0, 0, 0, 0)
            + b'\x00\x00\xff\x00')


def gif():
    # Two distinct 1x1 frames: red, then green. Complete original bytes survive.
    frame = b'\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
    return (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\x00\x00\x00\xff\x00'
            + frame + b'\x44\x01\x00' + frame + b'\x4c\x01\x00\x3b')


def images(api, doc):
    return [api.block_at(doc, i) for i in range(api.block_count(doc))
            if api.block_at(doc, i).contents.kind == 4]


def view(block):
    return c.cast(block.contents.image, c.POINTER(Image)).contents


def payload(block):
    im = view(block)
    return c.string_at(im.data, im.size)


def position(api, doc, block):
    paragraph_id, run, offset = ID(), c.c_size_t(), c.c_size_t()
    assert api.position(doc, block, c.byref(paragraph_id), c.byref(run), c.byref(offset)) == 0
    return paragraph_id.value, run.value, offset.value


def drawing(rid='image1', width=123456, height=234567):
    return (f'<w:drawing xmlns:wp="{WP}"><wp:anchor><wp:extent cx="{width}" cy="{height}"/>'
            f'<a:blip r:embed="{rid}"/></wp:anchor></w:drawing>')


def main(library):
    registration = (Path(__file__).parent / 'fixtures/docx-real/codex/register.cmake').read_text()
    preload_pattern = re.search(r'if\(test MATCHES "([^"]+)"', registration)[1]
    assert re.search(preload_pattern, 'native-docx-edit-e5')
    assert 'LD_PRELOAD=path_list_prepend:${asan_runtime}' in registration
    assert 'PYTHONMALLOC=set:malloc' in registration
    print('8 ASan preload regex: native-docx-edit-e5 MATCH; LD_PRELOAD/PYTHONMALLOC registered (Linux/GNU)')
    api = API(library)
    api.position = api.dll.exr_edit_image_position
    api.position.restype = c.c_int
    api.position.argtypes = [c.c_void_p, c.POINTER(Block), c.POINTER(ID),
                             c.POINTER(c.c_size_t), c.POINTER(c.c_size_t)]
    decode = api.dll.exr_image_decode_page
    decode.restype = c.c_int
    decode.argtypes = [c.c_void_p, c.c_size_t, c.c_size_t, c.POINTER(Bitmap), c.c_void_p]
    api.dll.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    display = api.dll.exr_image_decode
    display.restype = c.c_int
    display.argtypes = [c.c_void_p, c.c_size_t, c.POINTER(Bitmap), c.c_void_p]
    for index, expected in enumerate((b'\xff\x00\x00\xff', b'\x00\xff\x00\xff')):
        bitmap = Bitmap()
        assert decode(gif(), len(gif()), index, c.byref(bitmap), None) == 0
        try:
            assert (bitmap.width, bitmap.height) == (1, 1)
            assert c.string_at(bitmap.pixels, 4) == expected
        finally:
            api.dll.exr_bitmap_free(c.byref(bitmap))
    bitmap = Bitmap()
    assert display(gif(), len(gif()), c.byref(bitmap), None) == 0
    try:
        assert c.string_at(bitmap.pixels, 4) == b'\xff\x00\x00\xff'
    finally:
        api.dll.exr_bitmap_free(c.byref(bitmap))
    print('1 PNG/BMP/GIF insert: EXR_OK; GIF frame 0=red, frame 1=green, display=frame 0')
    source = package(body=paragraph('before') + SECT)
    for name, data, fmt in [('PNG', png(), 1), ('BMP', bmp(), 4), ('GIF', gif(), 3)]:
        doc = api.read(source)
        try:
            image_id = api.image(doc, 0, data, 12.5, 24.25)
            block = next(b for b in images(api, doc) if b.contents.id == image_id)
            im = view(block)
            expected = (im.format, im.width, im.height)
            assert expected == (fmt, 158750, 307975)
            assert (im.width / 635, im.height / 635) == (250, 485)
            assert payload(block) == data and position(api, doc, block) == (0, 0, 0)
            saved = api.write(doc)
            parts = unzip(saved)
            ext = name.lower()
            assert any(n.endswith('.' + ext) and value == data for n, value in parts.items())
            types = ET.fromstring(parts['[Content_Types].xml'])
            assert any(n.get('Extension') == ext and n.get('ContentType') == 'image/' + ext for n in types)
            reopened = api.read(saved)
            try:
                block, = images(api, reopened)
                im = view(block)
                assert (im.format, im.width, im.height) == expected
                assert payload(block) == data
                assert position(api, reopened, block)[0]
                assert unzip(api.write(reopened)) == parts
            finally:
                api.doc_free(reopened)
            before, count = api.write(doc), api.block_count(doc)
            bad = b'this is a text file renamed to .png'
            out = ID(999)
            assert api.insert_image(doc, 0, bad, len(bad), 10, 10, c.byref(out)) == 5
            assert not out.value and api.block_count(doc) == count and api.write(doc) == before
            print(f'3/4 {name}: reopen IMAGE format={fmt}, twips=250x485 (EMU=158750x307975), payload byte-identical ({len(data)} bytes)')
        finally:
            api.doc_free(doc)
    print('2 renamed text.png: EXR_FORMAT; output ID=0; model and serialized bytes unchanged')

    # Same-run mixed content, identical images, following text, and table cell anchors.
    raw = '<w:r><w:t>left</w:t>' + drawing() * 2 + '<w:t>right</w:t></w:r>'
    cell = '<w:tbl><w:tr><w:tc><w:p>' + raw + '</w:p></w:tc></w:tr></w:tbl>'
    for body, selected in [(b, i) for b in ('<w:p>' + raw + '</w:p>', cell) for i in (0, 1)]:
        parts = unzip(package(body=body + SECT))
        parts['word/media/image1.png'] = png()
        original = repack(parts)
        doc = api.read(original)
        try:
            blocks = images(api, doc)
            assert len(blocks) == 2
            locations = [position(api, doc, b) for b in blocks]
            assert locations[0][:2] == locations[1][:2] and locations[0][2] < locations[1][2]
            assert all((view(b).width, view(b).height) == (123456, 234567) for b in blocks)
            assert unzip(api.write(doc)) == parts
            assert api.delete_image(doc, blocks[selected].contents.id) == 0
            assert len(images(api, doc)) == 1
            saved = api.write(doc)
            xml = unzip(saved)['word/document.xml']
            assert xml.count(b'<w:drawing') == 1 and b'left' in xml and b'right' in xml
            assert api.undo(doc) == 0 and len(images(api, doc)) == 2
            assert unzip(api.write(doc)) == parts
            assert api.redo(doc) == 0 and len(images(api, doc)) == 1
            assert api.undo(doc) == 0 and len(images(api, doc)) == 2
            if body.startswith('<w:p>'):
                assert api.delete_block(doc, locations[0][0]) == 0
            else:
                tid, _ = api.table(doc)
                assert api.delete_table(doc, tid) == 0
            assert not images(api, doc)
            assert api.undo(doc) == 0 and len(images(api, doc)) == 2
            tx = api.begin(doc)
            assert tx and api.delete_image(doc, images(api, doc)[0].contents.id) == 0
            assert api.rollback(tx) == 0 and len(images(api, doc)) == 2
        finally:
            api.doc_free(doc)
    print('position/mutation: mixed runs, duplicate anchors, exact EMU, table cells, delete/undo/redo PASS')

    for filename in ('baseline.jpg', 'cmyk.jpg', 'ycck.jpg', 'cmyk-progressive.jpg'):
        data = (Path(__file__).parent / 'fixtures/pdf-images' / filename).read_bytes()
        doc = api.read(source)
        try:
            api.image(doc, 0, data, 10, 20)
            reopened = api.read(api.write(doc))
            try:
                block, = images(api, reopened)
                assert view(block).format == 2 and payload(block) == data
            finally:
                api.doc_free(reopened)
        finally:
            api.doc_free(doc)
    print('JPEG baseline/CMYK/YCCK/progressive: EXR_OK; format=JPEG; original bytes preserved')

    vml = ('<w:r><w:pict xmlns:v="urn:schemas-microsoft-com:vml"><v:shape style="width:12.5pt;height:24.25pt">'
           '<v:imagedata r:id="image1"/></v:shape></w:pict></w:r>')
    parts = unzip(package(body='<w:p>' + vml + '</w:p>' + SECT))
    parts['word/media/image1.png'] = bmp()
    doc = api.read(repack(parts))
    try:
        block, = images(api, doc)
        assert (view(block).format, view(block).width, view(block).height) == (4, 158750, 307975)
        assert unzip(api.write(doc)) == parts
    finally:
        api.doc_free(doc)
    print('VML pict: BMP detected from bytes, dimensions=12.5pt x 24.25pt, exact package preserved')

    # A synthetic EMF header plus opaque payload; unsupported decoding must preserve it.
    emf = struct.pack('<IIiiiiIIII', 1, 88, 0, 0, 10, 10, 0, 0, 10, 10) + b' EMF' + bytes(44)
    parts['word/media/image1.png'] = emf
    original = repack(parts)
    doc = api.read(original)
    try:
        assert not images(api, doc)
        assert any(p.runs[i].kind == 1 and b'pict' in c.string_at(p.runs[i].xml, p.runs[i].xml_size)
                   for p in api.paragraphs(doc) for i in range(p.count))
        saved = unzip(api.write(doc))
        assert saved == parts and saved['word/media/image1.png'] == emf
    finally:
        api.doc_free(doc)
    print(f'5 unsupported EMF: opaque run retained; {len(emf)} original payload bytes and all OPC parts unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    main(parser.parse_args().library.resolve())
