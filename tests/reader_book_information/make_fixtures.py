#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic book fixtures for the book-information package.

Everything is generated inside GitHub Actions; nothing is downloaded. The
product rows in the test harness are synthetic metadata, and no fixture is a real
user document.
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

ASCII_INFO = {
    "title": "Plain title",
    "author": "Plain author",
    "subject": "Plain subject",
    "keywords": "one, two",
    "producer": "fixture writer",
}

UNICODE_TITLE = "中文标题📚 第二版"
UNICODE_AUTHOR = "作者：欧阳雪"
UNICODE_SUBJECT = "主题描述：书籍信息"

# Keys the SDK derives from a PDF /Info dictionary, in provider order.
PDF_INFO_KEYS = {
    "title": "http://purl.org/dc/terms/title",
    "author": "http://purl.org/dc/terms/creator",
    "subject": "http://purl.org/dc/terms/description",
    "keywords": "http://ns.adobe.com/pdf/1.3/Keywords",
    "producer": "http://ns.adobe.com/pdf/1.3/Producer",
}


def pdf_string(value):
    """Literal string for ASCII, UTF-16BE hex string otherwise."""
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return "<FEFF" + value.encode("utf-16-be").hex().upper() + ">"
    escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return "(" + escaped + ")"


def pdf_bytes(pages, info=None):
    objects = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objects.append(f"<< /Type /Pages /Count {pages} /Kids [{kids}] >>".encode("ascii"))
    for _ in range(pages):
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Resources << >> >>")
    info_id = 0
    if info:
        info_id = len(objects) + 1
        entries = " ".join(
            "/%s %s" % (key.capitalize(), pdf_string(value)) for key, value in info.items()
        )
        objects.append(("<< " + entries + " >>").encode("utf-8"))
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    trailer = "<< /Size %d /Root 1 0 R" % (len(objects) + 1)
    if info_id:
        trailer += " /Info %d 0 R" % info_id
    out += ("trailer\n" + trailer + " >>\nstartxref\n%d\n%%%%EOF\n" % xref).encode("ascii")
    return bytes(out)


def png_bytes(width=2, height=2):
    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


COMIC_EXTRA = {f"Field{i:02d}": f"value-{i:02d}" for i in range(1, 39)}
COMIC_LONG_NAME = "Metadata" + "X" * 192          # 200-byte element name
COMIC_LONG_VALUE = "V" * 1200                     # beyond the 1024-byte value cap
COMIC_INFO_PROPERTIES = 3 + len(COMIC_EXTRA) + 2  # Title, Writer, Summary, extras, long key, long value


def comic_info():
    parts = ["<ComicInfo>",
             "<Title>漫画：夜空 &amp; 星</Title>",
             "<Writer>脚本：林</Writer>",
             "<Summary>合集测试</Summary>",
             f"<{COMIC_LONG_NAME}>{COMIC_LONG_VALUE}</{COMIC_LONG_NAME}>",
             "<LongValue>" + "W" * 1200 + "</LongValue>"]
    for name, value in COMIC_EXTRA.items():
        parts.append(f"<{name}>{value}</{name}>")
    parts.append("</ComicInfo>")
    return "".join(parts)


def cbz_bytes():
    import io
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("pages/1.png", "pages/2.png", "pages/3.png"):
            archive.writestr(name, png_bytes())
        archive.writestr("ComicInfo.xml", comic_info())
    return buffer.getvalue()


def epub_bytes(title="重排：书签与章节", author="作者：欧阳雪"):
    import io
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, "application/epub+zip")
        archive.writestr("META-INF/container.xml",
                         '<?xml version="1.0"?>'
                         '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                         '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                         'media-type="application/oebps-package+xml"/></rootfiles></container>')
        archive.writestr("OEBPS/content.opf",
                         '<?xml version="1.0" encoding="utf-8"?>'
                         '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
                         '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                         '<dc:identifier id="id">urn:uuid:book-information-fixture</dc:identifier>'
                         f'<dc:title>{title}</dc:title><dc:creator>{author}</dc:creator>'
                         '<dc:language>zh-CN</dc:language></metadata>'
                         '<manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
                         '</manifest><spine><itemref idref="c1"/></spine></package>')
        archive.writestr("OEBPS/chapter1.xhtml",
                         '<?xml version="1.0" encoding="utf-8"?>'
                         '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>一</title></head>'
                         '<body><p>第一章 正文</p></body></html>')
    return buffer.getvalue()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_fixtures(directory):
    directory = Path(directory)
    books = directory / "books"
    books.mkdir(parents=True, exist_ok=True)
    files = {}

    def emit(name, data):
        (books / name).write_bytes(data)
        files[name] = {"path": str((books / name).resolve()), "bytes": len(data), "sha256": sha256(data)}
        return files[name]

    emit("plain.pdf", pdf_bytes(3, ASCII_INFO))
    emit("unicode.pdf", pdf_bytes(2, {"title": UNICODE_TITLE, "author": UNICODE_AUTHOR,
                                     "subject": UNICODE_SUBJECT}))
    emit("long.pdf", pdf_bytes(1, {"title": "A" * 1500, "keywords": "B" * 1300,
                                  "subject": "short subject"}))
    emit("pages7.pdf", pdf_bytes(7, None))
    emit("swap-alpha.pdf", pdf_bytes(1, {"title": "Swap alpha"}))
    emit("swap-beta.pdf", pdf_bytes(1, {"title": "Swap beta!"}))
    emit("collection.cbz", cbz_bytes())
    emit("shelf.epub", epub_bytes())
    emit("shelf2.epub", epub_bytes(title="重排：第二本", author="作者：另一位"))
    emit("small.txt", ("第一章\n" + "正文一行。" * 40 + "\n").encode("utf-8"))
    emit("tiny.txt", ("另一本书" * 3 + "\n").encode("utf-8"))
    emit("large.txt", "".join(f"line {i:07d} 大量文本\n" for i in range(240000)).encode("utf-8"))

    manifest = {
        "directory": str(books.resolve()),
        "books": files,
        "expect": {
            "plain.pdf": {"pages": 3, "title": ASCII_INFO["title"], "properties": len(PDF_INFO_KEYS)},
            "unicode.pdf": {"pages": 2, "title": UNICODE_TITLE, "properties": 3},
            "long.pdf": {"pages": 1, "properties": 3},
            "pages7.pdf": {"pages": 7, "properties": 0},
            "collection.cbz": {"pages": 3, "properties": COMIC_INFO_PROPERTIES,
                               "kept": 32, "omitted": COMIC_INFO_PROPERTIES - 32},
        },
        "pdf_info_keys": PDF_INFO_KEYS,
        "comic": {"long_name": COMIC_LONG_NAME, "long_value": COMIC_LONG_VALUE,
                  "properties": COMIC_INFO_PROPERTIES, "kept": 32,
                  "omitted": COMIC_INFO_PROPERTIES - 32},
        "unicode": {"title": UNICODE_TITLE, "author": UNICODE_AUTHOR, "subject": UNICODE_SUBJECT},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    manifest = write_fixtures(args.out)
    print(json.dumps({"fixtures": len(manifest["books"]), "directory": manifest["directory"]}))


if __name__ == "__main__":
    main()
