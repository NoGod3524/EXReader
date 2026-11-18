#!/usr/bin/env python3
"""Build the 100-page memory fixture used by bench_memory.py.

Pages cycle deck (15) -> pptx-20 (20) -> word-5 (5) until 100 pages. Each source
is appended from a fresh PdfReader, so every copy gets its own image, font and
content objects (no cross-copy sharing): a long document whose images do not
repeat, i.e. the worst case for per-document decode caches.

  python -X utf8 tools/make_memory_fixture.py --out out/long-100.pdf
"""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / 'tests/fixtures/pdf-ppt/deck.pdf',
           ROOT / 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf',
           ROOT / 'tests/fixtures/pdf-hybrid-real/word-5.pdf']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--pages', type=int, default=100)
    args = ap.parse_args()
    writer = PdfWriter()
    index = 0
    while len(writer.pages) < args.pages:
        source = SOURCES[index % len(SOURCES)]
        index += 1
        reader = PdfReader(str(source))  # fresh reader -> no object sharing between copies
        take = min(len(reader.pages), args.pages - len(writer.pages))
        writer.append(reader, pages=(0, take))
    writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('wb') as handle:
        writer.write(handle)
    data = args.out.read_bytes()
    print(f'{args.out} pages={len(PdfReader(str(args.out)).pages)} bytes={len(data)} '
          f'sha256={hashlib.sha256(data).hexdigest()}')


if __name__ == '__main__':
    main()
