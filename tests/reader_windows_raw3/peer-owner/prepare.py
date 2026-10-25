"""Actions-only lossless expected-capture framing of the already authenticated Mac packet."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import struct

MANIFEST = 'f0960b35374e12827a8966f7022dc3f632e44c87419ca1482288386fb8031566'


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = (args.packet / 'manifest.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST
    manifest = json.loads(raw)
    assert manifest['schema'] == 1
    assert manifest['sender']['source_sha'] == '15dab6b2270dc296ed6239db67ced2e22d255e65'
    assert str(manifest['sender']['run_id']) == '40196978163' and str(manifest['sender']['attempt']) == '1'
    books, wires, records = (manifest[key] for key in ('originals', 'revisions', 'reading_records'))
    assert (len(books), len(wires), len(records)) == (4, 15, 11)
    assert {row['format'] for row in books} == {'txt', 'epub', 'pdf', 'cbz'}
    ids = {row['id'] for row in wires}
    assert len(ids) == 15 and len({row['revision_id'] for row in records}) == 11
    assert all(set(row['parents']) <= ids for row in wires)
    out = bytearray(b'EXRPEER1')

    def number(value):
        value = int(value)
        assert 0 <= value <= 0xffffffffffffffff
        out.extend(struct.pack('<Q', value))

    def field(value):
        if value is None:
            out.extend(struct.pack('<I', 0xffffffff))
        else:
            data = value.encode('utf-8') if isinstance(value, str) else value
            assert len(data) <= 262144
            out.extend(struct.pack('<I', len(data)))
            out.extend(data)

    field(MANIFEST)
    for rows in (books, wires, records):
        number(len(rows))
        for row in rows:
            if rows is books:
                assert re.fullmatch(r'(txt|epub|pdf|cbz):[0-9a-f]{64}', row['book_key'])
                assert row['book_key'] == row['format'] + ':' + row['sha256']
                data = (args.packet / (row['sha256'] + '.' + row['format'])).read_bytes()
                assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
                for key in ('book_key', 'format', 'sha256'):
                    field(row[key])
                number(row['bytes'])
            elif rows is wires:
                assert re.fullmatch('[0-9a-f]{32}', row['id'])
                data = (args.packet / (row['id'] + '.json')).read_bytes()
                assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
                field(row['id']); field(row['sha256']); number(row['bytes'])
            else:
                capture = row['capture']
                assert row['revision_id'] in ids and len(capture['numbers']) == 4
                assert len(capture['route']) == 5 and len(capture['selectors']) == 3
                field(row['revision_id']); field(row['role']); field(row['kind']); number(row['anchor_version'])
                for value in capture['numbers']:
                    assert isinstance(value, str) and re.fullmatch('0|[1-9][0-9]*', value)
                    number(value)
                for value in capture['route']:
                    assert value is None or '\0' not in value
                    field(value)
                for value in capture['selectors']:
                    field(None if value is None else base64.b64decode(value, validate=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    print(json.dumps(dict(manifest_sha256=MANIFEST, expected_sha256=hashlib.sha256(out).hexdigest(),
                         books=4, wires=15, records=11, retained_NULL_and_empty_distinct=True)), flush=True)


if __name__ == '__main__':
    main()
