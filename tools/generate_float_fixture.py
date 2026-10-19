"""Original deterministic float/BFC/continuation EPUBs; standard library only."""
# SPDX-License-Identifier: MIT
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED
import struct,zlib
root=Path(__file__).resolve().parents[1]/'tests/fixtures'
with ZipFile(root/'table-align-modes.epub') as base:
    files={name:base.read(name) for name in base.namelist()}
def chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',80,60,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x00\x80\xff\xff'*80)*60))+chunk(b'IEND',b'')
files['image.png']=png
count=0
def epub(name,body,css=''):
    global count
    content=dict(files)
    content['chapter.xhtml']=('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Float</title><link rel="stylesheet" href="style.css"/></head><body>'+body+'</body></html>').encode()
    content['style.css']=('html,body,p,div,table,tr,td {margin:0;padding:0;border:0} body {font-size:14px;line-height:20px} '+css).encode()
    with ZipFile(root/('float-'+name+'.epub'),'w') as z:
        for name,data in content.items():
            info=ZipInfo(name,(2026,1,1,0,0,0)); info.compress_type=ZIP_STORED if name=='mimetype' else ZIP_DEFLATED; z.writestr(info,data)
    count+=1
def image(name,side,width,extra=''):
    return f'<img id="{name}" src="image.png" alt="Original blue" style="float:{side};width:{width}px;{extra}"/>'
def text(n=100): return '<span id="text">'+('A '*n).rstrip()+'</span>'
epub('left','<p>'+image('picture','left',80)+text()+'</p>')
epub('right','<p>'+image('picture','right',80)+text()+'</p>')
epub('both','<p>'+image('left','left',60)+image('right','right',60)+text()+'</p>')
epub('same','<p>'+image('left','left',60)+image('right','left',60)+text()+'</p>')
epub('stack','<p>'+image('left','left',120)+image('right','left',100)+text()+'</p>')
epub('order','<p>'+image('first','left',120)+image('second','left',100)+image('third','right',40)+text()+'</p>')
for clear in ('left','right','both'):
    epub('clear-'+clear,'<p>'+image('left','left',80)+image('right','right',40)+'</p><p style="clear:'+clear+'">'+text()+'</p>')
epub('midline','<p><span id="before">AAAA</span>'+image('picture','left',60)+text()+'</p>')
epub('late','<p><span id="before">'+('A'*24)+'</span>'+image('picture','left',60)+text()+'</p>')
epub('block','<div id="floating" style="float:left;width:60px;height:80px;background:#ffe080">AAA</div><p>'+text()+'</p>')
epub('auto','<span id="floating" style="float:left;background:#ffe080">A A</span><p>'+text()+'</p>')
epub('table','<table id="floating" style="float:left;border-collapse:collapse"><tr><td>AA</td><td>AAA</td></tr></table><p>'+text()+'</p>','td {border:2px solid blue}')
epub('cell','<table style="width:200px;table-layout:fixed"><tr><td id="cell">'+image('picture','left',40)+text(25)+'</td><td id="peer">A</td></tr></table>')
epub('nested','<div id="floating" style="float:left;width:100px;background:#ffe080">'+image('picture','right',40)+text(10)+'</div><p>'+text()+'</p>')
epub('vertical-rl','<p>'+image('picture','left',80)+text()+'</p>','html {writing-mode:vertical-rl} img {width:auto !important;height:60px}')
epub('vertical-lr','<p>'+image('picture','left',80)+text()+'</p>','html {writing-mode:vertical-lr} img {width:auto !important;height:60px}')
epub('bidi','<p dir="rtl">'+image('picture','right',80)+'<span id="text">'+('سلام A '*35)+'</span></p>')
epub('soft','<p>'+image('picture','left',160)+'<span id="text">'+('AA\u00adAAA '*30)+'</span></p>')
epub('ruby','<p>'+image('picture','left',120)+'A <ruby>AA<rt>AAA</rt></ruby> '+text()+'</p>')
epub('pages',''.join('<p>'+image('i'+str(i),'left' if i%2 else 'right',40+10*(i%4))+text(40)+'</p>' for i in range(60)))
epub('next-page','<p>'+('A<br/>'*8)+'</p><p>'+image('picture','left',80)+text()+'</p>')
epub('full','<p>'+image('picture','left',200)+text(15)+'</p>')
epub('clear-br','<p>'+image('picture','left',80)+'A<br style="clear:both"/>'+text()+'</p>')
epub('margins','<p>'+image('picture','left',80,'margin:5px 7px 9px 11px;padding:3px;border:2px solid red')+text()+'</p>')
epub('oversized','<div style="float:left;width:80px">'+('<p>A</p>'*30)+'</div><p>A</p>')
epub('limit',''.join('<div style="float:left;width:8px;height:160px">A</div>' for i in range(129))+'<p>A</p>')
epub('normal-image',image('picture','left',80)+'<img id="normal" src="image.png" alt="Blue" style="width:40px;padding:2px;border:2px solid red"/><p>'+text()+'</p>')
epub('normal-table',image('picture','left',80)+'<table style="width:100px"><tr><td>A</td><td>A</td></tr></table><p>'+text()+'</p>')
epub('mixed-size','<p>'+image('first','left',80)+image('second','left',150)+'A A <span style="font-size:40px">AAA</span> '+text()+'</p>')
epub('ordinary-block',image('picture','left',80)+'<div style="padding:4px;border:2px solid red;background:#ffe080">'+text()+'</div>')
epub('nested-clear','<div style="float:left;width:100px;background:#ffe080">'+image('picture','right',40)+'<p style="clear:both">A A</p></div><p>'+text()+'</p>')
epub('joining','<p><span id="before">ل</span>'+image('picture','left',40)+'<span id="after">ا</span></p>')
epub('joining-control','<p><span id="before">ل</span><span id="after">ا</span></p>')
epub('percent','<p><img id="picture" src="image.png" alt="Blue" style="float:left;width:20%;padding:5%;border:2px solid red"/>'+text()+'</p>')
epub('empty','<div id="floating" style="float:left;width:60px;height:80px;background:#ffe080"></div><p>'+text()+'</p>')
epub('orthogonal-pages','<div style="writing-mode:vertical-rl">'+image('picture','left',40)+text(4000)+'</div>','html {writing-mode:horizontal-tb}')
epub('auto-percent','<div id="floating" style="float:left;padding:5%;background:#ffe080">A A</div><p>'+text()+'</p>')
epub('max-percent','<div id="floating" style="float:left;width:80%;max-width:30%;background:#ffe080">A A</div><p>'+text()+'</p>')
epub('cell-baseline','<table style="width:200px;table-layout:fixed"><tr><td id="cell"><div id="floating" style="float:left;width:60px;height:60px;background:#ffe080">A</div></td><td id="peer">A</td></tr></table>')
epub('auto-corridor',image('picture','left',140)+'<div id="floating" style="float:left;background:#ffe080">A A A A A A</div><p>'+text()+'</p>')
epub('source-overlap','<p>'+('A<br/>'*8)+'</p><p><span style="font-size:56px">A</span><span style="float:left;width:40px;height:20px;background:#ffe080">AAA</span>A A A A</p>')
for depth in (8,9):
    epub('depth-'+str(depth),('<div style="float:left;width:100px;height:40px;background:#ffe080">'*depth)+'A'+('</div>'*depth)+'<p>'+text()+'</p>')
long_body='<p>'+('A '*2500)+'</p>'
def side(body=long_body,style=''):
    return '<div id="floating" style="float:left;width:80px;background:#ffe080;'+style+'">'+body+'</div>'
epub('long-only',side())
epub('long-short-main',side()+'<p>'+text(10)+'</p>')
epub('long-main',side()+'<p>'+text(5000)+'</p>')
epub('long-right',side(style='float:right')+'<p>'+text(5000)+'</p>')
epub('long-pair',side()+side(style='float:right')+'<p>'+text(5000)+'</p>')
epub('long-clear',side()+'<p id="after" style="clear:both">AAA</p>')
epub('long-clear-br','<p>'+side()+'A<br style="clear:both"/><span id="after">AAA</span></p>')
epub('long-clear-float',side()+'<div id="after" style="float:right;clear:left;width:40px;background:blue">AAA</div>')
epub('long-partial','<p>'+('A<br/>'*7)+'</p>'+side()+'<p>'+text(1000)+'</p>')
epub('long-margins',side(style='margin:5px 7px 9px 11px;padding:3px;border:2px solid red')+'<p>'+text(1000)+'</p>')
epub('long-height',side('A','height:650px;padding:3px;border:2px solid red')+'<p>'+text(1000)+'</p>')
epub('long-empty',side('','height:650px')+'<p>'+text(1000)+'</p>')
epub('long-percent',side('A','height:250%')+'<p>'+text(1000)+'</p>')
epub('long-table','<table id="floating" style="float:left;width:80px;border-collapse:collapse">'+('<tr><td>A</td><td>AA</td></tr>'*250)+'</table><p>'+text(1000)+'</p>','td {border:2px solid blue}')
epub('long-nested',side('<div style="float:right;width:30px;background:blue">'+long_body+'</div><p>'+('A '*1000)+'</p>')+'<p>'+text(1000)+'</p>')
epub('long-orthogonal',side('<div style="writing-mode:vertical-rl">'+long_body+'</div>')+'<p>'+text(1000)+'</p>')
epub('long-orthogonal-margins','<p>'+('A<br/>'*7)+'</p>'+side('<div style="writing-mode:vertical-rl">'+long_body+'</div>','margin:5px 7px 9px 11px;padding:3px;border:2px solid red')+'<p>'+text(1000)+'</p>')
epub('long-vertical',side(style='width:80px;height:80px')+'<p>'+text(5000)+'</p>','html {writing-mode:vertical-rl}')
epub('long-unbreakable',side('<p style="font-size:240px;line-height:260px">A</p>'))
epub('long-table-unbreakable',side('<table><tr><td>'+long_body+'</td></tr></table>'))
epub('long-descending',side('<p>'+('A '*1000)+'</p>','height:10000px')+side('A','height:1200px')+'<p>'+text(100)+'</p>')
inner=''.join('<div style="float:left;width:1px;height:1000px;background:blue"></div>' for _ in range(64))
epub('long-cursor-limit',side(inner)+side(inner))
def table(n=1,style='width:100px',cell='A'):
    return '<table id="ordinary" style="background:#80ffaa;'+style+'">'+('<tr><td>'+cell+'</td><td>AA</td></tr>')*n+'</table>'
for side_name in ('left','right'):
    epub('bfc-'+side_name,image('picture',side_name,80)+table()+'<p>'+text(20)+'</p>')
epub('bfc-both',image('left','left',40)+image('right','right',40)+table()+'<p>'+text(20)+'</p>')
epub('bfc-auto',image('picture','left',80)+table(style='')+'<p>'+text(20)+'</p>')
epub('bfc-wide',image('picture','left',80)+table(style='width:160px')+'<p>'+text(20)+'</p>')
epub('bfc-percent',image('picture','left',80)+table(style='width:40%;padding:5%;border:2px solid blue')+'<p>'+text(20)+'</p>')
epub('bfc-percent-wide',image('picture','left',80)+table(style='width:50%;padding:5%;border:2px solid blue')+'<p>'+text(20)+'</p>')
epub('bfc-auto-margin',image('picture','left',80)+table(style='width:80px;margin:0 auto')+'<p>'+text(20)+'</p>')
epub('bfc-clear',image('picture','left',80)+table(style='width:100px;clear:both')+'<p>'+text(20)+'</p>')
epub('bfc-later-short',image('first','left',80)+image('second','left',150)+table()+'<p>'+text(20)+'</p>')
epub('bfc-later-long',image('first','left',80)+image('second','left',150)+table(20)+'<p>'+text(20)+'</p>')
epub('bfc-later-auto',image('first','left',80)+image('second','left',150)+table(20,style='',cell='AAAA AAAA AAAA AAAA')+'<p>'+text(20)+'</p>')
epub('bfc-stream',side()+table(250)+'<p>'+text(100)+'</p>')
epub('bfc-stream-wide',side()+table(250,'width:160px')+'<p>'+text(100)+'</p>')
epub('bfc-margins',image('picture','left',80)+table(250,'width:80px;padding:3px;border:2px solid blue;margin:5px 7px 9px 11px')+'<p>'+text(20)+'</p>')
epub('bfc-collapse',image('picture','left',80)+table(250,'width:100px;border-collapse:collapse;border:4px solid blue')+'<p>'+text(20)+'</p>','td {border:2px solid red}')
epub('bfc-vertical',image('picture','left',80)+table(250,'width:80px;height:100px')+'<p>'+text(20)+'</p>','html {writing-mode:vertical-rl} img {width:auto !important;height:60px}')
epub('bfc-orthogonal','<p>'+('A<br/>'*7)+'</p>'+image('picture','left',80)+table(250,cell='<div style="writing-mode:vertical-rl">A A A A</div>')+'<p>'+text(20)+'</p>')
epub('bfc-cell','<table style="width:200px;table-layout:fixed"><tr><td>'+image('picture','left',40)+table(1,'width:40px')+'</td><td>A</td></tr></table>')
epub('bfc-unbreakable',image('picture','left',80)+table(1,cell='<p>'+('A '*1000)+'</p>'))
epub('bfc-auto-defer','<div style="float:left;width:80px;height:150px;background:blue">A</div><div style="float:left;width:150px;height:40px;background:blue">A</div>'+table(1,style='',cell='AAAA '*26)+'<p>'+text(20)+'</p>')
epub('bfc-percent-height',side('','height:180px')+'<p>'+('A<br/>'*7)+'</p>'+table(3,'width:100px;height:250%'))
epub('bfc-stream-clear',side()+table(250,'width:100px;clear:left')+'<p>'+text(100)+'</p>')
print(count,'float fixtures generated')


