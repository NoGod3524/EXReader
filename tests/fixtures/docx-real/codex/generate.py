#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Thirty original mixed Word packages. Stdlib only; byte reproducible, <60 KiB."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
PIC = 'http://schemas.openxmlformats.org/drawingml/2006/picture'
NS = dict(w=W, r=R, a=A, wp=WP, pic=PIC, v='urn:schemas-microsoft-com:vml',
          mc='http://schemas.openxmlformats.org/markup-compatibility/2006',
          wpg='http://schemas.microsoft.com/office/word/2010/wordprocessingGroup',
          wps='http://schemas.microsoft.com/office/word/2010/wordprocessingShape')
DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
MARKER = 'Draft estimate: 42 units.'
REPLACEMENT = 'Reviewed estimate: 57 units; 中文 & <checked>.'


def root(tag, content):
    return DECL + '<' + tag + ' ' + ' '.join('xmlns:' + k + '=' + quoteattr(v) for k, v in NS.items()) + '>' + content + '</' + tag + '>'


def run(text, props=''):
    return '<w:r>' + ('<w:rPr>' + props + '</w:rPr>' if props else '') + '<w:t xml:space="preserve">' + escape(text) + '</w:t></w:r>'


def p(text='', props='', extra='', before=''):
    return '<w:p w:rsidR="00112233">' + ('<w:pPr>' + props + '</w:pPr>' if props else '') + before + run(text) + extra + '</w:p>'


def field(code, result, simple=False):
    if simple:
        return '<w:fldSimple w:instr=' + quoteattr(code) + ' w:dirty="true">' + run(result) + '</w:fldSimple>'
    return ('<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
            '<w:r><w:instrText xml:space="preserve">' + escape(code) + '</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + run(result) +
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def cell(content, props=''):
    return '<w:tc><w:tcPr><w:tcW w:w="2880" w:type="dxa"/>' + props + '</w:tcPr>' + content + '</w:tc>'


def row(cells, props=''):
    return '<w:tr>' + ('<w:trPr>' + props + '</w:trPr>' if props else '') + ''.join(cells) + '</w:tr>'


def table(rows=None):
    if rows is None:
        rows = [row([cell(p('Workstream')), cell(p('Units'))], '<w:tblHeader/>'),
                row([cell(p('Original sample analysis')), cell(p('42'))]),
                row([cell(p('Original sample review')), cell(p('15'))])]
    return ('<w:tbl><w:tblPr><w:tblW w:w="5760" w:type="dxa"/>'
            '<w:tblBorders><w:top w:val="single" w:sz="4"/><w:bottom w:val="single" w:sz="4"/></w:tblBorders>'
            '</w:tblPr><w:tblGrid><w:gridCol w:w="2880"/><w:gridCol w:w="2880"/></w:tblGrid>' + ''.join(rows) + '</w:tbl>')


def sect(extra='', landscape=False, margin=1440):
    return ('<w:sectPr><w:headerReference w:type="default" r:id="header"/>'
            '<w:footerReference w:type="default" r:id="footer"/>' + (extra if '<w:footnotePr>' in extra else '') +
            ('<w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/>' if landscape else '<w:pgSz w:w="12240" w:h="15840"/>') +
            f'<w:pgMar w:top="{margin}" w:right="{margin}" w:bottom="{margin}" w:left="{margin}" w:header="720" w:footer="720" w:gutter="0"/>' + ('' if '<w:footnotePr>' in extra else extra) + '</w:sectPr>')


def picture(floating=False, graphic=None, drawing_id=1):
    graphic = graphic or ('<a:graphicData uri="' + PIC + '"><pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="Original color tile"/>'
        '<pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="image"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="609600"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData>')
    if floating:
        tag = 'wp:anchor'
        start = '<wp:anchor distT="91440" distB="91440" distL="91440" distR="91440" simplePos="0" relativeHeight="1" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1"><wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="column"><wp:posOffset>182880</wp:posOffset></wp:positionH><wp:positionV relativeFrom="paragraph"><wp:posOffset>91440</wp:posOffset></wp:positionV>'
    else:
        tag, start = 'wp:inline', '<wp:inline distT="0" distB="0" distL="0" distR="0">'
    return ('<w:r><w:drawing>' + start + '<wp:extent cx="914400" cy="609600"/>'
            '<wp:effectExtent l="0" t="0" r="0" b="0"/>' + ('<wp:wrapSquare wrapText="bothSides"/>' if floating else '') +
            f'<wp:docPr id="{drawing_id}" name="Original diagram" descr="Original three-bar estimate chart"/><wp:cNvGraphicFramePr/>'
            '<a:graphic>' + graphic + '</a:graphic></' + tag + '></w:drawing></w:r>')


def png():
    import struct
    import zlib
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    width, height, scanlines = 160, 96, bytearray()
    for y in range(height):
        scanlines.append(0)
        for x in range(width):
            color = (255, 255, 255)
            if x == 18 and 10 <= y <= 82 or y == 82 and 18 <= x <= 148:
                color = (100, 110, 120)
            for top, length, ink in ((14, 118, (35, 87, 137)), (38, 84, (58, 125, 68)), (62, 52, (229, 143, 101))):
                if top <= y < top+14 and 19 <= x < 19+length:
                    color = ink
            scanlines.extend(color)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b'')


def styles():
    return root('w:styles', '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:asciiTheme="minorHAnsi" w:eastAsiaTheme="minorEastAsia"/><w:sz w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="120"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="ProjectHeading"><w:name w:val="Project heading"/><w:basedOn w:val="Heading1"/><w:rPr><w:color w:val="235789"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="ActionList"><w:name w:val="Action list"/><w:basedOn w:val="Normal"/><w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr></w:style>')


def numbering():
    levels = ''.join(f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="decimal"/>' +
        ('<w:pStyle w:val="ActionList"/>' if i == 1 else '') + '<w:lvlText w:val="' + '.'.join('%' + str(j+1) for j in range(i+1)) + '."/><w:lvlJc w:val="left"/>' + f'<w:pPr><w:tabs><w:tab w:val="num" w:pos="{720*(i+1)}"/></w:tabs><w:ind w:left="{720*(i+1)}" w:hanging="360"/></w:pPr></w:lvl>' for i in range(3))
    return root('w:numbering', '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="multilevel"/>' + levels + '</w:abstractNum>'
                '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num><w:num w:numId="2"><w:abstractNumId w:val="0"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>')


def theme():
    colors = ''.join('<a:' + k + '><a:srgbClr val="' + v + '"/></a:' + k + '>' for k, v in zip(
        ('dk1','lt1','dk2','lt2','accent1','accent2','accent3','accent4','accent5','accent6','hlink','folHlink'),
        ('000000','FFFFFF','235789','F1F4F8','235789','E58F65','3A7D44','885A89','D4A373','6C91BF','0563C1','954F72')))
    fonts = ''.join('<a:' + kind + '><a:latin typeface="Times New Roman"/><a:ea typeface=""/><a:cs typeface=""/><a:font script="Hans" typeface="SimSun"/></a:' + kind + '>' for kind in ('majorFont', 'minorFont'))
    # Complete DrawingML format scheme: three fill/line/effect/background entries.
    fill = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    lines = '<a:ln w="9525">' + fill + '<a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>'
    return DECL + f'<a:theme xmlns:a="{A}" name="Original project theme"><a:themeElements><a:clrScheme name="Original">{colors}</a:clrScheme><a:fontScheme name="Original">{fonts}</a:fontScheme><a:fmtScheme name="Original"><a:fillStyleLst>{fill*3}</a:fillStyleLst><a:lnStyleLst>{lines*3}</a:lnStyleLst><a:effectStyleLst>{("<a:effectStyle><a:effectLst/></a:effectStyle>")*3}</a:effectStyleLst><a:bgFillStyleLst>{fill*3}</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>'


CASES = [
    ('01-table-horizontal', '表格：横向合并', './/w:gridSpan'),
    ('02-table-vertical', '表格：纵向合并', './/w:vMerge'),
    ('03-table-nested', '表格：嵌套表', './/w:tc/w:tbl'),
    ('04-table-repeat-header', '表格：跨页重复表头', './/w:tblHeader'),
    ('05-table-multi-paragraph', '表格：单元格多段', './/w:tc/w:p[2]'),
    ('06-field-page', '域：PAGE', './/w:fldSimple'),
    ('07-field-numpages', '域：NUMPAGES', './/w:instrText'),
    ('08-field-date', '域：DATE', './/w:instrText'),
    ('09-field-ref', '域：REF 交叉引用', './/w:bookmarkStart'),
    ('10-field-toc', '域：TOC', './/w:instrText'),
    ('11-list-multilevel', '编号：多级', './/w:ilvl'),
    ('12-list-restart', '编号：重启', './/w:numId[@w:val="2"]'),
    ('13-list-style-bound', '编号：样式绑定', './/w:pStyle[@w:val="ActionList"]'),
    ('14-style-inheritance', '样式：三级继承', './/w:pStyle[@w:val="ProjectHeading"]'),
    ('15-style-direct-override', '样式：直接格式覆盖', './/w:rPr/w:b[@w:val="0"]'),
    ('16-style-theme-fonts', '样式：主题字体与空格式 run', './/w:rFonts[@w:asciiTheme="majorHAnsi"]'),
    ('17-section-margins', '节：不同页边距', './/w:pPr/w:sectPr'),
    ('18-section-landscape', '节：横向页混排', './/w:pgSz[@w:orient="landscape"]'),
    ('19-section-columns', '节：一二三栏混排', './/w:cols[@w:num="3"]'),
    ('20-footnote-restart', '脚注：每页重编号', './/w:footnotePr/w:numRestart'),
    ('21-footnote-table', '脚注：带表格', './/w:footnoteReference'),
    ('22-image-inline', '图形：内联 PNG', './/wp:inline'),
    ('23-image-floating', '图形：四周环绕', './/wp:wrapSquare'),
    ('24-shape-group', '图形：组合图形', './/wpg:wgp'),
    ('25-textbox', '其他：文本框', './/w:txbxContent'),
    ('26-comment-anchors', '其他：批注锚点', './/w:commentRangeStart'),
    ('27-bookmarks', '其他：跨 run 书签', './/w:bookmarkStart'),
    ('28-hidden-text', '其他：隐藏文字', './/w:vanish'),
    ('29-header-table', '其他：页眉表格', './/w:headerReference'),
    ('30-chinese-field-code', '其他：中文域代码', './/w:instrText'),
]


def package(index):
    ident, label, feature = CASES[index-1]
    end, extra, before, props = sect(), '', '', ''
    detail = table()
    after = p('The figures in this original planning memo are invented. Review the schedule and evidence before release.')
    if index == 1:
        detail = table([row([cell(p('Consolidated work plan'), '<w:gridSpan w:val="2"/>')]), row([cell(p('Analysis')), cell(p('42'))])])
    elif index == 2:
        detail = table([row([cell(p('Phase A'), '<w:vMerge w:val="restart"/>'), cell(p('Analysis'))]), row([cell(p(''), '<w:vMerge/>'), cell(p('Review'))])])
    elif index == 3:
        detail = table([row([cell(p('Phase detail') + table() + p('End of inner table.')), cell(p('Owner: Sample team'))])])
    elif index == 4:
        # 88 rows, tall enough to span pages with a genuine repeating header.
        detail = table([row([cell(p('Task')), cell(p('Estimate'))], '<w:tblHeader/><w:cantSplit/>')] +
                       [row([cell(p(f'Original work item {i:02}')), cell(p(str(i*3)))], '<w:trHeight w:val="360" w:hRule="atLeast"/>') for i in range(1, 89)])
    elif index == 5:
        detail = table([row([cell(p('Observation.') + p('Interpretation.') + p('Next action.')), cell(p('Owner: Sample team'))])])
    elif index in (6, 7, 8, 9, 10, 30):
        codes = {6: (' PAGE ', '1'), 7: (' NUMPAGES ', '4'), 8: (' DATE \\@ "yyyy年M月d日" ', '2026年11月10日'),
                 9: (' REF ProjectScope \\h ', 'Project scope'), 10: (' TOC \\o "1-3" \\h \\z \\u ', 'Project scope\t1'),
                 30: (' REF 项目范围 \\h \\* MERGEFORMAT ', '项目范围')}
        code, result = codes[index]
        extra = field(code, result, index == 6)
    elif index in (11, 12, 13):
        props = '<w:pStyle w:val="ActionList"/>' if index == 13 else '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
        after += ''.join(p(f'Original action {i+1}: document the assumptions.', '<w:numPr><w:ilvl w:val="' + str(i % 3 if index == 11 else 0) + '"/><w:numId w:val="' + ('2' if index == 12 and i >= 3 else '1') + '"/></w:numPr>') for i in range(6))
    elif index == 14:
        props = '<w:pStyle w:val="ProjectHeading"/>'
    elif index == 15:
        props = '<w:pStyle w:val="ProjectHeading"/>'
        extra = run(' Direct formatting overrides the inherited heading.', '<w:b w:val="0"/><w:color w:val="992211"/><w:sz w:val="22"/>')
    elif index == 16:
        extra = run(' Theme-selected 中文 font.', '<w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi" w:eastAsiaTheme="majorEastAsia"/>')
        extra += '<w:r><w:rPr><w:rFonts w:asciiTheme="minorHAnsi"/></w:rPr></w:r>'
    elif index in (17, 18, 19):
        props = sect('<w:cols w:num="1"/>', margin=1080)
        after += p('Wide analytical section.', sect('<w:cols w:num="2" w:space="720"/>', landscape=index == 18, margin=720))
        end = sect('<w:cols w:num="3" w:space="360"/>' if index == 19 else '<w:cols w:num="1"/>')
    elif index == 20:
        end = sect('<w:footnotePr><w:numFmt w:val="decimal"/><w:numRestart w:val="eachPage"/></w:footnotePr>')
        after += p('First-page sampling assumption.', extra='<w:r><w:footnoteReference w:id="2"/></w:r>')
        after += p('Next-page review starts here.', before='<w:r><w:br w:type="page"/></w:r>')
    elif index == 23:
        extra = picture(True)
    elif index == 24:
        shape = '<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="457200" cy="609600"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="235789"/></a:solidFill></wps:spPr><wps:bodyPr/></wps:wsp>'
        second = shape.replace('a:off x="0"', 'a:off x="457200"').replace('235789', '3A7D44')
        group = '<a:graphicData uri="' + NS['wpg'] + '"><wpg:wgp><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="609600"/><a:chOff x="0" y="0"/><a:chExt cx="914400" cy="609600"/></a:xfrm></wpg:grpSpPr>' + shape + second + '</wpg:wgp></a:graphicData>'
        extra = '<mc:AlternateContent><mc:Choice Requires="wpg">' + picture(True, group) + '</mc:Choice><mc:Fallback><w:r><w:pict><v:group id="OriginalGroup" style="width:72pt;height:48pt" coordsize="914400,609600"><v:rect id="Box1" style="width:36pt;height:48pt" fillcolor="#235789"/><v:rect id="Box2" style="left:36pt;width:36pt;height:48pt" fillcolor="#3A7D44"/></v:group></w:pict></w:r></mc:Fallback></mc:AlternateContent>'
    elif index == 25:
        extra = '<w:r><w:pict><v:rect id="MemoBox" style="width:180pt;height:80pt" fillcolor="#F1F4F8"><v:textbox><w:txbxContent>' + p('Original text box: note the sampling boundary.') + table() + p('End of note.') + '</w:txbxContent></v:textbox></v:rect></w:pict></w:r>'
    elif index == 26:
        before = '<w:commentRangeStart w:id="0"/>'
        extra = '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r>'
    elif index == 27:
        before = '<w:bookmarkStart w:id="8" w:name="ScopeBoundary"/>'
        extra = run(' Rationale continues across the bookmark.') + '<w:bookmarkEnd w:id="8"/>'
    elif index == 28:
        extra = run('Internal assumption: invented sample only.', '<w:vanish/><w:webHidden/>')
    elif index == 29:
        end = sect('<w:titlePg/>')
    # Every specimen mixes paragraphs, a table, a PNG, fields, notes, styles,
    # theme and headers. The edit is in the structure-bearing body paragraph.
    heading_before, heading_after = '', ''
    if index in (9, 30):
        name = '项目范围' if index == 30 else 'ProjectScope'
        heading_before = '<w:bookmarkStart w:id="8" w:name=' + quoteattr(name) + '/>'
        heading_after = '<w:bookmarkEnd w:id="8"/>'
    body = p('Original project memo — ' + label, '<w:pStyle w:val="Heading1"/>', heading_after, heading_before)
    body += p(MARKER, props, extra, before) + after + detail
    body += p('Scope and assumptions', '<w:pStyle w:val="ProjectHeading"/>')
    body += p('The sample team will compare three invented delivery scenarios. Estimates cover analysis, review and handover; no names or figures refer to a real client.')
    body += p('Schedule and ownership', '<w:pStyle w:val="Heading1"/>')
    body += p('Complete the draft on Monday, review the evidence on Wednesday and record a decision on Friday. The reviewer will keep the source assumptions with the final memo.')
    body += p('An original chart accompanies the estimate.', extra=picture(drawing_id=10))
    body += p('Method note.', extra='<w:r><w:footnoteReference w:id="1"/></w:r>')
    body += end
    document = root('w:document', '<w:body>' + body + '</w:body>')
    # Real serializers retain these import/export processing markers. These are
    # intentional lexical sentinels, not user text or invented feature elements.
    if index in (17, 18, 19):
        document = document.replace('</w:body>', '<!-- end-of-body audit marker --><?audit tail?></w:body>')
    if index in (14, 15, 16, 26, 27, 28):
        document = document.replace('<w:pPr>', '<!-- paragraph property boundary --><?audit properties?><w:pPr>', 1)
    parts = {'word/document.xml': document, 'word/styles.xml': styles(), 'word/numbering.xml': numbering(), 'word/theme/theme1.xml': theme(),
             'word/settings.xml': root('w:settings', '<w:defaultTabStop w:val="720"/><w:footnotePr><w:numRestart w:val="eachPage"/></w:footnotePr>'),
             'word/header1.xml': root('w:hdr', table() + p('Original project memo | ', extra=field(' PAGE ', '1', True))),
             'word/footer1.xml': root('w:ftr', p('Original sample | ', extra=field(' NUMPAGES ', '4'))),
             'word/footnotes.xml': root('w:footnotes', '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote><w:footnote w:id="1">' + p('These values are invented for compatibility testing.') + (table() + p('Footnote table ends here.') if index == 21 else '') + '</w:footnote>' + ('<w:footnote w:id="2">' + p('This separate page uses its own invented sample assumption.') + '</w:footnote>' if index == 20 else '')),
             'word/comments.xml': root('w:comments', '<w:comment w:id="0" w:author="Sample reviewer" w:initials="SR" w:date="2026-11-10T12:00:00Z">' + p('Verify the invented estimate against the sample table.') + '</w:comment>'),
             'word/media/original.png': png(),
             'docProps/core.xml': DECL + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + escape(label) + '</dc:title><dc:creator>EXReader original fixture generator</dc:creator></cp:coreProperties>'}
    relns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    links = [('styles','styles','styles.xml'), ('numbering','numbering','numbering.xml'), ('theme','theme','theme/theme1.xml'),
             ('settings','settings','settings.xml'), ('header','header','header1.xml'), ('footer','footer','footer1.xml'),
             ('notes','footnotes','footnotes.xml'), ('comments','comments','comments.xml'), ('image','image','media/original.png')]
    parts['word/_rels/document.xml.rels'] = DECL + '<Relationships xmlns="' + relns + '">' + ''.join(f'<Relationship Id="{i}" Type="{R}/{kind}" Target="{target}"/>' for i, kind, target in links) + '</Relationships>'
    parts['_rels/.rels'] = DECL + f'<Relationships xmlns="{relns}"><Relationship Id="document" Type="{R}/officeDocument" Target="word/document.xml"/><Relationship Id="core" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>'
    types = {'document': 'document.main', 'styles': 'styles', 'numbering':'numbering', 'settings':'settings', 'header1':'header', 'footer1':'footer', 'footnotes':'footnotes', 'comments':'comments'}
    overrides = ''.join(f'<Override PartName="/word/{name}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>' for name, kind in types.items())
    overrides += '<Override PartName="/word/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    parts['[Content_Types].xml'] = DECL + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>' + overrides + '</Types>'
    return {name: data.encode('utf-8') if isinstance(data, str) else data for name, data in parts.items()}


def pack(parts):
    out = io.BytesIO()
    with ZipFile(out, 'w', compression=ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(parts.items()):
            info = ZipInfo(name, (2026, 11, 10, 0, 0, 0))
            info.compress_type, info.external_attr = ZIP_DEFLATED, 0o100644 << 16
            z.writestr(info, data)
    return out.getvalue()


def generated():
    manifest = dict(license='MIT; all prose, numeric data and image pixels are original', documents=[])
    result = {}
    for index, (ident, label, feature) in enumerate(CASES, 1):
        data = pack(package(index))
        assert len(data) < 60 * 1024, (ident, len(data))
        result[ident + '.docx'] = data
        manifest['documents'].append(dict(id=ident, label=label, path=ident + '.docx', bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), feature=feature, edit_from=MARKER, edit_to=REPLACEMENT))
    result['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = generated()
    for name, data in result.items():
        if args.check:
            assert (HERE / name).read_bytes() == data, name
        else:
            (HERE / name).write_bytes(data)
    assert {p.name for p in HERE.glob('*.docx')} == {n for n in result if n.endswith('.docx')}
    print('30 original fixtures: deterministic bytes verified' if args.check else 'Generated 30 original mixed fixtures')


if __name__ == '__main__':
    main()
