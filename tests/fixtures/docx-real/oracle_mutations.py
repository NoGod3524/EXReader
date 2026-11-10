#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Each of the 18 metrics must reject a deliberate mutation, including equal counts."""
import tempfile
from pathlib import Path
import run_matrix as rt


def main():
    source = rt.generate.package(27)
    mutations = {
        'paragraphs': ('word/document.xml', b'<w:p w:rsidR="00112233">', b'<w:p/><w:p w:rsidR="00112233">'),
        'characters': ('word/document.xml', b'Draft estimate', b'Draft estimates'),
        'tables': ('word/document.xml', b'<w:tbl>', b'<w:tbl><w:tr><w:tc><w:tbl><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl><w:p/></w:tc></w:tr>'),
        'images': ('word/document.xml', b'<a:blip r:embed="image"/>', b'<a:blip r:embed="image"/><a:blip r:embed="image"/>'),
        'footnotes': ('word/footnotes.xml', b'</w:footnotes>', b'<w:footnote w:id="2"><w:p/></w:footnote></w:footnotes>'),
        'section_margins': ('word/document.xml', b'w:top="1440"', b'w:top="1441"'),
        'text_sha256': ('word/document.xml', b'42 units.', b'43 units.'),
        'image_sha256': ('word/media/original.png', source['word/media/original.png'], source['word/media/original.png'] + b'original negative control'),
        'opc_parts': ('docProps/core.xml', b'generator', b'generatos'),
        'relationships': ('word/_rels/document.xml.rels', b'Id="image"', b'Id="imagf"'),
        'tables_xml': ('word/document.xml', b'Workstream', b'Workstrean'),
        'fields_xml': ('word/header1.xml', b' PAGE ', b' DATE '),
        'numbering_styles_theme': ('word/numbering.xml', b'<w:startOverride w:val="1"/>', b'<w:startOverride w:val="2"/>'),
        'sections_xml': ('word/document.xml', b'w:gutter="0"', b'w:gutter="1"'),
        'notes_xml': ('word/footnotes.xml', b'values', b'valves'),
        'drawings_xml': ('word/document.xml', b'cx="914400"', b'cx="914401"'),
        'annotations_xml': ('word/document.xml', b'w:name="ScopeBoundary"', b'w:name="ScopeBoundarz"'),
        'main_xml': ('word/document.xml', b'w:rsidR="00112233"', b'w:rsidR="00112234"'),
    }
    assert set(mutations) == set(rt.METRICS)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'mutation.docx'
        path.write_bytes(rt.generate.pack(source))
        before = rt.measure(path)
        for metric, (part, old, new) in mutations.items():
            parts = dict(source)
            assert old in parts[part], metric
            parts[part] = parts[part].replace(old, new, 1)
            path.write_bytes(rt.generate.pack(parts))
            after = rt.measure(path)
            assert before[metric] != after[metric], f'{metric} failed to reject deliberate drift'
    print('18/18 metrics reject mutation; equal-count text/style/geometry/anchor changes detected')


if __name__ == '__main__':
    main()
