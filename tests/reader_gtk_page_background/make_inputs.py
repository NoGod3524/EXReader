# SPDX-License-Identifier: MIT
"""Actions-only authored-white/image EPUB for real native page-color checks."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zipfile
import zlib


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    target = Path(sys.argv[1])
    target.mkdir(parents=True)
    colors = ((255, 255, 255, 255), (240, 40, 50, 255), (30, 110, 220, 255), (20, 190, 80, 255))
    pixels = b''.join(b'\0' + b''.join(bytes(colors[(y >= 40) * 2 + (x >= 80)]) for x in range(160)) for y in range(80))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 160, 80, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
    html = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Authored page</title>'
            '<style>p{margin:0 0 12px}.white{background-color:#ffffff;padding:18px}</style></head><body>'
            '<p>Native canvas and original image.</p><p class="white">An explicit author white background stays white.</p>'
            '<p><img src="patch.png" width="160" height="80"/></p></body></html>')
    files = {
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': '<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>',
        'book.opf': '<package><metadata><title>Authored white and image</title></metadata><manifest>'
                    '<item id="one" href="one.xhtml" media-type="application/xhtml+xml"/>'
                    '<item id="two" href="two.xhtml" media-type="application/xhtml+xml"/>'
                    '<item id="image" href="patch.png" media-type="image/png"/></manifest>'
                    '<spine><itemref idref="one"/><itemref idref="two"/></spine></package>',
        'one.xhtml': html,
        'two.xhtml': '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Second native bounded chapter.</p></body></html>',
        'patch.png': png,
    }
    book = target / 'Authored white and original image.epub'
    with zipfile.ZipFile(book, 'w') as archive:
        for name, content in files.items():
            item = zipfile.ZipInfo(name, (2026, 10, 25, 0, 0, 0))
            item.compress_type = zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED
            archive.writestr(item, content.encode() if isinstance(content, str) else content)
    (target / 'manifest.json').write_text(json.dumps({'book': book.name, 'sha256': hashlib.sha256(book.read_bytes()).hexdigest(),
        'image_sha256': hashlib.sha256(png).hexdigest(), 'image_width': 160, 'image_height': 80, 'quadrants': colors}, indent=2) + '\n')


if __name__ == '__main__':
    main()
