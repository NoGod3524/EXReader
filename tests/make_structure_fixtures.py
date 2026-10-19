# SPDX-License-Identifier: MIT
"""Reproducible, original EPUB fixtures for the native document model tests."""
from pathlib import Path
import struct
import zipfile
import zlib

DEST = Path(__file__).parent / "fixtures"
NS = 'xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"'


def xhtml(body, head=""):
    return f'<html {NS}><head><title>Chapter</title>{head}</head><body>{body}</body></html>'


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(b"\0\x80\x40\x20")) + chunk(b"IEND", b""))
container = '<container><rootfiles><rootfile full-path="OPS%20Book/package.opf"/></rootfiles></container>'
manifest = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<metadata><title xmlns="http://purl.org/dc/elements/1.1/">Structured EPUB</title></metadata>
<manifest>
<item id="first" href="text/100%25-first.xhtml" media-type="application/xhtml+xml"/>
<item id="second" href="text/%E7%AC%AC%E4%BA%8C%E7%AB%A0.xhtml" media-type="application/xhtml+xml"/>
<item id="notes" href="notes.xhtml" media-type="application/xhtml+xml"/>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="css" href="styles/main.css" media-type="text/css"/>
<item id="picture" href="images/pic.png" media-type="image/png" properties="cover-image"/>
<item id="missing" href="missing.png" media-type="image/png"/>
<item id="large" href="large.bin" media-type="application/octet-stream"/>
</manifest><spine><itemref idref="second"/><itemref idref="first"/><itemref idref="notes" linear="no"/></spine>
</package>'''
members = {
    "mimetype": "application/epub+zip",
    "META-INF/container.xml": container,
    "OPS Book/package.opf": manifest,
    "OPS Book/text/100%-first.xhtml": xhtml('<h1 id="anchor one">First in manifest</h1><p>Final paragraph.</p>'),
    "OPS Book/text/第二章.xhtml": xhtml('''
<section id="chapter"><h2>Second in manifest</h2>
<p id="local" class="body" style="text-indent: 2em">Alpha <strong>bold 中文</strong> &amp; tail.</p>
<ol start="3"><li id="item">Item one<ul><li>Nested item</li></ul></li><li>Item two</li></ol>
<p><a href="100%25-first.xhtml#anchor%20one">Next chapter</a> <a epub:type="noteref" href="../notes.xhtml#注释">[1]</a></p>
<figure><img src="../images/pic.png" alt="Small &amp; original" width="1" height="1"/><figcaption>Caption</figcaption></figure>
<table id="table"><thead><tr><th scope="col">Heading</th><th>Other</th></tr></thead>
<tbody><tr><td colspan="2">Cell content</td></tr></tbody></table>
<p hidden="hidden">SECRET_HIDDEN</p><script>SECRET_SCRIPT</script>
</section>''', '<link rel="stylesheet" href="../styles/main.css"/><style>.body { color: #123456; }</style>'),
    "OPS Book/notes.xhtml": xhtml('<aside epub:type="footnote" id="注释"><p>Auxiliary note.</p><a href="text/第二章.xhtml#local">Back</a></aside>'),
    "OPS Book/nav.xhtml": xhtml('<nav epub:type="toc"><ol><li><a href="text/第二章.xhtml#chapter">Chapter two</a><ol><li><a href="text/100%25-first.xhtml#anchor%20one">Chapter one</a></li></ol></li></ol></nav>'),
    "OPS Book/styles/main.css": ".body { font-size: 1.2em; }\n",
    "OPS Book/images/pic.png": png,
    "OPS Book/large.bin": b"x" * (33 * 1024 * 1024),
}


def write(name, entries):
    with zipfile.ZipFile(DEST / name, "w") as z:
        for path, data in entries.items():
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if path == "mimetype" else zipfile.ZIP_DEFLATED
            z.writestr(info, data.encode("utf-8") if isinstance(data, str) else data)


write("structure.epub", members)
small = {k: v for k, v in members.items() if k != "OPS Book/large.bin"}
write("structure-missing.epub", {k: v for k, v in small.items() if k != "OPS Book/text/100%-first.xhtml"})
write("structure-duplicate.epub", {**small, "OPS Book/package.opf": manifest.replace('id="picture"', 'id="css"')})
write("structure-entity.epub", {**small, "OPS Book/text/第二章.xhtml":
      '<!DOCTYPE html [<!ENTITY ext SYSTEM "file:///etc/passwd">]>' + xhtml("<p>&ext;</p>")})
write("structure-deep.epub", {**small, "OPS Book/text/第二章.xhtml": xhtml("<div>" * 257 + "text" + "</div>" * 257)})
write("structure-broken.epub", {**small, "OPS Book/text/第二章.xhtml": xhtml("<p>Broken</div>")})
write("structure-attrs.epub", {**small, "OPS Book/text/第二章.xhtml": xhtml(
      "<p " + " ".join(f'a{i}="v"' for i in range(257)) + ">Text</p>")})
write("structure-nodes.epub", {**small, "OPS Book/text/第二章.xhtml": xhtml("<i/>" * 262144)})
write("structure-image.epub", {**small, "OPS Book/package.opf": manifest.replace('<itemref idref="first"/>', ''),
      "OPS Book/text/第二章.xhtml": xhtml('<img src="../images/pic.png" alt="Original"/>')})
