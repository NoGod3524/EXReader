# SPDX-License-Identifier: MIT
"""Generate the jump-history originals in Actions only; never run locally.

Standard library only. Stored ZIP entries and level-0 zlib keep the Windows,
Linux and macOS originals byte-identical, so one manifest hash set can be
compared across the three runners.
"""
import hashlib
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path

STAMP = (2026, 1, 1, 0, 0, 0)
LONG = 'is long enough to give more than thirty two scalars of context'
FILLER_LINES = 60


def filler():
    return ''.join('Filler line %04d keeps one long contiguous run for the oversized position selection.\n' % i
                   for i in range(FILLER_LINES))


def txt():
    block = ('Ambiguous block line one ' + LONG + '.\nAMBIGUOUS TARGET\n'
             'Ambiguous block line three ' + LONG + '.\n')
    return ('开头中文段落：阅读跳转历史跨格式验收🙂测试。\n'
            'Jump alpha start. The repeated phrase appears here. Tail alpha.\n'
            'Jump beta start. Unique context gamma. Tail beta.\n'
            + block + block + filler() +
            '结尾段落含多字节文字与表情🎉终').encode('utf-8')


def entry(archive, name, data):
    info = zipfile.ZipInfo(name, date_time=STAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def xhtml(body):
    return ('<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
            '<head><title>c</title></head><body>' + body + '</body></html>').encode('utf-8')


def epub(path):
    with zipfile.ZipFile(path, 'w') as book:
        entry(book, 'mimetype', b'application/epub+zip')
        entry(book, 'META-INF/container.xml',
              b'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
              b'<rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        entry(book, 'book.opf', (
            '<?xml version="1.0" encoding="UTF-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">jump-history</dc:identifier>'
            '<dc:title>Jump history fixture</dc:title><dc:language>zh</dc:language></metadata>'
            '<manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="b" href="b.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="a"/><itemref idref="b"/><itemref idref="a"/></spine></package>').encode('utf-8'))
        entry(book, 'a.xhtml', xhtml('<p>Repeated spine chapter appears twice in the reading order.</p>'
                                     '<p>Its text ' + LONG + ', so the same quote exists in both parts.</p>'))
        entry(book, 'b.xhtml', xhtml('<p>第二章节独有文字，阅读跳转在这里。</p>'
                                     '<p>Second chapter body ' + LONG + ' and ends here.</p><p>章末🌙</p>'))


def pdf(path):
    repeated = ('Identical context abcdefghijklmnopqrstuvwxyz 0123456789 selection target '
                'identical suffix abcdefghijklmnopqrstuvwxyz 0123456789')
    pages = [
        ['Fixed page one. Shared quote across pages.', 'Second distinct line on page one only.'],
        [repeated] * 3,
        [],
    ]
    count = len(pages)
    font = 3 + count * 2
    kids = ' '.join('%d 0 R' % (3 + i) for i in range(count))
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', ('<< /Type /Pages /Count %d /Kids [%s] >>' % (count, kids)).encode()]
    for i in range(count):
        objects.append(('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 %d 0 R >> >> '
                        '/Contents %d 0 R >>' % (font, 3 + count + i)).encode())
    for lines in pages:
        content = ('BT /F1 12 Tf 36 720 Td ' + ' 0 -32 Td '.join('(%s) Tj' % line for line in lines) + ' ET') if lines else ''
        stream = content.encode('ascii')
        objects.append(('<< /Length %d >>\nstream\n' % len(stream)).encode() + stream + b'\nendstream')
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    data = bytearray(b'%PDF-1.7\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += ('%d 0 obj\n' % index).encode() + body + b'\nendobj\n'
    xref = len(data)
    data += ('xref\n0 %d\n' % len(offsets)).encode() + b'0000000000 65535 f \n'
    for offset in offsets[1:]:
        data += ('%010d 00000 n \n' % offset).encode()
    data += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offsets), xref)).encode()
    path.write_bytes(bytes(data))


def png(width, height, shade):
    rows = b''.join(b'\x00' + bytes((shade, 80, 255 - shade)) * width for _ in range(height))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(rows, 0)) + chunk(b'IEND', b''))


def cbz(path):
    with zipfile.ZipFile(path, 'w') as archive:
        for i in range(3):
            entry(archive, '%03d.png' % (i + 1), png(60, 80, 40 + i * 70))


ROLES = (('txt', 'book.txt'), ('epub', 'book.epub'), ('pdf', 'pages.pdf'), ('cbz', 'pages.cbz'))


def main(folder):
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'book.txt').write_bytes(txt())
    epub(folder / 'book.epub')
    pdf(folder / 'pages.pdf')
    cbz(folder / 'pages.cbz')
    manifest = {}
    for role, name in ROLES:
        data = (folder / name).read_bytes()
        manifest[role] = {'file': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
