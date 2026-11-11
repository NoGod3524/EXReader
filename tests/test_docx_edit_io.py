#!/usr/bin/env python3
"""Exercise the compiled bridge through its public ABI, audited with ZIP/XML."""
import argparse
import base64
import ctypes as c
import io
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/docx'))
from roundtrip import metrics, Error
from verify_docx import verify, W, NS, R

ID = c.c_uint64
class RP(c.Structure):
    _fields_ = [('present', c.c_uint32), ('font', c.c_char * 128),
                ('size', c.c_uint32), ('color', c.c_uint32), ('bold', c.c_uint), ('italic', c.c_uint)]
class PP(c.Structure):
    _fields_ = [('present', c.c_uint32), ('align', c.c_int),
                ('left', c.c_int32), ('right', c.c_int32), ('first', c.c_int32),
                ('before', c.c_uint32), ('after', c.c_uint32), ('line', c.c_uint32),
                ('rule', c.c_int), ('keep_next', c.c_uint), ('keep_lines', c.c_uint),
                ('page_before', c.c_uint), ('numbering', c.c_uint32), ('level', c.c_uint32)]
class Run(c.Structure):
    _fields_ = [('id', ID), ('kind', c.c_int), ('text', c.c_void_p), ('length', c.c_size_t),
                ('props', RP), ('xml', c.c_void_p), ('xml_size', c.c_size_t)]
class Block(c.Structure):
    _fields_ = [('id', ID), ('section', ID), ('kind', c.c_int), ('props', PP),
                ('runs', c.POINTER(Run)), ('count', c.c_size_t),
                ('xml', c.c_void_p), ('xml_size', c.c_size_t),
                ('table', c.c_void_p), ('image', c.c_void_p)]
class Section(c.Structure):
    _fields_ = [('id', ID)] + [(n, c.c_int32) for n in
                ('width', 'height', 'top', 'right', 'bottom', 'left', 'header', 'footer')] + [
                ('landscape', c.c_uint), ('headers', (c.c_char * 128) * 3), ('footers', (c.c_char * 128) * 3)]
class Part(c.Structure):
    _fields_ = [('id', ID), ('name', c.c_char_p), ('data', c.c_void_p), ('size', c.c_size_t)]

class Bridge:
    def __init__(self, library):
        import os
        self.directory = os.add_dll_directory(str(library.parent)) if os.name == 'nt' else None
        self.dll = c.CDLL(str(library))
        ptr, size, err = c.c_void_p, c.c_size_t, c.POINTER(Error)
        for name, result, args in [
            ('edit_docx_read', c.c_int, [ptr, size, ptr, c.POINTER(ptr), err]),
            ('edit_docx_write', c.c_int, [ptr, c.POINTER(ptr), c.POINTER(size), err]),
            ('edit_doc_free', None, [ptr]), ('free', None, [ptr]),
            ('edit_block_count', size, [ptr]), ('edit_block_at', c.POINTER(Block), [ptr, size]),
            ('edit_sections', c.POINTER(Section), [ptr, c.POINTER(size)]),
            ('edit_parts', c.POINTER(Part), [ptr, c.POINTER(size)]),
            ('edit_doc_create', c.c_int, [c.POINTER(Section), size, c.POINTER(Block), size, ptr, size, ptr, c.POINTER(ptr)]),
            ('edit_insert_paragraph', c.c_int, [ptr, ID, c.POINTER(Run), size, c.POINTER(PP), c.POINTER(ID)]),
            ('edit_set_paragraph_props', c.c_int, [ptr, ID, c.POINTER(PP)]),
            ('edit_set_run_props', c.c_int, [ptr, ID, size, c.POINTER(RP)]),
            ('edit_split_paragraph', c.c_int, [ptr, ID, size, size]),
            ('edit_delete_block', c.c_int, [ptr, ID]),
            ('edit_begin', ptr, [ptr]), ('edit_commit', c.c_int, [ptr]),
            ('edit_undo', c.c_int, [ptr]), ('edit_redo', c.c_int, [ptr])]:
            f = getattr(self.dll, 'exr_' + name)
            f.restype, f.argtypes = result, args
            setattr(self, name.removeprefix('edit_'), f)
    def read(self, data):
        doc, err = c.c_void_p(), Error()
        status = self.docx_read(data, len(data), None, c.byref(doc), c.byref(err))
        assert status == 0, (status, err.message)
        return doc
    def write(self, doc):
        data, size, err = c.c_void_p(), c.c_size_t(), Error()
        status = self.docx_write(doc, c.byref(data), c.byref(size), c.byref(err))
        assert status == 0, (status, err.message)
        try:
            result = c.string_at(data, size.value)
            ET.fromstring(unzip(result)['word/document.xml'])
            return result
        finally:
            self.free(data)
    def paragraphs(self, doc):
        return [self.block_at(doc, i).contents for i in range(self.block_count(doc))
                if self.block_at(doc, i).contents.kind == 0]

def unzip(data):
    with ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist()))
        return {n: z.read(n) for n in z.namelist()}

def repack(parts):
    out = io.BytesIO()
    with ZipFile(out, 'w') as z:
        for name, value in parts.items():
            z.writestr(name, value)
    return out.getvalue()

def package(body=None, strict=False, prefix='w'):
    w = 'http://purl.oclc.org/ooxml/wordprocessingml/main' if strict else W
    sect = '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/><w:cols w:num="2"/></w:sectPr>'
    p = '<w:p custom="preserve"><w:pPr><w:pStyle w:val="Normal"/><w:spacing w:line="480" w:lineRule="auto" x:extra="keep"/>{}</w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:b w:val="0"/><w:sz w:val="24"/><w:u w:val="single"/></w:rPr><w:t xml:space="preserve">{}</w:t></w:r>{}</w:p>'
    image = '<w:r><w:drawing><a:blip r:embed="image1"/></w:drawing></w:r>'
    table = '<w:tbl x:extra="table"><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    unknown = '<x:unknown x:flag="1"><w:p><w:r><w:t>retained</w:t></w:r></w:p></x:unknown>'
    notes = '<w:r><w:footnoteReference w:id="1"/><w:endnoteReference w:id="2"/></w:r>'
    if body is None:
        body = p.format('', 'alpha &amp; 中文', image + notes) + table + unknown + p.format(sect, 'beta', '') + p.format('', 'gamma', '') + sect
    document = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="' + w + '" xmlns:r="' + R + '" xmlns:x="urn:unknown" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><w:body>' + body + '</w:body></w:document>').replace('w:', prefix + ':').replace('xmlns:w=', 'xmlns:' + prefix + '=')
    rel = 'http://schemas.openxmlformats.org/package/2006/relationships'
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels': f'<Relationships xmlns="{rel}"><Relationship Id="doc" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': document,
        'word/_rels/document.xml.rels': f'<Relationships xmlns="{rel}"><Relationship Id="image1" Type="{R}/image" Target="media/image1.png"/><Relationship Id="fn" Type="{R}/footnotes" Target="footnotes.xml"/><Relationship Id="en" Type="{R}/endnotes" Target="endnotes.xml"/><Relationship Id="numbering" Type="{R}/numbering" Target="numbering.xml"/></Relationships>',
        'word/numbering.xml': f'<w:numbering xmlns:w="{w}"><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="2"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%3."/></w:lvl></w:abstractNum><w:num w:numId="5"><w:abstractNumId w:val="0"/></w:num></w:numbering>',
        'word/footnotes.xml': f'<w:footnotes xmlns:w="{w}"><w:footnote w:id="1"><w:p><w:r><w:t>footnote</w:t></w:r></w:p></w:footnote></w:footnotes>',
        'word/endnotes.xml': f'<w:endnotes xmlns:w="{w}"><w:endnote w:id="2"><w:p><w:r><w:t>endnote</w:t></w:r></w:p></w:endnote></w:endnotes>',
        'word/styles.xml': f'<w:styles xmlns:w="{w}"><w:style w:type="paragraph" w:styleId="Normal"><w:rPr><w:color w:val="112233"/></w:rPr></w:style></w:styles>',
        'word/media/image1.png': base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aHfcAAAAASUVORK5CYII='),
        'customXml/item1.xml': '<unknown xmlns="urn:custom"> untouched </unknown>',
        'custom/data.bin': b'\0\xffbinary\r\n',
    }
    out = io.BytesIO()
    with ZipFile(out, 'w') as z:
        for n, v in parts.items():
            z.writestr(n, v)
    return out.getvalue()

def preserved(before, after):
    a, b = unzip(before), unzip(after)
    assert set(a) == set(b)
    assert all(a[n] == b[n] for n in a if n != 'word/document.xml')
    for tag in ('tbl', 'drawing', 'footnoteReference', 'endnoteReference', 'cols', 'u'):
        x, y = ET.fromstring(a['word/document.xml']), ET.fromstring(b['word/document.xml'])
        assert [ET.tostring(n) for n in x.iter('{%s}%s' % (W, tag))] == [ET.tostring(n) for n in y.iter('{%s}%s' % (W, tag))], tag

def audit(data):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'test.docx'
        p.write_bytes(data)
        return metrics(p)

def test(group, api):
    source = package()
    doc = api.read(source)
    try:
        if group in ('roundtrip', 'parts', 'unknown', 'sections'):
            saved = api.write(doc)
            preserved(source, saved)
            assert audit(source) == audit(saved)
            reopened = api.read(saved)
            try:
                assert audit(saved) == audit(api.write(reopened))
            finally:
                api.doc_free(reopened)
            if group == 'unknown':
                assert b'<x:unknown x:flag="1">' in unzip(saved)['word/document.xml']
                assert b'x:extra="keep"' in unzip(saved)['word/document.xml']
                parts = unzip(source)
                parts['word/document.xml'] = parts['word/document.xml'].replace(
                    b'<w:t xml:space="preserve">', b'<!--inline bytes--><?keep instruction?><w:t xml:space="preserve">')
                commented = repack(parts)
                model = api.read(commented)
                try:
                    out = unzip(api.write(model))['word/document.xml']
                    assert out.count(b'<!--inline bytes--><?keep instruction?>') == 3
                finally:
                    api.doc_free(model)
            if group == 'parts':
                parts = unzip(source)
                parts['custom/'] = b''
                parts['custom/empty.bin'] = b''
                parts['custom/' + 'a' * 600 + '.bin'] = b'long OPC name'
                extended = repack(parts)
                model = api.read(extended)
                try:
                    preserved(extended, api.write(model))
                finally:
                    api.doc_free(model)
            if group == 'sections':
                count = c.c_size_t()
                sections = api.sections(doc, c.byref(count))
                assert count.value == 2
                assert sections[0].width == 12240 and sections[1].left == 1440
                for body in ('<w:p><w:r><w:t>implicit section</w:t></w:r></w:p>',
                             '<w:p><w:pPr><w:sectPr/></w:pPr><w:r><w:t>paragraph section</w:t></w:r></w:p>'):
                    original = package(body=body)
                    model = api.read(original)
                    try:
                        assert audit(api.write(model)) == audit(original)
                    finally:
                        api.doc_free(model)
        elif group == 'properties':
            p = api.paragraphs(doc)[0]
            pp = PP(present=127, align=2, left=120, right=240, first=-720,
                    before=60, after=120, line=360, rule=1,
                    keep_next=1, keep_lines=1, page_before=1, numbering=5, level=2)
            rp = RP(present=31, font=b'Calibri', size=28, color=0x123456, bold=1, italic=1)
            assert api.set_paragraph_props(doc, p.id, c.byref(pp)) == 0
            assert api.set_run_props(doc, p.id, 0, c.byref(rp)) == 0
            model = api.read(api.write(doc))
            try:
                q = api.paragraphs(model)[0]
                for name, _ in PP._fields_:
                    assert getattr(q.props, name) == getattr(pp, name), name
                for name, _ in RP._fields_:
                    assert getattr(q.runs[0].props, name) == getattr(rp, name), name
            finally:
                api.doc_free(model)
            pp, rp = PP(), RP()
            assert api.set_paragraph_props(doc, p.id, c.byref(pp)) == 0
            assert api.set_run_props(doc, p.id, 0, c.byref(rp)) == 0
            saved = api.write(doc)
            assert b'<w:u w:val="single"/>' in unzip(saved)['word/document.xml']
            model = api.read(saved)
            try:
                assert api.paragraphs(model)[0].props.present == 0
                assert api.paragraphs(model)[0].runs[0].props.present == 0
            finally:
                api.doc_free(model)
            inherited = package(body='<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:spacing w:before="120"/><w:ind w:firstLine="240"/></w:pPr><w:r><w:t>inherit</w:t></w:r></w:p><w:sectPr/>')
            model = api.read(inherited)
            try:
                q = api.paragraphs(model)[0]
                pp = PP.from_buffer_copy(q.props)
                pp.present |= 1
                pp.align = 1
                pp.before = 180
                pp.first = 360
                assert api.set_paragraph_props(model, q.id, c.byref(pp)) == 0
                out_xml = unzip(api.write(model))['word/document.xml']
                assert b'w:line="0"' not in out_xml and b'w:left="0"' not in out_xml and b'w:right="0"' not in out_xml
            finally:
                api.doc_free(model)
        elif group == 'edits':
            paragraphs = api.paragraphs(doc)
            ids = [p.id for p in paragraphs]
            tx = api.begin(doc)
            assert tx
            pp = PP(present=7, align=3, first=720, after=120, line=480)
            for block in ids[:3]:
                assert api.set_paragraph_props(doc, block, c.byref(pp)) == 0
            rp = RP(present=31, font=b'Times New Roman', size=24, color=0xAA1122, bold=1, italic=1)
            assert api.set_run_props(doc, ids[0], 0, c.byref(rp)) == 0
            for i in range(5):
                text = ('inserted %d 中文' % i).encode()
                storage = c.create_string_buffer(text)
                run = Run(kind=0, text=c.cast(storage, c.c_void_p), length=len(text), props=rp)
                new = ID()
                assert api.insert_paragraph(doc, ids[0], c.byref(run), 1, c.byref(pp), c.byref(new)) == 0
            assert api.commit(tx) == 0
            saved = api.write(doc)
            preserved(source, saved)
            before, after = audit(source), audit(saved)
            assert after['paragraphs'] == before['paragraphs'] + 5
            for k in ('tables', 'images', 'footnotes', 'section_margins', 'image_sha256'):
                assert before[k] == after[k], k
            reopened = api.read(saved)
            try:
                ps = api.paragraphs(reopened)
                assert len(ps) == 8
                assert sum(p.props.first == 720 and p.props.after == 120 for p in ps) == 8
                assert ps[0].runs[0].props.bold == 1 and ps[0].runs[0].props.color == 0xAA1122
                assert b'<w:u w:val="single"/>' in unzip(saved)['word/document.xml']
                assert b'x:extra="keep"' in unzip(saved)['word/document.xml']
            finally:
                api.doc_free(reopened)
            assert api.undo(doc) == 0
            assert audit(api.write(doc)) == audit(source)
            assert api.redo(doc) == 0
            assert audit(api.write(doc)) == audit(saved)
        elif group == 'split':
            p = api.paragraphs(doc)[1]
            assert api.split_paragraph(doc, p.id, 0, 2) == 0
            saved = api.write(doc)
            assert audit(saved)['characters'] == audit(source)['characters']
            assert audit(saved)['paragraphs'] == audit(source)['paragraphs'] + 1
            assert audit(saved)['section_margins'] == audit(source)['section_margins']
            assert api.delete_block(doc, p.id) == 0
            reopened = api.read(api.write(doc))
            api.doc_free(reopened)
        elif group == 'namespaces':
            variants = [package(strict=s, prefix='z') for s in (False, True)]
            parts = unzip(package(prefix='z'))
            xml = parts['word/document.xml'].decode()
            xml = xml.replace('<z:document ', '<z:document xmlns="' + W + '" ')
            xml = xml.replace('<z:', '<').replace('</z:', '</')
            parts['word/document.xml'] = xml.encode()
            variants.append(repack(parts))
            parts = unzip(package(prefix='z'))
            parts['word/document.xml'] = parts['word/document.xml'].replace(
                b'<z:spacing ', b'<z:spacing xmlns:w="urn:other" w:line="opaque" ')
            variants.append(repack(parts))
            repeated = '<w:r><w:rPr><z:color z:val="123456"/></w:rPr><w:t>same</w:t></w:r>'
            variants.append(package(body='<w:p xmlns:z="' + W + '">' + repeated +
                '</w:p><w:p xmlns:z="urn:other">' + repeated + '</w:p><w:sectPr/>'))
            for data in variants:
                model = api.read(data)
                try:
                    p = api.paragraphs(model)[0]
                    pp = PP(present=7, first=720, after=120, line=480)
                    assert api.set_paragraph_props(model, p.id, c.byref(pp)) == 0
                    if b'xmlns:z="urn:other"' in data:
                        p = api.paragraphs(model)[1]
                        rp = RP(present=4, bold=1)
                        assert api.set_run_props(model, p.id, 0, c.byref(rp)) == 0
                    out = api.write(model)
                    if b'w:line="opaque"' in data:
                        assert b'w:line="opaque"' in unzip(out)['word/document.xml']
                        assert b'xmlns:w="urn:other"' in unzip(out)['word/document.xml']
                    again = api.read(out)
                    if b'xmlns:z="urn:other"' in data:
                        assert b'<z:color z:val="123456"/>' in unzip(out)['word/document.xml']
                        assert api.paragraphs(again)[1].runs[0].props.present == 4
                    api.doc_free(again)
                finally:
                    api.doc_free(model)
        elif group == 'section-scope':
            section = ('<q:sectPr><q:pgSz q:w="12240" q:h="15840"/>'
                       '<q:pgMar q:top="1440" q:right="1440" q:bottom="1440" q:left="1440"/>'
                       '<x:opaque v:flag="keep"><q:cols q:num="2"/></x:opaque></q:sectPr>')
            body = ('<w:p xmlns:q="' + W + '" xmlns:v="' + R + '" xmlns:x="urn:section-only">'
                    '<w:pPr>' + section + '</w:pPr><w:r><w:t>alpha</w:t></w:r></w:p>'
                    '<w:p><w:r><w:t>beta</w:t></w:r></w:p><w:sectPr/>')
            original = package(body=body)
            for action in ('insert', 'split', 'delete'):
                model = api.read(original)
                try:
                    first = api.paragraphs(model)[0]
                    if action == 'insert':
                        new_id = ID()
                        assert api.insert_paragraph(model, first.id, None, 0, None, c.byref(new_id)) == 0
                    elif action == 'split':
                        assert api.split_paragraph(model, first.id, 0, 2) == 0
                    else:
                        assert api.delete_block(model, first.id) == 0
                    saved = api.write(model)
                    xml = unzip(saved)['word/document.xml']
                    root = ET.fromstring(xml)
                    assert len(list(root.iter('{%s}sectPr' % W))) == 2
                    opaque = list(root.iter('{urn:section-only}opaque'))
                    assert len(opaque) == 1 and opaque[0].get('{%s}flag' % R) == 'keep'
                    assert b'<x:opaque v:flag="keep"><q:cols q:num="2"/></x:opaque>' in xml
                    reopened = api.read(saved)
                    api.doc_free(reopened)
                finally:
                    api.doc_free(model)
        elif group == 'section-edits':
            parts = unzip(source)
            parts['word/document.xml'] = parts['word/document.xml'].replace(
                b'<w:sectPr>', b'<w:sectPr><w:headerReference w:type="default" r:id="headerOld" x:extra="keep"/>'
                b'<w:footerReference w:type="default" r:id="footerOld"/>').replace(
                b'<w:pgMar ', b'<w:pgMar w:gutter="120" ')
            xml = parts['word/document.xml']
            boundary = xml.rfind(b'<w:sectPr>')
            parts['word/document.xml'] = xml[:boundary] + xml[boundary:].replace(
                b'<w:pgSz w:w="12240" w:h="15840"/>', b'').replace(
                b'<w:pgMar w:gutter="120" w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>', b'')
            for kind, refs in (('header', ('Old', 'New', 'First', 'Even')), ('footer', ('Old', 'First', 'Even'))):
                for suffix in refs:
                    ref = kind + suffix
                    relationship = f'<Relationship Id="{ref}" Type="{R}/{kind}" Target="{ref}.xml"/>'
                    parts['word/_rels/document.xml.rels'] = parts['word/_rels/document.xml.rels'].replace(
                        b'</Relationships>', relationship.encode() + b'</Relationships>')
                    parts['word/' + ref + '.xml'] = f'<w:{"hdr" if kind == "header" else "ftr"} xmlns:w="{W}"/>'
            original = api.read(repack(parts))
            try:
                ns, np = c.c_size_t(), c.c_size_t()
                old = api.sections(original, c.byref(ns))
                sections = (Section * ns.value)(*[old[i] for i in range(ns.value)])
                for s in sections:
                    s.width, s.height, s.landscape = 15840, 12240, 1
                    s.top, s.right, s.bottom, s.left = -360, 900, -720, 1800
                    s.header, s.footer = 360, 480
                    for i, ref in enumerate((b'headerNew', b'headerFirst', b'headerEven')):
                        s.headers[i].value = ref
                    for i, ref in enumerate((b'', b'footerFirst', b'footerEven')):
                        s.footers[i].value = ref
                count = api.block_count(original)
                blocks = (Block * count)(*[api.block_at(original, i).contents for i in range(count)])
                retained = api.parts(original, c.byref(np))
                seeded = c.c_void_p()
                assert api.doc_create(sections, ns, blocks, count, retained, np, None, c.byref(seeded)) == 0
                try:
                    saved = api.write(seeded)
                    reopened = api.read(saved)
                    try:
                        actual = api.sections(reopened, c.byref(ns))
                        for i in range(ns.value):
                            for field, _ in Section._fields_[1:-2]:
                                assert getattr(actual[i], field) == getattr(sections[i], field), field
                            for field in ('headers', 'footers'):
                                assert [r.value for r in getattr(actual[i], field)] == [r.value for r in getattr(sections[i], field)]
                        xml = unzip(saved)['word/document.xml']
                        assert xml.count(b'x:extra="keep"') == 5  # three spacing nodes plus two references
                        assert xml.count(b'w:gutter="120"') == 1
                        for section in ET.fromstring(xml).iter('{%s}sectPr' % W):
                            order = [n.tag.rsplit('}', 1)[-1] for n in section]
                            assert order.index('pgSz') < order.index('pgMar') < order.index('cols'), order
                    finally:
                        api.doc_free(reopened)
                finally:
                    api.doc_free(seeded)
            finally:
                api.doc_free(original)
        elif group == 'section-boundaries':
            trivia = b'\n<!--after section--><?keep boundary?>\n'
            parts = unzip(source)
            parts['word/document.xml'] = parts['word/document.xml'].replace(
                b'beta</w:t></w:r></w:p>', b'beta</w:t></w:r></w:p>' + trivia)
            with_trivia = repack(parts)
            model = api.read(with_trivia)
            try:
                saved = api.write(model)
                assert audit(saved) == audit(with_trivia)
                assert trivia in unzip(saved)['word/document.xml']
            finally:
                api.doc_free(model)
            # Removing a section's final paragraph must leave a preceding opaque
            # block in that section, even when it cannot itself host sectPr.
            opaque = '<x:unknown><w:p><w:r><w:t>opaque</w:t></w:r></w:p></x:unknown>'
            body = ('<w:p><w:r><w:t>first</w:t></w:r></w:p>' + opaque +
                    '<w:p><w:pPr><w:sectPr><w:pgMar w:top="720"/></w:sectPr></w:pPr></w:p>'
                    '<w:p><w:r><w:t>next section</w:t></w:r></w:p><w:sectPr/>')
            model = api.read(package(body=body))
            try:
                assert api.delete_block(model, api.paragraphs(model)[1].id) == 0
                saved = api.write(model)
                xml = unzip(saved)['word/document.xml']
                root = ET.fromstring(xml)
                children = list(root.find('w:body', NS))
                unknown = next(i for i, n in enumerate(children) if n.tag == '{urn:unknown}unknown')
                boundary = next(i for i, n in enumerate(children) if n.find('w:pPr/w:sectPr', NS) is not None)
                assert unknown < boundary, 'opaque block moved across the section boundary'
                assert opaque.encode() in xml
                reopened = api.read(saved)
                try:
                    blocks = [api.block_at(reopened, i).contents for i in range(api.block_count(reopened))]
                    assert blocks[0].section == blocks[1].section
                    assert blocks[-1].section != blocks[1].section
                finally:
                    api.doc_free(reopened)
            finally:
                api.doc_free(model)
            # A source with an implicit final section stays implicit on no-op,
            # but changes made through the section model must be serialized.
            implicit = package(body='<w:p><w:r><w:t>implicit</w:t></w:r></w:p>')
            original = api.read(implicit)
            try:
                assert b'sectPr' not in unzip(api.write(original))['word/document.xml']
                ns, np = c.c_size_t(), c.c_size_t()
                old = api.sections(original, c.byref(ns))
                sections = (Section * ns.value)(*[old[i] for i in range(ns.value)])
                sections[0].width, sections[0].left = 15840, 2160
                count = api.block_count(original)
                blocks = (Block * count)(*[api.block_at(original, i).contents for i in range(count)])
                retained = api.parts(original, c.byref(np))
                seeded = c.c_void_p()
                assert api.doc_create(sections, ns, blocks, count, retained, np, None, c.byref(seeded)) == 0
                try:
                    reopened = api.read(api.write(seeded))
                    try:
                        actual = api.sections(reopened, c.byref(ns))
                        assert actual[0].width == 15840 and actual[0].left == 2160
                    finally:
                        api.doc_free(reopened)
                finally:
                    api.doc_free(seeded)
            finally:
                api.doc_free(original)
        elif group == 'new':
            new = c.c_void_p()
            assert api.doc_create(None, 0, None, 0, None, 0, None, c.byref(new)) == 0
            try:
                pp = PP(present=7, first=720, after=120, line=480)
                rp = RP(present=3, font=b'Times New Roman', size=24)
                storage = c.create_string_buffer(b'new document')
                r = Run(text=c.cast(storage, c.c_void_p), length=12, props=rp)
                new_id = ID()
                assert api.insert_paragraph(new, 0, c.byref(r), 1, c.byref(pp), c.byref(new_id)) == 0
                saved = api.write(new)
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / 'new.docx'
                    p.write_bytes(saved)
                    assert all(r['status'] == 'PASS' for r in verify(p)), verify(p)
                reopened = api.read(saved)
                api.doc_free(reopened)
                assert b'DATE' in unzip(saved)['word/header1.xml']
            finally:
                api.doc_free(new)
            parts = unzip(source)
            xml = parts['word/document.xml'].decode()
            parts['word/document.xml'] = (xml.split('<w:body>')[0] + '<w:body/>' + xml.split('</w:body>')[1]).encode()
            empty = api.read(repack(parts))
            try:
                reopened = api.read(api.write(empty))
                api.doc_free(reopened)
            finally:
                api.doc_free(empty)
        elif group == 'errors':
            parts = unzip(source)
            xml = parts['word/document.xml'].decode().replace('encoding="UTF-8"', 'encoding="UTF-16"')
            parts['word/document.xml'] = xml.encode('utf-16')
            for data in (b'garbage', source[:100], package(body='<w:p>'), repack(parts)):
                model, err = c.c_void_p(123), Error()
                assert api.docx_read(data, len(data), None, c.byref(model), c.byref(err)) != 0
                assert model.value is None
            data, size, err = c.c_void_p(123), c.c_size_t(123), Error()
            assert api.docx_write(None, c.byref(data), c.byref(size), c.byref(err)) != 0
            assert data.value is None and size.value == 0
            template = c.create_string_buffer(b'<w:pPr xmlns:w="' + W.encode() + b'"><w:shd w:fill="abcdef"/></w:pPr>')
            b = Block(xml=c.cast(template, c.c_void_p), xml_size=len(template.value))
            seeded = c.c_void_p()
            assert api.doc_create(None, 0, c.byref(b), 1, None, 0, None, c.byref(seeded)) == 0
            try:
                assert api.docx_write(seeded, c.byref(data), c.byref(size), c.byref(err)) != 0
                assert data.value is None and size.value == 0
            finally:
                api.doc_free(seeded)
    finally:
        api.doc_free(doc)
    print(group, 'PASS')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('group', choices=('roundtrip', 'parts', 'unknown', 'sections', 'properties', 'edits', 'split', 'namespaces', 'section-scope', 'section-edits', 'section-boundaries', 'new', 'errors'))
    args = parser.parse_args()
    test(args.group, Bridge(args.library.resolve()))
