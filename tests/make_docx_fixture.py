#!/usr/bin/env python3
"""Original DOCX fixture: styles, images, links, merges and alternate content."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import base64, zipfile, xml.etree.ElementTree as ET
root=Path(__file__).resolve().parent/'fixtures'
w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
rel='http://schemas.openxmlformats.org/package/2006/relationships'
main=f'''<w:document xmlns:w="{w}" xmlns:r="{r}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Heading</w:t></w:r></w:p>
<w:p><w:r><w:t>Normal </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>Bold</w:t></w:r><w:r><w:t> </w:t></w:r><w:r><w:rPr><w:rStyle w:val="Child"/></w:rPr><w:t>Styled</w:t></w:r></w:p>
<w:p><w:bookmarkStart w:id="0" w:name="target"/><w:hyperlink r:id="Link"><w:r><w:t>Outside</w:t></w:r></w:hyperlink><w:r><w:t> </w:t></w:r><w:hyperlink w:anchor="target"><w:r><w:t>Inside</w:t></w:r></w:hyperlink><w:bookmarkEnd w:id="0"/></w:p>
<w:p><w:r><w:drawing><wp:inline><wp:extent cx="228600" cy="114300"/><a:graphic><a:graphicData><a:blip r:embed="Picture"/></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>
<w:tbl><w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>Left</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>Across</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>C</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<mc:AlternateContent><mc:Choice Requires="w"><w:p><w:r><w:t>Should not appear</w:t></w:r></w:p></mc:Choice><mc:Fallback><w:p><w:r><w:t>Fallback</w:t></w:r></w:p></mc:Fallback></mc:AlternateContent>
<w:p><w:del><w:r><w:t>Deleted</w:t></w:r></w:del><w:ins><w:r><w:t>Inserted </w:t></w:r></w:ins><w:r><w:instrText>Instruction</w:instrText><w:t>Result</w:t></w:r></w:p>
</w:body></w:document>'''
main=main.replace('</w:body>','<w:p><w:r><w:t>Foot</w:t><w:footnoteReference w:id="9"/><w:t> again</w:t><w:footnoteReference w:id="9"/><w:t> End</w:t><w:endnoteReference w:id="4"/></w:r></w:p></w:body>')
styles=f'''<w:styles xmlns:w="{w}"><w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:pPr><w:spacing w:after="60"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/></w:rPr></w:style>
<w:style w:type="character" w:styleId="Base"><w:rPr><w:sz w:val="28"/><w:color w:val="122334"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="Child"><w:basedOn w:val="Base"/><w:rPr><w:i/></w:rPr></w:style></w:styles>'''
entries={
'_rels/.rels':f'<Relationships xmlns="{rel}"><Relationship Id="Main" Type="{r}/officeDocument" Target="Content/main.xml"/></Relationships>',
'Content/main.xml':main,
'Content/_rels/main.xml.rels':f'<Relationships xmlns="{rel}"><Relationship Id="Styles" Type="{r}/styles" Target="../Styles/styles.xml"/><Relationship Id="Picture" Type="{r}/image" Target="images/%E5%9B%BE%23%25%3F.png"/><Relationship Id="Link" Type="{r}/hyperlink" Target="https://example.test/?a=1&amp;b=2" TargetMode="External"/></Relationships>',
'Styles/styles.xml':styles,
'Content/images/图#%?.png':base64.b64decode(ET.parse(root/'rich.fb2').find('{*}binary').text),
'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="png" ContentType="image/png"/><Default Extension="xml" ContentType="application/xml"/></Types>'}
entries['Content/_rels/main.xml.rels']=entries['Content/_rels/main.xml.rels'].replace('</Relationships>',f'<Relationship Id="Footnotes" Type="{r}/footnotes" Target="Notes/footnotes.xml"/><Relationship Id="Endnotes" Type="{r}/endnotes" Target="Notes/endnotes.xml"/></Relationships>')
entries['Content/Notes/footnotes.xml']=f'''<w:footnotes xmlns:w="{w}" xmlns:r="{r}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"><w:footnote w:id="-1" w:type="separator"><w:p><w:r><w:t>Separator ignored</w:t></w:r></w:p></w:footnote><w:footnote w:id="9"><w:p><w:r><w:footnoteRef/><w:t> Note text.</w:t></w:r></w:p><w:p><w:r><w:drawing><wp:inline><wp:extent cx="228600" cy="114300"/><a:graphic><a:blip r:embed="Picture"/></a:graphic></wp:inline></w:drawing></w:r></w:p></w:footnote><w:footnote w:id="7"><w:p><w:r><w:t>Orphan ignored</w:t></w:r></w:p></w:footnote></w:footnotes>'''
entries['Content/Notes/endnotes.xml']=f'''<w:endnotes xmlns:w="{w}"><w:endnote w:id="4"><w:p><w:r><w:endnoteRef/><w:t> Endnote text.</w:t></w:r></w:p></w:endnote></w:endnotes>'''
entries['Content/Notes/_rels/footnotes.xml.rels']=f'<Relationships xmlns="{rel}"><Relationship Id="Picture" Type="{r}/image" Target="note.png"/></Relationships>'
entries['Content/Notes/note.png']=entries['Content/images/图#%?.png']
with zipfile.ZipFile(root/'rich.docx','w') as archive:
    for name,data in entries.items():
        info=zipfile.ZipInfo(name,(2026,1,1,0,0,0)); info.compress_type=zipfile.ZIP_STORED; info.external_attr=0o100644<<16
        archive.writestr(info,data.encode() if isinstance(data,str) else data)
