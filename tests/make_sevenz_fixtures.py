#!/usr/bin/env python3
"""Original, deterministic 7Z fixtures; only Python's standard library is used.

The encoder is independent of the C reader. Reference 7-Zip checks and separately
7-Zip-created fixtures are described in sevenz-anchorstats.md.
"""
from pathlib import Path
import lzma
import struct
import zlib

ROOT = Path(__file__).resolve().parent / 'fixtures' / 'sevenz'
TEXT = b'The quick brown fox jumps over the lazy reader.\n'
DATA = TEXT * 257 + bytes(range(256)) * 8


def vu(n):
    for extra in range(8):
        if n < 1 << (7 + 7 * extra):
            return bytes([(256 - (256 >> extra)) | (n >> (8 * extra))]) + n.to_bytes(8, 'little')[:extra]
    return b'\xff' + struct.pack('<Q', n)


def crc(data):
    return struct.pack('<I', zlib.crc32(data))


def bits(values):
    result = bytearray((len(values) + 7) // 8)
    for i, value in enumerate(values):
        if value:
            result[i // 8] |= 128 >> (i % 8)
    return bytes(result)


def encode(chunks, method, props=(3, 0, 2), distance=7):
    raw = b''.join(chunks)
    filters, coders = [], []
    if 'delta' in method:
        filters.append(dict(id=lzma.FILTER_DELTA, dist=distance))
    if 'lzma' in method:
        lc, lp, pb = props
        two = method.endswith('2')
        filters.append(dict(id=lzma.FILTER_LZMA2 if two else lzma.FILTER_LZMA1,
                            dict_size=1 << 20, lc=lc, lp=lp, pb=pb))
        packed = lzma.compress(raw, format=lzma.FORMAT_RAW, filters=filters)
        codec = b'\x21\x21\x01\x10' if two else b'\x23\x03\x01\x01\x05' + bytes([(pb * 5 + lp) * 9 + lc]) + struct.pack('<I', 1 << 20)
        coders.append(codec)
    elif method == 'delta':
        packed = bytes((b - (raw[i-distance] if i >= distance else 0)) % 256 for i, b in enumerate(raw))
    else:
        packed = raw
        coders.append(b'\x01\x00')
    if 'delta' in method:
        coders.append(b'\x21\x03\x01' + bytes([distance - 1]))
    folder = vu(len(coders)) + b''.join(coders)
    if len(coders) == 2:
        folder += b'\x01\x00'  # decoder output 0 -> decoder input 1
    return dict(raw=raw, packed=packed, folder=folder, chunks=chunks, coders=len(coders))


def stream_info(groups, position=0):
    pack = b'\x06' + vu(position) + vu(len(groups)) + b'\x09'
    pack += b''.join(vu(len(g['packed'])) for g in groups)
    pack += b'\x0a\x01' + b''.join(crc(g['packed']) for g in groups) + b'\0'
    unpack = b'\x07\x0b' + vu(len(groups)) + b'\0' + b''.join(g['folder'] for g in groups)
    unpack += b'\x0c' + b''.join(vu(len(g['raw'])) * g['coders'] for g in groups)
    unpack += b'\x0a\x01' + b''.join(crc(g['raw']) for g in groups) + b'\0'
    subs = b'\x08\x0d' + b''.join(vu(len(g['chunks'])) for g in groups) + b'\x09'
    subs += b''.join(vu(len(c)) for g in groups for c in g['chunks'][:-1])
    subs += b'\x0a\x01' + b''.join(crc(c) for g in groups if len(g['chunks']) != 1 for c in g['chunks']) + b'\0\0'
    return pack + unpack + subs


def wrap(body, header):
    start = struct.pack('<QQ', len(body), len(header)) + crc(header)
    return b"7z\xbc\xaf\x27\x1c\0\x04" + crc(start) + start + body + header


def archive(files, groups, compressed_header=True):
    header = b'\x01'
    if groups:
        header += b'\x04' + stream_info(groups)
    header += b'\x05' + vu(len(files))
    empty = [not content for _, content in files]
    if any(empty):
        values = bits(empty)
        header += b'\x0e' + vu(len(values)) + values
        values = bits([content is not None for _, content in files if not content])
        header += b'\x0f' + vu(len(values)) + values
    names = b'\0' + ''.join(name + '\0' for name, _ in files).encode('utf-16le')
    header += b'\x11' + vu(len(names)) + names + b'\0\0'
    body = b''.join(g['packed'] for g in groups)
    if compressed_header:
        encoded = encode([header], 'lzma')
        next_header = b'\x17' + stream_info([encoded], len(body))
        return wrap(body + encoded['packed'], next_header)
    return wrap(body, header)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    def save(name, data):
        (ROOT / (name + '.7z')).write_bytes(data)
    chunks = [DATA, b'Single requested file.\n']
    save('lzma2-solid', archive(list(zip(['first.txt', 'second.txt'], chunks)), [encode(chunks, 'lzma2')]))
    nested = [('漫画', None), ('漫画/卷一', None), ('漫画/卷一/page.txt', b'Nested chapter text.\n'),
              ('漫画/empty.txt', b''), ('empty-directory', None)]
    save('nested', archive(nested, [encode([nested[2][1]], 'delta-lzma')]))
    methods = ['copy', 'lzma', 'lzma2', 'delta', 'delta-lzma2']
    groups = [encode([DATA], m) for m in methods]
    save('codecs', archive([(m + '.bin', DATA) for m in methods], groups, False))
    groups = [encode([DATA], m, p) for m in ('lzma', 'lzma2') for p in ((0, 0, 0), (2, 1, 1), (4, 0, 4))]
    save('properties', archive([(f'property-{i}.bin', DATA) for i in range(len(groups))], groups))
    for label, path in [('traversal', '../escape.txt'), ('backslash', 'a\\..\\escape.txt'),
                        ('nested-traversal', 'a/../escape.txt'), ('absolute', '/escape.txt'),
                        ('drive', 'C:/escape.txt'), ('ads', 'safe.txt:stream'), ('dot', './escape.txt')]:
        save(label, archive([(path, b'x')], [encode([b'x'], 'copy')], False))
    save('empty', archive([('empty.txt', b''), ('dir', None)], []))
    # These malformed inputs have correct signature and header CRCs, reaching
    # parser checks beyond the outer checksum boundary.
    save('oversized-count', wrap(b'', b'\x01\x05' + vu(10001) + b'\0\0'))
    save('truncated-name', wrap(b'', b'\x01\x05\x01\x11\x03\0x\0\0\0'))
    save('invalid-utf16', wrap(b'', b'\x01\x05\x01\x11\x05\0\0\xdc\0\0\0\0'))
    bad = bytearray(archive([('x', b'x')], [encode([b'x'], 'copy')], False))
    # Unsupported coder with a one-byte ID; preserve valid CRCs.
    header_at = 32 + struct.unpack_from('<Q', bad, 12)[0]
    header = bytes(bad[header_at:]).replace(b'\x07\x0b\x01\0\x01\x01\0', b'\x07\x0b\x01\0\x01\x01\x7f', 1)
    save('unsupported', wrap(b'x', header))


if __name__ == '__main__':
    main()
