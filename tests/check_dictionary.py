# SPDX-License-Identifier: MIT
"""Independent binary fixtures + oracle; no downloaded dictionaries in the repo."""
import argparse
import gzip
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib


def dictzip(data, length=97, optional=True):
    compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
    chunks = [compressor.compress(data[i:i+length]) + compressor.flush(zlib.Z_FULL_FLUSH)
              for i in range(0, len(data), length)]
    tail = compressor.flush(zlib.Z_FINISH)
    table = struct.pack('<HHH', 1, length, len(chunks)) + struct.pack('<'+'H'*len(chunks), *map(len, chunks))
    extra = (b'XY\x03\x00xyz' if optional else b'') + b'RA'+struct.pack('<H', len(table))+table
    header = b'\x1f\x8b\x08'+bytes([30 if optional else 4])+b'\0'*6+struct.pack('<H', len(extra))+extra
    if optional:
        header += b'fixture.dict\0comment\0'
        header += struct.pack('<H', zlib.crc32(header)&65535)
    return header+b''.join(chunks)+tail+struct.pack('<II', zlib.crc32(data), len(data))


def fixture(root, name='sample', entries=None, synonyms=None, compressed=True, bits=32, sequence='m', index_gzip=False):
    root.mkdir(parents=True, exist_ok=True)
    entries = entries or [(f'word{i:02}', f'n. definition {i}\n  second line, 中文'.encode()) for i in range(30)]
    entries = sorted(entries, key=lambda x: (x[0].lower(), x[0]))
    data, idx = b'', b''
    for word, definition in entries:
        idx += word.encode()+b'\0'+struct.pack('>QI' if bits == 64 else '>II', len(data), len(definition))
        data += definition
    stem = root/name
    stem.with_suffix('.dict.dz' if compressed else '.dict').write_bytes(dictzip(data) if compressed else data)
    stem.with_suffix('.idx.gz' if index_gzip else '.idx').write_bytes(gzip.compress(idx) if index_gzip else idx)
    syn = b''.join(word.encode()+b'\0'+struct.pack('>I', index) for word, index in (synonyms or []))
    if synonyms: stem.with_suffix('.syn').write_bytes(syn)
    stem.with_suffix('.ifo').write_text("StarDict's dict ifo file\nversion=3.0.0\n"+f'bookname={name}\nwordcount={len(entries)}\nidxfilesize={len(idx)}\nidxoffsetbits={bits}\nsynwordcount={len(synonyms or [])}\n'+(f'sametypesequence={sequence}\n' if sequence else ''), encoding='utf8')
    return stem.with_suffix('.ifo'), entries


def probe(exe, paths, words, ok=True):
    p = subprocess.run([str(exe), *map(str, paths)], input='\n'.join(words)+'\n', text=True,
                       encoding='utf8', capture_output=True)
    assert (p.returncode == 0) == ok, (p.returncode, p.stdout, p.stderr)
    rows = [json.loads(line) for line in p.stdout.splitlines()]
    if ok:
        assert len(rows) == len(paths) + (len(words) or 1), p.stdout
        assert [r['query'] for r in rows[len(paths):]] == (words or [''])
    return rows


def check(exe, root, group):
    if group == 'stardict':
        words = [(f'word{i:02}', f'n. definition {i}\n  second line, 中文'.encode()) for i in range(30)]
        syn = [(f'alias{i:02}', i) for i in range(10)]
        one, entries = fixture(root/'one', synonyms=syn, entries=words, bits=64)
        two, _ = fixture(root/'two', name='second', entries=words, compressed=False, index_gzip=True)
        queries = [w for w, _ in entries]+[f'alias{i:02}' for i in range(10)]+['WORD01', 'WORD05', 'WORD09', 'WORD12', 'WORD29']
        rows = probe(exe, [one], queries)
        assert rows[0]['wordcount'] == 30 and rows[0]['synwordcount'] == 10 and rows[0]['idxoffsetbits'] == 64
        for i, row in enumerate(rows[1:31]):
            assert row['status'] == 0 and row['results'][0]['word'] == entries[i][0]
            assert row['results'][0]['definition'] == entries[i][1].decode() and row['results'][0]['pos'] == 'n.'
            assert row['results'][0]['match'] == 0
        for i, row in enumerate(rows[31:41]): assert row['results'][0]['word'] == entries[i][0] and row['results'][0]['match'] == 2
        for row in rows[41:]: assert row['results'][0]['word'] == row['query'].lower() and row['results'][0]['match'] == 3
        merged = probe(exe, [one, two], ['word01'])[2]['results']
        assert [(r['dictionary'], r['dictionary_index']) for r in merged] == [('sample', 0), ('second', 1)]
        special = [('alpha'+str(i)+'tail', b'adj. prefix') for i in range(10)]+[('Straße', b'n. road'), ('Σίσυφος', b'n. myth')]
        path, _ = fixture(root/'prefix', entries=special)
        for row in probe(exe, [path], ['alpha'+str(i) for i in range(10)])[1:]:
            assert len(row['results']) == 1 and row['results'][0]['word'] == row['query']+'tail' and row['results'][0]['match'] == 1
        for row in probe(exe, [path], ['STRASSE', 'ΣΊΣΥΦΟΣ'])[1:]: assert len(row['results']) == 1 and row['results'][0]['match'] == 3
        # Stages, duplicates and original idx ordinals (ASCII-fold sorted, not byte-sorted).
        path, _ = fixture(root/'ordering', entries=[('a', b'first'), ('B', b'upper'), ('b', b'lower'), ('b', b'duplicate'), ('bc', b'prefix')], synonyms=[('b', 0), ('bcx', 1)])
        rows = probe(exe, [path], ['b', 'bcx', 'A', 'missing', ''])
        assert [r['definition'] for r in rows[1]['results']] == ['lower', 'duplicate']
        assert rows[2]['results'][0]['word'] == 'B' and rows[3]['results'][0]['word'] == 'a'
        assert not rows[4]['results'] and not rows[5]['results']
        path, _ = fixture(root/'long-alias', entries=[('word', b'meaning')], synonyms=[('alias'*80, 0)])
        assert probe(exe, [path], ['alias'*80])[1]['results'][0]['word']=='word'
    elif group == 'dictzip':
        entries = [(f'{chr(97+i)}word', (f'v. entry {i}\n'+('long text ' * (i*5+1))).encode()) for i in range(26)]
        path, entries = fixture(root, entries=entries)
        offset = 0
        rows = probe(exe, [path], [w for w, _ in entries])
        for row, (word, definition) in zip(rows[1:], entries):
            assert row['results'][0]['definition'].encode() == definition
            assert row['blocks'] == (offset+len(definition)-1)//97-offset//97+1
            assert row['inflated_bytes'] <= row['blocks']*97
            offset += len(definition)
        # Plain and compressed data must be byte-identical; boundary-exact entries.
        path, _ = fixture(root/'boundary', entries=[('a', b'a'*97), ('b', b'b'*194), ('z', b'z'*97)])
        rows = probe(exe, [path], ['a', 'b', 'z'])
        assert [r['blocks'] for r in rows[1:]] == [1, 2, 1]
    elif group == 'contracts':
        path, _ = fixture(root/'empty', entries=[('empty', b'')], compressed=False)
        assert probe(exe, [path], ['empty'])[1]['results'][0]['definition']==''
        path, _ = fixture(root/'markup', entries=[('hello', b'<p>n. hello &amp; world</p><li>one</li><br>two')], sequence='h')
        r = probe(exe, [path], ['hello'])[1]['results'][0]
        assert r['definition'] == 'n. hello & world\n• one\ntwo' and r['pos'] == 'n.'
        path, _ = fixture(root/'typed', entries=[('hello', b'tphonetic\0mmeaning\nline\0W\0\0\0\x03abc')], sequence='')
        assert probe(exe, [path], ['hello'])[1]['results'][0]['definition'] == 'phonetic\nmeaning\nline'
        path, _ = fixture(root/'sequence', entries=[('hello', b'phonetic\0n. meaning')], sequence='tm')
        assert probe(exe, [path], ['hello'])[1]['results'][0]['definition'] == 'phonetic\nn. meaning'
        for mode in ('wordcount', 'idxsize', 'truncated', 'offset', 'syn', 'gzip', 'ra', 'header_crc', 'bad_type', 'utf8'):
            path, _ = fixture(root/mode, entries=[('a', b'meaning')], synonyms=[('alias', 0)])
            idx = path.with_suffix('.idx'); dz = path.with_suffix('.dict.dz')
            if mode == 'wordcount': path.write_text(path.read_text().replace('wordcount=1\n', 'wordcount=2\n'))
            if mode == 'idxsize': idx.write_bytes(idx.read_bytes()+b'x')
            if mode == 'truncated': dz.write_bytes(dz.read_bytes()[:14])
            if mode == 'offset': idx.write_bytes(b'a\0'+struct.pack('>II', 0xffffffff, 7))
            if mode == 'syn': path.with_suffix('.syn').write_bytes(b'alias\0'+struct.pack('>I', 1))
            if mode == 'gzip': dz.write_bytes(gzip.compress(b'meaning'))
            if mode == 'ra': dz.write_bytes(dz.read_bytes().replace(b'RA', b'ZZ', 1))
            if mode == 'header_crc':
                data=bytearray(dz.read_bytes());data[4]^=1;dz.write_bytes(data)
            if mode == 'utf8': idx.write_bytes(b'\xff\0'+idx.read_bytes()[2:])
            if mode == 'bad_type':
                path.write_text(path.read_text().replace('sametypesequence=m', 'sametypesequence=tm'))
                assert probe(exe, [path], ['a'])[1]['status'] != 0
            else: probe(exe, [path], [], ok=False)
        # Valid table, corrupt compressed body: fail on demand without returning partial data.
        path, _=fixture(root/'body', entries=[('a', b'definition')])
        dz=path.with_suffix('.dict.dz');data=bytearray(dz.read_bytes());start=data.index(b'comment\0')+10;data[start]=0xff;dz.write_bytes(data)
        assert probe(exe, [path], ['a'])[1]['status'] != 0
    elif group == 'dictd':
        alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        def base64(n):
            s=alphabet[n%64]
            while n>=64: n//=64;s=alphabet[n%64]+s
            return s
        data=b'v. begin\n  next linen. end';path=root/'dictd.index'
        path.write_text('alpha\tA\t'+base64(19)+'\nzulu\t'+base64(19)+'\t'+base64(len(data)-19)+'\n')
        path.with_suffix('.dict.dz').write_bytes(dictzip(data))
        rows=probe(exe, [path], ['alpha', 'zulu', 'ALPHA', 'zul'])
        assert rows[0]['wordcount']==2 and rows[0]['version']=='dictd'
        assert rows[1]['results'][0]['definition']==data[:19].decode()
        assert rows[2]['results'][0]['definition']==data[19:].decode()
        assert rows[3]['results'][0]['match']==3 and rows[4]['results'][0]['match']==1
        path.write_text('alpha\t?\tB\n');probe(exe, [path], [], ok=False)
    print(group+': PASS')


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('probe', type=Path);p.add_argument('group');a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='exr-dictionary-') as d: check(a.probe.resolve(), Path(d), a.group)
