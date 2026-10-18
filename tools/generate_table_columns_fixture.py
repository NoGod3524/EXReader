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
print('33 EPUB table fixtures generated')
