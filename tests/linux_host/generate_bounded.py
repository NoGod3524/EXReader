"""Independent, small Linux host routing fixtures. Run in Actions only."""
# SPDX-License-Identifier: MIT
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=False)
for name, missing in (("routes.epub", False), ("missing.epub", True)):
    with zipfile.ZipFile(root / name, "w", compression=zipfile.ZIP_DEFLATED) as book:
        book.writestr("mimetype", "application/epub+zip")
        book.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
        book.writestr("book.opf", '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Linux route fixture</dc:title></metadata><manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/><item id="b" href="b.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/><itemref idref="a"/></spine></package>')
        for chapter in range(2):
            if missing and chapter == 1:
                continue
            paragraphs = "".join(f"<p>Chapter{chapter} position{position:04d}. Read stable native pages.</p>" for position in range(70))
            book.writestr("ab"[chapter] + ".xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body>' + paragraphs + '</body></html>')
