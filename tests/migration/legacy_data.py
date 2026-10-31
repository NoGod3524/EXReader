# SPDX-License-Identifier: MIT
"""Deterministic legacy dataset, fixture builders and an independent pack writer.

The pack writer is a second implementation of docs/WP12-LEGACY-MIGRATION.md section 2 (it shares no
code with the C reader or the browser exporter). Scenario packs are built with it; the end-to-end
chain uses the real browser exporter instead.
"""
import base64
import copy
import hashlib
import json
import struct
import zipfile
import zlib
from io import BytesIO

MAGIC = b"EXRLGP1\n"
TRAILER = b"EXRLGPT1"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- fixtures
TXT = (
    "Alpha harbor opens at dawn.\n\n"
    "The lantern keeper wrote one unique sentence about silver tides.\n\n"
    "Repeat this phrase twice. Between them is filler text.\n\n"
    "Repeat this phrase twice. The end of the second paragraph.\n\n"
    "中文引用在此处出现一次。\n"
).encode("utf-8")

TXT_OTHER = TXT.replace(b"Alpha", b"Omega")  # same size class, different bytes

CH1_P1 = "First paragraph with a unique marker phrase: cobalt lighthouse."
CH1_P2 = "Second paragraph repeats echo token once."
CH2_P1 = "Chapter two begins with echo token as well."


def epub(variant=""):
    def page(title, body):
        return ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head>'
                "<body>%s</body></html>" % (title, body)).encode()
    files = {
        "META-INF/container.xml": b'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        "OEBPS/content.opf": ('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:uuid:legacy-%s</dc:identifier><dc:title>Lighthouse Chronicle</dc:title><dc:creator>E. Pub</dc:creator><dc:language>en</dc:language></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/><item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>' % variant).encode(),
        "OEBPS/nav.xhtml": b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Nav</title></head><body><nav epub:type="toc"><ol><li><a href="ch1.xhtml">One</a></li><li><a href="ch2.xhtml">Two</a></li></ol></nav></body></html>',
        "OEBPS/ch1.xhtml": page("One", "<h1>One</h1><p>%s</p><p>%s</p>" % (CH1_P1, CH1_P2)),
        "OEBPS/ch2.xhtml": page("Two", "<p>%s</p>" % CH2_P1),
    }
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype", (2020, 1, 1, 0, 0, 0)), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            z.writestr(zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0)), data, compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()


def cfi_range(chapter_step, path, text, needle):
    """Foliate-style range CFI for `needle` inside the single text node (/1) of `path`."""
    start = text.index(needle)
    return "epubcfi(/6/%d!%s,/1:%d,/1:%d)" % (chapter_step, path, start, start + len(needle))


def cfi_point(chapter_step, path, offset):
    return "epubcfi(/6/%d!%s/1:%d)" % (chapter_step, path, offset)


def png(width=8, height=8, shade=0):
    raw = b"".join(b"\x00" + bytes([(shade + x * 8) & 255] * 3 * 1) * 1 + b"" for x in range(0)) or b""
    rows = b"".join(b"\x00" + bytes([(shade + x * 16) & 255 for x in range(width) for _ in range(3)]) for _ in range(height))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def cbz(pages=3):
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for i in range(pages):
            z.writestr(zipfile.ZipInfo("page%02d.png" % (i + 1), (2020, 1, 1, 0, 0, 0)), png(shade=i * 40), compress_type=zipfile.ZIP_STORED)
    return out.getvalue()


PDF_PAGES = ["Legacy page one quote alpha", "Legacy page two quote beta"]


def pdf(pages=PDF_PAGES):
    objects = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
               2: ("<< /Type /Pages /Count %d /Kids [%s] >>" % (len(pages), " ".join("%d 0 R" % (4 + i * 2) for i in range(len(pages))))).encode(),
               3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"}
    for i, text in enumerate(pages):
        content = ("BT /F1 18 Tf 72 700 Td (%s) Tj ET" % text).encode()
        objects[4 + i * 2] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + i * 2)).encode()
        objects[5 + i * 2] = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objects[number] + b"\nendobj\n"
    xref = len(out)
    size = max(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for number in range(1, size):
        out += b"%010d 00000 n \n" % offsets[number]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


AUDIO = b"ID3\x03\x00\x00\x00\x00\x00\x00legacy audio payload that the library cannot store" * 3
COVER = "data:image/png;base64," + base64.b64encode(png(shade=90)).decode()


# ---------------------------------------------------------------- dataset
def book_record(id, filename, **fields):
    record = {"id": id, "title": filename.rsplit(".", 1)[0].title(), "author": "", "format": filename.rsplit(".", 1)[1],
              "filename": filename, "size": 0, "modified": 1_700_000_000_000, "added": 1_700_000_100_000,
              "progress": 0, "favorite": False, "tags": [], "status": "unread", "audio": False}
    record.update(fields)
    return record


def note_record(id, book, quote, note="", **fields):
    record = {"id": id, "bookId": book, "quote": quote, "note": note, "created": 1_700_000_200_000}
    record.update(fields)
    return record


def entry(record, data, **file_meta):
    return {"legacy_id": record["id"], "record": record, "data": data, "file": file_meta}


def dataset():
    """The full legacy library: one of every kind of book and annotation."""
    ep = epub()
    books = [
        entry(book_record("b-txt", "tale.txt", title="The Tale", author="A. Writer", tags=["fiction", "local"], favorite=True,
                          status="reading", progress=0.5, cover=COVER, lastRead=1_700_000_300_000), TXT),
        entry(book_record("b-epub", "lighthouse.epub", title="Lighthouse Chronicle", author="E. Pub", status="reading", progress=0.7,
                          cfi=cfi_point(4, "/4/2", 24)), ep),
        entry(book_record("b-pdf", "scan.pdf", title="Scan", status="reading", progress=0.5, page=2), pdf()),
        entry(book_record("b-cbz", "comic.cbz", title="Comic", status="reading", progress=0.5), cbz()),
        entry(book_record("b-audio", "story.mp3", title="Story", format="mp3", audio=True, status="reading", seconds=75.5), AUDIO),
    ]
    notes = [
        note_record("n-txt-unique", "b-txt", "unique sentence about silver tides", "keep this", value=""),
        note_record("n-txt-ws", "b-txt", "unique sentence\nabout   silver tides", "whitespace differs"),
        note_record("n-txt-cjk", "b-txt", "中文引用在此处出现一次", "cjk"),
        note_record("n-txt-ambiguous", "b-txt", "Repeat this phrase twice.", "appears twice"),
        note_record("n-txt-missing", "b-txt", "this sentence was edited away", "gone"),
        note_record("n-txt-bookmark", "b-txt", "阅读书签", "no location", bookmark=True),
        note_record("n-epub-range", "b-epub", "cobalt lighthouse", "exact range",
                    value=cfi_range(2, "/4/4", CH1_P1, "cobalt lighthouse")),
        note_record("n-epub-disambiguate", "b-epub", "echo token", "second chapter occurrence", value=cfi_point(4, "/4/2", 0)),
        note_record("n-epub-ambiguous", "b-epub", "echo token", "no usable cfi"),
        note_record("n-epub-bookmark", "b-epub", "Two", "point bookmark", bookmark=True, value=cfi_point(4, "/4/2", 0)),
        note_record("n-pdf-quote", "b-pdf", "page two quote beta", "second page", page=2,
                    rects=[{"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.05}]),
        note_record("n-pdf-bookmark", "b-pdf", "第 1 页", "", page=1, bookmark=True),
        note_record("n-pdf-missing", "b-pdf", "text that is not on the page", "lost", page=1),
        note_record("n-audio-bookmark", "b-audio", "chapter two", "", seconds=30, bookmark=True),
        note_record("n-audio-note", "b-audio", "a quote", "listen again", seconds=61.25),
        note_record("n-orphan", "b-gone", "belongs to a deleted book", "orphan"),
    ]
    return books, notes


def clone(items):
    return copy.deepcopy(items)


# ---------------------------------------------------------------- pack writer
def build_pack(books, notes, *, version=1, fmt="exreader-legacy-pack", source=None, extra=None):
    """Return the bytes of a pack. `books` entries carry `data` (bytes or None) next to their record."""
    body = bytearray(MAGIC)
    manifest_books = []
    for item in books:
        file_meta = {"present": False}
        data = item.get("data")
        if data is not None:
            file_meta = {"present": True, "offset": len(body), "size": len(data), "sha256": sha256(data),
                         "name": item["record"].get("filename", ""), "type": "", "modified": item["record"].get("modified"),
                         "shape": "record"}
            file_meta.update(item.get("file") or {})
            body += data
        manifest_books.append({"legacy_id": item["legacy_id"], "record": item["record"], "file": file_meta})
    manifest = {"format": fmt, "version": version,
                "exporter": {"name": "tests/migration/legacy_data.py", "version": "1", "read_only": True},
                "source": source or {"kind": "indexeddb", "database": "exreader", "version": 1, "stores": ["books", "files", "notes"]},
                "counts": {"books": len(manifest_books), "notes": len(notes)},
                "books": manifest_books,
                "notes": [{"legacy_id": n["id"], "record": n} for n in notes], "orphans": {"files": []}, "warnings": []}
    if extra:
        manifest.update(extra)
    text = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return finish(bytes(body), text)


def finish(body, manifest_bytes):
    offset = len(body)
    trailer = TRAILER + struct.pack("<QQ", offset, len(manifest_bytes)) + hashlib.sha256(manifest_bytes).digest()
    return body + manifest_bytes + trailer


def split(pack):
    """(payload, manifest_bytes, trailer) of a well-formed pack, for the corruption cases."""
    offset, length = struct.unpack("<QQ", pack[-48:-32])
    return pack[:offset], pack[offset:offset + length], pack[-56:]
