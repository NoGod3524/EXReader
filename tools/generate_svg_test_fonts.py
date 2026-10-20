#!/usr/bin/env python3
"""Original OT-SVG subset fonts; fontTools is a developer-only dependency."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import gzip
import hashlib
import json
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables.S_V_G_ import table_S_V_G_, SVGDocument

ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/fonts'
EMPTY = 'empty'

SVG_HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            'viewBox="0 0 1000 1000">')
SVG_END = '</svg>'


def doc(body, view_box='0 0 1000 1000', extra=''):
    return ('<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'viewBox="{view_box}"{extra}>{body}</svg>')


SCENES = {
    'rect': doc('<rect x="100" y="100" width="800" height="800" fill="#e02020"/>'),
    'two_rects': doc('<g transform="translate(100,0)"><rect x="0" y="100" width="400" height="800" fill="#ff0000"/>'
                     '<rect x="400" y="100" width="400" height="800" fill="#0000ff"/></g>'),
    'path_curve': doc('<path d="M 100 500 C 100 280 280 100 500 100 C 720 100 900 280 900 500 '
                      'C 900 720 720 900 500 900 C 280 900 100 720 100 500 Z" fill="#00c000"/>'),
    'circle': doc('<circle cx="500" cy="500" r="400" fill="#0080ff"/>'),
    'ellipse': doc('<ellipse cx="500" cy="500" rx="450" ry="250" fill="#ff8000"/>'),
    'polygon': doc('<polygon points="500,100 900,900 100,900" fill="#8000ff"/>'),
    'polyline': doc('<polyline points="100,900 300,300 500,900 700,300 900,900" fill="none" '
                    'stroke="#000000" stroke-width="100" stroke-linejoin="round"/>'),
    'stroke_caps': doc('<line x1="100" y1="500" x2="900" y2="500" stroke="#2040ff" stroke-width="120" '
                       'stroke-linecap="round"/>'),
    'evenodd': doc('<path fill-rule="evenodd" fill="#c00040" d="M 100 100 H 900 V 900 H 100 Z '
                   'M 300 300 H 700 V 700 H 300 Z"/>'),
    'group_opacity': doc('<g opacity="0.5"><rect x="100" y="100" width="800" height="800" fill="#ff0000"/></g>'),
    'fill_opacity': doc('<rect x="100" y="100" width="800" height="800" fill="#ff0000" fill-opacity="0.5"/>'),
    'current_color': doc('<rect x="100" y="100" width="800" height="800" fill="currentColor"/>'),
    'transform_matrix': doc('<rect x="100" y="100" width="800" height="800" fill="#00a0a0" '
                            'transform="matrix(0.5,0,0,0.5,100,100)"/>'),
    'transform_rotate': doc('<rect x="200" y="200" width="600" height="600" fill="#a000a0" '
                            'transform="rotate(45 500 500)"/>'),
    'viewbox_scaled': doc('<rect x="100" y="100" width="300" height="300" fill="#008040"/>',
                          view_box='0 0 500 500'),
    'arc': doc('<path d="M 100 500 A 400 400 0 0 1 900 500 L 500 900 Z" fill="#4060c0"/>'),
    'named_color': doc('<rect x="100" y="100" width="800" height="800" fill="green"/>'),
    'rgb_color': doc('<rect x="100" y="100" width="800" height="800" fill="rgb(10,20,30)"/>'),
    'nested_groups': doc('<g transform="translate(100,100)"><g transform="scale(0.5)">'
                         '<rect x="0" y="0" width="800" height="800" fill="#ffa000"/></g></g>'),
    'defs_ignored': doc('<defs><rect x="0" y="0" width="1000" height="1000" fill="#ff0000"/></defs>'
                        '<rect x="200" y="200" width="600" height="600" fill="#00ff00"/>'),
    'no_viewbox': '<svg xmlns="http://www.w3.org/2000/svg"><rect x="100" y="-900" width="800" height="800" fill="#804000"/></svg>',
    'gzip_rect': doc('<rect x="100" y="100" width="800" height="800" fill="#20c020"/>', ),
    # Rejections.
    'bad_doctype': '<!DOCTYPE svg [<!ENTITY x "y">]>' + doc('<rect x="0" y="0" width="10" height="10"/>'),
    'bad_script': doc('<script>alert(1)</script><rect x="100" y="100" width="800" height="800"/>'),
    'bad_image': doc('<image x="0" y="0" width="100" height="100" href="http://example.com/a.png"/>'),
    'bad_use': doc('<use href="#glyph99"/>'),
    'bad_gradient': doc('<defs><linearGradient id="g"/></defs><rect x="100" y="100" width="800" '
                        'height="800" fill="url(#g)"/>'),
    'bad_style': doc('<rect x="100" y="100" width="800" height="800" style="fill:#ff0000"/>'),
    'bad_mask': doc('<rect x="100" y="100" width="800" height="800" mask="url(#m)"/>'),
    'bad_external_image': doc('<image x="0" y="0" width="10" height="10" xlink:href="file:///etc/passwd"/>'),
    'bad_parse': doc('<rect x="100" y="100" width="800" height="800"'),
    'bad_entity': doc('<rect x="100" y="100" width="800" height="800" fill="&evil;"/>'),
    'bad_preserve': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" ' \
                    'preserveAspectRatio="xMinYMin meet"><rect x="0" y="0" width="10" height="10"/></svg>',
    'bad_nested': doc('<g>' * 40 + '<rect x="0" y="0" width="10" height="10"/>' + '</g>' * 40),
    'bad_many_elements': doc('<rect x="0" y="0" width="10" height="10"/>' * 2100),
    'bad_rounded': doc('<rect x="100" y="100" width="800" height="800" rx="20"/>'),
    'bad_transform': doc('<rect x="100" y="100" width="800" height="800" transform="matrix(1,2)"/>'),
}

SHARED = ('<g id="glyph{first}"><rect x="100" y="100" width="800" height="800" fill="#c02020"/></g>'
          '<g id="glyph{second}"><circle cx="500" cy="500" r="300" fill="#2020c0"/></g>')

# Appended after the shared-document glyphs so existing glyph IDs stay stable.
EXTRA_SCENES = {
    'bad_attrs': doc('<rect ' + ' '.join(f'data-a{i}="1"' for i in range(25)) +
                     ' x="100" y="100" width="800" height="800"/>'),
    'bad_attr_size': doc('<rect x="100" y="100" width="800" height="800" fill="' +
                         'a' * 600 + '"/>'),
    'bad_viewbox': doc('<rect x="100" y="100" width="800" height="800"/>',
                       view_box='0 0 1000'),
    'bad_circle': doc('<circle cx="500" cy="500" r="0" fill="#ff0000"/>'),
    'bad_dash': doc('<line x1="100" y1="500" x2="900" y2="500" stroke="#000" '
                    'stroke-dasharray="10 10"/>'),
    'bad_segments': doc('<path d="M0 0' + 'l1 0' * 70000 + '" fill="none" stroke="#000"/>'),
}

ORDER = ['.notdef', 'space'] + list(SCENES.keys()) + ['shared_a', 'shared_b'] + list(EXTRA_SCENES.keys())


def empty_glyph():
    return TTGlyphPen(None).glyph()


def main():
    font = FontBuilder(1000, isTTF=True)
    font.setupGlyphOrder(ORDER)
    cmap = {32: 'space'}
    for i, name in enumerate(ORDER[2:]):
        cmap[0x41 + i] = name
    font.setupCharacterMap(cmap)
    font.setupGlyf({name: empty_glyph() for name in ORDER})
    font.setupHorizontalMetrics({name: (900, 0) for name in ORDER})
    font.setupHorizontalHeader(ascent=900, descent=-100)
    font.setupVerticalMetrics({name: (1000, 500) for name in ORDER})
    font.setupVerticalHeader(ascent=500, descent=-500)
    font.setupOS2(sTypoAscender=900, sTypoDescender=-100, usWinAscent=1000, usWinDescent=200)
    font.setupNameTable({'familyName': 'EXReader SVG Subset', 'styleName': 'Regular',
                         'uniqueFontIdentifier': 'EXReader-SVG-Subset',
                         'fullName': 'EXReader SVG Subset Regular',
                         'psName': 'EXReaderSVGSubset-Regular', 'version': 'Version 1.0'})
    font.setupPost(underlinePosition=-100, underlineThickness=50)
    font.setupMaxp()
    glyphs = font.font.getReverseGlyphMap()
    svg = table_S_V_G_()
    docs = []
    for name, body in {**SCENES, **EXTRA_SCENES}.items():
        gid = glyphs[name]
        docs.append(SVGDocument(body, gid, gid, compressed=(name == 'gzip_rect')))
    first, second = glyphs['shared_a'], glyphs['shared_b']
    shared = doc(SHARED.format(first=first, second=second))
    docs.append(SVGDocument(shared, first, second, compressed=False))
    svg.docList = sorted(docs, key=lambda item: item.startGlyphID)
    font.font['SVG '] = svg
    font.font['head'].created = font.font['head'].modified = 2082844800
    font.font.recalcTimestamp = False
    path = ROOT / 'svgfont.ttf'
    font.font.save(path)
    manifest = {
        'font': path.name,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'glyphs': {name: glyphs[name] for name in ORDER},
        'scenes': sorted(SCENES),
        'shared': {'first': first, 'second': second, 'doc': shared},
        'extra': sorted(EXTRA_SCENES),
        'rejections': sorted(n for n in {**SCENES, **EXTRA_SCENES} if n.startswith('bad_')),
    }
    (ROOT / 'svgfont.json').write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(path.name, path.stat().st_size, manifest['sha256'])


if __name__ == '__main__':
    main()