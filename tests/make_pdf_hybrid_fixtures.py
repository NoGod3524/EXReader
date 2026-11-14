"""Original hybrid fixtures; Python standard library only. Office PDFs are copied unmodified."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / 'tests/fixtures/pdf-hybrid-real'
EDGE = ROOT / 'tests/fixtures/pdf-hybrid-edge'


def office():
    REAL.mkdir(exist_ok=True)
    manifest = []
    for name, pages, producer in [('pptx-1', 1, 'PowerPoint'), ('pptx-20', 20, 'PowerPoint'),
                                  ('word-5', 5, 'Word'), ('excel-1', 1, 'Excel'),
                                  ('chinese', 1, 'PowerPoint'), ('image-only', 1, 'PowerPoint')]:
        source = ROOT / 'build/pdf-hybrid-office' / (name + '.pdf')
        data = source.read_bytes()
        match = re.search(rb'/XRefStm\s+(\d+)', data)
        assert match, f'{name}: not hybrid; refused admission'
        offset = int(match[1])
        assert re.match(rb'\d+ 0 obj\s*<<\s*/Type\s*/XRef', data[offset:])
        shutil.copyfile(source, REAL / source.name)
        manifest.append(dict(file=source.name, pages=pages, producer=producer, hybrid=True,
                             has_xrefstm=True, xrefstm=offset, bytes=len(data),
                             sha256=hashlib.sha256(data).hexdigest()))
    (REAL / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def rc4(key, data):
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    i = j = 0
    result = bytearray()
    for value in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        result.append(value ^ state[(state[i] + state[j]) % 256])
    return bytes(result)


def linearized():
    """Single-page, two-xref layout with forward /Prev and fixed-width hints.

    The acceptance target is sequential opening; the reader does not use hints.
    """
    data = bytearray(b'%PDF-1.5\n%\x80\x81\x82\x83\n')
    offsets = {}

    def obj(n, body):
        offsets[n] = len(data)
        data.extend(f'{n} 0 obj\n'.encode() + body + b'\nendobj\n')

    def stream(n, payload, extra=b''):
        obj(n, b'<< /Length ' + str(len(payload)).encode() + b' ' + extra + b' >>\nstream\n' + payload + b'\nendstream')

    obj(10, b'<< /Linearized 1 /L LLLLLLLLLL /H [HHHHHHHHHH JJJJJJJJJJ] /O 3 /E EEEEEEEEEE /N 1 /T TTTTTTTTTT >>')
    first = len(data)
    data.extend(b'xref\n0 12\n')
    row_at = len(data)
    data.extend(b'0000000000 00000 f \n' * 12)
    data.extend(b'trailer\n<< /Size 12 /Root 1 0 R /Prev PPPPPPPPPP /XRefStm XXXXXXXXXX >>\nstartxref\n0\n%%EOF\n')
    obj(1, b'<< /Type /Catalog /Pages 2 0 R >>')
    obj(2, b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>')
    hint_start = len(data)
    hint_marker = bytes(range(60))
    stream(9, hint_marker, b'/S 36')
    hint_length = len(data) - hint_start
    obj(3, b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> /Contents 4 0 R >>')
    content_start = len(data)
    stream(4, b'0 0.5 1 rg 20 20 140 140 re f\n')
    content_length = len(data) - content_start
    stream(6, struct.pack('>BIH', 1, offsets[3], 0), b'/Type /XRef /Size 12 /W [1 4 2] /Index [3 1]')
    end_first = len(data)
    main = len(data)
    data.extend(b'xref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 12 /Root 1 0 R >>\n')
    data.extend(f'startxref\n{first}\n%%EOF\n'.encode())
    for n in range(12):
        offset = 3 if n == 3 else offsets.get(n, 0)
        row = f'{offset:010d} {65535 if n == 0 else 0:05d} {"n" if n in offsets and n != 3 else "f"} \n'.encode()
        data[row_at + n * 20:row_at + (n + 1) * 20] = row
    for marker, value in [(b'LLLLLLLLLL', len(data)), (b'HHHHHHHHHH', hint_start),
                          (b'JJJJJJJJJJ', hint_length), (b'EEEEEEEEEE', end_first),
                          (b'TTTTTTTTTT', main + len(b'xref\n0 1\n')), (b'PPPPPPPPPP', main),
                          (b'XXXXXXXXXX', offsets[6])]:
        data[:] = data.replace(marker, f'{value:010d}'.encode(), 1)
    page_hint = struct.pack('>IIHIHIHIHHHHH', 3, offsets[3], 0, end_first - offsets[3], 0,
                            content_start - offsets[3], 0, content_length, 0, 0, 0, 0, 1)
    shared_hint = struct.pack('>IIIIHIH', 0, 0, 0, 0, 0, 0, 0)
    assert len(page_hint) == 36 and len(shared_hint) == 24
    return data.replace(hint_marker, page_hint + shared_hint, 1)


def generate(kind):
    if kind == 'linearized':
        return linearized()
    data = bytearray(b'%PDF-1.5\n%\x80\x81\x82\x83\n')
    offsets = {}

    def obj(number, body):
        offsets[number] = len(data)
        data.extend(f'{number} 0 obj\n'.encode() + body + b'\nendobj\n')
        return offsets[number]

    def stream(number, payload, attrs=b''):
        return obj(number, b'<< /Length ' + str(len(payload)).encode() + b' ' + attrs +
                   b' >>\nstream\n' + payload + b'\nendstream')

    def table(previous=None, supplemental=None, encrypt=b''):
        at = len(data)
        data.extend(b'xref\n0 12\n0000000000 65535 f \n')
        for n in range(1, 12):
            # Free-list pointer deliberately equals the missing page number.
            free = n not in offsets
            data.extend(f'{(3 if n == 3 and free else offsets.get(n, 0)):010d} 00000 {"f" if free else "n"} \n'.encode())
        trailer = b'trailer\n<< /Size 12 /Root 1 0 R ' + encrypt
        if previous is not None:
            trailer += f' /Prev {previous}'.encode()
        if supplemental is not None:
            trailer += f' /XRefStm {supplemental}'.encode()
        data.extend(trailer + b' >>\n')
        return at

    def finish(at):
        data.extend(f'startxref\n{at}\n%%EOF\n'.encode())

    obj(1, b'<< /Type /Catalog /Pages 2 0 R >>')
    obj(2, b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>')
    page = b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> /Contents 4 0 R >>'
    content = b'0 0.5 1 rg 20 20 140 140 re f\n'
    encrypt = b''
    if kind == 'encrypted-conflict':
        pad = bytes.fromhex('28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a')
        identifier = hashlib.md5(b'hybrid-original-fixture').digest()
        owner = rc4(hashlib.md5((b'owner' + pad)[:32]).digest()[:5], pad)
        key = hashlib.md5(pad + owner + struct.pack('<i', -4) + identifier).digest()[:5]
        user = rc4(key, pad)
        objkey = hashlib.md5(key + b'\x04\x00\x00\x00\x00').digest()[:10]
        content = rc4(objkey, content)
        obj(7, b'<< /Filter /Standard /V 1 /R 2 /O <' + owner.hex().encode() +
            b'> /U <' + user.hex().encode() + b'> /P -4 >>')
        obj(8, b'<< /Filter /UnsupportedConflictMustNotBeUsed >>')
        encrypt = b'/Encrypt 7 0 R /ID [<' + identifier.hex().encode() + b'><' + identifier.hex().encode() + b'>]'
    stream(4, content)
    if kind == 'objstm':
        stream(5, b'3 0 ' + page, b'/Type /ObjStm /N 1 /First 4')
        entry = (2, 5, 0)
    else:
        page_at = obj(3, page)
        entry = (1, page_at, 0)
    if kind == 'incremental':
        old = table()
        finish(old)
        # Latest page exists solely in the supplemental stream.
        entry = (1, obj(3, page.replace(b'200 200', b'240 240')), 0)
    offsets.pop(3, None)
    widths = b'[1 4 2]' if kind != 'bad-width' else b'[1 9 2]'
    index = b'[3 1]' if kind != 'bad-index' else b'[11 2]'
    row = struct.pack('>BIH', *entry)
    if kind == 'bad-truncated':
        row = row[:-1]
    attrs = b'/Type /XRef /Size 12 /W ' + widths + b' /Index ' + index
    if encrypt:
        attrs += b' /Encrypt 8 0 R'
    if kind == 'bad-truncated':
        xs = obj(6, b'<< /Length 7 ' + attrs + b' >>\nstream\n' + row + b'endstream')
    else:
        xs = stream(6, row, attrs)
    xref = table(old if kind == 'incremental' else None, xs, encrypt)
    finish(xref)
    return data


def edges():
    EDGE.mkdir(exist_ok=True)
    manifest = []
    for kind in ['incremental', 'free-entry', 'objstm', 'encrypted-conflict', 'linearized',
                 'bad-truncated', 'bad-width', 'bad-index']:
        data = generate(kind)
        (EDGE / (kind + '.pdf')).write_bytes(data)
        manifest.append(dict(file=kind + '.pdf', pages=-1 if kind.startswith('bad-') else 1,
                             encrypt_conflicts=int(kind == 'encrypted-conflict'),
                             security='encrypted' if kind == 'encrypted-conflict' else 'plain',
                             bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    (EDGE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--office', action='store_true', help='admit freshly exported Office PDFs')
    args = parser.parse_args()
    if args.office:
        office()
    edges()
