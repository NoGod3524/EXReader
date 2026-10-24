#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the J14 library-health originals, plans and manifest.

Actions only: the local tree never runs this. Standard library only, and every
byte is deterministic so Windows, Linux and macOS fixtures are identical.
Four real formats are used: EPUB, PDF, CBZ and TXT.
"""
import hashlib
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path

ROWS = 2202
VERIFIED = 2185
CYCLE = ('epub', 'pdf', 'cbz', 'txt')
# sort_title LH-2185 .. LH-2201 carry the named non-healthy identities.
DEFECTS = [
    ('cloud', 4),        # metadata without a local SDK mapping
    ('missing', 4),      # mapping whose retained original was deleted
    ('hash_bad', 4),     # same length, different bytes
    ('size_short', 2),   # retained original shorter than the catalog claims
    ('size_long', 2),    # retained original longer than the catalog claims
    ('limit', 1),        # larger than the scan's max_book_bytes
]
LIMIT_BYTES = 700 * 1024


def zip_open(path):
    handle = zipfile.ZipFile(path, 'w')
    return handle


def put(handle, name, data):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o644 << 16
    handle.writestr(info, data)


def xhtml(body):
    return ('<?xml version="1.0" encoding="utf-8"?>'
            '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
            '<body>' + body + '</body></html>').encode('utf-8')


def png_rgba(width, height, seed, note=b''):
    rows = []
    for y in range(height):
        row = bytearray(b'\x00')
        for x in range(width):
            row += bytes(((seed + x * 7) & 0xFF, (seed * 3 + y * 5) & 0xFF, (x * y + seed) & 0xFF, 0xFF))
        rows.append(bytes(row))
    raw = b''.join(rows)

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data +
                struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    text = chunk(b'tEXt', b'Comment\x00' + note) if note else b''
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
            chunk(b'IDAT', zlib.compress(raw, 9)) + text + chunk(b'IEND', b''))


def txt_bytes(index, size=None):
    if size is not None:
        block = ('Library health long original LH-%04d carries no payload semantics.\n' % index).encode('utf-8')
        data = bytearray()
        while len(data) < size:
            data += block
        return bytes(data[:size])
    return ('Library health original LH-%04d.\n'
            'Unique sentence %d of the text fixture.\n'
            'Second paragraph for %04d.\n' % (index, index * 7 + 3, index)).encode('utf-8')


def pdf_bytes(index):
    text = 'Library health original LH-%04d page one.' % index
    content = ('BT /F1 12 Tf 36 720 Td (%s) Tj ET' % text).encode('ascii')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 5 0 R >> >> '
        b'/Contents 4 0 R >>',
        b'<< /Length %d >>\nstream\n' % len(content) + content + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    data = bytearray(b'%PDF-1.7\n')
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += ('%d 0 obj\n' % number).encode('ascii') + body + b'\nendobj\n'
    xref = len(data)
    data += ('xref\n0 %d\n' % len(offsets)).encode('ascii') + b'0000000000 65535 f \n'
    for offset in offsets[1:]:
        data += ('%010d 00000 n \n' % offset).encode('ascii')
    data += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'
             % (len(offsets), xref)).encode('ascii')
    return bytes(data)


def epub_bytes(index, body_size=0):
    container = (b'<?xml version="1.0"?><container version="1.0" '
                 b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                 b'<rootfile full-path="book.opf" media-type="application/oebps-package+xml"/>'
                 b'</rootfiles></container>')
    opf = ('<?xml version="1.0" encoding="UTF-8"?><package xmlns="http://www.idpf.org/2007/opf" '
           'version="3.0" unique-identifier="id"><metadata '
           'xmlns:dc="http://purl.org/dc/elements/1.1/">'
           '<dc:identifier id="id">LH-%04d</dc:identifier><dc:title>LH-%04d</dc:title>'
           '<dc:language>en</dc:language></metadata><manifest>'
           '<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>'
           '</manifest><spine><itemref idref="a"/></spine></package>' % (index, index)).encode('utf-8')
    if body_size:
        body = ('<p>LH-%04d</p>' % index) + '<p>' + ('health scan payload ' * (body_size // 20)) + '</p>'
    else:
        body = '<p>Library health original LH-%04d.</p><p>Unique body %d.</p>' % (index, index * 11 + 5)
    return container, opf, xhtml(body)


def write_epub(path, index, body_size=0):
    container, opf, page = epub_bytes(index, body_size)
    with zip_open(path) as book:
        put(book, 'mimetype', b'application/epub+zip')
        put(book, 'META-INF/container.xml', container)
        put(book, 'book.opf', opf)
        put(book, 'a.xhtml', page)


def write_cbz(path, index):
    with zip_open(path) as book:
        put(book, 'page-000.png', png_rgba(16, 16, index & 0xFF, b'LH-%04d' % index))


def write_original(path, fmt, index, size=None):
    if fmt == 'txt':
        path.write_bytes(txt_bytes(index, size))
    elif fmt == 'pdf':
        path.write_bytes(pdf_bytes(index))
    elif fmt == 'epub':
        write_epub(path, index)
    elif fmt == 'cbz':
        write_cbz(path, index)
    else:
        raise SystemExit('unknown format ' + fmt)


def row(plan, sort_title, fmt, data, rel, action):
    plan.append((sort_title, fmt, hashlib.sha256(data).hexdigest(), len(data), rel, action))


def main(out_dir):
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=False)
    originals = root / 'originals'
    adversarial = root / 'adversarial'
    originals.mkdir()
    adversarial.mkdir()
    plan = []
    manifest = {}
    defect_at = {}
    cursor = VERIFIED
    for action, count in DEFECTS:
        for _ in range(count):
            defect_at[cursor] = action
            cursor += 1
    assert cursor == ROWS, cursor

    for index in range(ROWS):
        action = defect_at.get(index, 'map')
        fmt = CYCLE[index % 4]
        if action == 'limit':
            fmt = 'txt'
        name = 'lh-%04d.%s' % (index, fmt)
        path = originals / name
        write_original(path, fmt, index, LIMIT_BYTES if action == 'limit' else None)
        data = path.read_bytes()
        rel = 'originals/' + name
        manifest[rel] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        row(plan, 'LH-%04d' % index, fmt, data, rel, action)

    extra = {}
    (adversarial / 'big-read.txt').write_bytes(txt_bytes(90000, 300 * 1024))
    (adversarial / 'extra.txt').write_bytes(txt_bytes(90001))
    write_epub(adversarial / 'second.epub', 90002)
    write_epub(adversarial / 'big-scan.epub', 90003, 16 * 1024 * 1024)
    for path in sorted(adversarial.iterdir()):
        data = path.read_bytes()
        rel = 'adversarial/' + path.name
        manifest[rel] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        extra[path.name] = rel

    plan_text = ''.join('\t'.join(str(field) for field in line) + '\n' for line in plan)
    (root / 'plan.tsv').write_text(plan_text, encoding='utf-8')

    small = plan[:40]
    big_rel = extra['big-read.txt']
    extra_rel = extra['extra.txt']
    adversarial_plan = [
        ('A000', 'txt', manifest[big_rel]['sha256'], manifest[big_rel]['bytes'], big_rel, 'map'),
        ('A001', 'txt', manifest[extra_rel]['sha256'], manifest[extra_rel]['bytes'], extra_rel, 'map'),
    ]
    for offset, line in enumerate(small):
        adversarial_plan.append(('A%03d' % (2 + offset),) + tuple(line[1:]))
    second = extra['second.epub']
    adversarial_plan.append(('A042', 'epub', manifest[second]['sha256'], manifest[second]['bytes'], second, 'map'))
    victim = plan[40]
    adversarial_plan.append(('A043', victim[1], victim[2], victim[3], victim[4], 'map'))
    assert len(adversarial_plan) == 44, len(adversarial_plan)
    (root / 'adversarial.tsv').write_text(
        ''.join('\t'.join(str(f) for f in line) + '\n' for line in adversarial_plan), encoding='utf-8')

    (root / 'manifest.json').write_text(json.dumps({
        'plan_rows': ROWS,
        'verified_rows': VERIFIED,
        'limit_book_bytes': LIMIT_BYTES,
        'files': manifest,
    }, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'rows': ROWS, 'files': len(manifest), 'root': str(root)}))


if __name__ == '__main__':
    main(sys.argv[1])
