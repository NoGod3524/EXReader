"""Run: python -m unittest discover -s tests/docx -v (no third-party packages)."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'docx'))
from verify_docx import W, R, REL, NS, verify
from roundtrip import metrics, differences, pdf_compare

DOCUMENT = '''<w:document xmlns:w="%s" xmlns:r="%s"><w:body>
<w:p><w:pPr><w:spacing w:line="480" w:lineRule="auto"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/></w:rPr><w:t>Title alpha</w:t></w:r></w:p>
<w:sectPr><w:headerReference w:type="default" r:id="h"/><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
</w:body></w:document>''' % (W, R)
PARTS = {
    'word/document.xml': DOCUMENT,
    '[Content_Types].xml': '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/></Types>''',
    '_rels/.rels': '<Relationships xmlns="%s"><Relationship Id="main" Type="%s/officeDocument" Target="word/document.xml"/></Relationships>' % (REL, R),
    'word/_rels/document.xml.rels': '<Relationships xmlns="%s"><Relationship Id="h" Type="%s/header" Target="header1.xml"/></Relationships>' % (REL, R),
    'word/header1.xml': '<w:hdr xmlns:w="%s"><w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:hdr>' % W,
}


def write(path, parts):
    with ZipFile(path, 'w') as z:
        for name, value in parts.items():
            z.writestr(name, value)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'test.docx'

    def statuses(self, parts):
        write(self.path, parts)
        return {r['check']: r for r in verify(self.path)}

    def test_good_then_deliberately_broken_cli(self):
        tool = Path(__file__).resolve().parents[2] / 'tools/docx/verify_docx.py'
        write(self.path, PARTS)
        good = subprocess.run([sys.executable, str(tool), str(self.path)], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertGreaterEqual(good.stdout.count('| PASS |'), 8)
        broken = dict(PARTS, **{'word/document.xml': DOCUMENT.replace('<w:pgSz w:w="12240" w:h="15840"/>', '')})
        write(self.path, broken)
        bad = subprocess.run([sys.executable, str(tool), str(self.path)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn('| letter_page_size | FAIL |', bad.stdout)
        self.assertIn('FAIL XML: letter_page_size', bad.stdout)
        self.assertIn('<w:sectPr', bad.stdout)

    def test_each_contract_mutation(self):
        mutations = [
            ('section_present', lambda d: d.find('w:body', NS).remove(d.find('.//w:sectPr', NS))),
            ('section_nonempty', lambda d: d.find('.//w:sectPr', NS).clear()),
            ('paragraph_properties', lambda d: d.find('.//w:p', NS).remove(d.find('.//w:pPr', NS))),
            ('double_spacing', lambda d: d.find('.//w:spacing', NS).set('{%s}line' % W, '240')),
            ('double_spacing', lambda d: d.find('.//w:spacing', NS).set('{%s}lineRule' % W, 'exact')),
            ('letter_page_size', lambda d: d.find('.//w:pgSz', NS).set('{%s}h' % W, '16838')),
            ('one_inch_margins', lambda d: d.find('.//w:pgMar', NS).set('{%s}left' % W, '720')),
            ('font_times_new_roman', lambda d: d.find('.//w:rFonts', NS).set('{%s}hAnsi' % W, 'Arial')),
            ('font_size_12pt', lambda d: d.find('.//w:sz', NS).set('{%s}val' % W, '22')),
            ('header_page_field', lambda d: d.find('.//w:headerReference', NS).set('{%s}id' % R, 'missing')),
        ]
        for name, mutate in mutations:
            with self.subTest(check=name):
                root = ET.fromstring(DOCUMENT)
                mutate(root)
                rows = self.statuses(dict(PARTS, **{'word/document.xml': ET.tostring(root)}))
                self.assertEqual(rows[name]['status'], 'FAIL')
                self.assertTrue(rows[name]['xml'])

    def test_header_must_be_used_and_page_is_not_pageref(self):
        parts = dict(PARTS)
        parts['word/header1.xml'] = parts['word/header1.xml'].replace(' PAGE ', ' PAGEREF bookmark ')
        self.assertEqual(self.statuses(parts)['header_page_field']['status'], 'FAIL')
        parts['word/_rels/document.xml.rels'] = '<Relationships xmlns="%s"/>' % REL
        rows = self.statuses(parts)
        self.assertEqual(rows['header_part']['status'], 'WARN')
        self.assertEqual(rows['header_page_field']['status'], 'FAIL')

    def test_inherited_format_and_direct_override(self):
        root = ET.fromstring(DOCUMENT)
        root.find('.//w:pPr', NS).remove(root.find('.//w:spacing', NS))
        root.find('.//w:r', NS).remove(root.find('.//w:rPr', NS))
        parts = dict(PARTS, **{'word/document.xml': ET.tostring(root)})
        parts['word/styles.xml'] = '''<w:styles xmlns:w="%s"><w:docDefaults><w:pPrDefault><w:pPr><w:spacing w:line="480" w:lineRule="auto"/></w:pPr></w:pPrDefault><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults></w:styles>''' % W
        self.assertTrue(all(r['status'] == 'PASS' for r in self.statuses(parts).values()))
        props = ET.SubElement(root.find('.//w:r', NS), '{%s}rPr' % W)
        ET.SubElement(props, '{%s}sz' % W, {'{%s}val' % W: '20'})
        parts['word/document.xml'] = ET.tostring(root)
        self.assertEqual(self.statuses(parts)['font_size_12pt']['status'], 'FAIL')

    def test_malformed_zip_xml_and_missing_part_fail(self):
        self.path.write_bytes(b'not a ZIP')
        self.assertEqual(verify(self.path)[0]['status'], 'FAIL')
        for parts in [{'word/document.xml': '<bad'}, {'word/not-document.xml': '<ok/>'}]:
            self.assertEqual(self.statuses(parts)['package_xml']['status'], 'FAIL')

    def test_later_section_and_later_paragraph_are_checked(self):
        root = ET.fromstring(DOCUMENT)
        body = root.find('w:body', NS)
        body.insert(0, ET.fromstring('<w:p xmlns:w="%s"><w:r><w:t>Later</w:t></w:r></w:p>' % W))
        section = copy.deepcopy(body.find('w:sectPr', NS))
        section.find('w:pgMar', NS).set('{%s}right' % W, '700')
        props = ET.SubElement(body[0], '{%s}pPr' % W)
        props.append(section)
        rows = self.statuses(dict(PARTS, **{'word/document.xml': ET.tostring(root)}))
        self.assertEqual(rows['one_inch_margins']['status'], 'FAIL')
        self.assertEqual(rows['double_spacing']['status'], 'FAIL')

    def test_metrics_exclude_separator_notes_and_detect_all_six_losses(self):
        parts = dict(PARTS)
        parts['word/_rels/document.xml.rels'] = parts['word/_rels/document.xml.rels'].replace('</Relationships>', '<Relationship Id="f" Type="%s/footnotes" Target="footnotes.xml"/></Relationships>' % R)
        parts['word/footnotes.xml'] = '<w:footnotes xmlns:w="%s"><w:footnote w:id="-1" w:type="separator"><w:p><w:r><w:t>IGNORE</w:t></w:r></w:p></w:footnote><w:footnote w:id="1"><w:p><w:r><w:t>Note</w:t></w:r></w:p></w:footnote></w:footnotes>' % W
        write(self.path, parts)
        result = metrics(self.path)
        self.assertEqual(result['footnotes'], 1)
        self.assertEqual(result['characters'], len('Title alphaNote'))
        before = dict(paragraphs=5, characters=50, tables=1, images=1, footnotes=1,
                      section_margins=[{'left': '1440'}, {'left': '720'}])
        after = dict(paragraphs=4, characters=49, tables=0, images=0, footnotes=0,
                     section_margins=[{'left': None}])
        rows = differences(before, after)
        self.assertEqual(sum(r['status'] == 'FAIL' for r in rows), 6)
        self.assertEqual(rows[-1]['lost_sections'], 1)
        self.assertEqual(rows[-1]['changed_sections'], [1, 2])
        # Equal counts do not imply equal content: the separate text SHA changes.
        original_hash = result['text_sha256']
        parts['word/document.xml'] = DOCUMENT.replace('alpha', 'omega')
        write(self.path, parts)
        self.assertEqual(metrics(self.path)['characters'], result['characters'])
        self.assertNotEqual(metrics(self.path)['text_sha256'], original_hash)

    def test_pdf_compares_page_count_and_each_pages_text(self):
        def run(command, **kwargs):
            if command[0] == 'soffice':
                dest = Path(command[command.index('--outdir')+1])
                (dest / (Path(command[-1]).stem + '.pdf')).write_bytes(b'PDF placeholder')
                return subprocess.CompletedProcess(command, 0)
            original = 'original' in str(command)
            text = b'First page  \n\fSecond page\f' if original else b'First page\n\fChanged page\fThird page\f'
            return subprocess.CompletedProcess(command, 0, stdout=text)

        with patch('roundtrip.subprocess.run', side_effect=run):
            result = pdf_compare(self.path, self.path, Path(self.temporary.name) / 'pdf', 'soffice', 'pdftotext')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual((result['original_pages'], result['exported_pages']), (2, 3))
        self.assertEqual([p['page'] for p in result['changed_pages']], [2, 3])


if __name__ == '__main__':
    unittest.main()
