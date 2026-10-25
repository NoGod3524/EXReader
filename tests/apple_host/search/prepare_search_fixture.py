# SPDX-License-Identifier: MIT
"""Add exactly 32 real text hits to the existing cloud-only search EPUB."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    args = parser.parse_args()
    source = args.resources / 'Sample.epub'
    query = 'EXRSEARCH32TOKEN'
    with zipfile.ZipFile(source) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    assert all(query.encode() not in data for _, data in entries)
    paragraphs = ''.join('<p>Unique search tail %04d before %s after tail %04d.</p>' % (index, query, index)
                         for index in range(32)).encode()
    changed = 0
    with zipfile.ZipFile(source, 'w') as archive:
        for item, data in entries:
            if item.filename == 'OPS/c0.xhtml':
                assert data.count(b'</body>') == 1
                data = data.replace(b'</body>', paragraphs + b'</body>')
                changed += 1
            archive.writestr(item, data)
    assert changed == 1
    with zipfile.ZipFile(source) as archive:
        assert sum(archive.read(name).count(query.encode()) for name in archive.namelist()) == 32
    expected = args.resources / 'search-expected.json'
    expected.write_text(json.dumps({'query': query, 'count': 32, 'source': 'Sample.epub'}, sort_keys=True) + '\n')
    path = args.resources / 'manifest.json'
    manifest = json.loads(path.read_text())
    for file in (source, expected):
        manifest[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
