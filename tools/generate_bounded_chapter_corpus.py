#!/usr/bin/env python3
"""Generate the fixed WP6 bounded-chapter corpus (single and segmented chapters).

The corpus is deterministic: every member carries a fixed timestamp, the text
bank is a fixed ASCII sentence repeated by block index, and the block pattern is
a pure function of the block counter.  manifest.json records the SHA-256 of
every archive, the exact uncompressed member sizes and the block census so that
a later run can prove it measured the same bytes.

Structural blocks are deliberately small (well under 1 KiB) and always align to
block boundaries, so a windowed reader may cut between blocks without cutting a
paragraph, table, float, ruby run or bidi paragraph.
"""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
import platform
import sys
import zipfile
import zlib
from pathlib import Path

MIB = 1024 * 1024

SENTENCE_BANK = (
    "A portable reading engine keeps its text model small and its pages exact. ",
    "Every chapter carries nested blocks, inline emphasis and measured lines. ",
    "The window boundary is a real constraint, not an accounting trick. ",
    "Source offsets, page ranges and checkpoints must survive eviction. ",
)

STYLE = """@charset "utf-8";
html { font-size: 100%; }
body { font-size: 1em; line-height: 1.45; margin: 1em 2em; }
h2 { font-size: 1.4em; margin: 1.2em 0 .4em; page-break-after: avoid; }
p { margin: 0 0 .6em; text-align: justify; }
p.em em { font-style: italic; }
p.em strong { font-weight: bold; }
div.callout { margin: .8em 0; padding: .5em .8em; border-left: 3px solid #446; }
div.floatbox { float: left; width: 40%; margin: 0 1em .6em 0; padding: .4em; border: 1px solid #888; }
table.t { border-collapse: collapse; margin: .8em 0; }
table.t td { border: 1px solid #666; padding: .2em .4em; }
ruby rt { font-size: .6em; }
span.rtl { direction: rtl; unicode-bidi: embed; }
"""

BLOCK_TEXT_BYTES = 384


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Counter:
    def __init__(self):
        self.blocks = 0
        self.kinds = {}

    def bump(self, kind):
        self.blocks += 1
        self.kinds[kind] = self.kinds.get(kind, 0) + 1


def text_for(index):
    """Deterministic ASCII body text of exactly BLOCK_TEXT_BYTES bytes."""
    out = []
    size = 0
    bank = len(SENTENCE_BANK)
    while size < BLOCK_TEXT_BYTES:
        piece = SENTENCE_BANK[(index + len(out)) % bank]
        out.append(piece)
        size += len(piece.encode("utf-8"))
    return "".join(out)[:BLOCK_TEXT_BYTES]


def words(index, count=6):
    bank = SENTENCE_BANK[index % len(SENTENCE_BANK)].split()
    return " ".join(bank[(index + i) % len(bank)] for i in range(count))


def block(index, counter):
    """Return one self-contained XHTML block for this index (UTF-8 string)."""
    if index % 4001 == 0:
        counter.bump("bidi")
        return ('<p class="bidi"><ruby>漢字<rt>kanji</rt></ruby> '
                '<span class="rtl">אבגד</span> ' + text_for(index)[:BLOCK_TEXT_BYTES // 2] + '</p>')
    if index % 3001 == 0:
        counter.bump("table")
        rows = "".join(
            '<tr><td>r%d</td><td>%s</td><td>%d</td></tr>' % (r, words(index + r), r * 7)
            for r in range(3))
        return '<table class="t"><tbody>%s</tbody></table>' % rows
    if index % 1501 == 0:
        counter.bump("float")
        return '<div class="floatbox"><p>%s</p></div>' % text_for(index)
    if index % 211 == 0:
        counter.bump("callout")
        return '<div class="callout"><p>%s</p></div>' % text_for(index)
    if index % 97 == 0:
        counter.bump("heading")
        return '<h2 id="h%d">Section %d</h2>' % (index, index)
    if index % 31 == 0:
        counter.bump("inline")
        text = text_for(index)
        cut = BLOCK_TEXT_BYTES // 3
        return ('<p class="em">%s<em>%s</em>%s<strong>%s</strong>%s</p>'
                % (text[:cut], words(index, 3), text[cut:cut + cut],
                   words(index + 1, 3), text[cut + cut:]))
    counter.bump("paragraph")
    return "<p>%s</p>" % text_for(index)


def chapter_body(body_bytes, counter, chapter_index):
    """One body whose serialized UTF-8 length is exactly body_bytes."""
    parts = []
    size = 0
    index = chapter_index * 100003
    while True:
        piece = block(index, counter)
        length = len(piece.encode("utf-8"))
        if size + length > body_bytes:
            break
        parts.append(piece)
        size += length
        index += 1
    if size < body_bytes:
        head = "<p>"
        tail = "</p>"
        pad = body_bytes - size - len(head) - len(tail)
        if pad > 0:
            parts.append(head + ("x" * pad) + tail)
            size += pad + len(head) + len(tail)
            counter.bump("pad")
    return "".join(parts), size


def xhtml(title, body):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">'
            '<head><title>%s</title>' % title +
            '<link rel="stylesheet" type="text/css" href="../styles/book.css"/>'
            '</head><body>%s</body></html>' % body)


def container_xml():
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>')


def package_opf(parts):
    manifest = "".join(
        '<item id="c%d" href="text/c%d.xhtml" media-type="application/xhtml+xml"/>' % (i, i)
        for i in range(parts))
    spine = "".join('<itemref idref="c%d"/>' % i for i in range(parts))
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'unique-identifier="bookid">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="bookid">urn:exreader:wp6-bounded</dc:identifier>'
            '<dc:title>WP6 bounded chapter corpus</dc:title>'
            '<dc:language>en</dc:language></metadata>'
            '<manifest><item id="css" href="styles/book.css" media-type="text/css"/>%s</manifest>'
            '<spine>%s</spine></package>' % (manifest, spine))


def write_epub(path, body_bytes, parts, counter):
    chapters = []
    per = body_bytes // parts
    for i in range(parts):
        size = per if i + 1 < parts else body_bytes - per * (parts - 1)
        body, produced = chapter_body(size, counter, i)
        assert produced == size, (produced, size)
        chapters.append(xhtml("Chapter %d" % i, body))
    members = [("mimetype", "application/epub+zip", True),
               ("META-INF/container.xml", container_xml(), False),
               ("OPS/package.opf", package_opf(parts), False),
               ("OPS/styles/book.css", STYLE, False)]
    members += [("OPS/text/c%d.xhtml" % i, chapters[i], False) for i in range(parts)]
    with zipfile.ZipFile(path, "w") as archive:
        for name, content, stored in members:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content.encode("utf-8"))
    return [{"name": name, "uncompressed_bytes": len(content.encode("utf-8")),
             "stored": stored, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
            for name, content, stored in members]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sizes", default="10,50,100", help="MiB values, comma separated")
    parser.add_argument("--segment-bytes", type=int, default=MIB,
                        help="fixed chapter size of the segmented corpus")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Choose a new output directory to preserve earlier corpora")
    args.output.mkdir(parents=True)
    sizes = [int(value) for value in args.sizes.split(",")]
    if not sizes or any(value <= 0 for value in sizes):
        parser.error("sizes must be positive")
    if args.segment_bytes <= 0:
        parser.error("segment bytes must be positive")
    manifest = {
        "schema": 1,
        "generator": str(Path(__file__).name),
        "generator_sha256": sha256(Path(__file__).absolute()),
        "mib": MIB,
        "segment_bytes": args.segment_bytes,
        "block_text_bytes": BLOCK_TEXT_BYTES,
        "python": sys.version.split()[0],
        "zlib": zlib.ZLIB_VERSION,
        "platform": platform.platform(),
        "style_sha256": hashlib.sha256(STYLE.encode("utf-8")).hexdigest(),
        "cases": [],
    }
    for size in sizes:
        body_bytes = size * MIB
        for shape in ("single", "segmented"):
            parts = 1 if shape == "single" else max(1, body_bytes // args.segment_bytes)
            counter = Counter()
            path = args.output / ("%s-%dMiB.epub" % (shape, size))
            members = write_epub(path, body_bytes, parts, counter)
            manifest["cases"].append({
                "name": path.name,
                "shape": shape,
                "chapter_count": parts,
                "chapter_bytes": body_bytes if parts == 1 else args.segment_bytes,
                "body_bytes": body_bytes,
                "file_bytes": path.stat().st_size,
                "sha256": sha256(path),
                "block_count": counter.blocks,
                "block_kinds": dict(sorted(counter.kinds.items())),
                "members": members,
            })
            print("%s %d bytes sha256=%s" % (path.name, path.stat().st_size,
                                             manifest["cases"][-1]["sha256"]))
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())