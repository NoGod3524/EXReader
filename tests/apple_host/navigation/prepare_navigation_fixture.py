# SPDX-License-Identifier: MIT
"""Cloud-only authored TOC with hierarchy, 70 roots and explicit bad targets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import zipfile
import zlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    source = args.resources / 'Sample.epub'
    with zipfile.ZipFile(source) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    nav = ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
           '<head><title>Navigation</title></head><body><nav epub:type="toc"><ol>'
           '<li><a href="c1.xhtml#p000">Directory group</a><ol><li><a href="c1.xhtml#p040">Destination chapter</a></li></ol></li>'
           '<li><a href="c1.xhtml#missing">Missing fragment</a></li>'
           '<li><a href="c0.xhtml#p010">Repeated chapter</a></li>'
           '<li><a href="https://example.invalid/reader">External target</a></li>'
           '<li><a href="../../outside.xhtml">Unsafe target</a></li>' +
           ''.join('<li><a href="c2.xhtml#p%03d">Entry %03d</a></li>' % (index, index) for index in range(65)) +
           '</ol></nav></body></html>').encode()
    with zipfile.ZipFile(source, 'w') as archive:
        for item, data in entries:
            if item.filename.endswith('.opf'):
                data = data.replace(b'</spine>', b'<itemref idref="c0"/></spine>')
                data = data.replace(b'</manifest>', b'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest>')
            if item.filename.startswith('OPS/c') and item.filename.endswith('.xhtml'):
                chapter = int(Path(item.filename).stem[1:])
                paragraphs = ['<p id="p%03d">' % paragraph +
                              ' '.join('C%02dP%03dW%02d reading' % (chapter, paragraph, word) for word in range(12)) +
                              '</p>' for paragraph in range(80)]
                paragraphs += ['<p id="unicode">A😀Z unique raw scalar.</p>', '<p id="folded">A   B folded text.</p>']
                data = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>' + ''.join(paragraphs) + '</body></html>').encode()
            archive.writestr(item, data)
        archive.writestr('OPS/nav.xhtml', nav)
    expected = args.resources / 'navigation-expected.json'
    expected.write_text(json.dumps({'roots': 70, 'nodes': 71, 'group': 0, 'destination': 1,
        'missing': 2, 'duplicate': 3, 'external': 4, 'unsafe': 5,
        'duplicate_parts': [0, 3], 'destination_text': 'C01P040W00', 'duplicate_text': 'C00P010W00'}, sort_keys=True) + '\n')
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 8, 8, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress((b'\x00' + b'\x77\x88\x99' * 8) * 8)) + chunk(b'IEND', b'')
    cbz = args.resources / 'NavigationPages.cbz'
    with zipfile.ZipFile(cbz, 'w') as archive:
        archive.writestr('01.png', png); archive.writestr('02.png', png)
    manifest_path = args.resources / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for path in (source, expected, cbz):
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
