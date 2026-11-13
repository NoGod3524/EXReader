#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate six original python-pptx decks with deterministic ZIP metadata."""
import argparse
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from pptx import Presentation

HERE = Path(__file__).resolve().parent
CASES = [('empty', 0, 9144000), ('title', 1, 9144000),
         ('layouts', 5, 9144000), ('wide', 1, 12192000),
         ('standard', 1, 9144000), ('twenty', 20, 9144000)]


def generate(check=False):
    manifest = []
    for name, count, width in CASES:
        deck = Presentation()
        deck.slide_width, deck.slide_height = width, 6858000
        for i in range(count):
            slide = deck.slides.add_slide(deck.slide_layouts[i % 5 if name == 'layouts' else 0])
            if slide.shapes.title is not None:
                slide.shapes.title.text = f'{name}: slide {i + 1}'
        raw, canonical = BytesIO(), BytesIO()
        deck.save(raw)
        with ZipFile(raw) as src, ZipFile(canonical, 'w', compression=ZIP_DEFLATED) as dst:
            for member in sorted(src.namelist()):
                info = ZipInfo(member, (2020, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o600 << 16
                dst.writestr(info, src.read(member))
        data = canonical.getvalue()
        oracle = Presentation(BytesIO(data))
        entry = dict(file=f'{name}.pptx', pages=len(oracle.slides),
                     cx=int(oracle.slide_width), cy=int(oracle.slide_height))
        manifest.append(entry)
        path = HERE / entry['file']
        if check:
            assert path.read_bytes() == data, path
        else:
            path.write_bytes(data)
        print(f"{name}: python-pptx pages={entry['pages']} EMU={entry['cx']}x{entry['cy']}")
    data = json.dumps(manifest, indent=2) + '\n'
    if check:
        assert (HERE / 'manifest.json').read_text() == data
    else:
        (HERE / 'manifest.json').write_text(data, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    generate(parser.parse_args().check)
