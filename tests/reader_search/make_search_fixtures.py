# SPDX-License-Identifier: MIT
"""Generate reader-search originals in Actions only; never run locally.

Standard library only. Stored ZIP entries keep Windows and Linux originals
byte-identical; the manifest records each original's size and SHA-256.
"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_reading_state'))
from make_fixtures import entry, xhtml  # noqa: E402  (stored-entry ZIP helper and XHTML wrapper)

LONG = 'is long enough to give more than thirty two scalars of context'
NEEDLE = 'NEEDLE-ALPHA-BETA-GAMMA-' * 33  # 792 ASCII bytes, repeated in every long paragraph
LONG_PARAGRAPHS = 1500


def txt():
    block = (f'Ambiguous block line one {LONG}.\nAMBIGUOUS TARGET\n'
             f'Ambiguous block line three {LONG}.\n')
    lines = ['开头中文段落：书内搜索🙂测试。\n',
             'repeat-phrase one. repeat-phrase two. repeat-phrase three. repeat-phrase four.\n',
             'overlap: aaaaa and aaaa end.\n',
             block, block]
    lines += [f'Z-hit {i:03d}\n' for i in range(250)]
    lines += [f'E-hit {i:03d}\n' for i in range(100)]
    lines += ['emoji pair 🙂🎉 and 🙂🎉 again\n', '尾声段落：终点']
    return ''.join(lines).encode('utf-8')


def container(book, name):
    entry(book, 'mimetype', b'application/epub+zip')
    entry(book, 'META-INF/container.xml',
          b'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
          b'<rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')


def opf(title, items, spine):
    manifest = ''.join(f'<item id="{i}" href="{i}.xhtml" media-type="application/xhtml+xml"/>' for i in items)
    refs = ''.join(f'<itemref idref="{i}"/>' for i in spine)
    return ('<?xml version="1.0" encoding="UTF-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
            f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">{title}</dc:identifier>'
            f'<dc:title>{title}</dc:title><dc:language>zh</dc:language></metadata>'
            f'<manifest>{manifest}</manifest><spine>{refs}</spine></package>').encode('utf-8')


def epub(path):
    with zipfile.ZipFile(path, 'w') as book:
        container(book, 'book.epub')
        entry(book, 'book.opf', opf('reader-search', ['a', 'b'], ['a', 'b', 'a']))
        entry(book, 'a.xhtml', xhtml('<p>Alpha SEARCHTOKEN 开头 one. Repeated spine paragraph body '
                                     f'{LONG}. alpha-to</p>'))
        entry(book, 'b.xhtml', xhtml('<p>-beta 第二章节 SEARCHTOKEN 🙂 SEARCHTOKEN 终。</p>'
                                     '<p>unique-b-only 🙂 章末</p>'))


def long_epub(path):
    paragraphs = []
    for i in range(LONG_PARAGRAPHS):
        filler = ' '.join(f'{(i * 7 + k) % 1000:03d}x' for k in range(18))
        paragraphs.append(f'<p>P{i:04d} {filler} {NEEDLE} {filler}</p>')
    with zipfile.ZipFile(path, 'w') as book:
        container(book, 'long.epub')
        entry(book, 'book.opf', opf('reader-search-long', ['c'], ['c']))
        entry(book, 'c.xhtml', xhtml(''.join(paragraphs)))


def pdf(path):
    pages = [
        ['Fixed page one. Shared quote across pages.', 'Second distinct line on page one only.'],
        ['Identical context abcdefghijklmnopqrstuvwxyz 0123456789 selection target identical suffix abcdefghijklmnopqrstuvwxyz 0123456789'] * 3,
        [],
        ['Fixed page four. Shared quote across pages.', 'Closing line.'],
    ]
    count = len(pages)
    font = 3 + count * 2
    kids = ' '.join(f'{3 + i} 0 R' for i in range(count))
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', f'<< /Type /Pages /Count {count} /Kids [{kids}] >>'.encode()]
    for i in range(count):
        objects.append((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 {font} 0 R >> >> '
                        f'/Contents {3 + count + i} 0 R >>').encode())
    for lines in pages:
        content = ('BT /F1 12 Tf 36 720 Td ' + ' 0 -32 Td '.join(f'({line}) Tj' for line in lines) + ' ET') if lines else ''
        stream = content.encode('ascii')
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream')
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    data = bytearray(b'%PDF-1.7\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref = len(data)
    data += f'xref\n0 {len(offsets)}\n'.encode() + b'0000000000 65535 f \n'
    for offset in offsets[1:]:
        data += f'{offset:010d} 00000 n \n'.encode()
    data += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    path.write_bytes(bytes(data))


def main(folder):
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'book.txt').write_bytes(txt())
    epub(folder / 'book.epub')
    long_epub(folder / 'long.epub')
    pdf(folder / 'pages.pdf')
    manifest = {}
    for role, name in (('txt', 'book.txt'), ('epub', 'book.epub'), ('pdf', 'pages.pdf'), ('long', 'long.epub')):
        data = (folder / name).read_bytes()
        manifest[role] = {'file': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
