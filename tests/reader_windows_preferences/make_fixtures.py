#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authored fixtures for the F3 Windows preferences checks.

The text book, the picture book and the large comic page are generated here so
that every observed pixel has a declared origin. The real PDF fixture is copied
byte for byte from the repository, never regenerated.
"""
import argparse
import struct
import zlib
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def png(width, height, row):
    """Truecolour PNG whose every scanline is produced by the given painter."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(row(y))
    assert len(raw) == height * (1 + width * 3)

    def chunk(tag, body):
        return (struct.pack('>I', len(body)) + tag + body +
                struct.pack('>I', zlib.crc32(tag + body) & 0xffffffff))
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) +
            chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


def entry(name, data, compress=zipfile.ZIP_DEFLATED):
    item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    item.compress_type = compress
    item.external_attr = 0o100644 << 16
    return item, data


def epub(path, title, body, image=None):
    container = ('<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                 '<rootfiles><rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    manifest = '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
    if image:
        manifest += '<item id="i1" href="picture.png" media-type="image/png"/>'
    package = ('<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:identifier id="id">urn:exreader:windows-preferences</dc:identifier>'
               '<dc:title>' + title + '</dc:title></metadata>'
               '<manifest>' + manifest + '</manifest>'
               '<spine><itemref idref="c1"/></spine></package>')
    files = [entry('mimetype', b'application/epub+zip', zipfile.ZIP_STORED),
             entry('META-INF/container.xml', container.encode()),
             entry('OPS/package.opf', package.encode()),
             entry('OPS/c1.xhtml',
                   ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>' + title +
                    '</title></head><body>' + body + '</body></html>').encode())]
    if image:
        files.append(entry('OPS/picture.png', image))
    with zipfile.ZipFile(path, 'w') as archive:
        for item, data in files:
            archive.writestr(item, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    paragraphs = ''.join(
        '<p>Reading page %04d keeps the authored words, the saved position and the '
        'selected appearance together.</p>' % row for row in range(140))
    (output / 'Reading sample.txt').write_text(
        ''.join('Reading page %04d keeps the authored words, the saved position and the '
                'selected appearance together.\n\n' % row for row in range(420)),
        encoding='utf-8')
    picture = png(120, 80, lambda y: bytes((51, 102, 204)) * 120)
    epub(output / 'Picture book.epub', 'Picture book',
         '<p>Picture book opening paragraph before the image.</p>'
         '<p><img src="picture.png" alt="authored"/></p>'
         '<p>Picture book closing paragraph after the image.</p>' + paragraphs,
         picture)

    def comic_row(y):
        line = bytearray(bytes((250, 250, 250)) * 2000)
        if 200 <= y < 400:
            line[200 * 3:400 * 3] = bytes((204, 32, 32)) * 200
        return bytes(line)
    with zipfile.ZipFile(output / 'Large comic.cbz', 'w') as archive:
        archive.writestr(entry('page-1.png', png(2000, 3000, comic_row)))

    shutil.copyfile(ROOT / 'tests/fixtures/pdf-public.pdf', output / 'Fixed page.pdf')
    print('authored F3 fixtures:', sorted(item.name for item in output.iterdir()), flush=True)


if __name__ == '__main__':
    main()
