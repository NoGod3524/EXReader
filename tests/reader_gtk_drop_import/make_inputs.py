# SPDX-License-Identifier: MIT
"""Actions-only source files and independently declared import expectations."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


def main(fixtures, output):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    output.mkdir(parents=True)
    mixed = output / 'selected files 书籍'
    mixed.mkdir()
    names = [('Selected 书籍.TXT', 'sample.txt', 'TXT'), ('sample.html', 'sample.html', 'HTML'),
             ('sample.fb2', 'sample.fb2', 'FB2'), ('sample.epub', 'sample.epub', 'EPUB'),
             ('sample.docx', 'sample.docx', 'DOCX'), ('sample.rtf', 'sample.rtf', 'RTF'),
             ('sample.mobi', 'sample.mobi', 'MOBI'), ('sample.azw3', 'kf8-basic.azw3', 'MOBI'),
             ('selected.pdf', 'pdf-public-text.pdf', 'PDF'), ('selected.cbz', 'comic.cbz', 'CBZ')]
    expected = []
    for name, source, fmt in names:
        path = mixed / name
        shutil.copyfile(fixtures / source, path)
        expected.append(dict(path=str(path.resolve()), format=fmt, bytes=path.stat().st_size,
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    duplicate = mixed / 'Exact duplicate.epub'
    shutil.copyfile(mixed / 'sample.epub', duplicate)
    bad = mixed / 'Broken.epub'
    bad.write_bytes(b'not an EPUB archive')
    directory = mixed / 'Explicit directory'
    directory.mkdir()
    (directory / 'Never recurse.txt').write_text('This directory was not explicitly imported.\n')
    outside = output / 'Outside.txt'
    outside.write_text('A symbolic link must never import this original.\n')
    link = mixed / 'Linked.txt'
    link.symlink_to(outside)
    fifo = mixed / 'Pipe.txt'
    os.mkfifo(fifo)
    # 20 distinct delivered entries: 10 new, 1 exact duplicate, 9 refusals.
    entries = [row['path'] for row in expected] + [str(duplicate), str(bad), str(directory), str(link)]
    uris = [Path(path).resolve().as_uri() if Path(path) != link else link.absolute().as_uri() for path in entries]
    uris += ['https://127.0.0.1:9/remote.epub', 'file://another-host/unavailable.epub', 'mtp://device/promised.epub',
             (mixed / 'Missing.txt').as_uri(), 'file:///invalid%ZZ', fifo.as_uri()]
    uris.insert(1, uris[0])
    (output / 'mixed.uris').write_bytes(('\ufeff# Native exact file selection\r\n' + '\r\n'.join(uris) + '\r\n').encode())
    bulk, overflow = [], []
    for group, count, rows in [('bulk', 40, bulk), ('overflow', 300, overflow)]:
        folder = output / group
        folder.mkdir()
        for index in range(count):
            path = folder / ('%03d.txt' % index)
            path.write_text('%s original %03d: native owner keeps exact bytes.\n' % (group, index))
            rows.append(dict(path=str(path.resolve()), format='TXT', bytes=path.stat().st_size,
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        (output / (group + '.uris')).write_text('\n'.join(Path(row['path']).as_uri() for row in rows) + '\n')
    (output / 'bulk.gnome').write_text('cut\n' + (output / 'bulk.uris').read_text())
    (output / 'empty.uris').write_text('# no selected entries\n\r\n')
    (output / 'oversize.uris').write_bytes(b'#' + b'x' * (1024 * 1024))
    originals = []
    for path in output.rglob('*'):
        if path.is_file() and not path.is_symlink():
            originals.append(dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (output / 'manifest.json').write_text(json.dumps(dict(mixed=expected, bulk=bulk, overflow=overflow,
        mixed_counts=dict(items=20, duplicates=1, imported=10, failed=9), originals=originals), ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
