#!/usr/bin/env python3
"""Original library cover-import fixtures, including bounded large covers."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import base64,xml.etree.ElementTree as ET,zipfile
root=Path(__file__).resolve().parent/'fixtures'
png=base64.b64decode(next(n.text for n in ET.parse(root/'rich.fb2').getroot().iter() if n.tag.endswith('binary')))
for name,image,properties in [('cover-import.epub',png,'  cover-image  '),('cover-import-boundary.epub',png+bytes(8*1024*1024-len(png)),'cover-image'),('cover-import-large.epub',png+bytes(8*1024*1024),'cover-image'),('cover-import-missing.epub',None,'cover-image'),('cover-import-no-flag.epub',png,'cover-image-preview')]:
    with zipfile.ZipFile(root/name,'w',compression=zipfile.ZIP_DEFLATED) as z:
        def put(name,data,store=False):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0)); info.create_system=3; info.external_attr=0o100644<<16
            info.compress_type=zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
            z.writestr(info,data)
        put('mimetype','application/epub+zip',True)
        put('META-INF/container.xml','<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        put('book.opf','<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Cover import</dc:title></metadata><manifest><item id="text" href="text.xhtml" media-type="application/xhtml+xml"/><item id="cover" href="cover.png" media-type="image/png" properties="'+properties+'"/></manifest><spine><itemref idref="text"/></spine></package>')
        put('text.xhtml','<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Cover import</title></head><body><p>Retained original book.</p></body></html>')
        if image is not None: put('cover.png',image)
