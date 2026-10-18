"""Original EPUB table-width cases; reproducible standard-library ZIPs."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED
import struct
import zlib

root = Path(__file__).resolve().parents[1]/'tests/fixtures'
def epub(name, body, css, image=None):
    files = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'book.opf': b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">EXReader-table-columns</dc:identifier><dc:title>Original column fixture</dc:title><dc:language>en</dc:language><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata><manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="s" href="style.css" media-type="text/css"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="c"/></spine></package>',
        'nav.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><h1>Contents</h1><ol><li><a href="chapter.xhtml">Columns</a></li></ol></nav></body></html>',
        'chapter.xhtml': ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Columns</title><link rel="stylesheet" href="style.css"/></head><body>'+body+'</body></html>').encode(),
        'style.css': ('html,body,table,tr,td {margin:0;padding:0;border:0} td {font-size:14px;line-height:1.2} '+css).encode(),
    }
    if image is not None:
        files['image.png']=image
        files['book.opf']=files['book.opf'].replace(b'</manifest>',b'<item id="image" href="image.png" media-type="image/png"/></manifest>')
    with ZipFile(root/(name+'.epub'),'w') as z:
        for path,data in files.items():
            info = ZipInfo(path, (2026,1,1,0,0,0))
            info.compress_type = ZIP_STORED if path=='mimetype' else ZIP_DEFLATED
            z.writestr(info,data)

epub('table-columns', '<table><colgroup style="width:20%"><col/></colgroup><col width="100"/><col/>'
     '<tr><td id="a" rowspan="2">A</td><td id="b">B</td><td id="c">C</td></tr>'
     '<tr><td id="span" colspan="2" style="width:300px">A B</td></tr>'+
     ''.join(f'<tr><td id="a{i}">A</td><td>B</td><td>C</td></tr>' for i in range(100))+'</table>', 'table {width:400px}')
epub('table-cell-widths', '<table><tr><td id="a" style="width:25%">A A A A A A</td><td id="b" style="width:75%">B</td></tr></table>', 'table {width:200px}')
epub('table-span-widths', '<table width="300"><tr><td id="span" colspan="2" width="60%">A</td><td id="c">C</td></tr><tr><td id="a">A</td><td id="b">B</td><td>C</td></tr></table>', '')
epub('table-group-widths', '<table width="300"><colgroup span="2" width="20%"/><col/>'
     '<tr><td id="a">A</td><td id="b">B</td><td id="c">C</td></tr></table>', '')
epub('table-column-overflow', '<table><col span="65"/><tr><td>A</td></tr></table>', '')
epub('table-overconstrained', '<table><tr><td id="a" style="width:900px">A</td><td id="b" style="width:300px">B</td></tr></table>', 'table {width:240px}')
epub('table-vertical-columns', '<table><col style="height:20%"/><col style="height:90px"/><col/>'
     '<tr><td id="a">A</td><td id="b">B</td><td id="c">C</td></tr></table>', 'html {writing-mode:vertical-rl} table {height:300px}')
epub('table-tiny-column', '<table><tr><td id="a" style="width:.01px">A</td><td id="b" style="width:10000px">B</td></tr></table>', 'table {width:100px}')
epub('table-max-columns', '<table><col span="64"/><tr><td id="a" colspan="63">A</td><td id="b">B</td></tr></table>', 'table {width:64px}')
epub('table-column-padding', '<table><tr><td id="a" style="width:10%;padding:2px;border:1px solid black">A</td><td id="b">B</td></tr></table>', 'table {width:200px}')
epub('table-auto-content', '<table id="table"><tr><td id="a">A</td><td id="b">AAA</td></tr></table>', '')
epub('table-auto-range', '<table id="table"><tr><td id="a">A</td><td id="b">A A A</td></tr></table>', 'table {width:28px}')
epub('table-auto-extra', '<table id="table"><tr><td id="a">A</td><td id="b">A A A</td></tr></table>', 'table {width:70px}')
epub('table-auto-centered', '<table id="table"><tr><td id="a">A</td><td id="b">AAA</td></tr></table>', 'table {margin-left:auto;margin-right:auto}')
epub('table-auto-later-row', '<table id="table"><tr><td id="a">A</td><td id="b">A</td></tr><tr><td>AAAAAA</td><td>A</td></tr></table>', '')
epub('table-fixed-later-row', '<table id="table"><tr><td id="a">A</td><td id="b">A</td></tr><tr><td>AAAAAA</td><td>A</td></tr></table>', 'table {width:70px;table-layout:fixed}')
epub('table-auto-span', '<table id="table"><tr><td colspan="2">A A A A</td><td>AAA</td></tr><tr><td id="a">A</td><td id="b">A</td><td id="c">AAA</td></tr></table>', '')
epub('table-auto-soft', '<table id="table"><tr><td id="a">AA\u00adAAA</td><td id="b">A</td></tr></table>', 'table {width:28px}')
epub('table-auto-nested', '<table id="table"><tr><td id="a"><table><tr><td>A</td><td>AAA</td></tr></table></td><td id="b">A</td></tr></table>', '')
epub('table-auto-script', '<table id="table"><tr><td id="a">\u0644\u0627</td><td id="b">AAA</td></tr></table>', '')
epub('table-auto-grapheme', '<table id="table"><tr><td id="a">a\u0301</td><td id="b">AAA</td></tr></table>', '')
epub('table-auto-cjk', '<table id="table"><tr><td id="a">\u7532\u4e59\u7532</td><td id="b">A</td></tr></table>', 'table {width:32px}')
epub('table-auto-streaming', '<table id="table"><tr><td id="a">'+('A '*8192).rstrip()+'</td><td id="b">AAA</td></tr></table>', '')
epub('table-auto-multi-block', '<table id="table"><tr><td id="a"><p>A A</p><p>AAA</p></td><td id="b">A</td></tr></table>', 'p {margin:0}')
def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',80,20,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x00\x80\xff\xff'*80)*20))+chunk(b'IEND',b'')
epub('table-auto-image', '<table id="table"><tr><td id="a"><img src="image.png" style="width:50%" alt="Original blue rectangle"/></td><td id="b">A</td></tr></table>', '', png)
epub('table-auto-fixed-image', '<table id="table"><tr><td id="a"><img src="image.png" style="width:40px" alt="Original blue rectangle"/></td><td id="b">A</td></tr></table>', '', png)
epub('table-auto-fixed-block', '<table id="table"><tr><td id="a"><div style="width:40px">A</div></td><td id="b">A</td></tr></table>', '')
epub('table-auto-percent-block', '<table id="table"><tr><td id="a"><div style="width:50%">AAA</div></td><td id="b">A</td></tr></table>', '')
epub('table-auto-mixed-size', '<table id="table"><tr><td id="a">A<span style="font-size:28px">A</span></td><td id="b">A</td></tr></table>', '')
epub('table-auto-insets', '<table id="table"><tr><td id="a" style="padding:3px;border:3px solid black">A</td><td id="b">A</td></tr></table>', '')
epub('table-auto-break', '<table id="table"><tr><td id="a">A<br/>AAA</td><td id="b">A</td></tr></table>', '')
epub('table-auto-pages', '<table id="table">'+''.join('<tr><td id="r'+str(i)+'">'+('A'*(i%5+1))+'</td><td>A</td></tr>' for i in range(100))+'</table>', '')
epub('table-auto-vertical', '<table id="table"><tr><td id="a">A</td><td id="b">AAA</td></tr></table>', 'html {writing-mode:vertical-rl} td {text-orientation:sideways}')
aligned='<table><tr><td id="top">AA</td><td id="middle"><div id="panel" style="background:#ffe080">A<img id="image" src="image.png" alt="Original blue rectangle"/></div></td><td id="bottom">AAA</td><td id="tall" style="height:100px">A</td></tr></table>'
aligncss='table {width:400px;table-layout:fixed} td {vertical-align:top;padding:3px;border:1px solid black;background:#e0e0e0} #middle {vertical-align:middle} #bottom {vertical-align:bottom}'
epub('table-align-modes',aligned,aligncss,png)
epub('table-align-control',aligned,aligncss+' #middle,#bottom {vertical-align:top}',png)
epub('table-align-baseline','<table><tr><td id="small">A</td><td id="big" style="font-size:28px">A</td><td id="picture"><img id="image" src="image.png" alt="Blue"/></td></tr></table>','table {width:300px} td {padding:2px;vertical-align:baseline}',png)
epub('table-align-rowspan','<table><tr><td id="span" rowspan="2">A</td><td id="big" style="font-size:28px">A</td></tr><tr><td id="lower">A</td></tr></table>','table {width:200px} td {padding:2px;vertical-align:baseline}')
epub('table-align-empty','<table><tr><td id="empty" style="height:100px;background:blue"></td><td id="text">A</td></tr></table>','table {width:200px}')
inherit='<table><tbody valign="BOTTOM"><tr><td id="small">A</td><td id="big" style="font-size:28px">A</td></tr></tbody></table>'
epub('table-align-inherit',inherit,'table {width:200px} td {padding:2px}')
epub('table-align-override',inherit,'table {width:200px} td {padding:2px} #small {vertical-align:top;vertical-align:auto}')
epub('table-align-vertical','<table><tr style="width:100px"><td id="top">A</td><td id="middle">A</td><td id="bottom">A</td><td>A</td></tr></table>','html {writing-mode:vertical-rl} table {height:120px;table-layout:fixed} td {text-orientation:upright;vertical-align:top} #middle {vertical-align:middle} #bottom {vertical-align:bottom}')
epub('table-align-vertical-baseline','<table><tr style="width:100px"><td id="small">A</td><td id="big" style="font-size:28px">A</td></tr></table>','html {writing-mode:vertical-rl} table {height:120px} td {text-orientation:upright;vertical-align:baseline}')
epub('table-align-nested','<table><tr><td id="nested"><table><tr><td style="font-size:28px">A</td></tr></table></td><td id="peer">A</td></tr></table>','td {padding:2px;vertical-align:baseline}')
epub('table-align-pages','<table>'+''.join('<tr><td id="r'+str(i)+'" style="vertical-align:'+['top','middle','bottom','baseline'][i%4]+'">A</td><td style="font-size:28px">AAA</td></tr>' for i in range(80))+'</table>','table {width:200px} td {padding:2px;background:#e0e0e0}')
epub('table-align-height','<table>'+''.join('<tr><td id="r'+str(i)+'" style="height:50%;vertical-align:middle">A</td><td>A</td></tr>' for i in range(4))+'</table>','table {height:100px;width:200px} td {vertical-align:top}')
epub('table-align-ruby','<table><tr><td id="ruby"><ruby><span id="base">A</span><rt id="annotation">A</rt></ruby></td><td id="peer">A</td></tr></table>','table {width:200px} td {vertical-align:baseline}')
epub('table-align-vertical-lr','<table><tr style="width:100px"><td id="top">A</td><td id="middle">A</td><td id="bottom">A</td><td>A</td></tr></table>','html {writing-mode:vertical-lr} table {height:120px;table-layout:fixed} td {text-orientation:upright;vertical-align:top} #middle {vertical-align:middle} #bottom {vertical-align:bottom}')
epub('table-align-opposite-directions','<table><tr style="width:100px"><td id="small" style="writing-mode:vertical-lr">A</td><td id="big" style="font-size:28px">A</td></tr></table>','html {writing-mode:vertical-rl} table {height:120px} td {text-orientation:sideways;vertical-align:baseline}')
epub('table-align-nested-fallback','<table><tr><td><table><tr><td id="inner" style="vertical-align:bottom;height:60px">A</td></tr></table></td><td id="peer">A</td></tr></table>','td {padding:2px;vertical-align:baseline}')
epub('table-align-baseline-values','<table><tr><td id="small" style="vertical-align:middle;vertical-align:sub">A</td><td id="big" style="font-size:28px">A</td><td id="length" style="vertical-align:middle;vertical-align:-5px">A</td></tr></table>','table {width:300px} td {vertical-align:baseline}')
epub('table-column-float-floor','<table><tr><td colspan="2" style="width:117px">AA</td><td colspan="2" style="width:.01px">AA</td><td style="width:200px">A</td></tr><tr><td>A</td><td>A</td><td>A</td><td>A</td><td>A</td></tr></table>','table {width:175px;table-layout:fixed}')
# Collapsed-border cases share the same deterministic package generator.
body='<table id="table"><tr><td id="a">A</td><td id="b">A</td></tr><tr><td id="c">A</td><td id="d">A</td></tr></table>'
bordercss='table {width:200px;table-layout:fixed;border-collapse:collapse} td {height:40px;vertical-align:top;border:2px solid blue;background:white}'
epub('table-border-basic',body,bordercss)
epub('table-border-inapplicable',body,bordercss+' table {padding:20px} td {margin:10px}')
epub('table-border-separate',body,bordercss+' table {border-collapse:separate}')
epub('table-border-mixed',body,bordercss+' #a,#c {border:4px solid red}')
epub('table-border-alpha',body,bordercss+' td {border-color:#00000080}')
epub('table-border-hidden',body,bordercss+' #a {border:100px hidden red}')
epub('table-border-none',body,bordercss+' #a {border:100px none red}')
epub('table-border-inherit',body,'body {border-collapse:collapse} '+bordercss.replace('border-collapse:collapse','border-collapse:inherit'))
epub('table-border-vertical',body,bordercss+' html {writing-mode:vertical-rl} table {width:auto;height:200px} td {width:40px;height:auto;text-orientation:upright}')
epub('table-border-vertical-lr',body,bordercss+' html {writing-mode:vertical-lr} table {width:auto;height:200px} td {width:40px;height:auto;text-orientation:upright}')
epub('table-border-opposite',body,bordercss+' html {writing-mode:vertical-rl} table {width:auto;height:200px} td {width:40px;height:auto;text-orientation:upright} #a {writing-mode:vertical-lr;margin:10px} #b {border:8px solid blue} #c {border:6px solid red}')
epub('table-border-tie',body,bordercss+' #a {border-color:red} #b {border-color:green} #c {border-color:blue} #d {border-color:black}')
epub('table-border-rtl',body,bordercss+' table {direction:rtl} #a {border-color:red} #b {border-color:green} #c {border-color:blue} #d {border-color:black}')
spanbody='<table id="table"><tr><td id="a" rowspan="2">A</td><td id="b" colspan="2">A</td></tr><tr><td id="c">A</td><td id="d">A</td></tr><tr><td id="e" colspan="3">A</td></tr></table>'
epub('table-border-spans',spanbody,bordercss+' tr {border:2px solid red}')
groupbody='<table id="table"><colgroup style="border:6px solid red"><col span="2" style="border:4px solid green"/></colgroup><tbody style="border:6px solid blue"><tr style="border:6px solid black"><td id="a">A</td><td id="b">A</td></tr><tr><td id="c">A</td><td id="d">A</td></tr></tbody></table>'
epub('table-border-groups',groupbody,bordercss+' td {border:2px solid #ff00ff}')
epub('table-border-origin',groupbody,bordercss+' td {border:6px solid #ff00ff}')
epub('table-border-wide-table',groupbody,bordercss+' table {border:8px solid #808000}')
epub('table-border-nested','<table id="table"><tr><td id="a"><table id="inner"><tr><td id="innercell">A</td></tr></table></td><td id="b">A</td></tr></table>',bordercss+' #inner {width:auto} td {height:auto}')
epub('table-border-nested-separate','<table id="table"><tr><td id="a"><table id="inner"><tr><td id="innercell">A</td></tr></table></td><td id="b">A</td></tr></table>',bordercss+' #inner {width:auto;border-collapse:separate} td {height:auto}')
epub('table-border-columns','<table id="table"><col span="3" style="border:2px solid blue"/><tr><td id="a">A</td><td id="b">A</td></tr></table>',bordercss+' td {border:0}')
epub('table-border-pages','<table id="table">'+''.join('<tr><td id="r'+str(i)+'" style="border:'+str(2+2*(i%3))+'px solid #00000080">A</td><td>A</td></tr>' for i in range(60))+'</table>',bordercss+' td {height:24px}')
print('72 EPUB table fixtures generated')
