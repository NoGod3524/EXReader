"""Original EPUB table-width cases; reproducible standard-library ZIPs."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED

root = Path(__file__).resolve().parents[1]/'tests/fixtures'
def epub(name, body, css):
    files = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'book.opf': b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">EXReader-table-columns</dc:identifier><dc:title>Original column fixture</dc:title><dc:language>en</dc:language><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata><manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="s" href="style.css" media-type="text/css"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="c"/></spine></package>',
        'nav.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><h1>Contents</h1><ol><li><a href="chapter.xhtml">Columns</a></li></ol></nav></body></html>',
        'chapter.xhtml': ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Columns</title><link rel="stylesheet" href="style.css"/></head><body>'+body+'</body></html>').encode(),
        'style.css': ('html,body,table,tr,td {margin:0;padding:0;border:0} td {font-size:14px;line-height:1.2} '+css).encode(),
    }
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
print('10 EPUB column fixtures generated')
