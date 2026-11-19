#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Concatenate existing fixture pages; never rasterize, scale or reorder them."""
import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/pdf-large'
DEFAULTS = [ROOT / name for name in
            ('real-mixed-120.pdf', 'image-heavy-100.pdf', 'vector-heavy-100.pdf')]


def build(sources, pages, out):
    sources = list(map(Path, sources))
    if not sources or pages < 1 or out.resolve() in [p.resolve() for p in sources]:
        raise ValueError('need sources, positive page count and distinct output')
    writer = PdfWriter()
    remaining = pages
    while remaining:
        for source in sources:
            with source.open('rb') as stream:
                reader = PdfReader(stream)
                take = min(remaining, len(reader.pages))
                if not take:
                    raise ValueError(f'empty fixture: {source}')
                writer.append(reader, pages=(0, take), import_outline=False)
                writer.reset_translation(reader)
            remaining -= take
            if not remaining:
                break
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('wb') as stream:
        writer.write(stream)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, action='append', help='ordered fixture (repeatable)')
    ap.add_argument('--pages', type=int, choices=(1000, 2000), default=1000)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    build(args.input or DEFAULTS, args.pages, args.out)


if __name__ == '__main__':
    main()
