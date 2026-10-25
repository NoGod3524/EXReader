# SPDX-License-Identifier: MIT
"""Add authored page-theme probes without changing any legacy fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import zipfile
import zlib


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    parser = argparse.ArgumentParser()
    parser.add_argument('--resources', type=Path, required=True)
    args = parser.parse_args()
    root = args.resources
    text = '\n\n'.join('Theme paragraph %04d. Explicit canvas and unchanged reading location.' % n for n in range(300))
    (root / 'Theme.txt').write_text(text, encoding='utf-8')

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 32, 32, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress((b'\x00' + b'\xc0\x20\x40' * 32) * 32)) + chunk(b'IEND', b'')
    with zipfile.ZipFile(root / 'Bounded.epub') as source:
        entries = [(item, source.read(item.filename)) for item in source.infolist()]
    for name, authored in (('ThemeText.epub', False), ('ThemeAuthored.epub', True)):
        with zipfile.ZipFile(root / name, 'w') as target:
            for item, data in entries:
                if item.filename.endswith('.opf') and authored:
                    data = data.replace(b'</manifest>', b'<item id="theme-image" href="theme.png" media-type="image/png"/></manifest>')
                if item.filename.startswith('OPS/c') and item.filename.endswith('.xhtml'):
                    content = ''.join('<p>Theme paragraph %04d. Explicit canvas and unchanged reading location.</p>' % n for n in range(300))
                    if authored:
                        content = '<p style="background-color:#223344">Author background retained.</p><p><img src="theme.png" width="32" height="32"/></p><p>Explicit theme foreground.</p>'
                    data = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>' + content + '</body></html>').encode()
                target.writestr(item, data)
            if authored:
                target.writestr('OPS/theme.png', png)
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(root.iterdir()) if path.is_file() and path.name != 'manifest.json'}
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
