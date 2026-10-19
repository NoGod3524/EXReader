#!/usr/bin/env python3
"""Deterministic EPUB using only the repository's original geometric fonts."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent / "fixtures"
files = {
    "mimetype": "application/epub+zip",
    "META-INF/container.xml": '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
    "OPS/book.opf": '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Original font book</dc:title></metadata><manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/><item id="b" href="b.xhtml" media-type="application/xhtml+xml"/><item id="css" href="Styles/main.css" media-type="text/css"/><item id="font" href="Fonts/书体.ttf" media-type="font/ttf"/><item id="regular" href="Fonts/regular.ttf" media-type="font/ttf"/><item id="bad" href="Fonts/bad.ttf" media-type="font/ttf"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>',
    "OPS/a.xhtml": '<html xmlns="http://www.w3.org/1999/xhtml"><head><link rel="stylesheet" href="Styles/main.css"/></head><body><p class="book">A</p><p class="book" style="font-weight:bold">A</p><p class="book" style="font-style:italic">A</p><table class="book"><tr><td>A</td></tr></table></body></html>',
    "OPS/b.xhtml": '<html xmlns="http://www.w3.org/1999/xhtml"><head><style>@font-face { font-family: "Book Face"; src:url(Fonts/regular.ttf); } p {font-family:"Book Face"}</style></head><body><p>A</p></body></html>',
    "OPS/Styles/main.css": '''
/* Names/URLs exercise CSS strings, escapes, URL fallback and Unicode paths. */
@font-face {font-family:"Unused";src:url(../Fonts/bad.ttf)}
@font-face {font-family:"Book Face";src:local("No system scan"),url(../Fonts/bad.ttf),url("../Fonts/%E4%B9%A6%E4%BD%93.ttf") format("truetype")}
@font-face {font-family:Book Face;font-weight:700;src:url(../Fonts/regular.ttf)}
@font-face {font-family:"Book Face";font-style:italic;src:url("../Fonts/书体.ttf")}
.book {font-family:"Missing", "Book Face", serif; margin:0}
''',
    "OPS/Fonts/bad.ttf": b"not a font",
    "OPS/Fonts/书体.ttf": (root / "fonts/fallback.ttf").read_bytes(),
    "OPS/Fonts/regular.ttf": (root / "fonts/primary.ttf").read_bytes(),
}
with zipfile.ZipFile(root / "font-book.epub", "w") as archive:
    for name, value in files.items():
        entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_STORED
        entry.external_attr = 0o100644 << 16
        archive.writestr(entry, value.encode("utf-8") if isinstance(value, str) else value)
