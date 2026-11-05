# SPDX-License-Identifier: MIT
# Writes the Studio UI probes into DIR: probe.epub (an author, two pictures on
# its first page, three chapters of text and a table of contents) and probe.pdf
# (three pages of solid shapes, no fonts needed). The first picture is opaque
# red; the second is a transparent frame 40 px wide around an opaque green
# center. The contents list the three chapters plus a nested entry pointing at
# a fragment in the middle of chapter two. long-title.epub has a title far
# wider than a shelf card or the reader's top bar.
import os
import struct
import sys
import zipfile
import zlib


def png(width, height, rgba):
    """RGBA PNG; rgba(x, y) gives each pixel."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\0" + b"".join(bytes(rgba(x, y)) for x in range(width)) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def framed(x, y):
    inside = 40 <= x < 200 and 40 <= y < 120
    return (0, 160, 0, 255) if inside else (0, 0, 0, 0)


def epub(path):
    words = "the quiet reader turns another page while the lamp hums over an old wooden desk".split()

    def paragraphs(first, count):
        return "".join("<p>%d. %s</p>" % (i + 1, " ".join(words[(i + j) % len(words)] for j in range(90)))
                       for i in range(first, first + count))

    def page(title, body):
        return ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head><body>%s</body></html>'
                % (title, body))

    text = page("Studio Probe", '<h1>Studio Probe</h1><p><img src="red.png" alt="red"/></p>'
                '<p><img src="framed.png" alt="framed"/></p>' + paragraphs(0, 40))
    two = page("Chapter Two", "<h1>Chapter Two</h1>" + paragraphs(40, 20) + '<h2 id="two-b">Part B</h2>' +
               paragraphs(60, 20))
    three = page("Chapter Three", "<h1>Chapter Three</h1>" + paragraphs(80, 20))
    nav = ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head>'
           '<title>Contents</title></head><body><nav epub:type="toc"><ol>'
           '<li><a href="text.xhtml">Studio Probe</a></li>'
           '<li><a href="two.xhtml">Chapter Two</a><ol><li><a href="two.xhtml#two-b">Part B</a></li></ol></li>'
           '<li><a href="three.xhtml">Chapter Three</a></li></ol></nav></body></html>')
    opf = ('<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">studio-probe</dc:identifier>'
           '<dc:title>Studio Probe</dc:title><dc:creator>Probe Author</dc:creator><dc:language>en</dc:language>'
           '</metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
           '<item id="text" href="text.xhtml" media-type="application/xhtml+xml"/>'
           '<item id="two" href="two.xhtml" media-type="application/xhtml+xml"/>'
           '<item id="three" href="three.xhtml" media-type="application/xhtml+xml"/>'
           '<item id="red" href="red.png" media-type="image/png"/>'
           '<item id="framed" href="framed.png" media-type="image/png"/></manifest>'
           '<spine><itemref idref="text"/><itemref idref="two"/><itemref idref="three"/></spine></package>')
    container = ('<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                 '<rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        z.writestr("book.opf", opf, zipfile.ZIP_DEFLATED)
        z.writestr("nav.xhtml", nav, zipfile.ZIP_DEFLATED)
        z.writestr("text.xhtml", text, zipfile.ZIP_DEFLATED)
        z.writestr("two.xhtml", two, zipfile.ZIP_DEFLATED)
        z.writestr("three.xhtml", three, zipfile.ZIP_DEFLATED)
        z.writestr("red.png", png(240, 160, lambda x, y: (255, 0, 0, 255)), zipfile.ZIP_DEFLATED)
        z.writestr("framed.png", png(240, 160, framed), zipfile.ZIP_DEFLATED)


def long_title(path):
    title = "一本书名特别特别长的测试书籍，用来检查书架卡片和阅读顶栏在空间不够时是否以省略号收尾而不是把字切掉"
    text = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body><h1>%s</h1>'
            '<p>正文。</p></body></html>' % title)
    opf = ('<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">studio-long</dc:identifier>'
           '<dc:title>%s</dc:title><dc:language>zh</dc:language></metadata>'
           '<manifest><item id="text" href="text.xhtml" media-type="application/xhtml+xml"/></manifest>'
           '<spine><itemref idref="text"/></spine></package>' % title)
    container = ('<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                 '<rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        z.writestr("book.opf", opf.encode("utf-8"), zipfile.ZIP_DEFLATED)
        z.writestr("text.xhtml", text.encode("utf-8"), zipfile.ZIP_DEFLATED)


def pdf(path, pages=3):
    objects = ["<< /Type /Catalog /Pages 2 0 R >>",
               "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % (3 + i) for i in range(pages)), pages)]
    for i in range(pages):
        objects.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 595] /Contents %d 0 R >>" % (3 + pages + i))
    for i in range(pages):
        shapes = "".join("0.2 0.35 0.75 rg %d %d 90 90 re f\n" % (40 + 120 * (k % 3), 440 - 120 * (k // 3))
                         for k in range(i + 1))
        objects.append("<< /Length %d >>\nstream\n%sendstream" % (len(shapes), shapes))
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body.encode("ascii"))
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    with open(path, "wb") as f:
        f.write(out)


if __name__ == "__main__":
    os.makedirs(sys.argv[1], exist_ok=True)
    epub(os.path.join(sys.argv[1], "probe.epub"))
    pdf(os.path.join(sys.argv[1], "probe.pdf"))
    long_title(os.path.join(sys.argv[1], "long-title.epub"))
