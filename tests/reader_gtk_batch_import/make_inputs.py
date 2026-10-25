# SPDX-License-Identifier: MIT
"""Actions-only native folder-import fixtures, frozen expectations before SDK use."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


def main(output):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    output.mkdir(parents=True)
    root = output / 'folder 书籍'
    root.mkdir()
    for index in range(35):
        # The accepted original spans pages for the post-import NEXT/PREVIOUS
        # check; PREVIOUS on its initial page is correctly rejected by the host.
        (root / ('Book %02d 文字.txt' % index)).write_text(('Folder %02d book. Native reading stays usable.\n' % index) * (120 if index == 0 else 12), encoding='utf-8')
    shutil.copyfile(root / 'Book 00 文字.txt', root / 'Exact duplicate.txt')
    (root / 'Broken.epub').write_bytes(b'not an EPUB archive')
    (root / 'ignored.bin').write_bytes(b'unsupported')
    (root / 'nested').mkdir()
    (root / 'nested/Nested.txt').write_text('Explicit recursive import only.\n', encoding='utf-8')
    (output / 'outside.txt').write_text('Outside symlink must never enter the bookshelf.\n', encoding='utf-8')
    (root / 'linked.txt').symlink_to(output / 'outside.txt')
    (root / 'linked-folder').symlink_to(root / 'nested', target_is_directory=True)
    os.mkfifo(root / 'pipe.txt')
    (output / 'linked-root').symlink_to(root, target_is_directory=True)
    for name in ('cancel', 'closing'):
        folder = output / name
        folder.mkdir()
        for index in range(96):
            (folder / ('%03d.txt' % index)).write_text(('%s %03d readable native source\n' % (name, index)) * 24)
    deep = output / 'depth'
    deep.mkdir()
    for index in range(10):
        deep = deep / ('level%d' % index)
        deep.mkdir()
    (deep / 'Too deep.txt').write_text('The default depth budget must truncate before here.\n')
    changed = output / 'changed'
    changed.mkdir()
    for name in ('one.txt', 'two.txt'):
        (changed / name).write_text('Original selected path %s.\n' % name)
    repair = output / 'repair'
    repair.mkdir()
    (repair / 'Kept after catalog failure.txt').write_text('The SDK committed source survives a product writer failure.\n')
    files = []
    for path in sorted(output.rglob('*')):
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            files.append(dict(relative=path.relative_to(output).as_posix(), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    (output / 'manifest.json').write_text(json.dumps(dict(files=files, flat_candidates=37, flat_new=35, flat_duplicates=1, flat_failed=1), ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
