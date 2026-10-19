#!/usr/bin/env python3
"""Original XHTML/CSS hyphenation cases and a derived original shaping font."""
# SPDX-License-Identifier: MIT
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
rewrite_words=('aaaaaaaa '*800).strip()
epub('rewrite-canonical','<p style="width:28px">'+('ÉTÉ '*800).strip()+'</p>',attrs='lang="zr"')
epub('rewrite-long','<p style="width:42px">'+rewrite_words+'</p>',attrs='lang="zz"')
epub('rewrite-rtl','<p dir="rtl" style="width:42px">'+rewrite_words+'</p>',attrs='lang="zz"')
epub('rewrite-vertical','<p style="height:42px">'+rewrite_words+'</p>','html {writing-mode:vertical-rl}',attrs='lang="zz"')
epub('rewrite-float','<div style="float:left;width:42px;background:#ffe080">'+rewrite_words+'</div><p>'+rewrite_words+'</p>',attrs='lang="zz"')
epub('rewrite-orthogonal','<div style="writing-mode:vertical-rl;height:42px">'+rewrite_words+'</div>',attrs='lang="zz"')
epub('rewrite-inline','<p style="width:50px">'+('aaa<span style="font-weight:bold">a</span><span style="color:blue">a</span>aaa '*800).strip()+'</p>',attrs='lang="zz"')
epub('rewrite-gap','<p style="width:49px">aaa<span style="float:left;width:7px">A</span>aaaaa</p><p style="width:42px">'+rewrite_words+'</p>',attrs='lang="zz"')
epub('rewrite-table','<table style="width:42px">'+('<tr><td>aaaaaaaa</td></tr>'*160)+'</table>',attrs='lang="zz"')
epub('arabic','<p dir="rtl" style="width:14px">لالالا</p>',attrs='lang="ar"')
rematch_words=('abcdefghijklmnopqr '*400).strip()
epub('rematch-long','<p style="width:42px">'+rematch_words+'</p>',attrs='lang="zm"')
epub('rematch-rtl','<p dir="rtl" style="width:42px">'+rematch_words+'</p>',attrs='lang="zm"')
epub('rematch-vertical','<p style="height:42px">'+rematch_words+'</p>','html {writing-mode:vertical-rl}',attrs='lang="zm"')
epub('rematch-float','<div style="float:left;width:42px;background:#ffe080">'+rematch_words+'</div><p>'+rematch_words+'</p>',attrs='lang="zm"')
epub('rematch-orthogonal','<div style="writing-mode:vertical-rl;height:42px">'+rematch_words+'</div>',attrs='lang="zm"')
epub('rematch-table','<table style="width:42px">'+('<tr><td>abcdefghijklmnopqr</td></tr>'*100)+'</table>',attrs='lang="zm"')
epub('rematch-inline','<p style="width:42px">'+('abc<span style="font-weight:bold">d</span><span style="color:blue">e</span>fghijklmnopqr '*400).strip()+'</p>',attrs='lang="zm"')
epub('rematch-gap','<p style="width:49px">abc<span style="float:left;width:7px">A</span>defghijklmnopqr</p><p style="width:42px">'+rematch_words+'</p>',attrs='lang="zm"')
epub('rematch-canonical','<p style="width:42px">'+('Ébcdefghijklmnopqr '*400).strip()+'</p>',attrs='lang="zn"')
boundary_words=('aaaaaaaa '*800).strip()
epub('boundary-long','<p style="width:42px">'+boundary_words+'</p>',attrs='lang="zp"')
epub('boundary-rtl','<p dir="rtl" style="width:42px">'+boundary_words+'</p>',attrs='lang="zp"')
epub('boundary-vertical','<p style="height:42px">'+boundary_words+'</p>','html {writing-mode:vertical-rl}',attrs='lang="zp"')
epub('boundary-float','<div style="float:left;width:42px;background:#ffe080">'+boundary_words+'</div><p>'+boundary_words+'</p>',attrs='lang="zp"')
epub('boundary-orthogonal','<div style="writing-mode:vertical-rl;height:42px">'+boundary_words+'</div>',attrs='lang="zp"')
epub('boundary-table','<table style="width:42px">'+('<tr><td>aaaaaaaa</td></tr>'*160)+'</table>',attrs='lang="zp"')
epub('boundary-inline','<p style="width:42px">'+('aa<span style="font-weight:bold">aa</span><span style="color:blue">a</span>aaa '*800).strip()+'</p>',attrs='lang="zp"')
epub('boundary-gap','<p style="width:49px">aa<span style="float:left;width:7px">A</span>aaaaaa</p><p style="width:42px">'+boundary_words+'</p>',attrs='lang="zp"')
epub('boundary-canonical','<p style="width:42px">'+('Éaaaaaaa '*800).strip()+'</p>',attrs='lang="zu"')
epub('boundary-ri','<p style="width:28px">'+('aaaaa🇸🇨 '*800).strip()+'</p>',attrs='lang="zv"')
epub('boundary-emoji','<p style="width:28px">'+('aaaaa👩‍💻 '*800).strip()+'</p>',attrs='lang="zw"')
bidi_words=('aaaaaaaaaaaa '*800).strip()
epub('bidi-long','<p style="width:49px">'+bidi_words+'</p>',attrs='lang="zb"')
epub('bidi-rtl','<p dir="rtl" style="width:49px">'+bidi_words+'</p>',attrs='lang="zb"')
epub('bidi-vertical','<p style="height:56px">'+bidi_words+'</p>','html {writing-mode:vertical-rl}',attrs='lang="zb"')
epub('bidi-float','<div style="float:left;width:49px;background:#ffe080">'+bidi_words+'</div><p>'+bidi_words+'</p>',attrs='lang="zb"')
epub('bidi-orthogonal','<div style="writing-mode:vertical-rl;height:56px">'+bidi_words+'</div>',attrs='lang="zb"')
epub('bidi-table','<table style="width:49px">'+('<tr><td>aaaaaaaaaaaa</td></tr>'*100)+'</table>',attrs='lang="zb"')
epub('bidi-inline','<p style="width:56px">'+('aaa<span style="font-weight:bold">a</span><span style="color:blue">a</span>aaaaaaa '*800).strip()+'</p>',attrs='lang="zb"')
epub('bidi-bracket',('<p style="width:56px">'+('(aaaaaaaaaaaa) '*12).strip()+'</p>')*40,attrs='lang="zb"')
epub('bidi-isolate',('<p style="width:49px">'+('aaaaaaaaaaaa '*12).strip()+'</p>')*40,attrs='lang="zc"')
epub('bidi-override',('<p style="width:49px">'+('aaaaaaaaaaaa '*12).strip()+'</p>')*40,attrs='lang="zd"')
epub('bidi-auto','<p style="width:49px;text-align:start">'+bidi_words+'</p>',attrs='lang="ze"')
leading='1111111111111111111111111111111111111111111111111111111111111111 '
epub('bidi-leading','<p style="width:49px;text-align:start">'+leading+bidi_words+'</p>',attrs='lang="ze"')
epub('bidi-leading-float','<div style="float:left;width:14px;height:100px;background:#ffe080">A</div><p style="width:49px;text-align:start">'+leading+bidi_words+'</p>',attrs='lang="ze"')
epub('bidi-paragraphs','<p style="width:49px;text-align:start">1111\u2029'+leading+bidi_words+'</p>',attrs='lang="ze"')
epub('bidi-leading-ruby','<p style="width:49px;text-align:start"><ruby>AA<rt>A</rt></ruby> '+leading+bidi_words+'</p>',attrs='lang="ze"')
future_neutral='a אב '+('+'*96)+' aaaaaaaaaaaa'
future_bracket='a אב ('+('1'*96)+' aaaaaaaaaaaa'
future_isolate='a אב \u2067abc '+('1'*64)+' aaaaaaaaaaaa'
future_numbers='a ا '+('111,$+1,'*12)+' aaaaaaaaaaaa'
epub('bidi-future-neutral',('<p style="width:56px">'+future_neutral+'</p>')*12,attrs='lang="zf"')
epub('bidi-future-bracket',('<p style="width:56px">'+future_bracket+'</p>')*12,attrs='lang="zg"')
epub('bidi-future-isolate',('<p style="width:56px">'+future_isolate+'</p>')*12,attrs='lang="zh"')
epub('bidi-future-numbers',('<p style="width:56px">'+future_numbers+'</p>')*12,attrs='lang="zf"')
epub('bidi-future-float','<div style="float:left;width:14px;height:100px;background:#ffe080">A</div>'+('<p style="width:56px">'+future_neutral+'</p>')*12,attrs='lang="zf"')
epub('bidi-future-vertical',('<p style="height:56px">'+future_neutral+'</p>')*12,'html {writing-mode:vertical-rl}',attrs='lang="zf"')
epub('bidi-future-tall-row','<table style="width:56px">'+('<tr><td>'+future_neutral+'</td></tr>')*12+'</table>',attrs='lang="zf"')
epub('bidi-future-table','<table style="width:56px">'+('<tr><td>a אב +++++++++++++ aaaaaaaaaaaa</td></tr>')*40+'</table>',attrs='lang="zf"')
insertion_words=('aaaaaaaa '*160).strip()
epub('insertion-long','<p style="width:35px">'+insertion_words+'</p>',attrs='lang="zi"')
epub('insertion-rtl','<p dir="rtl" style="width:35px">'+insertion_words+'</p>',attrs='lang="zi"')
epub('insertion-vertical','<p style="height:35px">'+insertion_words+'</p>','html {writing-mode:vertical-rl}',attrs='lang="zi"')
epub('insertion-float','<div style="float:left;width:35px;background:#ffe080">'+insertion_words+'</div><p>'+insertion_words+'</p>',attrs='lang="zi"')
epub('insertion-orthogonal','<div style="writing-mode:vertical-rl;height:35px">'+insertion_words+'</div>',attrs='lang="zi"')
epub('insertion-inline','<p style="width:42px">'+('aaa<span style="font-weight:bold">a</span><span style="color:blue">a</span>aaa '*160).strip()+'</p>',attrs='lang="zi"')
epub('insertion-table','<table style="width:35px">'+('<tr><td>aaaaaaaa</td></tr>'*40)+'</table>',attrs='lang="zi"')
epub('insertion-mixed','<p style="width:35px">'+insertion_words+'</p>',attrs='lang="zj"')
case_words=('AAAAAAAA '*160).strip()
epub('case-long','<p style="width:42px">'+case_words+'</p>',attrs='lang="de"')
epub('case-title','<p style="width:42px">'+('Aaaaaaaa '*160).strip()+'</p>',attrs='lang="en"')
epub('case-rtl','<p dir="rtl" style="width:42px">'+case_words+'</p>',attrs='lang="de"')
epub('case-vertical','<p style="height:42px">'+case_words+'</p>','html {writing-mode:vertical-rl}',attrs='lang="de"')
epub('case-float','<div style="float:left;width:42px;background:#ffe080">'+case_words+'</div><p>'+case_words+'</p>',attrs='lang="de"')
epub('case-table','<table style="width:42px">'+('<tr><td>AAAAAAAA</td></tr>'*100)+'</table>',attrs='lang="de"')
epub('case-tr','<p style="width:42px">'+('IIIIIIII '*160).strip()+'</p>',attrs='lang="tr-TR"')
epub('case-lt','<p style="width:49px">'+('aaaaaaaa '*160).strip()+'</p>',attrs='lang="lt-LT"')
epub('case-el','<p style="width:42px">'+('αααααααα '*160).strip()+'</p>',attrs='lang="el"')
epub('case-canonical','<p style="width:42px">'+('Éaaaaaaa '*160).strip()+'</p>',attrs='lang="fr"')
epub('case-insertion','<p style="width:35px">'+('BBBBBBBB '*160).strip()+'</p>',attrs='lang="de"')
epub('case-title-delete','<p style="width:42px">'+('Cccccccc '*160).strip()+'</p>',attrs='lang="en"')
epub('case-mixed','<p style="width:42px">'+('AaAAaaaa '*160).strip()+'</p>',attrs='lang="de"')
epub('case-orthogonal','<div style="writing-mode:vertical-rl;height:42px">'+case_words+'</div>',attrs='lang="de"')
epub('case-inline','<p style="width:49px">'+('AAA<span style="font-weight:bold">A</span><span style="color:blue">A</span>AAA '*160).strip()+'</p>',attrs='lang="de"')
stem_words=('abcdefghijk '*160).strip()
epub('stem-long','<p style="width:35px">'+stem_words+'</p>',attrs='lang="zk"')
epub('stem-rtl','<p dir="rtl" style="width:35px">'+stem_words+'</p>',attrs='lang="zk"')
epub('stem-vertical','<p style="height:35px">'+stem_words+'</p>','html {writing-mode:vertical-rl}',attrs='lang="zk"')
epub('stem-float','<div style="float:left;width:35px;background:#ffe080">'+stem_words+'</div><p>'+stem_words+'</p>',attrs='lang="zk"')
epub('stem-orthogonal','<div style="writing-mode:vertical-rl;height:35px">'+stem_words+'</div>',attrs='lang="zk"')
epub('stem-table','<table style="width:35px">'+('<tr><td>abcdefghijk</td></tr>'*100)+'</table>',attrs='lang="zk"')
epub('stem-inline','<p style="width:42px">'+('abc<span style="font-weight:bold">d</span><span style="color:blue">e</span>fghijk '*160).strip()+'</p>',attrs='lang="zk"')
epub('stem-canonical','<p style="width:35px">'+('abcdéfghijk '*160).strip()+'</p>',attrs='lang="zk"')
epub('stem-case','<p style="width:63px">'+('ABCDEFGHIJK '*160).strip()+'</p>',attrs='lang="zk"')
print(count,'hyphenation EPUBs and shaping/hyphen.ttf generated')
