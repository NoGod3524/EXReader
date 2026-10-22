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
