"""Actions-only real EPUB image/background fixture and byte-pinned existing books."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import zipfile
import zlib

assert os.environ.get('GITHUB_ACTIONS') == 'true'
folder = Path(sys.argv[1])
shutil.copytree('build/android-reading/fixtures', folder)
def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',48,48,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes([20,120,220,255])*48)*48))+chunk(b'IEND',b'')
html = '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Theme EPUB</title></head><body><p>Theme foreground ink MMMMMMMMMMMMMMMMMMMMMMMMMMMMM.</p><div style="background-color:#e0b070; width:140px; height:64px;">A</div><p><img src="image.png" width="48" height="48"/></p>' + ''.join('<p>Theme chapter line %d with immutable selector and native page colors.</p>'%i for i in range(160)) + '</body></html>'
for name,title in [('search.epub','Theme EPUB'),('legacy.epub','Theme legacy EPUB')]:
    with zipfile.ZipFile(folder/name,'w') as package:
        package.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
        package.writestr('META-INF/container.xml','<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        package.writestr('book.opf','<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">theme-'+name+'</dc:identifier><dc:title>'+title+'</dc:title><dc:language>en</dc:language></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="image" href="image.png" media-type="image/png"/></manifest><spine><itemref idref="chapter"/></spine></package>')
        package.writestr('chapter.xhtml',html)
        package.writestr('image.png',png)
manifest=json.loads((folder/'manifest.json').read_text())
for row in manifest['books']:
    data=(folder/row['file']).read_bytes();row['bytes']=len(data);row['sha256']=hashlib.sha256(data).hexdigest()
    if row['role']=='epub':row['title']='Theme EPUB'
    if row['role']=='legacy':row['title']='Theme legacy EPUB'
manifest['theme']={'author_background':'e0b070ff','image_rgba':'1478dcff','image_bytes':len(png),'image_sha256':hashlib.sha256(png).hexdigest(),'light_foreground':'1a1a1aff','dark_foreground':'e6e6e6ff','dark_background':'101010ff'}
(folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
