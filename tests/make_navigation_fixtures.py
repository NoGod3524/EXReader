#!/usr/bin/env python3
"""Original, deterministic EPUB 2/3 navigation fixtures."""
# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent / "fixtures"
ncx = '''<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<navMap><navPoint id="a"><navLabel><text> First &amp; chapter </text></navLabel><content src="../Text/a.xhtml#start"/>
<navPoint id="b"><navLabel><text>子节</text></navLabel><content src="../Text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml#intro"/></navPoint></navPoint>
<navPoint id="group"><navLabel><text>Group</text></navLabel><navPoint id="again"><navLabel><text>Again</text></navLabel><content src="../Text/a.xhtml#again"/></navPoint></navPoint></navMap>
<pageList><pageTarget><navLabel><text>1</text></navLabel><content src="../Text/a.xhtml#p1"/></pageTarget></pageList>
<navList><navTarget><navLabel><text>Illustration</text></navLabel><content src="../Text/第二章.xhtml#fig"/></navTarget></navList></ncx>'''
nav = '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol><li><a href="../Text/a.xhtml#start"> First <em>&amp;</em> chapter </a>
<ol><li><a href="../Text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml#intro">子节</a></li></ol></li>
<li><span>Group</span><ol><li><a href="https://example.test/">Outside</a></li></ol>
<nav epub:type="page-list"><ol><li><a href="../Text/a.xhtml#p1">1</a></li></ol></nav></li></ol></nav>
<nav epub:type="landmarks"><ol><li><a href="../Text/a.xhtml">Begin</a></li></ol></nav></body></html>'''

def make(name, version=2, navigation=None, duplicate=False, missing=False, empty=False):
    entries = {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
        "OPS/Text/a.xhtml": '<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="start">A</p></body></html>',
        "OPS/Text/第二章.xhtml": '<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="intro">B</p></body></html>',
    }
    manifest = '<item id="a" href="Text/a.xhtml" media-type="application/xhtml+xml"/><item id="b" href="Text/第二章.xhtml" media-type="application/xhtml+xml"/>'
    if not empty:
        manifest += '<item id="wrong" href="Nav/wrong.ncx" media-type="application/x-dtbncx+xml"/><item id="chosen" href="Nav/main.ncx" media-type="application/x-dtbncx+xml"/>'
        entries["OPS/Nav/main.ncx"] = ncx
        entries["OPS/Nav/wrong.ncx"] = ncx.replace("First &amp; chapter", "WRONG FILE")
    if navigation is not None:
        manifest += '<item id="nav" href="Nav/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        entries["OPS/Nav/nav.xhtml"] = navigation
    spine = '<itemref idref="a"/>' + ('<itemref idref="a"/>' if duplicate else '') + '<itemref idref="b"/>'
    toc = '' if empty else f' toc="{"missing" if missing else "chosen"}"'
    entries["OPS/book.opf"] = f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Navigation fixture</dc:title></metadata><manifest>{manifest}</manifest><spine{toc}>{spine}</spine></package>'
    with zipfile.ZipFile(root / name, "w") as archive:
        for path, text in entries.items():
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, text.encode("utf-8"))

make("navigation-epub2.epub")
make("navigation-epub3.epub", 3, nav)
make("navigation-repeated.epub", 3, nav, duplicate=True)
make("navigation-broken.epub", 3, '<html><nav><ol><li>Unclosed')
make("navigation-entity.epub", 3, '<!DOCTYPE html [<!ENTITY x "blocked">]><html><nav><ol><li><a href="../Text/a.xhtml">&x;</a></li></ol></nav></html>')
make("navigation-missing.epub", missing=True)
make("navigation-empty.epub", empty=True)
