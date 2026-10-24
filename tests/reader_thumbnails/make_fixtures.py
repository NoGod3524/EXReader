# SPDX-License-Identifier: MIT
"""Actions-only: deterministic originals and independently computed thumbnail expectations.

The expected pixels come from the integer box filter written out here, not from the
module under test: fit-contain (never upscale), alpha-weighted averaging, fully
transparent output texels carry RGB 0.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile
import zlib


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)


def png(width, height, rgba):
    raw = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def image(width, height, pixel):
    out = bytearray()
    for y in range(height):
        for x in range(width):
            out += bytes(pixel(x, y))
    return bytes(out)


def fit(sw, sh, bw, bh):
    if sw <= bw and sh <= bh:
        return sw, sh
    if sw * bh >= sh * bw:
        return bw, max(1, min(bh, (sh * bw + sw // 2) // sw))
    return max(1, min(bw, (sw * bh + sh // 2) // sh)), bh


def thumb(rgba, sw, sh, bw, bh):
    ow, oh = fit(sw, sh, bw, bh)
    out = bytearray()
    for oy in range(oh):
        y0 = oy * sh // oh
        y1 = max(y0 + 1, -(-((oy + 1) * sh) // oh))
        for ox in range(ow):
            x0 = ox * sw // ow
            x1 = max(x0 + 1, -(-((ox + 1) * sw) // ow))
            sa = sr = sg = sb = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    r, g, b, a = rgba[(y * sw + x) * 4:(y * sw + x) * 4 + 4]
                    sa += a; sr += r * a; sg += g * a; sb += b * a
            n = (x1 - x0) * (y1 - y0)
            a = (sa + n // 2) // n
            if sa == 0:
                out += bytes((0, 0, 0, a))
            else:
                out += bytes(((sr + sa // 2) // sa, (sg + sa // 2) // sa, (sb + sa // 2) // sa, a))
    return ow, oh, bytes(out)


def epub(cover):
    def put(archive, name, data, store=False):
        info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); info.create_system = 3; info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
        archive.writestr(info, data)
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        put(z, 'mimetype', 'application/epub+zip', True)
        put(z, 'META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        put(z, 'book.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Thumbnail cover</dc:title></metadata><manifest><item id="text" href="text.xhtml" media-type="application/xhtml+xml"/>'
            + ('<item id="cover" href="cover.png" media-type="image/png" properties="cover-image"/>' if cover else '') + '</manifest><spine><itemref idref="text"/></spine></package>')
        put(z, 'text.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Thumbnail cover</title></head><body><p>Retained original book.</p></body></html>')
        if cover:
            put(z, 'cover.png', cover)
    return buffer.getvalue()


def pdf(pages):
    # pages: list of (width, height, content bytes)
    objects = {1: b'<< /Type /Catalog /Pages 2 0 R >>'}
    kids = []
    number = 3
    for width, height, content in pages:
        page, stream = number, number + 1
        kids.append(f'{page} 0 R')
        objects[page] = f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents {stream} 0 R /Resources << >> >>'.encode()
        objects[stream] = b'<< /Length %d >>\nstream\n' % len(content) + content + b'\nendstream'
        number += 2
    objects[2] = f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {len(kids)} >>'.encode()
    out = bytearray(b'%PDF-1.4\n')
    offsets = {}
    for index in sorted(objects):
        offsets[index] = len(out)
        out += b'%d 0 obj\n' % index + objects[index] + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    for index in sorted(objects):
        out += b'%010d 00000 n \n' % offsets[index]
    out += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, xref)
    return bytes(out)


def cbz(pages):
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        for name, data in pages:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); info.create_system = 3; info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, data)
    return buffer.getvalue()


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    files = {}
    pixels = {}
    def add_image(name, width, height, pixel):
        rgba = image(width, height, pixel)
        pixels[name] = (width, height, rgba)
        files[name + '.png'] = png(width, height, rgba)

    add_image('grad16x8', 16, 8, lambda x, y: (x * 16, y * 32, (x + y) * 8, 255))
    add_image('swap16x8', 16, 8, lambda x, y: ((x + y) * 8, y * 32, x * 16, 255))
    add_image('alpha8x8', 8, 8, lambda x, y: (255, 0, 0, 0) if x < 4 else ((0, 255, 0, 128) if x == 4 else (0, 0, 255, 255)))
    add_image('wide300x100', 300, 100, lambda x, y: (12, 34, 56, 255))
    add_image('tall100x300', 100, 300, lambda x, y: (12, 34, 56, 255))
    add_image('small10x10', 10, 10, lambda x, y: (x * 20, y * 20, 100, 255))
    # Genuinely non-uniform in every channel, with transparent, half-transparent and
    # opaque bands: a downscale that reads the wrong buffer, or that ignores alpha
    # weighting, cannot match this reference by accident.
    add_image('noise64x48', 64, 48,
              lambda x, y: ((x * 37 + y * 11) & 0xff, (x * 5 + y * 61) & 0xff, (x * 3 ^ y * 29) & 0xff,
                            (255, 200, 140, 90, 30, 0)[(x // 3 + y // 2) % 6]))
    mid = bytes((200, 100, 50, 255)) * (3000 * 3000)
    files['mid3000x3000.png'] = png(3000, 3000, mid)
    huge = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 30000, 30000, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0' * 16)) + chunk(b'IEND', b''))
    files['huge-dims.png'] = huge
    files['wide9000x1.png'] = png(9000, 1, bytes((1, 2, 3, 255)) * 9000)
    files['big4100x4100.png'] = png(4100, 4100, bytes((9, 8, 7, 255)) * (4100 * 4100))
    grad = files['grad16x8.png']
    files['truncated.png'] = grad[:len(grad) * 7 // 10]
    files['badmagic.png'] = b'not an image at all, just text\n' * 3

    files['cover-exact.epub'] = epub(files['alpha8x8.png'])
    files['cover-none.epub'] = epub(None)
    files['pages2.pdf'] = pdf([(200, 100, b'1 0 0 rg 0 0 100 100 re f 0 0 1 rg 100 0 100 100 re f'),
                               (100, 200, b'0 1 0 rg 0 0 100 200 re f')])
    files['pages2.cbz'] = cbz([('001.png', png(60, 90, bytes((200, 30, 30, 255)) * 5400)),
                               ('002.png', png(60, 90, bytes((30, 30, 200, 255)) * 5400))])
    manifest = {}
    for name, data in sorted(files.items()):
        (out / name).write_bytes(data)
        manifest[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    lines = []
    for name, box in [('grad16x8', (8, 8)), ('grad16x8', (5, 5)), ('swap16x8', (8, 8)), ('alpha8x8', (4, 4)), ('alpha8x8', (3, 3)),
                      ('alpha8x8', (8, 8)), ('small10x10', (64, 64)), ('small10x10', (4, 7)), ('wide300x100', (60, 60)), ('tall100x300', (60, 60)),
                      ('noise64x48', (64, 48)), ('noise64x48', (16, 12)), ('noise64x48', (7, 5)), ('noise64x48', (31, 9))]:
        width, height, rgba = pixels[name]
        ow, oh, data = thumb(rgba, width, height, *box)
        lines.append(f'{name} {box[0]} {box[1]} {ow} {oh} {data.hex()}')
    (out / 'expect.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'files': len(files), 'expectations': len(lines)}))


if __name__ == '__main__':
    main()
