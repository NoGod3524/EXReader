#!/usr/bin/env python3
"""Generate 30 deterministic real-world structural DOCX fixtures (< 60 KB each)."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZipInfo, ZIP_STORED
import zlib

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
PIC = 'http://schemas.openxmlformats.org/drawingml/2006/picture'
WPG = 'http://schemas.microsoft.com/office/word/2010/wordprocessingGroup'
WPS = 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape'
VML = 'urn:schemas-microsoft-com:vml'

# 30 fixtures across 8 categories (>= 3 per category), each with a 1-line description.
FIXTURE_SPECS = [
    # Category 1: 表格 (Tables) — 4 fixtures
    ('01-table-merged-grid-vmerge', 'tables',
     '4x3 table with horizontal w:gridSpan=2 and vertical w:vMerge restart/continue merged cells.'),
    ('02-table-merged-hmerge-vmerge', 'tables',
     '4x3 table combining legacy horizontal w:hMerge restart/continue with vertical w:vMerge across rows.'),
    ('03-table-nested-subtable', 'tables',
     'Outer 2x2 table containing a nested 2x2 w:tbl inside cell (0,1) alongside cell paragraphs.'),
    ('04-table-repeating-header-multipar-list', 'tables',
     'Multi-row table with w:tblHeader repeating header row and cells containing multiple paragraphs and lists.'),
    # Category 2: 域 (Fields) — 4 fixtures
    ('05-field-page-numpages', 'fields',
     'Simple (w:fldSimple) and complex (w:fldChar/w:instrText) PAGE and NUMPAGES fields in header and body.'),
    ('06-field-date-formatted', 'fields',
     'Complex DATE \\@ "yyyy-MM-dd" and CREATEDATE \\@ "HH:mm" fields with cached result runs.'),
    ('07-field-ref-crossref', 'fields',
     'Complex REF and PAGEREF cross-reference fields (\\h switch) targeting body bookmark anchors.'),
    ('08-field-toc-complex', 'fields',
     'Multi-entry TOC \\o "1-3" \\h \\z \\u complex field with begin/separate/end fldChar and internal links.'),
    # Category 3: 编号 (Numbering) — 4 fixtures
    ('09-numbering-multilevel-nested', 'numbering',
     '3-level nested numbering (w:ilvl 0/1/2 with decimal, lowerLetter, lowerRoman) and bullet sub-items.'),
    ('10-numbering-restart-override', 'numbering',
     'Mid-list numbering restart using w:lvlRestart val=1 and w:lvlOverride with w:startOverride val=1.'),
    ('11-numbering-style-bound', 'numbering',
     'Style-bound numbering linking paragraph style NumberedHeading via styles.xml w:numPr and w:numStyleLink.'),
    ('12-numbering-chinese-counting', 'numbering',
     'Chinese numbering levels using chineseCounting, chineseLegalSimplified, and decimalEnclosedCircle.'),
    # Category 4: 样式 (Styles) — 4 fixtures
    ('13-style-inheritance-chain', 'styles',
     '3-level paragraph and character style inheritance chain (Normal -> Heading1 -> SubHeading -> CalloutLeaf).'),
    ('14-style-direct-override-unbold', 'styles',
     'Direct run w:b val=0 / w:i val=0 overriding bold/italic style plus w:spacing before/after inheriting line=480.'),
    ('15-style-direct-indent-override', 'styles',
     'Direct paragraph w:ind firstLine=480 overriding style left=720 while inheriting line=480 from Normal.'),
    ('16-style-theme-fonts', 'styles',
     'Theme font attributes (w:asciiTheme/w:hAnsiTheme/w:eastAsiaTheme) paired with word/theme/theme1.xml.'),
    # Category 5: 节 (Sections) — 4 fixtures
    ('17-section-multi-margins', 'sections',
     '3-section document with distinct w:pgMar page margins per section (1440, 1800/1080, 720/720 twips).'),
    ('18-section-portrait-landscape-mix', 'sections',
     '3-section document alternating Portrait -> Landscape (w:pgSz w=15840 h=12240 orient=landscape) -> Portrait.'),
    ('19-section-columns-1-2-3', 'sections',
     '3-section document switching between 1-column, 2-column (w:cols num=2), and unequal 3-column layouts.'),
    ('20-section-headers-first-even', 'sections',
     'Multi-section document with w:titlePg and distinct default, first, and even header and footer parts.'),
    # Category 6: 脚注 (Footnotes) — 3 fixtures
    ('21-footnote-restart-each-page', 'footnotes',
     'Footnotes configured with per-page numbering restart (w:footnotePr/w:numRestart val=eachPage).'),
    ('22-footnote-containing-table', 'footnotes',
     'Footnote in word/footnotes.xml containing an embedded 2x2 w:tbl alongside footnote text paragraphs.'),
    ('23-footnote-endnote-mixed-formatted', 'footnotes',
     'Mixed footnotes (word/footnotes.xml) and endnotes (word/endnotes.xml) with multi-paragraph formatted notes.'),
    # Category 7: 图形 (Graphics) — 3 fixtures
    ('24-graphic-inline-drawing', 'graphics',
     'Inline DrawingML image (wp:inline + pic:pic + a:blip referencing word/media/inline1.png).'),
    ('25-graphic-floating-anchor-wrap', 'graphics',
     'Floating anchored DrawingML image (wp:anchor + wp:wrapSquare wrapText=bothSides + positionH/positionV).'),
    ('26-graphic-group-shapes', 'graphics',
     'Grouped shapes using DrawingML wpg:wgp (multiple wps:wsp shapes + pic:pic) and VML v:group fallback.'),
    # Category 8: 其他 (Other) — 4 fixtures
    ('27-other-textbox-txbxcontent', 'other',
     'DrawingML shape with embedded textbox (wps:txbx/w:txbxContent) containing styled paragraphs and a list.'),
    ('28-other-comment-anchors', 'other',
     'Comment range anchors (w:commentRangeStart, w:commentRangeEnd, w:commentReference) with word/comments.xml.'),
    ('29-other-bookmarks-and-vanish', 'other',
     'Intra-paragraph and cross-paragraph bookmarks (w:bookmarkStart/End) plus hidden text runs (w:vanish).'),
    ('30-other-header-table-chinese-fields', 'other',
     'Header (word/header1.xml) with 2x2 w:tbl + PAGE field, body Chinese DATE/TOC fields, and ideograph numbering.'),
]

RPR_DEFAULT = (
    '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
    'w:eastAsia="SimSun" w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
)


def make_png(width=8, height=8, seed=1):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend(((32 + seed * 19 + x * 17) & 0xff, (80 + y * 23) & 0xff, (140 + (x ^ y) * 13) & 0xff))
        rows.append(bytes(row))
    raw = b''.join(rows)
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        # One explicit stored DEFLATE block, independent of zlib/zlib-ng compression.
        + chunk(b'IDAT', b'\x78\x01\x01' + struct.pack('<HH', len(raw), 0xffff ^ len(raw))
                + raw + struct.pack('>I', zlib.adler32(raw)))
        + chunk(b'IEND', b'')
    )


def p_xml(text, ppr_inner='<w:pStyle w:val="Normal"/><w:spacing w:line="480" w:lineRule="auto"/>',
          rpr=RPR_DEFAULT, extra_runs=''):
    return f'<w:p><w:pPr>{ppr_inner}</w:pPr><w:r>{rpr}<w:t>{escape(text)}</w:t></w:r>{extra_runs}</w:p>'


def complex_field_runs(instr, result_text, rpr=RPR_DEFAULT):
    return (
        f'<w:r>{rpr}<w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r>{rpr}<w:instrText xml:space="preserve">{escape(instr)}</w:instrText></w:r>'
        f'<w:r>{rpr}<w:fldChar w:fldCharType="separate"/></w:r>'
        f'<w:r>{rpr}<w:t>{escape(result_text)}</w:t></w:r>'
        f'<w:r>{rpr}<w:fldChar w:fldCharType="end"/></w:r>'
    )


def sect_xml(w=12240, h=15840, orient=None, margins=(1440, 1440, 1440, 1440),
             headers=(('default', 'rIdHeader1'),), footers=(), cols_xml='', extra_xml=''):
    refs = ''.join(f'<w:headerReference w:type="{t}" r:id="{rid}"/>' for t, rid in headers)
    refs += ''.join(f'<w:footerReference w:type="{t}" r:id="{rid}"/>' for t, rid in footers)
    orient_attr = f' w:orient="{orient}"' if orient else ''
    top, right, bottom, left = margins
    return (
        f'<w:sectPr>{refs}{extra_xml}'
        f'<w:pgSz w:w="{w}" w:h="{h}"{orient_attr}/>'
        f'<w:pgMar w:top="{top}" w:right="{right}" w:bottom="{bottom}" w:left="{left}" '
        f'w:header="720" w:footer="720" w:gutter="0"/>'
        f'{cols_xml}</w:sectPr>'
    )


def default_header_xml(title='Synthetic Header'):
    return (
        f'<w:hdr xmlns:w="{W}" xmlns:r="{R}">'
        + p_xml(f'{title} — Page ', extra_runs=f'<w:fldSimple w:instr=" PAGE "><w:r>{RPR_DEFAULT}<w:t>1</w:t></w:r></w:fldSimple>')
        + '</w:hdr>'
    )


def default_footer_xml(title='Synthetic Footer'):
    return (
        f'<w:ftr xmlns:w="{W}" xmlns:r="{R}">'
        + p_xml(f'{title} — Total ', extra_runs=complex_field_runs(' NUMPAGES ', '1'))
        + '</w:ftr>'
    )


def default_styles_xml(extra_styles=''):
    return (
        f'<w:styles xmlns:w="{W}">'
        f'<w:docDefaults>'
        f'<w:rPrDefault>{RPR_DEFAULT}</w:rPrDefault>'
        f'<w:pPrDefault><w:pPr><w:spacing w:line="480" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
        f'</w:docDefaults>'
        f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        f'<w:name w:val="Normal"/>'
        f'<w:pPr><w:spacing w:line="480" w:lineRule="auto"/></w:pPr>'
        f'<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
        f'w:eastAsia="SimSun" w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        f'</w:style>'
        f'<w:style w:type="paragraph" w:styleId="Heading1">'
        f'<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
        f'<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120" w:line="480" w:lineRule="auto"/>'
        f'<w:outlineLvl w:val="0"/></w:pPr>'
        f'<w:rPr><w:b/><w:i/></w:rPr>'
        f'</w:style>'
        f'{extra_styles}</w:styles>'
    )


def default_numbering_xml():
    return (
        f'<w:numbering xmlns:w="{W}">'
        '<w:abstractNum w:abstractNumId="0">'
        '<w:multiLevelType w:val="hybridMultilevel"/>'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/></w:lvl>'
        '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%2)"/><w:lvlJc w:val="left"/></w:lvl>'
        '<w:lvl w:ilvl="2"><w:start w:val="1"/><w:numFmt w:val="lowerRoman"/><w:lvlText w:val="%3."/><w:lvlJc w:val="left"/></w:lvl>'
        '</w:abstractNum>'
        '<w:abstractNum w:abstractNumId="1">'
        '<w:multiLevelType w:val="singleLevel"/>'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/></w:lvl>'
        '</w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
        '</w:numbering>'
    )


def build_fixture(spec_id, category, description):
    parts = {}
    rels = [
        ('rIdStyles', 'styles', 'styles.xml'),
        ('rIdHeader1', 'header', 'header1.xml'),
    ]
    overrides = [
        ('/word/document.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'),
        ('/word/styles.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'),
        ('/word/header1.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml'),
    ]
    parts['word/header1.xml'] = default_header_xml(spec_id)
    extra_styles = ''
    sect = sect_xml()

    lead = p_xml(f'Fixture {spec_id} ({category}): {description}')
    target_p = p_xml(
        f'Editable body paragraph for {spec_id}: original synthetic text alpha 中文 beta.',
        ppr_inner='<w:pStyle w:val="Normal"/><w:ind w:left="720" w:right="120" w:firstLine="360"/>'
                  '<w:spacing w:before="60" w:after="120" w:line="480" w:lineRule="auto"/>',
    )
    tail = p_xml(f'Trailing verification paragraph for {spec_id}: gamma delta epsilon.')
    middle = ''

    if spec_id == '01-table-merged-grid-vmerge':
        middle = (
            '<w:tbl>'
            '<w:tblPr><w:tblW w:w="9000" w:type="dxa"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/></w:tblGrid>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="6000" w:type="dxa"/><w:gridSpan w:val="2"/></w:tcPr>' + p_xml('Span 2 Header AB') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Header C') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/><w:vMerge w:val="restart"/></w:tcPr>' + p_xml('Vertical Merge Root') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Row 2 Col 2') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Row 2 Col 3') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/><w:vMerge/></w:tcPr>' + p_xml('') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Row 3 Col 2') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Row 3 Col 3') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Row 4 Col 1') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Row 4 Col 2') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Row 4 Col 3') + '</w:tc>'
            '</w:tr>'
            '</w:tbl>'
        )
    elif spec_id == '02-table-merged-hmerge-vmerge':
        middle = (
            '<w:tbl>'
            '<w:tblPr><w:tblW w:w="9000" w:type="dxa"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/></w:tblGrid>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="6000" w:type="dxa"/><w:hMerge w:val="restart"/><w:vMerge w:val="restart"/></w:tcPr>'
            + p_xml('Combined HMerge+VMerge Top') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/><w:hMerge/></w:tcPr>' + p_xml('') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Side R1C3') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="6000" w:type="dxa"/><w:gridSpan w:val="2"/><w:vMerge/></w:tcPr>' + p_xml('') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Side R2C3') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Bottom R3C1') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Bottom R3C2') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>' + p_xml('Bottom R3C3') + '</w:tc>'
            '</w:tr>'
            '</w:tbl>'
        )
    elif spec_id == '03-table-nested-subtable':
        nested = (
            '<w:tbl>'
            '<w:tblPr><w:tblW w:w="4000" w:type="dxa"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>' + p_xml('Inner 1,1') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>' + p_xml('Inner 1,2') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>' + p_xml('Inner 2,1') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>' + p_xml('Inner 2,2') + '</w:tc>'
            '</w:tr>'
            '</w:tbl>'
        )
        middle = (
            '<w:tbl>'
            '<w:tblPr><w:tblW w:w="9000" w:type="dxa"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Outer 1,1') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Outer 1,2 Lead') + nested + p_xml('Outer 1,2 Trail') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Outer 2,1') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Outer 2,2') + '</w:tc>'
            '</w:tr>'
            '</w:tbl>'
        )
    elif spec_id == '04-table-repeating-header-multipar-list':
        rels.append(('rIdNum', 'numbering', 'numbering.xml'))
        overrides.append(('/word/numbering.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'))
        parts['word/numbering.xml'] = default_numbering_xml()
        cell_list = (
            p_xml('Cell intro paragraph with style inheritance.', ppr_inner='<w:pStyle w:val="Normal"/>')
            + p_xml('Cell list item one', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('Cell list item two', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('Cell bullet item', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>')
        )
        middle = (
            '<w:tbl>'
            '<w:tblPr><w:tblW w:w="9000" w:type="dxa"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>'
            '<w:tr><w:trPr><w:tblHeader/></w:trPr>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Repeating Column A', ppr_inner='<w:pStyle w:val="Normal"/>') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Repeating Column B', ppr_inner='<w:pStyle w:val="Normal"/>') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + cell_list + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Simple cell row 2', ppr_inner='<w:pStyle w:val="Normal"/>') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Simple cell row 3 A', ppr_inner='<w:pStyle w:val="Normal"/>') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('Simple cell row 3 B', ppr_inner='<w:pStyle w:val="Normal"/>') + '</w:tc>'
            '</w:tr>'
            '</w:tbl>'
        )
    elif spec_id == '05-field-page-numpages':
        rels.append(('rIdFooter1', 'footer', 'footer1.xml'))
        overrides.append(('/word/footer1.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml'))
        parts['word/footer1.xml'] = default_footer_xml(spec_id)
        sect = sect_xml(headers=(('default', 'rIdHeader1'),), footers=(('default', 'rIdFooter1'),))
        middle = (
            p_xml('Body page indicator: ', extra_runs=(
                f'<w:fldSimple w:instr=" PAGE \\* Arabic "><w:r>{RPR_DEFAULT}<w:t>1</w:t></w:r></w:fldSimple>'
                f'<w:r>{RPR_DEFAULT}<w:t> of </w:t></w:r>'
                + complex_field_runs(' NUMPAGES \\* Arabic ', '3')
            ))
        )
    elif spec_id == '06-field-date-formatted':
        middle = (
            p_xml('Document ISO Date: ', extra_runs=complex_field_runs(' DATE \\@ "yyyy-MM-dd" ', '2026-11-10'))
            + p_xml('Creation Timestamp: ', extra_runs=complex_field_runs(' CREATEDATE \\@ "HH:mm" ', '09:30'))
        )
    elif spec_id == '07-field-ref-crossref':
        middle = (
            f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            f'<w:bookmarkStart w:id="10" w:name="SecTarget"/>'
            f'<w:r>{RPR_DEFAULT}<w:t>Section Anchor Title</w:t></w:r>'
            f'<w:bookmarkEnd w:id="10"/></w:p>'
            + p_xml('See section ', extra_runs=(
                complex_field_runs(' REF SecTarget \\h ', 'Section Anchor Title')
                + f'<w:r>{RPR_DEFAULT}<w:t> on page </w:t></w:r>'
                + complex_field_runs(' PAGEREF SecTarget \\h ', '1')
            ))
        )
    elif spec_id == '08-field-toc-complex':
        middle = (
            '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
            f'<w:r>{RPR_DEFAULT}<w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r>{RPR_DEFAULT}<w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
            f'<w:r>{RPR_DEFAULT}<w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:hyperlink w:anchor="_Toc101" w:history="1">'
            f'<w:r>{RPR_DEFAULT}<w:t>1. First Synthetic Heading\t1</w:t></w:r>'
            f'</w:hyperlink>'
            '</w:p>'
            '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
            f'<w:hyperlink w:anchor="_Toc102" w:history="1">'
            f'<w:r>{RPR_DEFAULT}<w:t>1.1 Nested Synthetic Subheading\t1</w:t></w:r>'
            f'</w:hyperlink>'
            f'<w:r>{RPR_DEFAULT}<w:fldChar w:fldCharType="end"/></w:r>'
            '</w:p>'
            f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:bookmarkStart w:id="1" w:name="_Toc101"/>'
            f'<w:r>{RPR_DEFAULT}<w:t>1. First Synthetic Heading</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p>'
            f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:bookmarkStart w:id="2" w:name="_Toc102"/>'
            f'<w:r>{RPR_DEFAULT}<w:t>1.1 Nested Synthetic Subheading</w:t></w:r><w:bookmarkEnd w:id="2"/></w:p>'
        )
    elif spec_id == '09-numbering-multilevel-nested':
        rels.append(('rIdNum', 'numbering', 'numbering.xml'))
        overrides.append(('/word/numbering.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'))
        parts['word/numbering.xml'] = default_numbering_xml()
        middle = (
            p_xml('Top level item 1', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('Second level item 1a', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('Third level item 1a-i', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="2"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('Top level item 2', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('Bullet note item', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>')
        )
    elif spec_id == '10-numbering-restart-override':
        rels.append(('rIdNum', 'numbering', 'numbering.xml'))
        overrides.append(('/word/numbering.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'))
        parts['word/numbering.xml'] = (
            f'<w:numbering xmlns:w="{W}">'
            '<w:abstractNum w:abstractNumId="0">'
            '<w:multiLevelType w:val="hybridMultilevel"/>'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlRestart w:val="1"/><w:lvlText w:val="%1."/></w:lvl>'
            '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlRestart w:val="1"/><w:lvlText w:val="%1.%2."/></w:lvl>'
            '</w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            '<w:num w:numId="2"><w:abstractNumId w:val="0"/>'
            '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>'
            '</w:num>'
            '</w:numbering>'
        )
        middle = (
            p_xml('First list item one', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('First list subitem 1.a', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('First list item two', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('First list subitem 2.a (restarted)', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('Restarted list item one via lvlOverride', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>')
        )
    elif spec_id == '11-numbering-style-bound':
        rels.append(('rIdNum', 'numbering', 'numbering.xml'))
        overrides.append(('/word/numbering.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'))
        extra_styles = (
            '<w:style w:type="numbering" w:styleId="OutlineNumStyle">'
            '<w:name w:val="OutlineNumStyle"/>'
            '<w:pPr><w:numPr><w:numId w:val="2"/></w:numPr></w:pPr>'
            '</w:style>'
            '<w:style w:type="paragraph" w:styleId="NumberedHeading">'
            '<w:name w:val="NumberedHeading"/><w:basedOn w:val="Heading1"/>'
            '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
            '</w:style>'
        )
        parts['word/numbering.xml'] = (
            f'<w:numbering xmlns:w="{W}">'
            '<w:abstractNum w:abstractNumId="10">'
            '<w:numStyleLink w:val="OutlineNumStyle"/>'
            '</w:abstractNum>'
            '<w:abstractNum w:abstractNumId="11">'
            '<w:styleLink w:val="OutlineNumStyle"/>'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="upperRoman"/><w:pStyle w:val="NumberedHeading"/><w:lvlText w:val="Article %1."/></w:lvl>'
            '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="Section %1.%2"/></w:lvl>'
            '</w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="10"/></w:num>'
            '<w:num w:numId="2"><w:abstractNumId w:val="11"/></w:num>'
            '</w:numbering>'
        )
        middle = (
            p_xml('Style-bound Roman heading one', ppr_inner='<w:pStyle w:val="NumberedHeading"/>')
            + p_xml('Style-bound Roman heading two', ppr_inner='<w:pStyle w:val="NumberedHeading"/>')
            + p_xml('Explicit sub-level under style-linked numbering', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr>')
        )
    elif spec_id == '12-numbering-chinese-counting':
        rels.append(('rIdNum', 'numbering', 'numbering.xml'))
        overrides.append(('/word/numbering.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'))
        parts['word/numbering.xml'] = (
            f'<w:numbering xmlns:w="{W}">'
            '<w:abstractNum w:abstractNumId="0">'
            '<w:multiLevelType w:val="multilevel"/>'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="chineseCounting"/><w:lvlText w:val="%1、"/></w:lvl>'
            '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="chineseLegalSimplified"/><w:lvlText w:val="（%2）"/></w:lvl>'
            '<w:lvl w:ilvl="2"><w:start w:val="1"/><w:numFmt w:val="decimalEnclosedCircle"/><w:lvlText w:val="%3"/></w:lvl>'
            '</w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            '</w:numbering>'
        )
        middle = (
            p_xml('总则与适用范围', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('术语定义条款', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('细则第一目', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="2"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('附则与实施日期', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
        )
    elif spec_id == '13-style-inheritance-chain':
        extra_styles = (
            '<w:style w:type="paragraph" w:styleId="SubHeading">'
            '<w:name w:val="SubHeading"/><w:basedOn w:val="Heading1"/>'
            '<w:pPr><w:ind w:left="360"/></w:pPr>'
            '<w:rPr><w:color w:val="1F4E79"/></w:rPr>'
            '</w:style>'
            '<w:style w:type="paragraph" w:styleId="CalloutLeaf">'
            '<w:name w:val="CalloutLeaf"/><w:basedOn w:val="SubHeading"/>'
            '<w:pPr><w:ind w:left="720" w:firstLine="240"/></w:pPr>'
            '<w:rPr><w:u w:val="single"/></w:rPr>'
            '</w:style>'
            '<w:style w:type="character" w:styleId="BaseChar">'
            '<w:name w:val="BaseChar"/><w:rPr><w:b/></w:rPr>'
            '</w:style>'
            '<w:style w:type="character" w:styleId="DerivedChar">'
            '<w:name w:val="DerivedChar"/><w:basedOn w:val="BaseChar"/><w:rPr><w:i/></w:rPr>'
            '</w:style>'
        )
        target_p = p_xml(
            f'Editable body paragraph for {spec_id}: SubHeading inheriting left=360 and line=480 from chain.',
            ppr_inner='<w:pStyle w:val="SubHeading"/><w:ind w:firstLine="240"/>',
        )
        middle = (
            p_xml('Level 1 Heading1 style paragraph', ppr_inner='<w:pStyle w:val="Heading1"/>')
            + p_xml('Level 2 SubHeading style paragraph', ppr_inner='<w:pStyle w:val="SubHeading"/>')
            + p_xml('Level 3 CalloutLeaf style paragraph', ppr_inner='<w:pStyle w:val="CalloutLeaf"/>',
                    extra_runs=f'<w:r><w:rPr><w:rStyle w:val="DerivedChar"/></w:rPr><w:t> [DerivedChar run]</w:t></w:r>')
        )
    elif spec_id == '14-style-direct-override-unbold':
        # Target paragraph has direct spacing before/after WITHOUT w:line (inherits line=480 from Heading1/Normal)
        # and run with w:b val="0" w:i val="0" overriding Heading1's bold+italic!
        unbold_rpr = (
            '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
            'w:eastAsia="SimSun" w:cs="Times New Roman"/><w:b w:val="0"/><w:i w:val="0"/>'
            '<w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        )
        target_p = p_xml(
            f'Editable body paragraph for {spec_id}: unbolded override on Heading1 with inherited line=480.',
            ppr_inner='<w:pStyle w:val="Heading1"/><w:spacing w:before="120" w:after="120"/>',
            rpr=unbold_rpr,
        )
        middle = p_xml(
            'Second paragraph with explicit unbold run inside bold style.',
            ppr_inner='<w:pStyle w:val="Heading1"/><w:spacing w:before="60" w:after="60"/>',
            rpr=unbold_rpr,
        )
    elif spec_id == '15-style-direct-indent-override':
        extra_styles = (
            '<w:style w:type="paragraph" w:styleId="IndentedQuote">'
            '<w:name w:val="IndentedQuote"/><w:basedOn w:val="Normal"/>'
            '<w:pPr><w:ind w:left="720" w:right="360"/><w:spacing w:line="480" w:lineRule="auto"/></w:pPr>'
            '</w:style>'
        )
        # Target paragraph has w:ind firstLine="480" (inheriting left=720, right=360 from IndentedQuote)
        # and w:spacing before="100" (inheriting line=480 from IndentedQuote)
        target_p = p_xml(
            f'Editable body paragraph for {spec_id}: direct firstLine=480 inheriting left=720 from IndentedQuote.',
            ppr_inner='<w:pStyle w:val="IndentedQuote"/><w:spacing w:before="100"/><w:ind w:firstLine="480"/>',
        )
        middle = p_xml(
            'Companion quote paragraph inheriting full IndentedQuote indent.',
            ppr_inner='<w:pStyle w:val="IndentedQuote"/>',
        )
    elif spec_id == '16-style-theme-fonts':
        rels.append(('rIdTheme1', 'theme', 'theme/theme1.xml'))
        overrides.append(('/word/theme/theme1.xml', 'application/vnd.openxmlformats-officedocument.theme+xml'))
        parts['word/theme/theme1.xml'] = (
            f'<a:theme xmlns:a="{A}" name="Synthetic Office Theme">'
            '<a:themeElements>'
            '<a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
            '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
            '<a:dk2><a:srgbClr val="1F497D"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
            '<a:accent1><a:srgbClr val="4F81BD"/></a:accent1><a:accent2><a:srgbClr val="C0504D"/></a:accent2>'
            '<a:accent3><a:srgbClr val="9BBB59"/></a:accent3><a:accent4><a:srgbClr val="8064A2"/></a:accent4>'
            '<a:accent5><a:srgbClr val="4BACC6"/></a:accent5><a:accent6><a:srgbClr val="F79646"/></a:accent6>'
            '<a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme>'
            '<a:fontScheme name="Office">'
            '<a:majorFont><a:latin typeface="Times New Roman"/><a:ea typeface="SimSun"/><a:cs typeface="Times New Roman"/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Times New Roman"/><a:ea typeface="SimSun"/><a:cs typeface="Times New Roman"/></a:minorFont>'
            '</a:fontScheme>'
            '<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
            '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
            '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
            '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>'
            '</a:themeElements></a:theme>'
        )
        theme_rpr = (
            '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
            'w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi" '
            'w:eastAsia="SimSun" w:eastAsiaTheme="minorEastAsia" '
            'w:cs="Times New Roman" w:cstheme="minorBidi"/>'
            '<w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        )
        middle = p_xml('Paragraph using explicit theme font bindings (minorHAnsi / minorEastAsia) 中英混排.', rpr=theme_rpr)
    elif spec_id == '17-section-multi-margins':
        s1 = sect_xml(margins=(1440, 1440, 1440, 1440), headers=(('default', 'rIdHeader1'),))
        s2 = sect_xml(margins=(1800, 1080, 1800, 1080), headers=(('default', 'rIdHeader1'),))
        sect = sect_xml(margins=(720, 720, 720, 720), headers=(('default', 'rIdHeader1'),))
        middle = (
            p_xml('Section 1 boundary paragraph (1440 twip margins).', ppr_inner=f'<w:pStyle w:val="Normal"/>{s1}')
            + p_xml('Section 2 body paragraph (1800/1080 twip margins).', ppr_inner=f'<w:pStyle w:val="Normal"/>{s2}')
            + p_xml('Section 3 body paragraph (720 twip narrow margins).')
        )
    elif spec_id == '18-section-portrait-landscape-mix':
        s1 = sect_xml(w=12240, h=15840, headers=(('default', 'rIdHeader1'),))
        s2 = sect_xml(w=15840, h=12240, orient='landscape', headers=(('default', 'rIdHeader1'),))
        sect = sect_xml(w=12240, h=15840, headers=(('default', 'rIdHeader1'),))
        middle = (
            p_xml('Section 1 Portrait page.', ppr_inner=f'<w:pStyle w:val="Normal"/>{s1}')
            + p_xml('Section 2 Landscape wide table page.', ppr_inner=f'<w:pStyle w:val="Normal"/>{s2}')
            + p_xml('Section 3 Portrait concluding page.')
        )
    elif spec_id == '19-section-columns-1-2-3':
        s1 = sect_xml(cols_xml='<w:cols w:num="1" w:space="720"/>')
        s2 = sect_xml(cols_xml='<w:cols w:num="2" w:space="720" w:sep="1"/>')
        sect = sect_xml(cols_xml=(
            '<w:cols w:num="3" w:equalWidth="0" w:sep="1">'
            '<w:col w:w="2800" w:space="360"/><w:col w:w="2800" w:space="360"/><w:col w:w="3040"/>'
            '</w:cols>'
        ))
        middle = (
            p_xml('Section 1 single column layout.', ppr_inner=f'<w:pStyle w:val="Normal"/>{s1}')
            + p_xml('Section 2 two-column balanced layout.', ppr_inner=f'<w:pStyle w:val="Normal"/>{s2}')
            + p_xml('Section 3 three-column custom-width layout.')
        )
    elif spec_id == '20-section-headers-first-even':
        for idx, kind in ((2, 'First Page Header'), (3, 'Even Page Header')):
            rels.append((f'rIdHeader{idx}', 'header', f'header{idx}.xml'))
            overrides.append((f'/word/header{idx}.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml'))
            parts[f'word/header{idx}.xml'] = default_header_xml(f'{spec_id} {kind}')
        for idx, kind in ((1, 'Default Footer'), (2, 'First Page Footer'), (3, 'Even Page Footer')):
            rels.append((f'rIdFooter{idx}', 'footer', f'footer{idx}.xml'))
            overrides.append((f'/word/footer{idx}.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml'))
            parts[f'word/footer{idx}.xml'] = default_footer_xml(f'{spec_id} {kind}')
        hdrs = (('default', 'rIdHeader1'), ('first', 'rIdHeader2'), ('even', 'rIdHeader3'))
        ftrs = (('default', 'rIdFooter1'), ('first', 'rIdFooter2'), ('even', 'rIdFooter3'))
        s1 = sect_xml(headers=hdrs, footers=ftrs, extra_xml='<w:titlePg/>')
        sect = sect_xml(headers=hdrs, footers=ftrs, extra_xml='<w:titlePg/>')
        middle = (
            p_xml('Section 1 with titlePg and default/first/even headers+footers.', ppr_inner=f'<w:pStyle w:val="Normal"/>{s1}')
            + p_xml('Section 2 continuing multi-header configuration.')
        )
    elif spec_id == '21-footnote-restart-each-page':
        rels.append(('rIdFootnotes', 'footnotes', 'footnotes.xml'))
        overrides.append(('/word/footnotes.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml'))
        rels.append(('rIdSettings', 'settings', 'settings.xml'))
        overrides.append(('/word/settings.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml'))
        parts['word/settings.xml'] = (
            f'<w:settings xmlns:w="{W}">'
            '<w:footnotePr>'
            '<w:pos w:val="pageBottom"/>'
            '<w:numFmt w:val="decimal"/>'
            '<w:numRestart w:val="eachPage"/>'
            '<w:footnote w:id="-1"/><w:footnote w:id="0"/>'
            '</w:footnotePr>'
            '</w:settings>'
        )
        parts['word/footnotes.xml'] = (
            f'<w:footnotes xmlns:w="{W}">'
            '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
            '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
            '<w:footnote w:id="1">' + p_xml('First page-restarted footnote.') + '</w:footnote>'
            '<w:footnote w:id="2">' + p_xml('Second page-restarted footnote.') + '</w:footnote>'
            '</w:footnotes>'
        )
        sect = sect_xml(extra_xml='<w:footnotePr><w:numRestart w:val="eachPage"/></w:footnotePr>')
        middle = (
            p_xml('Paragraph citing first per-page footnote', extra_runs='<w:r><w:footnoteReference w:id="1"/></w:r>')
            + p_xml('Paragraph citing second per-page footnote', extra_runs='<w:r><w:footnoteReference w:id="2"/></w:r>')
        )
    elif spec_id == '22-footnote-containing-table':
        rels.append(('rIdFootnotes', 'footnotes', 'footnotes.xml'))
        overrides.append(('/word/footnotes.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml'))
        fn_table = (
            '<w:tbl>'
            '<w:tblPr><w:tblW w:w="5000" w:type="dxa"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="2500"/><w:gridCol w:w="2500"/></w:tblGrid>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="2500" w:type="dxa"/></w:tcPr>' + p_xml('Footnote Cell A1') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="2500" w:type="dxa"/></w:tcPr>' + p_xml('Footnote Cell B1') + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="2500" w:type="dxa"/></w:tcPr>' + p_xml('Footnote Cell A2') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="2500" w:type="dxa"/></w:tcPr>' + p_xml('Footnote Cell B2') + '</w:tc>'
            '</w:tr>'
            '</w:tbl>'
        )
        parts['word/footnotes.xml'] = (
            f'<w:footnotes xmlns:w="{W}">'
            '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:footnote>' if False else
            f'<w:footnotes xmlns:w="{W}">'
            '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
            '<w:footnote w:id="1">'
            + p_xml('Footnote lead text before embedded table:')
            + fn_table
            + p_xml('Footnote trailing explanation after table.')
            + '</w:footnote></w:footnotes>'
        )
        middle = p_xml('Body statement with tabular footnote reference', extra_runs='<w:r><w:footnoteReference w:id="1"/></w:r>')
    elif spec_id == '23-footnote-endnote-mixed-formatted':
        rels.append(('rIdFootnotes', 'footnotes', 'footnotes.xml'))
        overrides.append(('/word/footnotes.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml'))
        rels.append(('rIdEndnotes', 'endnotes', 'endnotes.xml'))
        overrides.append(('/word/endnotes.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml'))
        parts['word/footnotes.xml'] = (
            f'<w:footnotes xmlns:w="{W}">'
            '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
            '<w:footnote w:id="1">'
            + p_xml('Footnote paragraph 1 with bold emphasis.')
            + p_xml('Footnote paragraph 2 continuation.')
            + '</w:footnote></w:footnotes>'
        )
        parts['word/endnotes.xml'] = (
            f'<w:endnotes xmlns:w="{W}">'
            '<w:endnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:endnote>'
            '<w:endnote w:id="2">'
            + p_xml('Endnote archival citation alpha.')
            + p_xml('Endnote archival citation beta.')
            + '</w:endnote></w:endnotes>'
        )
        middle = (
            p_xml('Body paragraph with footnote callout', extra_runs='<w:r><w:footnoteReference w:id="1"/></w:r>')
            + p_xml('Body paragraph with endnote callout', extra_runs='<w:r><w:endnoteReference w:id="2"/></w:r>')
        )
    elif spec_id == '24-graphic-inline-drawing':
        rels.append(('rIdImg1', 'image', 'media/inline1.png'))
        parts['word/media/inline1.png'] = make_png(12, 8, seed=3)
        inline_drawing = (
            '<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            '<wp:extent cx="914400" cy="609600"/><wp:docPr id="1" name="Inline Diagram 1"/>'
            f'<a:graphic><a:graphicData uri="{PIC}"><pic:pic>'
            '<pic:nvPicPr><pic:cNvPr id="1" name="inline1.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="rIdImg1"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="609600"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
        )
        middle = p_xml('Paragraph containing inline DrawingML PNG figure: ', extra_runs=inline_drawing)
    elif spec_id == '25-graphic-floating-anchor-wrap':
        rels.append(('rIdImgAnchor', 'image', 'media/floating1.png'))
        parts['word/media/floating1.png'] = make_png(10, 10, seed=7)
        anchor_drawing = (
            '<w:r><w:drawing>'
            '<wp:anchor distT="0" distB="0" distL="114300" distR="114300" simplePos="0" '
            'relativeHeight="25165824" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
            '<wp:simplePos x="0" y="0"/>'
            '<wp:positionH relativeFrom="column"><wp:posOffset>457200</wp:posOffset></wp:positionH>'
            '<wp:positionV relativeFrom="paragraph"><wp:posOffset>127000</wp:posOffset></wp:positionV>'
            '<wp:extent cx="762000" cy="762000"/>'
            '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
            '<wp:wrapSquare wrapText="bothSides"/>'
            '<wp:docPr id="2" name="Floating Figure 2"/>'
            f'<a:graphic><a:graphicData uri="{PIC}"><pic:pic>'
            '<pic:nvPicPr><pic:cNvPr id="2" name="floating1.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="rIdImgAnchor"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="762000" cy="762000"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            '</pic:pic></a:graphicData></a:graphic>'
            '</wp:anchor></w:drawing></w:r>'
        )
        middle = p_xml('Paragraph with floating wp:anchor square-wrapped image: ', extra_runs=anchor_drawing)
    elif spec_id == '26-graphic-group-shapes':
        rels.append(('rIdImgGrp', 'image', 'media/group1.png'))
        parts['word/media/group1.png'] = make_png(8, 8, seed=11)
        group_drawing = (
            f'<w:r><w:drawing xmlns:wpg="{WPG}" xmlns:wps="{WPS}">'
            '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            '<wp:extent cx="1828800" cy="914400"/><wp:docPr id="30" name="Grouped Diagram"/>'
            f'<a:graphic><a:graphicData uri="{WPG}">'
            '<wpg:wgp>'
            '<wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1828800" cy="914400"/>'
            '<a:chOff x="0" y="0"/><a:chExt cx="1828800" cy="914400"/></a:xfrm></wpg:grpSpPr>'
            '<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="800000" cy="400000"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></wps:spPr><wps:style/><wps:bodyPr/></wps:wsp>'
            '<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="900000" y="0"/><a:ext cx="800000" cy="400000"/></a:xfrm>'
            '<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom></wps:spPr><wps:style/><wps:bodyPr/></wps:wsp>'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="31" name="group1.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="rIdImgGrp"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            '<pic:spPr><a:xfrm><a:off x="400000" y="450000"/><a:ext cx="457200" cy="457200"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            '</wpg:wgp>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing>'
            f'<w:pict xmlns:v="{VML}"><v:group id="vgrp1" style="width:120pt;height:60pt" coordsize="2400,1200">'
            '<v:rect id="vrect1" style="left:0;top:0;width:1000;height:800"/>'
            '<v:oval id="voval1" style="left:1200;top:0;width:1000;height:800"/>'
            '</v:group></w:pict></w:r>'
        )
        middle = p_xml('Paragraph containing wpg:wgp grouped shapes and VML v:group: ', extra_runs=group_drawing)
    elif spec_id == '27-other-textbox-txbxcontent':
        rels.append(('rIdNum', 'numbering', 'numbering.xml'))
        overrides.append(('/word/numbering.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'))
        parts['word/numbering.xml'] = default_numbering_xml()
        txbx = (
            f'<w:r><w:drawing xmlns:wps="{WPS}">'
            '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            '<wp:extent cx="2286000" cy="914400"/><wp:docPr id="40" name="Callout Textbox"/>'
            f'<a:graphic><a:graphicData uri="{WPS}">'
            '<wps:wsp><wps:cNvSpPr txBox="1"/>'
            '<wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="2286000" cy="914400"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></wps:spPr>'
            '<wps:txbx><w:txbxContent>'
            + p_xml('Textbox internal heading paragraph.')
            + p_xml('Textbox numbered item 1', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + '</w:txbxContent></wps:txbx><wps:bodyPr/></wps:wsp>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
        )
        middle = p_xml('Host paragraph embedding DrawingML textbox: ', extra_runs=txbx)
    elif spec_id == '28-other-comment-anchors':
        rels.append(('rIdComments', 'comments', 'comments.xml'))
        overrides.append(('/word/comments.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml'))
        parts['word/comments.xml'] = (
            f'<w:comments xmlns:w="{W}">'
            '<w:comment w:id="0" w:author="Synthetic Reviewer" w:date="2026-11-10T10:00:00Z" w:initials="SR">'
            + p_xml('First reviewer comment on terminology.')
            + '</w:comment>'
            '<w:comment w:id="1" w:author="Synthetic Auditor" w:date="2026-11-10T10:05:00Z" w:initials="SA">'
            + p_xml('Second reviewer comment spanning clauses.')
            + '</w:comment>'
            '</w:comments>'
        )
        middle = (
            '<w:p><w:pPr><w:pStyle w:val="Normal"/><w:spacing w:line="480" w:lineRule="auto"/></w:pPr>'
            f'<w:r>{RPR_DEFAULT}<w:t>Prefix before comment </w:t></w:r>'
            '<w:commentRangeStart w:id="0"/>'
            f'<w:r>{RPR_DEFAULT}<w:t>annotated phrase one</w:t></w:r>'
            '<w:commentRangeEnd w:id="0"/>'
            f'<w:r>{RPR_DEFAULT}<w:commentReference w:id="0"/></w:r>'
            f'<w:r>{RPR_DEFAULT}<w:t> and </w:t></w:r>'
            '<w:commentRangeStart w:id="1"/>'
            f'<w:r>{RPR_DEFAULT}<w:t>annotated phrase two</w:t></w:r>'
            '<w:commentRangeEnd w:id="1"/>'
            f'<w:r>{RPR_DEFAULT}<w:commentReference w:id="1"/></w:r>'
            '</w:p>'
        )
    elif spec_id == '29-other-bookmarks-and-vanish':
        vanish_rpr = (
            '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
            'w:eastAsia="SimSun" w:cs="Times New Roman"/><w:vanish/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        )
        middle = (
            '<w:p><w:pPr><w:pStyle w:val="Normal"/><w:spacing w:line="480" w:lineRule="auto"/></w:pPr>'
            '<w:bookmarkStart w:id="20" w:name="IntraBookmark"/>'
            f'<w:r>{RPR_DEFAULT}<w:t>Visible bookmarked span</w:t></w:r>'
            '<w:bookmarkEnd w:id="20"/>'
            f'<w:r>{vanish_rpr}<w:t> [hidden vanish token]</w:t></w:r>'
            '<w:bookmarkStart w:id="21" w:name="CrossParaBookmark"/>'
            f'<w:r>{RPR_DEFAULT}<w:t> start of cross-paragraph bookmark.</w:t></w:r>'
            '</w:p>'
            '<w:p><w:pPr><w:pStyle w:val="Normal"/><w:spacing w:line="480" w:lineRule="auto"/></w:pPr>'
            f'<w:r>{RPR_DEFAULT}<w:t>Concluding paragraph of cross-paragraph bookmark.</w:t></w:r>'
            '<w:bookmarkEnd w:id="21"/>'
            '</w:p>'
        )
    elif spec_id == '30-other-header-table-chinese-fields':
        rels.append(('rIdNum', 'numbering', 'numbering.xml'))
        overrides.append(('/word/numbering.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'))
        parts['word/numbering.xml'] = (
            f'<w:numbering xmlns:w="{W}">'
            '<w:abstractNum w:abstractNumId="0">'
            '<w:multiLevelType w:val="singleLevel"/>'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="ideographTraditional"/><w:lvlText w:val="%1、"/></w:lvl>'
            '</w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            '</w:numbering>'
        )
        parts['word/header1.xml'] = (
            f'<w:hdr xmlns:w="{W}" xmlns:r="{R}">'
            '<w:tbl>'
            '<w:tblPr><w:tblW w:w="9000" w:type="dxa"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('眉题表格左栏：技术规范') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
            + p_xml('页码：', extra_runs=f'<w:fldSimple w:instr=" PAGE "><w:r>{RPR_DEFAULT}<w:t>1</w:t></w:r></w:fldSimple>')
            + '</w:tc>'
            '</w:tr>'
            '<w:tr>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>' + p_xml('版本：2026-R1') + '</w:tc>'
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
            + p_xml('总页数：', extra_runs=complex_field_runs(' NUMPAGES ', '1'))
            + '</w:tc>'
            '</w:tr>'
            '</w:tbl>'
            '</w:hdr>'
        )
        middle = (
            p_xml('中文日期域：', extra_runs=complex_field_runs(' DATE \\@ "yyyy年M月d日" ', '2026年11月10日'))
            + p_xml('中文目录域：', extra_runs=complex_field_runs(' TOC \\o "1-3" ', '第一章 概述\t1'))
            + p_xml('天干编号条目甲', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
            + p_xml('天干编号条目乙', ppr_inner='<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
        )
    else:
        raise ValueError(f'Unknown fixture id: {spec_id}')

    body = lead + target_p + middle + tail + sect
    parts['word/document.xml'] = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}" xmlns:wp="{WP}" xmlns:pic="{PIC}">'
        f'<w:body>{body}</w:body></w:document>'
    )
    parts['word/styles.xml'] = default_styles_xml(extra_styles)
    parts['_rels/.rels'] = (
        f'<Relationships xmlns="{REL}">'
        f'<Relationship Id="rIdMain" Type="{R}/officeDocument" Target="word/document.xml"/>'
        f'</Relationships>'
    )
    parts['word/_rels/document.xml.rels'] = (
        f'<Relationships xmlns="{REL}">'
        + ''.join(f'<Relationship Id="{rid}" Type="{R}/{rtype}" Target="{target}"/>' for rid, rtype, target in rels)
        + '</Relationships>'
    )
    parts['[Content_Types].xml'] = (
        f'<Types xmlns="{CT}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        + ''.join(f'<Override PartName="{pname}" ContentType="{ctype}"/>' for pname, ctype in overrides)
        + '</Types>'
    )

    buf = io.BytesIO()
    with ZipFile(buf, 'w') as zf:
        for name, content in sorted(parts.items()):
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 0  # Match the committed DOS ZIP headers on every host.
            info.compress_type = ZIP_STORED  # Avoid implementation-dependent DEFLATE output.
            info.external_attr = 0o100644 << 16
            raw = content.encode('utf-8') if isinstance(content, str) else content
            zf.writestr(info, raw)
    return buf.getvalue()


def generate_all():
    if len(FIXTURE_SPECS) != 30:
        raise ValueError(f'Expected 30 fixtures, got {len(FIXTURE_SPECS)}')
    cat_counts = {}
    for _, cat, _ in FIXTURE_SPECS:
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    for cat, count in cat_counts.items():
        if count < 3:
            raise ValueError(f'Category {cat} has fewer than 3 fixtures: {count}')

    files = {}
    manifest_entries = []
    for spec_id, category, description in FIXTURE_SPECS:
        filename = f'{spec_id}.docx'
        data = build_fixture(spec_id, category, description)
        if len(data) >= 60_000:
            raise ValueError(f'{filename} exceeds 60 KB limit: {len(data)} bytes')
        files[filename] = data
        manifest_entries.append({
            'id': spec_id,
            'category': category,
            'path': filename,
            'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
            'description': description,
        })
    manifest = {
        'license': 'MIT',
        'origin': 'Original synthetic structural fixtures generated by make_fixtures.py; zero external or copyrighted material.',
        'total_fixtures': len(manifest_entries),
        'category_counts': cat_counts,
        'fixtures': manifest_entries,
    }
    files['manifest.json'] = (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--check', action='store_true', help='Verify committed fixtures match generator output.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    generated = generate_all()
    for name, data in generated.items():
        target = args.output / name
        if args.check:
            if not target.is_file() or target.read_bytes() != data:
                raise SystemExit(f'Mismatch or missing file: {target}')
        else:
            target.write_bytes(data)
    print(f'{"Verified" if args.check else "Generated"} {len(FIXTURE_SPECS)} DOCX fixtures in {args.output} '
          f'(max size {max(len(v) for k, v in generated.items() if k.endswith(".docx"))} bytes < 60000).')


if __name__ == '__main__':
    main()
