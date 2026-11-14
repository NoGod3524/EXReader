#!/usr/bin/env python3
"""L13 public-ABI header/footer checks, independently audited with ZIP/OOXML."""
import argparse
import ctypes as c
from pathlib import Path
import posixpath
import xml.etree.ElementTree as ET

from test_docx_edit_io import Bridge, ID, package, repack, unzip
from verify_docx import W, R, REL, CT, NS


class Headers(Bridge):
    def __init__(self, library):
        super().__init__(library)
        ptr, size, uint = c.c_void_p, c.c_size_t, c.c_uint
        for name, args in [
            ('header_footer_text', [ptr, ID, uint, uint, c.POINTER(ptr), c.POINTER(size)]),
            ('set_header_footer_text', [ptr, ID, uint, uint, ptr, size]),
            ('header_footer_flags', [ptr, ID, c.POINTER(uint), c.POINTER(uint)]),
            ('set_header_footer_flags', [ptr, ID, uint, uint]),
            ('rollback', [ptr]),
        ]:
            fn = getattr(self.dll, 'exr_edit_' + name)
            fn.restype, fn.argtypes = c.c_int, args
            setattr(self, name, fn)

    def section(self, doc, index=0):
        count = c.c_size_t()
        sections = self.sections(doc, c.byref(count))
        assert count.value > index
        return sections[index].id

    def text(self, doc, footer=0, variant=0, section=None):
        data, size = c.c_void_p(), c.c_size_t()
        assert self.header_footer_text(doc, section or self.section(doc), footer, variant,
                                       c.byref(data), c.byref(size)) == 0
        try:
            return c.string_at(data, size.value).decode('utf-8')
        finally:
            self.free(data)

    def put(self, doc, text, footer=0, variant=0, section=None):
        data = text.encode('utf-8')
        assert self.set_header_footer_text(doc, section or self.section(doc), footer,
                                           variant, data, len(data)) == 0

    def flags(self, doc):
        first, even = c.c_uint(), c.c_uint()
        assert self.header_footer_flags(doc, self.section(doc), c.byref(first), c.byref(even)) == 0
        return first.value, even.value


def audit(data, expected, first=0, even=0):
    parts = unzip(data)
    document = ET.fromstring(parts['word/document.xml'])
    section = document.find('.//w:sectPr', NS)
    assert section is not None
    title = section.find('w:titlePg', NS)
    assert (title is not None and title.get('{%s}val' % W, '1') not in ('0', 'false', 'off')) == bool(first)
    rels = {n.get('Id'): n for n in ET.fromstring(parts['word/_rels/document.xml.rels'])}
    types = {n.get('PartName'): n.get('ContentType') for n in ET.fromstring(parts['[Content_Types].xml'])}
    variants = ('default', 'first', 'even')
    for (footer, variant), text in expected.items():
        kind = 'footer' if footer else 'header'
        ref = next(n for n in section.findall('w:' + kind + 'Reference', NS)
                   if n.get('{%s}type' % W) == variants[variant])
        rel = rels[ref.get('{%s}id' % R)]
        assert rel.get('Type').endswith('/' + kind)
        name = posixpath.normpath(posixpath.join('word', rel.get('Target')))
        node = ET.fromstring(parts[name])
        assert node.tag == '{%s}%s' % (W, 'ftr' if footer else 'hdr')
        # The API represents paragraph separators as newlines; text nodes retain
        # exact escaping and scalar values inside each paragraph.
        value = '\n'.join(''.join(p.itertext()) for p in node.findall('w:p', NS))
        assert value == text, (name, value, text)
        assert types['/' + name].endswith('.' + kind + '+xml')
    settings = [n for n in rels.values() if n.get('Type').endswith('/settings')]
    if settings:
        name = posixpath.normpath(posixpath.join('word', settings[0].get('Target')))
        node = ET.fromstring(parts[name]).find('w:evenAndOddHeaders', NS)
        actual = node is not None and node.get('{%s}val' % W, '1') not in ('0', 'false', 'off')
        assert actual == bool(even)
    else:
        assert not even
    return parts


def run(api):
    original = package(body='<w:p><w:r><w:t>body retained</w:t></w:r></w:p><w:sectPr/>')
    before = unzip(original)
    doc = api.read(original)
    expected = {}
    try:
        assert api.flags(doc) == (0, 0)
        assert api.text(doc) == api.text(doc, 1) == ''
        for footer, text in ((0, 'HDR'), (1, 'FTR')):
            api.put(doc, text, footer)
            expected[footer, 0] = text
        saved = api.write(doc)
        parts = audit(saved, expected)
        assert b'HDR' in parts['word/header1.xml']
        assert b'FTR' in parts['word/footer1.xml']
        for name, value in before.items():
            if name not in ('word/document.xml', 'word/_rels/document.xml.rels', '[Content_Types].xml'):
                assert parts[name] == value, name
        reopened = api.read(saved)
        try:
            assert (api.text(reopened), api.text(reopened, 1)) == ('HDR', 'FTR')
            audit(api.write(reopened), expected)
        finally:
            api.doc_free(reopened)
        print('HDR/FTR PASS: saved ZIP header1.xml=HDR footer1.xml=FTR; reopen and second write equal')

        section = api.section(doc)
        assert api.set_header_footer_flags(doc, section, 1, 1) == 0
        assert api.flags(doc) == (1, 1)
        audit(api.write(doc), expected, 1, 1)
        assert api.undo(doc) == 0 and api.flags(doc) == (0, 0)
        audit(api.write(doc), expected)
        assert api.redo(doc) == 0 and api.flags(doc) == (1, 1)
        assert api.set_header_footer_flags(doc, section, 0, 0) == 0
        audit(api.write(doc), expected)
        print('flags PASS: sectPr/titlePg and settings/evenAndOddHeaders 0->1->0, undo/redo')

        for footer, variant, text in ((0, 1, 'FIRST & <中>'), (0, 2, 'EVEN'), (1, 1, 'FIRST FOOT'), (1, 2, 'EVEN FOOT')):
            api.put(doc, text, footer, variant)
            expected[footer, variant] = text
        audit(api.write(doc), expected)
        for key, text in expected.items():
            assert api.text(doc, *key) == text
        snapshot = unzip(api.write(doc))
        tx = api.begin(doc)
        assert tx
        api.put(doc, 'temporary')
        assert api.set_header_footer_flags(doc, section, 1, 1) == 0
        assert api.rollback(tx) == 0
        assert unzip(api.write(doc)) == snapshot
        api.put(doc, 'changed')
        assert api.undo(doc) == 0 and api.text(doc) == 'HDR'
        assert api.redo(doc) == 0 and api.text(doc) == 'changed'
        expected[0, 0] = 'changed'
        audit(api.write(doc), expected)
        print('variants/history PASS: independent default/first/even header/footer; UTF-8/XML escaping; atomic rollback')

        multiline = '\nHDR\n\n'
        api.put(doc, multiline)
        expected[0, 0] = multiline
        assert api.text(doc) == multiline
        saved = api.write(doc)
        audit(saved, expected)
        reopened = api.read(saved)
        try:
            assert api.text(reopened) == multiline
            assert len(ET.fromstring(unzip(saved)['word/header1.xml']).findall('w:p', NS)) == 4
            audit(api.write(reopened), expected)
        finally:
            api.doc_free(reopened)
        api.put(doc, 'changed')
        expected[0, 0] = 'changed'
        assert len(ET.fromstring(unzip(api.write(doc))['word/header1.xml']).findall('w:p', NS)) == 1
        print('multiline PASS: leading/trailing/empty lines use four real w:p paragraphs; shrink back to one; save/reopen')

        assert api.set_header_footer_text(doc, section, 2, 0, b'x', 1) != 0
        assert api.set_header_footer_text(doc, section, 0, 3, b'x', 1) != 0
        assert api.set_header_footer_text(doc, section, 0, 0, b'\x01', 1) != 0
        assert api.set_header_footer_flags(doc, section, 2, 0) != 0
        audit(api.write(doc), expected)
        print('invalid input PASS: kind/variant/XML scalar/flags rejected; saved model unchanged')
    finally:
        api.doc_free(doc)

    parts = unzip(original)
    parts['word/document.xml'] = parts['word/document.xml'].replace(
        b'<w:sectPr/>', b'<w:sectPr><w:headerReference w:type="default" r:id="richHdr"/></w:sectPr>')
    parts['word/_rels/document.xml.rels'] = parts['word/_rels/document.xml.rels'].replace(
        b'</Relationships>', ('<Relationship Id="richHdr" Type="' + R + '/header" Target="header9.xml"/></Relationships>').encode())
    parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace(
        b'</Types>', b'<Override PartName="/word/header9.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/></Types>')
    keep = ('<w:pPr><w:pStyle w:val="Header"/><w:tabs><w:tab w:val="right" w:pos="9000"/></w:tabs></w:pPr>',
            '<w:bookmarkStart w:id="7" w:name="keep"/>',
            '<w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple>',
            '<w:hyperlink w:anchor="keep"><w:r><w:t>linked</w:t></w:r></w:hyperlink>',
            '<x:opaque x:mark="retained"/>',
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:rPr><w:i/></w:rPr><w:t>7</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>',
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>table retained</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
    rich = ('<w:hdr xmlns:w="' + W + '" xmlns:x="urn:keep"><w:p>' + keep[0] +
            '<w:r><w:rPr><w:b/></w:rPr><w:t>old</w:t></w:r>' + ''.join(keep[1:-1]) +
            '<w:r><w:rPr><w:i/></w:rPr><w:t>tail</w:t></w:r><w:bookmarkEnd w:id="7"/></w:p>' + keep[-1] + '</w:hdr>')
    parts['word/header9.xml'] = rich.encode()
    source = repack(parts)
    doc = api.read(source)
    try:
        api.put(doc, 'new & 中文')
        assert api.text(doc) == 'new & 中文'
        saved = api.write(doc)
        out = unzip(saved)
        assert 'word/header1.xml' not in out
        for fragment in keep:
            assert fragment.encode() in out['word/header9.xml'], fragment
        root = ET.fromstring(out['word/header9.xml'])
        direct_runs = root.find('w:p', NS).findall('w:r', NS)
        assert direct_runs[0].find('w:rPr/w:b', NS) is not None
        assert ''.join(direct_runs[0].find('w:t', NS).itertext()) == 'new & 中文'
        assert ''.join(direct_runs[-1].itertext()) == ''
        assert out['word/_rels/document.xml.rels'] == parts['word/_rels/document.xml.rels']
        assert api.undo(doc) == 0 and unzip(api.write(doc))['word/header9.xml'] == parts['word/header9.xml']
        assert api.redo(doc) == 0
        reopened = api.read(api.write(doc))
        try:
            assert api.text(reopened) == 'new & 中文'
            assert unzip(api.write(reopened))['word/header9.xml'] == out['word/header9.xml']
        finally:
            api.doc_free(reopened)
        print('rich existing header PASS: word/header9.xml, bold, tabs, bookmark, simple/complex PAGE fields, hyperlink, extension and table retained; undo/reopen')
    finally:
        api.doc_free(doc)

    for existing_flag in ('', '<w:evenAndOddHeaders w:val="0"/>'):
        parts = unzip(original)
        parts['word/_rels/document.xml.rels'] = parts['word/_rels/document.xml.rels'].replace(
            b'</Relationships>', ('<Relationship Id="settings" Type="' + R + '/settings" Target="settings.xml"/></Relationships>').encode())
        parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace(
            b'</Types>', b'<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/></Types>')
        fragments = ('<w:zoom w:percent="100"/>', '<w:defaultTabStop w:val="720"/>',
                     '<w:compat/>', '<w:docVars/>', '<x:extension x:keep="yes"/>')
        parts['word/settings.xml'] = ('<w:settings xmlns:w="' + W + '" xmlns:x="urn:keep">' +
                                     ''.join(fragments[:2]) + existing_flag + ''.join(fragments[2:]) + '</w:settings>').encode()
        doc = api.read(repack(parts))
        try:
            for enabled in (1, 0, 1):
                assert api.set_header_footer_flags(doc, api.section(doc), 0, enabled) == 0
                assert api.flags(doc) == (0, enabled)
                saved = api.write(doc)
                settings = unzip(saved)['word/settings.xml']
                for fragment in fragments:
                    assert fragment.encode() in settings
                children = [n.tag.rsplit('}', 1)[-1] for n in ET.fromstring(settings)]
                expected_order = ['zoom', 'defaultTabStop'] + (['evenAndOddHeaders'] if enabled else []) + ['compat', 'docVars', 'extension']
                assert children == expected_order, children
                reopened = api.read(saved)
                try:
                    assert api.flags(reopened) == (0, enabled)
                    assert unzip(api.write(reopened))['word/settings.xml'] == settings
                finally:
                    api.doc_free(reopened)
        finally:
            api.doc_free(doc)
    print('existing settings PASS: insert/replace/remove evenAndOddHeaders in schema order; zoom/defaultTabStop/compat/docVars/extension retained')

    strict_w = 'http://purl.oclc.org/ooxml/wordprocessingml/main'
    strict_r = 'http://purl.oclc.org/ooxml/officeDocument/relationships'
    strict_parts = {name: value.replace(W.encode(), strict_w.encode()).replace(R.encode(), strict_r.encode())
                    if name.endswith(('.xml', '.rels')) else value for name, value in unzip(original).items()}
    doc = api.read(repack(strict_parts))
    try:
        api.put(doc, 'strict HDR')
        api.put(doc, 'strict FTR', 1)
        assert api.set_header_footer_flags(doc, api.section(doc), 1, 1) == 0
        saved = api.write(doc)
        parts = unzip(saved)
        for name, local in (('header1', 'hdr'), ('footer1', 'ftr'), ('settings', 'settings')):
            assert ET.fromstring(parts['word/' + name + '.xml']).tag == '{%s}%s' % (strict_w, local)
        types = [n.get('Type') for n in ET.fromstring(parts['word/_rels/document.xml.rels'])]
        assert all(strict_r + '/' + kind in types for kind in ('header', 'footer', 'settings'))
        section = ET.fromstring(parts['word/document.xml']).find('.//{%s}sectPr' % strict_w)
        refs = [n for n in section if n.tag.endswith(('headerReference', 'footerReference'))]
        assert len(refs) == 2 and all(n.get('{%s}id' % strict_r) for n in refs)
        reopened = api.read(saved)
        try:
            assert (api.text(reopened), api.text(reopened, 1), api.flags(reopened)) == ('strict HDR', 'strict FTR', (1, 1))
            for name in ('word/header1.xml', 'word/footer1.xml', 'word/settings.xml'):
                assert unzip(api.write(reopened))[name] == parts[name]
        finally:
            api.doc_free(reopened)
    finally:
        api.doc_free(doc)
    print('Strict namespaces PASS: new header/footer/settings use Strict W namespace, relationship Types/IDs use Strict R; save/reopen')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    args = parser.parse_args()
    run(Headers(args.library.resolve()))
    print('L13 engine header/footer acceptance PASS')
