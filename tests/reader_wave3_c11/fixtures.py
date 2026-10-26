#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Author the C11 reading fixtures in Actions.

The two books are the same deterministic EPUB/TXT shapes the existing host
walkthrough uses. `c11-notes.txt` is long enough for several reflow pages and
carries one unique token near its end, so the real in-book search and the jump
history can prove a later landing. `c11-layout.epub` carries three authored
chapters and a real EPUB 3 navigation document for the directory entry.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from build_android_host import epub  # noqa: E402  (same deterministic writer)

TXT_TITLE = 'C11 notes sample'
EPUB_TITLE = 'C11 layout sample'
QUERY = 'quixotic-c11-marker'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def txt_body():
    parts = ['C11 reflow notes for the reviewed reader host.']
    for index in range(1, 161):
        parts.append(
            'Paragraph %03d keeps the page layout honest. Every sentence is real text for the '
            'actual pager, the real selector bytes and the real search index. Token %03d stays '
            'stable across runs so a stored position can be checked again.' % (index, index))
    parts.append('The single searchable marker is ' + QUERY + ' and it appears here only once.')
    for index in range(1, 31):
        parts.append(
            'Trailing paragraph %03d keeps several real pages behind the marker so a page turn '
            'after the landing is still a forward turn and the earlier position remains earlier.' % index)
    return '\n\n'.join(parts) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output
    folder.mkdir(parents=True, exist_ok=True)

    text = txt_body().encode('utf-8')
    (folder / 'c11-notes.txt').write_bytes(text)
    epub(folder / 'c11-layout.epub', EPUB_TITLE, [
        '<h1>C11 layout chapter one</h1><p>First chapter of the reviewed layout fixture. '
        'The reader opens here and the directory can move to a later chapter.</p>',
        '<h1>C11 layout chapter two</h1><p>Second chapter with distinct source text. '
        'Chapter two is the explicit directory target used by the real UI check.</p>',
        '<h1>C11 layout chapter three</h1><p>Third chapter closes the fixture.</p>',
    ])

    rows = []
    for role, name, title, book_format in (('txt', 'c11-notes.txt', TXT_TITLE, 'txt'),
                                           ('epub', 'c11-layout.epub', EPUB_TITLE, 'epub')):
        data = (folder / name).read_bytes()
        rows.append({'role': role, 'file': name, 'title': title, 'format': book_format,
                     'bytes': len(data), 'sha256': sha(data)})
    manifest = {'books': rows, 'expected': {'txt_unique_query': QUERY}}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
