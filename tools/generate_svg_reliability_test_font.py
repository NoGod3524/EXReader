#!/usr/bin/env python3
"""Small SVG regression font; preserve the original reference font and its IDs."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import hashlib
import json
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.S_V_G_ import SVGDocument

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/fonts'


def doc(body, attrs=''):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" '
            + attrs + '>' + body + '</svg>')


RECT = '<rect x="100" y="100" width="800" height="800" fill="red"{}/>'
SMALL = '<rect x="100" y="100" width="100" height="100" fill="red" stroke="black" stroke-width="100"/>'
MITER = ('<path d="M100 900 L500 100 L600 900" fill="none" stroke="red" '
         'stroke-width="100" stroke-linejoin="miter" stroke-miterlimit="20"/>')
PAD = '<rect x="-500" y="-500" width="2000" height="2000" fill="none" stroke="none"/>'
OVERLAP = ('<rect x="100" y="100" width="600" height="800"/>'
           '<rect x="300" y="100" width="600" height="800"/>')
ROOT_PAINT = 'fill="blue" stroke="none" fill-opacity="0.5" opacity="0.5"'

# IDs start at 2; keep this order in tests/test_font_svg.c.
SCENES = {
    'default_stroke': doc(RECT.format(' stroke-width="100"')),
    'no_stroke': doc(RECT.format(' stroke-width="100" stroke="none"')),
    'explicit_stroke': doc(RECT.format(' stroke="black" stroke-width="100"')),
    'inherited_stroke': doc('<g stroke="black" stroke-width="100">' + RECT.format('') + '</g>'),
    'fill_decimal': doc(RECT.format(' stroke="none" fill-opacity="0.5"')),
    'fill_percent': doc(RECT.format(' stroke="none" fill-opacity="50%"')),
    'stroke_decimal': doc(RECT.format(' stroke="black" stroke-width="100" stroke-opacity="0.5"')),
    'stroke_percent': doc(RECT.format(' stroke="black" stroke-width="100" stroke-opacity="50%"')),
    'group_decimal': doc('<g opacity="0.5">' + RECT.format(' stroke="none"') + '</g>'),
    'group_percent': doc('<g opacity="50%">' + RECT.format(' stroke="none"') + '</g>'),
    'root_opacity': doc(RECT.format(' stroke="none"'), 'opacity="0.5"'),
    'root_selected': doc('<defs><g id="glyph{gid}" opacity="0.5">' + OVERLAP + '</g></defs>'
                         '<rect width="1000" height="1000" fill="green"/>', ROOT_PAINT),
    'root_selected_reference': doc('<g ' + ROOT_PAINT + '><g opacity="0.5">' + OVERLAP + '</g></g>'),
    'root_id': doc('<g opacity="0.5">' + OVERLAP + '</g>', ROOT_PAINT + ' id="glyph{gid}"'),
    'root_transform': doc(RECT.format(' stroke="none"'), 'opacity="0.5" transform="translate(100 0)"'),
    'root_transform_reference': doc('<g opacity="0.5" transform="translate(100 0)">' + RECT.format(' stroke="none"') + '</g>'),
    'one_stroke': doc(SMALL),
    'many_strokes': doc(SMALL * 100),
    'miter': doc(MITER),
    'miter_padded': doc(PAD + MITER),
    'miter_large_limit': doc(MITER.replace('stroke-miterlimit="20"', 'stroke-miterlimit="1000000"')),
    'bad_fill_percent': doc(RECT.format(' fill-opacity="101%"')),
    'bad_stroke_percent': doc(RECT.format(' stroke="black" stroke-opacity="-1%"')),
    'bad_opacity_unit': doc(RECT.format(' opacity="50px"')),
    'bad_opacity_percent': doc(RECT.format(' opacity="%"')),
    'root_zero': doc(RECT.format(''), 'opacity="0"'),
    'default_line': doc('<line x1="100" y1="500" x2="900" y2="500"/>'),
    'no_paint': doc(RECT.format('').replace('fill="red"', 'fill="none"')),
    'miter_shear': doc('<g transform="matrix(1.2 0.3 -0.2 0.8 0 0)">' + MITER + '</g>'),
}


def main():
    font = TTFont(ROOT / 'svgfont.ttf')
    font['SVG '].docList = [SVGDocument(body.replace('{gid}', str(gid)), gid, gid)
                            for gid, body in enumerate(SCENES.values(), 2)]
    font.recalcTimestamp = False
    path = ROOT / 'svg-reliability.ttf'
    font.save(path)
    manifest = {'font': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'glyphs': {name: gid for gid, name in enumerate(SCENES, 2)}}
    path.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(path.name, path.stat().st_size, manifest['sha256'])


if __name__ == '__main__':
    main()
