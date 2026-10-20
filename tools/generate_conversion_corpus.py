#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic WP12-lite conversion corpus generator.

All text is original, written for this test. The embedded font is the
EXReader MIT test font tests/fixtures/fonts/primary.ttf. MOBI/KF8 inputs are
copied from the repository's original fixtures; their hashes are recorded.
"""
import argparse
import base64
import hashlib
import json
import os
import struct
import sys
import zipfile
import zlib
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

THEMES = [
    ("ascii", "The Quiet Library", [
        "The reading room opened before sunrise.",
        "A single lamp lit the long oak table.",
        "Every shelf held a different century.",
    ]),
    ("chinese", "山间书舍", [
        "清晨的山谷里有一座小小的书舍。",
        "竹影落在纸页上，风从窗边经过。",
        "读者把书放回原处，记下了下一页。",
    ]),
    ("rtl", "مكتبة عربية", [
        "افتتحت المكتبة أبوابها في الصباح.",
        "גלגל הספרים נשען על הקיר הישן.",
        "הקורא סימן את הדף והמשיך הלאה.",
    ]),
    ("supplementary", "Plane Two", [
        "Emoji \U0001F600 and rare CJK \U00020000 stay visible.",
        "Mathematical bold \U0001D400 and music \U0001D11E follow.",
        "Latin, 中文, العربية, עברית and \U0001F4DA share a line.",
    ]),
    ("special", "Symbols & Signs", [
        "Ampersand & less < greater > quote \" apostrophe '.",
        "Backslash \\ braces { } and a literal entity &#38;.",
        "Tabs\tand markers [x] (y) {z} remain text.",
    ]),
    ("whitespace", "Whitespace Rules", [
        "One  space, then   three spaces.",
        "Leading and trailing spaces are meaningful input.   ",
        "A blank line follows this paragraph.",
        "",
        "The final paragraph has a tab\tinside.",
    ]),
    ("structure", "Chapter and Verse", [
        "Heading one introduces the section.",
        "A list follows: alpha, beta, gamma.",
        "Heading two closes the reading order.",
    ]),
    ("multichapter", "Three Chapters", [
        "Chapter one begins the journey.",
        "Chapter two crosses the river.",
        "Chapter three returns home.",
    ]),
    ("long", "Long Reading", [
        "This paragraph is repeated to exercise a longer body with stable words.",
        "段落二保持中文与 English 混排，用于检查长正文的顺序。",
        "The third paragraph adds punctuation: commas, periods; and colons.",
    ]),
    ("metadata", "Title & <Book> 书", [
        "Metadata escapes must survive <tags> & quotes.",
        "The identifier urn:exreader:wp12-lite is generated.",
        "Language und is reported rather than guessed.",
    ]),
]

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def png_rgba(width, height, rgba):
    raw = b"".join(b"\x00" + bytes(rgba[y * width:(y + 1) * width]) for y in range(height))
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) +
            chunk(b"IEND", b""))

def zip_write(path, members, mimetype_first=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        if mimetype_first:
            info = zipfile.ZipInfo("mimetype", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, b"application/epub+zip")
        for name, data in members:
            if isinstance(data, str):
                data = data.encode("utf-8")
            if mimetype_first and name == "mimetype":
                continue
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)

def text_document(theme):
    name, title, paragraphs = theme
    if name == "multichapter":
        chapters = [[paragraphs[0]], [paragraphs[1]], [paragraphs[2]]]
    else:
        chapters = [paragraphs]
    return title, chapters

def write_txt(path, theme):
    title, chapters = text_document(theme)
    blocks = [title]
    for chapter in chapters:
        for paragraph in chapter:
            if paragraph:
                blocks.append(paragraph)
        blocks.append("")
    path.write_text("\n\n".join(blocks).rstrip() + "\n", encoding="utf-8", newline="\n")

def write_html(path, theme):
    title, chapters = text_document(theme)
    body = []
    body.append("<h1>%s</h1>" % xml_escape(title))
    for index, chapter in enumerate(chapters):
        if len(chapters) > 1:
            body.append('<section id="ch%d"><h2>Chapter %d</h2>' % (index + 1, index + 1))
        for paragraph in chapter:
            if paragraph:
                body.append("<p>%s</p>" % xml_escape(paragraph))
        if len(chapters) > 1:
            body.append("</section>")
    document = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title>'
                '<style>body{font-family:serif} table{border-collapse:collapse}</style>'
                '</head><body>%s</body></html>' % (xml_escape(title), "".join(body)))
    path.write_text(document, encoding="utf-8", newline="\n")

def write_fb2(path, theme):
    title, chapters = text_document(theme)
    sections = []
    for index, chapter in enumerate(chapters):
        body = ['<section id="s%d"><title><p>%s %d</p></title>' %
                (index + 1, xml_escape("Section"), index + 1)]
        for paragraph in chapter:
            if paragraph:
                body.append("<p>%s</p>" % xml_escape(paragraph))
        body.append("</section>")
        sections.append("".join(body))
    document = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
                '<description><title-info><genre>prose</genre>'
                '<author><nickname>EXReader</nickname></author>'
                '<book-title>%s</book-title><lang>en</lang></title-info></description>'
                '<body>%s</body></FictionBook>' % (xml_escape(title), "".join(sections)))
    path.write_text(document, encoding="utf-8", newline="\n")

def write_docx(path, theme):
    title, chapters = text_document(theme)
    paragraphs = ['<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % xml_escape(title)]
    for index, chapter in enumerate(chapters):
        if len(chapters) > 1:
            paragraphs.append('<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t xml:space="preserve">Chapter %d</w:t></w:r></w:p>' % (index + 1))
        for paragraph in chapter:
            if paragraph:
                paragraphs.append('<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % xml_escape(paragraph))
    document = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body>%s<w:sectPr/></w:body></w:document>' % "".join(paragraphs))
    types = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    zip_write(path, [("[Content_Types].xml", types), ("_rels/.rels", rels),
                     ("word/document.xml", document)])

def rtf_escape(text):
    out = []
    for ch in text:
        cp = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif cp < 128:
            out.append(ch)
        elif cp <= 0xffff:
            out.append("\\u%d?" % (cp if cp < 32768 else cp - 65536))
        else:
            value = cp - 0x10000
            out.append("\\u%d?\\u%d?" % (0xd800 + (value >> 10) - 65536, 0xdc00 + (value & 1023) - 65536))
    return "".join(out)

def write_rtf(path, theme):
    title, chapters = text_document(theme)
    parts = ["{\\rtf1\\ansi\\ansicpg1252\\deff0{\\fonttbl{\\f0\\fnil\\fcharset0 Arial;}}",
             "\\b %s\\b0\\par\n" % rtf_escape(title)]
    for index, chapter in enumerate(chapters):
        if len(chapters) > 1:
            parts.append("\\b Chapter %d\\b0\\par\n" % (index + 1))
        for paragraph in chapter:
            if paragraph:
                parts.append(rtf_escape(paragraph) + "\\par\n")
    parts.append("}")
    path.write_text("".join(parts), encoding="ascii", newline="\n")

def epub_members(title, chapters, resources, css, extra_manifest="", extra_spine=""):
    chapter_files = []
    for index, paragraphs in enumerate(chapters):
        body = ['<h1 id="ch%d">%s</h1>' % (index + 1, xml_escape(title if index == 0 else "Chapter %d" % (index + 1)))]
        for pindex, paragraph in enumerate(paragraphs):
            body.append('<p id="p%d_%d">%s</p>' % (index + 1, pindex + 1, xml_escape(paragraph)))
        chapter_files.append(("OEBPS/ch%d.xhtml" % (index + 1),
            '<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>%s</title><link rel="stylesheet" type="text/css" href="styles/book.css"/></head><body>%s</body></html>' %
            (xml_escape(title), "".join(body))))
    nav_items = "".join('<li><a href="ch%d.xhtml">Chapter %d</a></li>' % (i + 1, i + 1) for i in range(len(chapters)))
    nav = ('<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body>'
           '<nav epub:type="toc"><ol>%s</ol></nav></body></html>' % nav_items)
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="css" href="styles/book.css" media-type="text/css"/>']
    for i in range(len(chapters)):
        manifest.append('<item id="ch%d" href="ch%d.xhtml" media-type="application/xhtml+xml"/>' % (i + 1, i + 1))
    for rid, path, media in resources:
        manifest.append('<item id="%s" href="%s" media-type="%s"/>' % (rid, path, media))
    spine = "".join('<itemref idref="ch%d"/>' % (i + 1) for i in range(len(chapters)))
    opf = ('<?xml version="1.0" encoding="UTF-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:exreader:wp12-lite:%s</dc:identifier>'
           '<dc:title>%s</dc:title><dc:language>en</dc:language>'
           '<meta property="dcterms:modified">2026-10-20T00:00:00Z</meta></metadata>'
           '<manifest>%s%s</manifest><spine>%s%s</spine></package>' %
           (hashlib.sha1(title.encode()).hexdigest()[:12], xml_escape(title), "".join(manifest),
            extra_manifest, spine, extra_spine))
    container = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    members = [("OEBPS/content.opf", opf), ("OEBPS/nav.xhtml", nav),
               ("META-INF/container.xml", container), ("OEBPS/styles/book.css", css)]
    members.extend(chapter_files)
    return members

def preserve_epub(index, theme, font_bytes, out):
    title, chapters = text_document(theme)
    if len(chapters) == 1:
        chapters = [chapters[0], ["Second chapter of %s." % title, "A repeated basename follows."],
                    ["Third chapter with a footnote.", "Closing paragraph."]]
    png_a = png_rgba(2, 2, [255, 0, 0, 255, 255, 255, 0, 255, 0, 0, 255, 255, 0, 255, 0, 255])
    png_b = png_rgba(2, 2, [0, 0, 255, 255, 0, 255, 255, 255, 255, 0, 255, 255, 255, 255, 0, 255])
    css = ('@font-face{font-family:"Primary";src:url("../fonts/primary.ttf");}'
           'body{font-family:"Primary",serif;line-height:1.3}'
           'table{border-collapse:collapse}td{border:1px solid #333;padding:1px}'
           '.rtl{direction:rtl}.note{font-size:80%}')
    chapters[0] = chapters[0][:]
    chapters[0].append("Table follows.")
    chapters[1] = chapters[1][:]
    resources = [
        ("img_a", "images/a/pic.png", "image/png", png_a),
        ("img_b", "images/b/pic.png", "image/png", png_b),
        ("font", "fonts/primary.ttf", "font/ttf", font_bytes),
    ]
    # Inject a table, images, footnote and an id target into the chapter XHTML.
    members = epub_members(title, chapters, [(a, b, c) for a, b, c, _ in resources], css)
    rewritten = []
    for name, data in members:
        if isinstance(data, str):
            data = data.encode("utf-8")
        if name == "OEBPS/ch1.xhtml":
            text = data.decode("utf-8")
            text = text.replace("</body>",
                '<p><a href="ch2.xhtml#sec2">next</a></p>'
                '<table><tr><td>Alpha</td><td>Beta</td></tr>'
                '<tr><td colspan="2">Gamma</td></tr></table>'
                '<p><img src="images/a/pic.png" alt="a"/>'
                '<img src="images/b/pic.png" alt="b"/></p></body>')
            data = text
        elif name == "OEBPS/ch2.xhtml":
            text = data.decode("utf-8")
            text = text.replace('<h1 id="ch2">', '<h1 id="ch2"><span id="sec2"></span>')
            text = text.replace("</body>",
                '<p class="rtl">نص عربي <span>עברית</span></p>'
                '<aside epub:type="footnote" id="fn1"><p>Note one.</p></aside></body>')
            data = text
        rewritten.append((name, data))
    for rid, path, media, payload in resources:
        rewritten.append(("OEBPS/" + path, payload))
    zip_write(out, rewritten, mimetype_first=True)

def preserve_xhtml(index, theme, png_b64):
    title, chapters = text_document(theme)
    paragraphs = []
    for chapter in chapters:
        for paragraph in chapter:
            if paragraph:
                paragraphs.append("<p>%s</p>" % xml_escape(paragraph))
    document = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title>'
                '<style>body{font-family:"Primary",serif}table{border-collapse:collapse}'
                'td{border:1px solid #333}.rtl{direction:rtl}</style></head><body>'
                '<h1 id="top">%s</h1>%s'
                '<p><a href="#sec2">jump</a> <a href="#top">top</a></p>'
                '<h2 id="sec2">Second section</h2>'
                '<table><tr><td>One</td><td>Two</td></tr><tr><td colspan="2">Three</td></tr></table>'
                '<p><img src="data:image/png;base64,%s" alt="inline"/></p>'
                '<p class="rtl">نص عربي <span>עברית</span></p>'
                '<aside id="fn1"><p>Inline footnote.</p></aside>'
                '</body></html>' % (xml_escape(title), xml_escape(title), "".join(paragraphs), png_b64))
    return document

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--fixtures", default=str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))
    args = parser.parse_args()
    out = Path(args.out)
    fixtures = Path(args.fixtures)
    font = (fixtures / "fonts" / "primary.ttf").read_bytes()
    corpus = []
    out.mkdir(parents=True, exist_ok=True)
    matrix = []
    formats = {
        "txt": (".txt", write_txt),
        "html": (".html", write_html),
        "fb2": (".fb2", write_fb2),
        "epub": (".epub", None),
        "docx": (".docx", write_docx),
        "rtf": (".rtf", write_rtf),
    }
    for fmt, (extension, writer) in formats.items():
        for index, theme in enumerate(THEMES):
            rel = Path("text") / fmt / (theme[0] + extension)
            path = out / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "epub":
                title, chapters = text_document(theme)
                zip_write(path, epub_members(title, chapters, [], "body{font-family:serif}"), mimetype_first=True)
            else:
                writer(path, theme)
            data = path.read_bytes()
            corpus.append({"kind": "text", "format": fmt, "theme": theme[0],
                           "path": rel.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data),
                           "features": ["heading", "multi_paragraph"] + (["multi_chapter"] if theme[0] == "multichapter" else [])})
            matrix.append("text|%s|%s|%s" % (fmt, theme[0], rel.as_posix()))
    png = png_rgba(2, 2, [10, 20, 30, 255, 40, 50, 60, 255, 70, 80, 90, 255, 100, 110, 120, 255])
    png_b64 = base64.b64encode(png).decode("ascii")
    for index, theme in enumerate(THEMES):
        rel = Path("preserve") / "epub" / (theme[0] + ".epub")
        path = out / rel
        preset = preserve_epub(index, theme, font, path)
        data = path.read_bytes()
        corpus.append({"kind": "preserve", "format": "epub", "theme": theme[0],
                       "path": rel.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data),
                       "features": ["multi_chapter", "image", "duplicate_basename", "table",
                                    "internal_link", "font", "css", "footnote", "rtl"]})
    for index, theme in enumerate(THEMES):
        rel = Path("preserve") / "xhtml" / (theme[0] + ".xhtml")
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(preserve_xhtml(index, theme, png_b64), encoding="utf-8", newline="\n")
        data = path.read_bytes()
        corpus.append({"kind": "preserve", "format": "xhtml", "theme": theme[0],
                       "path": rel.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data),
                       "features": ["heading", "table", "internal_link", "inline_image",
                                    "inline_css", "footnote", "rtl", "supplementary"]})
    mobi_names = ["sample.mobi", "mobi-huff.mobi", "mobi-huff-split.mobi",
                  "mobi-huff-trailers.mobi", "mobi-huff-many-trailers.mobi",
                  "mobi-palmdoc-trailers.mobi", "mobi-raw-trailers.mobi",
                  "mobi-huff-cp1252.mobi", "mobi-palmdoc-overlap.mobi",
                  "mobi-huff-recursive.mobi"]
    kf8_names = ["kf8-basic.azw3", "kf8-metadata.azw3", "kf8-hybrid.azw3",
                 "kf8-navigation.azw3", "kf8-flows.azw3", "kf8-unsplit.azw3",
                 "kf8-two-inserts.azw3", "kf8-multirecord.azw3",
                 "kf8-multicontrol.azw3", "kf8-positions.azw3"]
    mobile = []
    for variant, names, extension in (("mobi", mobi_names, ".mobi"), ("kf8", kf8_names, ".azw3")):
        for index, name in enumerate(names):
            rel = Path("mobile") / variant / (variant + "-%02d%s" % (index + 1, extension))
            path = out / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            data = (fixtures / name).read_bytes()
            path.write_bytes(data)
            corpus.append({"kind": "mobile", "format": variant, "theme": name,
                           "path": rel.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data),
                           "source_fixture": name, "features": ["real-fixture", "hash-distinct"]})
            mobile.append("mobile|%s|%s|%s" % (variant, name, rel.as_posix()))
    long_rel = Path("long") / "one-mib.txt"
    long_path = out / long_rel
    long_path.parent.mkdir(parents=True, exist_ok=True)
    unit = ("Long body 长正文 \U0001F600 line %d. " % 0).encode("utf-8")
    body = bytearray()
    index = 0
    while len(body) < 1024 * 1024:
        body += ("Paragraph %d: " % index).encode("utf-8") + unit + b"\n"
        index += 1
    body = body[:1024 * 1024]
    while body and body[-1] & 0x80:
        body = body[:-1]
    long_path.write_bytes(bytes(body))
    data = long_path.read_bytes()
    corpus.append({"kind": "long", "format": "txt", "theme": "one-mib",
                   "path": long_rel.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data),
                   "features": ["one_mib_body", "unicode"]})
    (out / "matrix.txt").write_text("\n".join(matrix) + "\n", encoding="utf-8", newline="\n")
    (out / "mobile.txt").write_text("\n".join(mobile) + "\n", encoding="utf-8", newline="\n")
    (out / "corpus.json").write_text(json.dumps({
        "schema": 1,
        "generator": "tools/generate_conversion_corpus.py",
        "license": "MIT; all text original; font tests/fixtures/fonts/primary.ttf (MIT)",
        "font": {"path": "tests/fixtures/fonts/primary.ttf", "sha256": sha256_bytes(font)},
        "entries": corpus}, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    print("generated %d files in %s" % (len(corpus), out))
    return 0

if __name__ == "__main__":
    sys.exit(main())
