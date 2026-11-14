#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate deterministic PPTX M5 table decks (stdlib, ZIP_STORED)."""
import argparse
from pathlib import Path
import runpy
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = Path(__file__).resolve().parent
TEXT = runpy.run_path(str(HERE.parent / 'pptx-text/generate.py'))
package, archive = TEXT['package'], TEXT['archive']
P, A = TEXT['P'], TEXT['A']
SLIDE = TEXT['SLIDE']
BORDER = '9128C4'
COLORS = ('E84032', '38B75B', '3267D9', 'E8B62E')


def solid(rgb):
    return f'<a:solidFill><a:srgbClr val="{rgb}"/></a:solidFill>'


def borders(rgb=BORDER, width=4, sides='LRTB'):
    return ''.join(f'<a:ln{side} w="{round(width * 12700)}">{solid(rgb)}</a:ln{side}>' for side in sides)


def body(text, size=24, rgb='000000', body_attrs='', paragraphs=None):
    paragraph = TEXT['paragraph'](TEXT['run'](text, f'sz="{size * 100}"', solid(rgb)))
    return f'<a:txBody><a:bodyPr {body_attrs}/><a:lstStyle/>{paragraph if paragraphs is None else paragraphs}</a:txBody>'


def cell(text=None, fill=None, lines='', attrs='', props='', size=24, text_rgb='000000',
         no_props=False, body_attrs='', paragraphs=None):
    tx = '' if text is None else body(text, size, text_rgb, body_attrs, paragraphs)
    pr = '' if no_props else f'<a:tcPr {props}>{solid(fill) if fill else ""}{lines}</a:tcPr>'
    return f'<a:tc {attrs}>{tx}{pr}</a:tc>'


def table(rows, columns=(160, 160), heights=None, box=None, attrs='', table_props='', xfrm_attrs=''):
    heights = heights or [120] * len(rows)
    x, y, width, height = box or (40, 40, sum(columns), sum(heights))
    x, y, width, height = (round(value * 12700) for value in (x, y, width, height))
    grid = ''.join(f'<a:gridCol w="{round(value * 12700)}"/>' for value in columns)
    trs = ''.join(f'<a:tr h="{round(h * 12700)}">{"".join(row)}</a:tr>' for row, h in zip(rows, heights))
    return ('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="1" name="M5 table"/>'
            '<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>'
            f'<p:xfrm {xfrm_attrs}><a:off x="{x}" y="{y}"/><a:ext cx="{width}" cy="{height}"/></p:xfrm>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
            f'<a:tbl><a:tblPr {attrs}>{table_props}</a:tblPr><a:tblGrid>{grid}</a:tblGrid>{trs}'
            '</a:tbl></a:graphicData></a:graphic></p:graphicFrame>')


def cases():
    line = borders()
    colored = [[cell(fill=COLORS[r * 2 + c], lines=line) for c in range(2)] for r in range(2)]
    merged = [[cell('Merged', 'EFEFEF', line, attrs='gridSpan="2"'),
               cell('SHOULD NOT DRAW', 'FF0000', line, attrs='hMerge="1"')],
              [cell(fill='FFFFFF', lines=line), cell(fill='FFFFFF', lines=line)]]
    vertical = [[cell('Tall', 'EFEFEF', line, attrs='rowSpan="2"'), cell(fill='FFFFFF', lines=line)],
                [cell('SHOULD NOT DRAW', 'FF0000', line, attrs='vMerge="1"'), cell(fill='FFFFFF', lines=line)]]
    return {
        'fills': package(table(colored)),
        'columns': package(table([[cell(fill=COLORS[0]), cell(fill=COLORS[1])]], columns=(100, 300))),
        'text': package(table([[cell('A'), cell()], [cell(), cell('B')]])),
        'merged': package(table(merged)),
        'rowspan': package(table(vertical)),
        'anchor': package(table([[cell('Anchor', props='anchor="t"'), cell('Anchor', props='anchor="b"')]], heights=[240])),
        'malformed': package(table([[cell(fill=COLORS[0]), cell(fill=COLORS[1]), cell(fill=COLORS[2])]])),
        'empty-row': package(table([[], [cell(fill=COLORS[0]), cell(fill=COLORS[1])]])),
        'clipped': package(table([[cell(fill=COLORS[0], lines=line, attrs='gridSpan="20" rowSpan="20"'),
                                   cell(attrs='hMerge="1"')]], heights=[120])),
        'empty-cell': package(table([[cell(no_props=True), cell(no_props=True)]])),
        'no-border': package(table([[cell(fill=COLORS[0], lines='<a:lnL w="50800"/><a:lnR w="50800"><a:noFill/></a:lnR>'),
                                     cell(fill=COLORS[1], lines='<a:lnT/><a:lnB/>')]])),
        'overflow': package(table([[cell('word ' * 80, fill=COLORS[0], lines=line), cell(fill=COLORS[1], lines=line)]], heights=[30])),
    }


def generate(check=False):
    for name, data in cases().items():
        path = HERE / f'{name}.pptx'
        if check:
            assert path.read_bytes() == data, path
        else:
            path.write_bytes(data)
        print(f'{name}: deterministic OPC ZIP_STORED {len(data)} bytes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    generate(parser.parse_args().check)
