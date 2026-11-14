#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate deterministic shape decks and a python-pptx coordinate oracle."""
import argparse
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Pt

HERE = Path(__file__).resolve().parent
CASES = [('rect', MSO_SHAPE.RECTANGLE, (72, 72, 144, 72), 'FF0000'),
         ('circle', MSO_SHAPE.OVAL, (72, 72, 144, 144), '00CC44'),
         ('roundrect', MSO_SHAPE.ROUNDED_RECTANGLE, (72, 72, 180, 90), '3366CC'),
         ('triangle', MSO_SHAPE.ISOSCELES_TRIANGLE, (72, 72, 144, 108), 'FF9900'),
         ('group', None, None, None),
         ('standard', MSO_SHAPE.RECTANGLE, (72, 108, 180, 90), 'CC33AA')]


def shape(shapes, kind, box, color):
    item = shapes.add_shape(kind, *(Pt(value) for value in box))
    item.fill.solid()
    item.fill.fore_color.rgb = RGBColor.from_string(color)
    item.line.fill.background()
    return item


def oracle_shapes(shapes, offset=(0, 0), scale=(1, 1)):
    result = []
    for item in shapes:
        if item.shape_type == 6:  # GROUP_SHAPE
            xf = item._element.grpSpPr.xfrm
            child_scale = (scale[0] * xf.ext.cx / xf.chExt.cx,
                           scale[1] * xf.ext.cy / xf.chExt.cy)
            child_offset = (offset[0] + scale[0] * xf.off.x - child_scale[0] * xf.chOff.x,
                            offset[1] + scale[1] * xf.off.y - child_scale[1] * xf.chOff.y)
            result.extend(oracle_shapes(item.shapes, child_offset, child_scale))
        else:
            result.append(dict(geometry=item._element.spPr.prstGeom.get('prst'),
                               rgb=str(item.fill.fore_color.rgb),
                               bounds_pt=[(offset[0] + item.left * scale[0]) / 12700,
                                          (offset[1] + item.top * scale[1]) / 12700,
                                          item.width * scale[0] / 12700,
                                          item.height * scale[1] / 12700]))
    return result


def generate(check=False):
    manifest = []
    for name, kind, box, color in CASES:
        deck = Presentation()
        deck.slide_width, deck.slide_height = Pt(720 if name == 'standard' else 960), Pt(540)
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        if kind is None:
            group = slide.shapes.add_group_shape()
            shape(group.shapes, MSO_SHAPE.RECTANGLE, (36, 24, 72, 48), 'FF0000')
            shape(group.shapes, MSO_SHAPE.RECTANGLE, (144, 96, 108, 60), '0066FF')
            # Deliberately use different off/chOff and anisotropic 2 x 1.5 scale.
            group.left, group.top, group.width, group.height = Pt(180), Pt(108), Pt(432), Pt(198)
        else:
            shape(slide.shapes, kind, box, color)
        raw, canonical = BytesIO(), BytesIO()
        deck.save(raw)
        with ZipFile(raw) as src, ZipFile(canonical, 'w') as dst:
            for member in sorted(src.namelist()):
                info = ZipInfo(member, (2020, 1, 1, 0, 0, 0))
                info.compress_type, info.create_system = ZIP_DEFLATED, 3
                info.external_attr = 0o600 << 16
                dst.writestr(info, src.read(member))
        data = canonical.getvalue()
        oracle = Presentation(BytesIO(data))
        entry = dict(file=f'{name}.pptx', size_pt=[oracle.slide_width / 12700,
                                                oracle.slide_height / 12700],
                     shapes=oracle_shapes(oracle.slides[0].shapes))
        manifest.append(entry)
        if check:
            assert (HERE / entry['file']).read_bytes() == data, name
        else:
            (HERE / entry['file']).write_bytes(data)
        print(f'{name}: python-pptx {entry}')
    text = json.dumps(manifest, indent=2) + '\n'
    if check:
        assert (HERE / 'manifest.json').read_text() == text
    else:
        (HERE / 'manifest.json').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    generate(parser.parse_args().check)
