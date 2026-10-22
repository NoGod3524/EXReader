#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate deterministic extra books for the Windows host acceptance run.

Everything here is produced in CI; the host never generates test data.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

CONTAINER = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
             '<rootfiles><rootfile full-path="OPS/package.opf" '
             'media-type="application/oebps-package+xml"/></rootfiles></container>')


def epub(path, title, text):
    package = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:identifier id="id">urn:exreader:windows-host</dc:identifier>'
               f'<dc:title>{title}</dc:title><dc:language>en</dc:language></metadata>'
               '<manifest><item id="c0" href="c0.xhtml" media-type="application/xhtml+xml"/></manifest>'
               '<spine><itemref idref="c0"/></spine></package>')
    chapter = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>'
               + title + '</title></head><body><p>' + text + '</p></body></html>')
    with zipfile.ZipFile(path, 'w') as archive:
        def write(name, data, stored=False):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
        write('mimetype', 'application/epub+zip', True)
        write('META-INF/container.xml', CONTAINER)
        write('OPS/package.opf', package)
        write('OPS/c0.xhtml', chapter)


def pdf(path, count):
    objects = []
    width, height = 612, 792
    content_ids = [3 + count + i for i in range(count)]
    font_id = 3 + 2 * count
    kids = " ".join("%d 0 R" % (3 + i) for i in range(count))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(("<< /Type /Pages /Count %d /Kids [%s] >>" % (count, kids)).encode())
    for i in range(count):
        objects.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                        "/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                        % (width, height, font_id, content_ids[i])).encode())
    for i in range(count):
        text = "Page %d: Windows host acceptance text on a renderable PDF page." % (i + 1)
        stream = ("BT /F1 24 Tf 72 700 Td (%s) Tj 0 -32 Td "
                  "(Second line for selection and notes on page %d.) Tj ET" % (text, i + 1)).encode()
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (len(objects) + 1)
    for index, body in enumerate(objects, 1):
        offsets[index] = len(out)
        out += ("%d 0 obj\n" % index).encode() + body + b"\nendobj\n"
    xref = len(out)
    out += ("xref\n0 %d\n" % (len(objects) + 1)).encode() + b"0000000000 65535 f \n"
    for index in range(1, len(objects) + 1):
        out += ("%010d 00000 n \n" % offsets[index]).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, xref)).encode()
    path.write_bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sentence = ('Windows host acceptance keeps every import cancellable and every '
                'page owned by a single worker at a time. ')
    epub(args.output / 'Extra-Book.epub', 'Extra Book', sentence * 600)
    epub(args.output / 'Stale-Book.epub', 'Stale Book', sentence * 900)
    epub(args.output / 'Cancel-Big.epub', 'Cancel Big', sentence * 40000)
    pdf(args.output / 'Pages.pdf', 4)
    (args.output / 'Broken.epub').write_bytes(b'this is not a zip container')
    (args.output / 'Unsupported.bin').write_bytes(bytes(range(256)) * 8)
    manifest = {}
    for path in sorted(args.output.iterdir()):
        if path.is_file() and path.name != 'fixtures.json':
            manifest[path.name] = {'bytes': path.stat().st_size,
                                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (args.output / 'fixtures.json').write_text(json.dumps({'schema': 1, 'files': manifest},
                                                         indent=2) + '\n')
    print(json.dumps({'files': len(manifest), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
