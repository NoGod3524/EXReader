"""L09 resize ABI: exact dimensions, independent ZIP/XML and history checks."""
import argparse
import ctypes as c
from pathlib import Path
import xml.etree.ElementTree as ET

from test_docx_edit_images_e5 import images, view, payload, drawing
from test_docx_edit_table_image import API, png, paragraph, SECT, WP, A
from test_docx_edit_io import ID, package, repack, unzip


def main(library):
    api = API(library)
    resize = api.dll.exr_edit_image_size
    resize.restype = c.c_int
    resize.argtypes = [c.c_void_p, ID, c.c_double, c.c_double]
    # Same run, duplicate drawings, different namespaces, local bindings,
    # protected table cells, both inline/floating and legacy VML.
    dr = drawing(width=1270000, height=635000).replace(
        '</wp:anchor>', f'<a:xfrm><a:ext cx="1270000" cy="635000"/></a:xfrm></wp:anchor>')
    vml = ('<w:pict xmlns:v="urn:schemas-microsoft-com:vml"><v:shape '
           'style="position:absolute;width:100pt;height:50pt;rotation:0">'
           '<v:imagedata r:id="image1"/></v:shape></w:pict>')
    variants = [dr, dr.replace('wp:anchor', 'wp:inline'), vml]
    for variant in variants:
        for cell in (False, True):
            body = '<w:p><w:r><w:t>left</w:t>' + variant * 2 + '<w:t>right</w:t></w:r></w:p>'
            if cell:
                body = '<w:tbl><w:tr><w:tc><w:tcPr><w:shd w:fill="ABCDEF"/></w:tcPr>' + body + '</w:tc></w:tr></w:tbl>'
            parts = unzip(package(body=body + SECT))
            parts['word/media/image1.png'] = png()
            doc = api.read(repack(parts))
            try:
                ids = [b.contents.id for b in images(api, doc)]
                assert len(ids) == 2
                before = api.write(doc)
                for width, height in [(150, 75), (120, 60), (100, 50), (175, 87.5)]:
                    assert resize(doc, ids[0], width, height) == 0
                    current = images(api, doc)
                    assert [b.contents.id for b in current] == ids
                    assert (view(current[0]).width, view(current[0]).height) == (round(width*12700), round(height*12700))
                    assert (view(current[1]).width, view(current[1]).height) == (1270000, 635000)
                    assert payload(current[0]) == png()
                    saved = api.write(doc)
                    out = unzip(saved)
                    assert all(out[n] == p for n, p in parts.items() if n != 'word/document.xml')
                    root = ET.fromstring(out['word/document.xml'])
                    assert 'leftright' == ''.join(root.itertext())
                    if variant != vml:
                        extents = list(root.iter('{'+WP+'}extent'))
                        assert [(int(e.get('cx')), int(e.get('cy'))) for e in extents] == [(round(width*12700), round(height*12700)), (1270000,635000)]
                        extents = list(root.iter('{'+A+'}ext'))
                        assert int(extents[0].get('cx')) == round(width*12700)
                    else:
                        assert b'position:absolute' in out['word/document.xml'] and b'rotation:0' in out['word/document.xml']
                    reopened = api.read(saved)
                    try:
                        im = view(images(api, reopened)[0])
                        assert (im.width, im.height) == (round(width*12700), round(height*12700))
                    finally:
                        api.doc_free(reopened)
                tx = api.begin(doc)
                assert tx and resize(doc, ids[1], 90, 45) == 0
                assert resize(doc, ids[0], 200, 100) == 0
                assert api.rollback(tx) == 0 and api.write(doc) == saved
                assert api.undo(doc) == 0 and api.redo(doc) == 0 and api.write(doc) == saved
                for width, height in [(0,1), (-1,1), (float('nan'),1), (1,float('inf')), (1e100,1), (1e-20,1)]:
                    assert resize(doc, ids[0], width, height) != 0
                    assert api.write(doc) == saved
                tx = api.begin(doc)
                assert resize(doc, ids[0], 80, 40) == 0
                assert resize(doc, ids[0], 0, 40) != 0
                assert api.commit(tx) != 0 and api.write(doc) == saved
            finally:
                api.doc_free(doc)
    doc = api.read(package(body=paragraph('standalone')+SECT))
    try:
        id = api.image(doc, 0, png(), 100, 50)
        assert resize(doc, id, 150, 75) == 0
        reopened = api.read(api.write(doc))
        try:
            assert (view(images(api,reopened)[0]).width, view(images(api,reopened)[0]).height) == (1905000,952500)
        finally:
            api.doc_free(reopened)
    finally:
        api.doc_free(doc)
    print('L09 image_size: standalone/inline/floating/VML, duplicate anchors, protected cells, repeat/reopen, payload, rollback/undo/redo, invalid inputs PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', required=True, type=Path)
    main(parser.parse_args().library.resolve())
