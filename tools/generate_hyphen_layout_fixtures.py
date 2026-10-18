#!/usr/bin/env python3
"""Original XHTML/CSS hyphenation cases and a derived original shaping font."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_STORED,ZIP_DEFLATED
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.otlLib.builder import buildPairPosGlyphsSubtable
from fontTools.ttLib.tables.otBase import ValueRecord
from fontTools.pens.ttGlyphPen import TTGlyphPen
root=Path(__file__).resolve().parents[1]/'tests/fixtures'
font=TTFont(root/'shaping/shaping.ttf');font.recalcTimestamp=False
pen=TTGlyphPen(None);pen.moveTo((20,250));pen.lineTo((230,250));pen.lineTo((230,310));pen.lineTo((20,310));pen.closePath()
order=font.getGlyphOrder()+['hyphen'];font.setGlyphOrder(order);font['glyf']['hyphen']=pen.glyph();font['hmtx'].metrics['hyphen']=(250,0)
for table in font['cmap'].tables:
    if table.isUnicode(): table.cmap[45]=table.cmap[0x2010]='hyphen'
value=ValueRecord();value.XAdvance=-80
lookup=otTables.Lookup();lookup.LookupType=2;lookup.LookupFlag=0
lookup.SubTable=[buildPairPosGlyphsSubtable({('f','hyphen'):(value,None)},font.getReverseGlyphMap())];lookup.SubTableCount=1
gpos=font['GPOS'].table;index=len(gpos.LookupList.Lookup);gpos.LookupList.Lookup.append(lookup);gpos.LookupList.LookupCount+=1
for feature in gpos.FeatureList.FeatureRecord:
    if feature.FeatureTag=='kern': feature.Feature.LookupListIndex.append(index);feature.Feature.LookupCount+=1
font.save(root/'shaping/hyphen.ttf',reorderTables=False)
with ZipFile(root/'float-both.epub') as z: base={n:z.read(n) for n in z.namelist()}
count=0
def epub(name,body,css='',attrs='',language='en'):
    global count
    files=dict(base)
    files['chapter.xhtml']=('<html xmlns="http://www.w3.org/1999/xhtml" '+attrs+'><head><title>Hyphens</title><link rel="stylesheet" href="style.css"/></head><body>'+body+'</body></html>').encode()
    files['style.css']=('html,body,p,div,table,tr,td {margin:0;padding:0;border:0} body {font-size:14px;line-height:20px;hyphens:auto} '+css).encode()
    for key in ('book.opf','content.opf','package.opf'):
        if key in files:
            import re
            files[key]=re.sub(rb'<dc:language>.*?</dc:language>',('<dc:language>'+language+'</dc:language>').encode(),files[key])
    with ZipFile(root/('hyphen-'+name+'.epub'),'w') as z:
        for key,data in files.items():
            info=ZipInfo(key,(2026,1,1,0,0,0));info.compress_type=ZIP_STORED if key=='mimetype' else ZIP_DEFLATED;z.writestr(info,data)
    count+=1
words=('AAAAAA '*800).strip()
epub('opf','<p>AAAAAA AAAAAA</p>')
epub('xml-lang','<p>AAAAAA AAAAAA</p>',attrs='xml:lang="en-US"',language='fr')
epub('unknown','<p>AAAAAA AAAAAA</p>',attrs='lang="de"')
epub('empty-lang','<p lang="">AAAAAA AAAAAA</p>')
epub('manual','<p style="hyphens:manual">AAAAAA AAAAAA</p>')
epub('none','<p style="hyphens:none">AA\u00adAAAA AAAAAA</p>')
epub('soft','<p style="hyphens:manual">AA\u00adAAAA AAAAAA</p>')
epub('inline','<p>AA<span style="font-weight:bold">AA</span>AA AA<span style="color:blue">AAAA</span></p>')
epub('inherit','<p style="hyphens:inherit">AAAAAA AAAAAA</p>')
epub('invalid-css','<p style="hyphens:auto;hyphens:invalid">AAAAAA AAAAAA</p>')
epub('invalid-lang','<p lang="en_US">AAAAAA AAAAAA</p>')
epub('inline-optin','<p style="hyphens:manual">AA<span style="hyphens:auto">AAAA</span> AAAAAA</p>')
epub('inline-none','<p>AA<span style="hyphens:none">AAAA</span></p>')
epub('gap','<p>AA<span style="float:left;width:14px">A</span>AAAA</p>')
epub('long','<p>'+words+'</p>')
epub('rtl','<p dir="rtl">'+words+'</p>')
epub('vertical','<p>'+words+'</p>','html {writing-mode:vertical-rl}')
epub('table','<table style="width:50px"><tr><td>AAAAAA</td><td>AAAAAA</td></tr></table><p>'+words+'</p>')
epub('float','<div style="float:left;width:30px;background:#ffe080">'+words+'</div><p>'+words+'</p>')
epub('orthogonal','<div style="writing-mode:vertical-rl">'+words+'</div>')
epub('ruby','<p>AAAAAA <ruby>AA<rt>A</rt></ruby> AAAAAA</p>')
epub('fi','<p style="width:7px">fifififi</p>')
epub('fi-wide','<p>fifififi</p>')
epub('canonical','<p style="width:28px">'+('ÉTÉ '*800).strip()+'</p>',attrs='lang="fr"')
epub('compound','<p style="width:42px">'+('AAAAAAAA '*800).strip()+'</p>',attrs='lang="xx"')
epub('compound-joiner','<p style="width:42px">'+('AAAAAA’AAAAAA '*800).strip()+'</p>')
epub('arabic','<p dir="rtl" style="width:14px">لالالا</p>',attrs='lang="ar"')
print(count,'hyphenation EPUBs and shaping/hyphen.ttf generated')
