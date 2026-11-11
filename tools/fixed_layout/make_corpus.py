"""Generate the synthetic EPUB 3 Fixed Layout corpus with geometry oracles.

Each book is deterministic (fixed ZIP timestamps, PNG art drawn here, no
third-party content). Every positioned element carries a unique opaque
background colour and its declared CSS geometry is written to the oracle, so
the verifier can locate it in layout boxes and in rendered pixels.
"""
import argparse
import io
import json
from pathlib import Path
import zipfile

from PIL import Image, ImageDraw

STAMP = (2026, 11, 10, 0, 0, 0)
FRAME = (255, 0, 0)  # 1-px-plus border of every full-page image: crop detector


def png(width, height, fill, label, frame=True, seed=0):
    image = Image.new('RGB', (width, height), fill)
    draw = ImageDraw.Draw(image)
    step = max(24, min(width, height) // 12)
    for i in range(0, width + height, step):
        shade = tuple(max(0, c - 18 - (seed * 7 + i // step) % 30) for c in fill)
        draw.line([(i, 0), (i - height, height)], fill=shade, width=3)
    band = max(4, min(width, height) // 60)
    if frame:
        draw.rectangle([0, 0, width - 1, height - 1], outline=FRAME, width=band)
    draw.rectangle([width // 2 - 40, height // 2 - 40, width // 2 + 40, height // 2 + 40], fill=(20, 20, 20))
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue(), {'frame_px': band, 'frame': '#ff0000' if frame else None}


def hexcolor(rgb):
    return '#%02x%02x%02x' % rgb


def xhtml(title, body, viewport=None, css=''):
    meta = f'<meta name="viewport" content="width={viewport[0]}, height={viewport[1]}"/>' if viewport else ''
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">
<head><meta charset="utf-8"/>{meta}<title>{title}</title>
<style type="text/css">{css}</style></head>
<body>{body}</body></html>
'''


LOREM = ('The tide came in slowly over the flat grey sand, and the children ran ahead of it, '
         'shouting the names of the boats they could see far out on the water. ')


class Book:
    def __init__(self, ident, title, layout=None, spread=None, viewport=None, progression=None):
        self.ident, self.title = ident, title
        self.layout, self.spread, self.viewport, self.progression = layout, spread, viewport, progression
        self.files, self.manifest, self.spine, self.toc = {}, [], [], []
        self.oracle = {'id': ident, 'title': title, 'pages': [], 'expected_spreads': None}

    def add(self, name, data, media, props=None, ident=None):
        self.files['OEBPS/' + name] = data
        ident = ident or name.replace('/', '-').replace('.', '-')
        self.manifest.append((ident, name, media, props))
        return ident

    def page(self, name, html, spine_props=None, oracle=None, linear=True):
        ident = self.add(name, html.encode('utf-8'), 'application/xhtml+xml')
        self.spine.append((ident, spine_props, linear))
        self.oracle['pages'].append(dict(oracle or {}, href=name, spine_properties=spine_props or ''))
        return ident

    def write(self, directory):
        meta = []
        if self.layout:
            meta.append(f'<meta property="rendition:layout">{self.layout}</meta>')
        if self.spread:
            meta.append(f'<meta property="rendition:spread">{self.spread}</meta>')
        if self.viewport:
            meta.append(f'<meta property="rendition:viewport">width={self.viewport[0]}, height={self.viewport[1]}</meta>')
        nav_items = ''.join(f'<li><a href="{href}">{label}</a></li>' for label, href in self.toc) or \
            f'<li><a href="{self.spine_href(0)}">Start</a></li>'
        nav = f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head>
<body><nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{nav_items}</ol></nav></body></html>
'''
        self.add('nav.xhtml', nav.encode('utf-8'), 'application/xhtml+xml', 'nav', 'nav')
        items = '\n'.join(
            f'    <item id="{i}" href="{h}" media-type="{m}"' + (f' properties="{p}"' if p else '') + '/>'
            for i, h, m, p in self.manifest)
        refs = '\n'.join(
            f'    <itemref idref="{i}"' + (f' properties="{p}"' if p else '') + ('' if lin else ' linear="no"') + '/>'
            for i, p, lin in self.spine)
        ppd = f' page-progression-direction="{self.progression}"' if self.progression else ''
        opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"
  prefix="rendition: http://www.idpf.org/vocab/rendition/#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:exreader:fxl:{self.ident}</dc:identifier>
    <dc:title>{self.title}</dc:title>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-11-10T00:00:00Z</meta>
    {chr(10).join('    ' + m for m in meta).strip()}
  </metadata>
  <manifest>
{items}
  </manifest>
  <spine{ppd}>
{refs}
  </spine>
</package>
'''
        container = b'''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
'''
        path = Path(directory) / f'{self.ident}.epub'
        with zipfile.ZipFile(path, 'w') as z:
            def put(name, data, method):
                info = zipfile.ZipInfo(name, STAMP)
                info.compress_type = method
                z.writestr(info, data)
            put('mimetype', b'application/epub+zip', zipfile.ZIP_STORED)
            put('META-INF/container.xml', container, zipfile.ZIP_DEFLATED)
            put('OEBPS/package.opf', opf.encode('utf-8'), zipfile.ZIP_DEFLATED)
            for name in sorted(self.files):
                put(name, self.files[name], zipfile.ZIP_DEFLATED)
        self.oracle['package'] = {'layout': self.layout, 'spread': self.spread,
                                  'viewport': self.viewport, 'progression': self.progression}
        self.oracle['toc'] = [{'label': label, 'href': href} for label, href in self.toc]
        return path

    def spine_href(self, index):
        ident = self.spine[index][0]
        return next(h for i, h, _, _ in self.manifest if i == ident)


def boxed(ident, color, css, text='', tag='div'):
    return f'<{tag} id="{ident}" style="position:absolute; background-color:{hexcolor(color)}; {css}">{text}</{tag}>'


def picture_book():
    """Picture book: full-bleed art plus absolutely positioned text boxes."""
    vw, vh = 1024, 768
    b = Book('fxl-picturebook', 'The Tide Garden', layout='pre-paginated', spread='none')
    colors = [(250, 214, 165), (180, 220, 200), (200, 200, 240), (240, 200, 210)]
    for n in range(4):
        art, frame = png(vw, vh, colors[n], f'page {n + 1}', seed=n)
        image = b.add(f'img/page{n + 1}.png', art, 'image/png')
        sticker, _ = png(160, 120, (90, 140, 230), 'sticker', frame=False, seed=n)
        b.add(f'img/sticker{n + 1}.png', sticker, 'image/png')
        boxes = [
            {'id': f't{n}a', 'color': (255, 255, 255), 'left': 64, 'top': 48, 'width': 400,
             'css': 'left:64px; top:48px; width:400px; padding:12px; font-size:22px;'},
            {'id': f't{n}b', 'color': (255, 248, 200), 'right': 64, 'bottom': 48, 'width': 360,
             'css': 'right:64px; bottom:48px; width:360px; padding:10px; font-size:20px;'},
        ]
        body = (f'<img id="bg{n}" src="img/page{n + 1}.png" alt="art" '
                f'style="position:absolute; left:0; top:0; width:{vw}px; height:{vh}px;"/>')
        for box in boxes:
            body += boxed(box['id'], box['color'], box['css'],
                          f'<p style="margin:0">{LOREM[:120 + 20 * n]}</p>')
        body += (f'<img id="st{n}" src="img/sticker{n + 1}.png" alt="sticker" '
                 'style="position:absolute; left:60%; top:40%; width:160px;"/>')
        b.page(f'p{n + 1}.xhtml', xhtml(f'Page {n + 1}', body, (vw, vh), 'body{margin:0}'),
               oracle={'viewport': [vw, vh], 'viewport_source': 'content', 'fixed': True,
                       'full_image': {'id': f'bg{n}', 'left': 0, 'top': 0, 'width': vw, 'height': vh, **frame},
                       'boxes': [{k: v for k, v in x.items() if k != 'css'} for x in boxes],
                       'images': [{'id': f'st{n}', 'left_pct': 0.60, 'top_pct': 0.40, 'width': 160, 'height': 120}]})
    b.oracle['expected_spreads'] = [{'left': i, 'right': None, 'single': True} for i in range(4)]
    return b


def magazine():
    """Magazine: three absolutely positioned columns, a headline, a vertical-rl
    (90-degree rotated) sidebar, and one transform:rotate caption."""
    vw, vh = 1200, 1600
    b = Book('fxl-magazine', 'Harbour Quarterly', layout='pre-paginated', spread='landscape')
    tones = [(230, 238, 246), (240, 230, 220), (232, 244, 232), (246, 232, 240)]
    for n in range(4):
        cols = []
        for c in range(3):
            left = 60 + c * 370
            cols.append({'id': f'c{n}{c}', 'color': tones[(n + c) % 4], 'left': left, 'top': 300, 'width': 340,
                         'css': f'left:{left}px; top:300px; width:340px; font-size:20px; line-height:1.4;'})
        head = {'id': f'h{n}', 'color': (30, 50, 90), 'left': 60, 'top': 60, 'width': 1080,
                'css': 'left:60px; top:60px; width:1080px; height:180px; font-size:64px; color:#ffffff;'}
        side = {'id': f's{n}', 'color': (250, 200, 60), 'right': 10, 'top': 300, 'width': 40,
                'css': 'right:10px; top:300px; width:40px; font-size:26px; writing-mode:vertical-rl;'}
        body = boxed(head['id'], head['color'], head['css'], f'Issue {n + 1}: Harbour Lights')
        for col in cols:
            body += boxed(col['id'], col['color'], col['css'], ''.join(f'<p style="margin:0 0 12px 0">{LOREM}</p>' for _ in range(3)))
        body += boxed(side['id'], side['color'], side['css'], 'ROTATED SIDEBAR TEXT')
        body += ('<div id="r%d" style="position:absolute; left:60px; top:1480px; width:500px; '
                 'transform:rotate(-8deg); font-size:22px;">Caption declared with transform:rotate</div>' % n)
        b.page(f'm{n + 1}.xhtml', xhtml(f'Magazine {n + 1}', body, (vw, vh), 'body{margin:0}'),
               spine_props='page-spread-left' if n % 2 else 'page-spread-right',
               oracle={'viewport': [vw, vh], 'viewport_source': 'content', 'fixed': True,
                       'boxes': [{k: v for k, v in x.items() if k != 'css'} for x in [head] + cols + [side]],
                       'vertical': side['id'], 'transform': f'r{n}'})
    # ltr: m1 right alone, (m2 L, m3 R), m4 left alone.
    b.oracle['expected_spreads'] = [{'left': None, 'right': 0}, {'left': 1, 'right': 2}, {'left': 3, 'right': None}]
    return b


def toc_book():
    """Fixed layout with a navigation document pointing at three of five pages."""
    vw, vh = 800, 1100
    b = Book('fxl-toc', 'A Field Guide in Five Plates', layout='pre-paginated')
    fills = [(210, 225, 240), (240, 225, 200), (215, 240, 210), (240, 210, 225), (230, 230, 230)]
    for n in range(5):
        art, frame = png(vw, vh, fills[n], f'plate {n + 1}', seed=n)
        b.add(f'img/plate{n + 1}.png', art, 'image/png')
        body = (f'<img id="pl{n}" src="img/plate{n + 1}.png" alt="plate" '
                f'style="position:absolute; left:0; top:0; width:{vw}px; height:{vh}px;"/>'
                + boxed(f'cap{n}', (255, 255, 255), 'left:40px; top:980px; width:720px; font-size:28px; padding:8px;',
                        f'Plate {n + 1}'))
        b.page(f'plate{n + 1}.xhtml', xhtml(f'Plate {n + 1}', body, (vw, vh), 'body{margin:0}'),
               oracle={'viewport': [vw, vh], 'viewport_source': 'content', 'fixed': True,
                       'full_image': {'id': f'pl{n}', 'left': 0, 'top': 0, 'width': vw, 'height': vh, **frame},
                       'boxes': [{'id': f'cap{n}', 'color': (255, 255, 255), 'left': 40, 'top': 980, 'width': 720}]})
    b.toc = [('Plate one: Shore', 'plate1.xhtml'), ('Plate three: Dunes', 'plate3.xhtml'),
             ('Plate five: Night', 'plate5.xhtml')]
    b.oracle['expected_toc_parts'] = [0, 2, 4]
    # auto sides, ltr: p1 right alone, (p2,p3), (p4,p5)
    b.oracle['expected_spreads'] = [{'left': None, 'right': 0}, {'left': 1, 'right': 2}, {'left': 3, 'right': 4}]
    return b


def spread_book():
    """ltr two-page spreads with explicit left/right/center and one auto side."""
    vw, vh = 700, 1000
    b = Book('fxl-spread-ltr', 'Seven Panels', layout='pre-paginated', spread='both', progression='ltr')
    sides = ['page-spread-right', 'page-spread-left', 'page-spread-right', 'rendition:page-spread-center',
             'page-spread-left', 'page-spread-right', None]
    for n, side in enumerate(sides):
        art, frame = png(vw, vh, (200 + 7 * n, 210, 240 - 9 * n), f'panel {n + 1}', seed=n)
        b.add(f'img/panel{n + 1}.png', art, 'image/png')
        body = (f'<img id="pa{n}" src="img/panel{n + 1}.png" alt="panel" '
                f'style="position:absolute; left:0; top:0; width:{vw}px; height:{vh}px;"/>'
                + boxed(f'no{n}', (255, 255, 255), 'left:20px; top:20px; width:120px; font-size:40px;', str(n + 1)))
        b.page(f'panel{n + 1}.xhtml', xhtml(f'Panel {n + 1}', body, (vw, vh), 'body{margin:0}'), spine_props=side,
               oracle={'viewport': [vw, vh], 'viewport_source': 'content', 'fixed': True,
                       'full_image': {'id': f'pa{n}', 'left': 0, 'top': 0, 'width': vw, 'height': vh, **frame},
                       'boxes': [{'id': f'no{n}', 'color': (255, 255, 255), 'left': 20, 'top': 20, 'width': 120}]})
    b.oracle['expected_spreads'] = [{'left': None, 'right': 0}, {'left': 1, 'right': 2},
                                    {'left': 3, 'right': None, 'single': True}, {'left': 4, 'right': 5},
                                    {'left': 6, 'right': None}]
    return b


def mixed_book():
    """Reflowable package default; fixed pages declared per itemref. The package
    rendition:viewport is the only viewport for the fixed pages (no meta)."""
    vw, vh = 800, 1000
    b = Book('fxl-mixed', 'Notes with Plates', layout='reflowable', viewport=(vw, vh))
    art, frame = png(vw, vh, (235, 220, 190), 'cover')
    b.add('img/cover.png', art, 'image/png')
    b.page('cover.xhtml', xhtml('Cover', f'<img id="cv" src="img/cover.png" alt="cover" style="position:absolute; left:0; top:0; width:{vw}px; height:{vh}px;"/>', None, 'body{margin:0}'),
           spine_props='rendition:layout-pre-paginated',
           oracle={'viewport': [vw, vh], 'viewport_source': 'package', 'fixed': True,
                   'full_image': {'id': 'cv', 'left': 0, 'top': 0, 'width': vw, 'height': vh, **frame}})
    long_text = ''.join(f'<p>{LOREM * 3}</p>' for _ in range(14))
    b.page('ch1.xhtml', xhtml('Chapter 1', f'<h1>Chapter One</h1>{long_text}'),
           spine_props='rendition:layout-reflowable', oracle={'fixed': False})
    art2, frame2 = png(vw, vh, (190, 215, 235), 'plate')
    b.add('img/plate.png', art2, 'image/png')
    b.page('plate.xhtml', xhtml('Plate', f'<img id="pt" src="img/plate.png" alt="plate" style="position:absolute; left:0; top:0; width:{vw}px; height:{vh}px;"/>'
                                + boxed('pcap', (255, 255, 255), 'left:50px; bottom:40px; width:400px; font-size:24px;', 'Plate I'), None, 'body{margin:0}'),
           spine_props='rendition:layout-pre-paginated',
           oracle={'viewport': [vw, vh], 'viewport_source': 'package', 'fixed': True,
                   'full_image': {'id': 'pt', 'left': 0, 'top': 0, 'width': vw, 'height': vh, **frame2},
                   'boxes': [{'id': 'pcap', 'color': (255, 255, 255), 'left': 50, 'bottom': 40, 'width': 400}]})
    b.page('ch2.xhtml', xhtml('Chapter 2', f'<h1>Chapter Two</h1>{long_text}'), oracle={'fixed': False})
    art3, frame3 = png(vw, vh, (215, 235, 200), 'end')
    b.add('img/end.png', art3, 'image/png')
    b.page('end.xhtml', xhtml('End', f'<img id="en" src="img/end.png" alt="end" style="position:absolute; left:0; top:0; width:{vw}px; height:{vh}px;"/>', None, 'body{margin:0}'),
           spine_props='rendition:layout-pre-paginated page-spread-left',
           oracle={'viewport': [vw, vh], 'viewport_source': 'package', 'fixed': True,
                   'full_image': {'id': 'en', 'left': 0, 'top': 0, 'width': vw, 'height': vh, **frame3}})
    b.oracle['expected_spreads'] = [{'left': None, 'right': 0}, {'left': 1, 'right': None, 'single': True},
                                    {'left': None, 'right': 2}, {'left': 3, 'right': None, 'single': True},
                                    {'left': 4, 'right': None}]
    return b


def noviewport_book():
    """Pre-paginated without any viewport declaration: image page falls back to
    the image intrinsic size, text-only page to the requested page size."""
    b = Book('fxl-noviewport', 'Undeclared Sizes', layout='pre-paginated', spread='none')
    art, frame = png(600, 900, (225, 225, 245), 'intrinsic')
    b.add('img/a.png', art, 'image/png')
    b.page('a.xhtml', xhtml('Image page', '<img id="ia" src="img/a.png" alt="a" style="position:absolute; left:0; top:0;"/>', None, 'body{margin:0}'),
           oracle={'viewport': [600, 900], 'viewport_source': 'image', 'fixed': True,
                   'full_image': {'id': 'ia', 'left': 0, 'top': 0, 'width': 600, 'height': 900, **frame}})
    b.page('b.xhtml', xhtml('Text page', boxed('tb', (220, 240, 255), 'left:10%; top:10%; width:50%; font-size:24px;',
                                               'A text-only fixed page with no declared viewport.'), None, 'body{margin:0}'),
           oracle={'viewport': None, 'viewport_source': 'page', 'fixed': True,
                   'boxes': [{'id': 'tb', 'color': (220, 240, 255), 'left_pct': 0.10, 'top_pct': 0.10, 'width_pct': 0.50}]})
    b.oracle['expected_spreads'] = [{'left': 0, 'right': None, 'single': True}, {'left': 1, 'right': None, 'single': True}]
    return b


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    oracles = []
    for make in (picture_book, magazine, toc_book, spread_book, mixed_book, noviewport_book):
        book = make()
        path = book.write(args.output)
        oracles.append(dict(book.oracle, path=str(path)))
        print(path)
    (args.output / 'oracle.json').write_text(json.dumps(oracles, indent=2, default=list) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
