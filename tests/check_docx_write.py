#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Export through the CLI, then validate the OPC parts with an independent XML reader.

--independent additionally reports python-docx values (optional developer dependency).
"""
import argparse
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS = {'w': W}


def check(tool, work, independent=False):
    work.mkdir(parents=True, exist_ok=True)
    source, output = work / 'fidelity.html', work / 'fidelity.docx'
    source.write_text('''<html><head><title>DOCX fidelity verification</title></head><body>
<h1>DOCX fidelity verification</h1>
<p>Body paragraph one verifies Times New Roman twelve point type, double line spacing,
a half inch first line indent, six points after each paragraph, and left alignment.
The paper is US Letter with one inch margins on all four sides.</p>
<p>Body paragraph two preserves XML characters &amp; &lt; &gt; and Unicode café 中文.
The date below the title and the number at the upper right are Word fields.</p>
<h1>References</h1><p>EXReader DOCX export verification. References begin on a separate page.</p>
</body></html>''', encoding='utf-8')
    # The CLI protects existing output files; make repeated checks independent.
    if output.exists():
        output.unlink()
    subprocess.run([str(tool), '--input', str(source), '--to', 'docx',
                    '--output', str(output)], check=True, capture_output=True)
    with zipfile.ZipFile(output) as package:
        roots = {}
        for name in package.namelist():
            roots[name] = ET.fromstring(package.read(name))
            destination = work / 'unpacked' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            ET.indent(roots[name])
            ET.ElementTree(roots[name]).write(destination, encoding='utf-8', xml_declaration=True)
    document = roots['word/document.xml']
    body = document.find('w:body', NS)
    paragraphs = body.findall('w:p', NS)
    assert len(paragraphs) == 7
    for p in paragraphs:
        if p.find('w:r/w:br', NS) is not None:
            continue
        spacing = p.find('w:pPr/w:spacing', NS)
        assert spacing.attrib == {f'{{{W}}}{k}': v for k, v in
                                  dict(before='0', after='120', line='480', lineRule='auto').items()}
    for run in document.findall('.//w:r', NS) + roots['word/header1.xml'].findall('.//w:r', NS):
        properties = run.find('w:rPr', NS)
        fonts = properties.find('w:rFonts', NS)
        assert all(fonts.get(f'{{{W}}}{key}') == 'Times New Roman' for key in ('ascii', 'hAnsi', 'eastAsia'))
        assert properties.find('w:sz', NS).get(f'{{{W}}}val') == '24'
        assert properties.find('w:szCs', NS).get(f'{{{W}}}val') == '24'
    assert paragraphs[0].find('w:pPr/w:jc', NS).get(f'{{{W}}}val') == 'center'
    date = paragraphs[1].find('w:fldSimple', NS)
    assert date.get(f'{{{W}}}instr').strip() == 'DATE'
    for p in (paragraphs[2], paragraphs[3], paragraphs[6]):
        assert p.find('w:pPr/w:jc', NS).get(f'{{{W}}}val') == 'left'
        assert p.find('w:pPr/w:ind', NS).get(f'{{{W}}}firstLine') == '720'
    assert paragraphs[4].find('w:r/w:br', NS).get(f'{{{W}}}type') == 'page'
    assert ''.join(paragraphs[5].itertext()).strip() == 'References'
    section = body.find('w:sectPr', NS)
    assert len(section) == 3 and list(body)[-1] is section
    assert section.find('w:pgSz', NS).attrib == {f'{{{W}}}w': '12240', f'{{{W}}}h': '15840'}
    assert section.find('w:pgMar', NS).attrib == {f'{{{W}}}{k}': v for k, v in
        dict(top='1440', right='1440', bottom='1440', left='1440', header='720', footer='720', gutter='0').items()}
    header = roots['word/header1.xml']
    assert header.find('w:p/w:pPr/w:jc', NS).get(f'{{{W}}}val') == 'right'
    assert header.find('w:p/w:fldSimple', NS).get(f'{{{W}}}instr').strip() == 'PAGE'
    assert not document.findall('.//w:r/w:fldSimple', NS)
    relationship = list(roots['word/_rels/document.xml.rels'])[0]
    assert relationship.get('Type') == R + '/header'
    assert relationship.get('Target') == 'header1.xml'
    assert relationship.get('Id') == section.find('w:headerReference', NS).get(f'{{{R}}}id')
    styles_rel = list(roots['word/_rels/document.xml.rels'])[1]
    assert styles_rel.get('Type') == R + '/styles' and styles_rel.get('Target') == 'styles.xml'
    styles = roots['word/styles.xml']
    for path in ('w:docDefaults/w:rPrDefault/w:rPr', 'w:style/w:rPr'):
        properties = styles.find(path, NS)
        assert properties.find('w:rFonts', NS).get(f'{{{W}}}ascii') == 'Times New Roman'
        assert properties.find('w:sz', NS).get(f'{{{W}}}val') == '24'
    assert any(item.get('PartName') == '/word/styles.xml' for item in roots['[Content_Types].xml'])
    assert any(item.get('PartName') == '/word/header1.xml' and
               item.get('ContentType') == 'application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml'
               for item in roots['[Content_Types].xml'])
    assert 'café 中文' in ''.join(document.itertext())
    if independent:
        from docx import Document
        doc = Document(output)
        p, run, s = doc.paragraphs[2], doc.paragraphs[2].runs[0], doc.sections[0]
        rows = [
            ('font.name', 'Times New Roman', run.font.name),
            ('font.size (pt)', 12, run.font.size.pt),
            ('line_spacing (multiple)', 2.0, p.paragraph_format.line_spacing),
            ('line_spacing_rule', 'DOUBLE (2)', str(p.paragraph_format.line_spacing_rule)),
            ('first_line_indent (in)', 0.5, p.paragraph_format.first_line_indent.inches),
            ('space_after (pt)', 6, p.paragraph_format.space_after.pt),
            ('alignment', 'LEFT (0)', str(p.alignment)),
            ('page_width (in)', 8.5, s.page_width.inches),
            ('page_height (in)', 11, s.page_height.inches),
        ]
        rows.extend((f'{edge}_margin (in)', 1, getattr(s, edge + '_margin').inches)
                    for edge in ('top', 'right', 'bottom', 'left'))
        rows.extend((f'{edge}_distance (in)', 0.5, getattr(s, edge + '_distance').inches)
                    for edge in ('header', 'footer'))
        report = [dict(field=k, expected=e, actual=a, passed=e == a) for k, e, a in rows]
        (work / 'python-docx.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        assert all(row['passed'] for row in report), report
        print(json.dumps(report, indent=2))
    print('DOCX package, fields, formatting, escaping and reference pagination passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tool', type=Path)
    parser.add_argument('work', type=Path)
    parser.add_argument('--independent', action='store_true')
    args = parser.parse_args()
    check(args.tool.resolve(), args.work.resolve(), args.independent)
