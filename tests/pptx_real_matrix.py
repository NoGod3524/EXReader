#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""PPTX M6: independent geometry/fill oracle, public-ABI raster measurements.

No engine pixels participate in selecting the twelve reference color samples.
Text is measured by subtracting a second render with txBody paragraphs emptied;
this distinguishes glyphs from photographs, borders and dark shape fills.
"""
import argparse
import colorsys
import copy
import ctypes as C
from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
from zipfile import ZipFile, ZIP_STORED

from lxml import etree as ET
from PIL import Image, ImageChops, ImageDraw
from pptx import Presentation
from pptx.oxml.ns import qn

from test_pptx_skeleton import Bitmap, Engine, Error

HERE = Path(__file__).resolve().parent / 'fixtures/pptx-real'
IDENTITY = (1, 0, 0, 1, 0, 0)
WHITE = (255, 255, 255)


def child(element, tag):
    return element.find(qn(tag)) if element is not None else None


def local(element):
    return ET.QName(element).localname


def compose(a, b):
    return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5])


def point(m, x, y):
    return m[0]*x+m[2]*y+m[4], m[1]*x+m[3]*y+m[5]


def inverse(m, x, y):
    det = m[0]*m[3]-m[1]*m[2]
    if not det:
        raise ValueError('zero-area reference transform')
    x, y = x-m[4], y-m[5]
    return (m[3]*x-m[2]*y)/det, (-m[1]*x+m[0]*y)/det


def box(m, w, h):
    corners = [point(m, x, y) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
    return (min(p[0] for p in corners), min(p[1] for p in corners),
            max(p[0] for p in corners), max(p[1] for p in corners))


def union(boxes):
    return ((min(b[0] for b in boxes), min(b[1] for b in boxes),
             max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else None)


def font_warnings_only(message):
    """A fallback substring must never hide a second, non-font warning."""
    if not message:
        return True
    if not message.startswith('PPTX warning: '):
        return False
    glyphs = False
    for field in message.removeprefix('PPTX warning: ').split(';'):
        field = field.strip()
        if not field:
            continue
        if field.startswith('font fallback=') and len(field) > len('font fallback='):
            continue
        if field.startswith('missing glyph: '):
            glyphs = True
            field = field.removeprefix('missing glyph: ')
        if glyphs and re.fullmatch(r'.+ U\+[0-9A-F]{4,6} (?:missing|fallback)', field):
            continue
        # The public error buffer abbreviates long host-only glyph lists. The
        # textless package is checked separately so later non-font diagnostics
        # cannot be hidden by this abbreviation.
        if glyphs and len(message.encode('utf-8')) >= 250 and re.fullmatch(r'.+ U\+[0-9A-F]{4,6} [a-z]+\.\.\.', field):
            prefix = field.rsplit(' ', 1)[1][:-3]
            if 'missing'.startswith(prefix) or 'fallback'.startswith(prefix):
                continue
        return False
    return True


def without_text(data):
    out = BytesIO()
    with ZipFile(BytesIO(data)) as src, ZipFile(out, 'w', ZIP_STORED) as dst:
        for name in src.namelist():
            content = src.read(name)
            if name.endswith('.xml') and name.startswith('ppt/'):
                root = ET.fromstring(content)
                for body in root.iter(qn('p:txBody'), qn('a:txBody')):
                    for paragraph in list(body.findall(qn('a:p'))):
                        body.remove(paragraph)
                    ET.SubElement(body, qn('a:p'))
                content = ET.tostring(root)
            dst.writestr(name, content)
    return out.getvalue()


def opened(engine, path=None, data=None):
    doc, error = C.c_void_p(), Error()
    if path is not None:
        status = engine.lib.exr_fixed_open(str(path).encode('utf-8'), None, C.byref(doc), C.byref(error))
    else:
        status = engine.lib.exr_fixed_open_memory(11, data, len(data), None, C.byref(doc), C.byref(error))
    return status, error.code, error.message.decode('utf-8', errors='replace'), doc


def render(engine, doc, page):
    bitmap, error = Bitmap(), Error()
    start = time.perf_counter_ns()
    status = engine.lib.exr_fixed_render(doc, page, 1, None, C.byref(bitmap), C.byref(error))
    elapsed = (time.perf_counter_ns()-start)/1e6
    try:
        if status or error.code or not font_warnings_only(error.message.decode('utf-8', errors='replace')):
            raise ValueError(f'render status={status} code={error.code}: {error.message!r}')
        if bitmap.channels != 4 or not bitmap.pixels:
            raise ValueError('invalid RGBA bitmap')
        image = Image.frombytes('RGBA', (bitmap.width, bitmap.height),
                                C.string_at(bitmap.pixels, bitmap.stride*bitmap.height),
                                'raw', 'RGBA', bitmap.stride).convert('RGB')
        return image, elapsed
    finally:
        engine.lib.exr_bitmap_free(C.byref(bitmap))


@dataclass
class Paint:
    kind: str
    value: object
    angle: float = 0
    scaled: bool = False

    def rgba(self, x, y, w, h):
        if self.kind == 'solid':
            return self.value
        if self.kind == 'image':
            image, crop = self.value
            u, v = crop[0]+x/w*(1-crop[0]-crop[2]), crop[1]+y/h*(1-crop[1]-crop[3])
            return image.getpixel((min(image.width-1, max(0, int(u*image.width))),
                                   min(image.height-1, max(0, int(v*image.height)))))
        if self.kind == 'tile':
            image = self.value
            return image.getpixel((int(x/.75) % image.width, int(y/.75) % image.height))
        dx, dy = math.cos(self.angle), math.sin(self.angle)
        if self.scaled:
            dx, dy = dx*w, dy*h
        span = abs(dx*w)+abs(dy*h)
        t = (dx*x+dy*y-min(0, dx*w)-min(0, dy*h))/span
        stops = self.value
        if t <= stops[0][0]:
            return stops[0][1]
        for (left, a), (right, b) in zip(stops, stops[1:]):
            if t <= right:
                f = (t-left)/(right-left)
                return tuple(a[i]+f*(b[i]-a[i]) for i in range(4))
        return stops[-1][1]


@dataclass
class Region:
    name: str
    matrix: tuple
    width: float
    height: float
    geometry: str
    paint: Paint | None
    text: bool = False
    stroke: float = 0

    @property
    def bounds(self):
        return box(self.matrix, self.width, self.height)

    def contains(self, x, y, margin=0):
        x, y = inverse(self.matrix, x, y)
        w, h = self.width, self.height
        if self.geometry == 'line':
            t = max(0, min(1, (x*w+y*h)/(w*w+h*h)))
            return math.hypot(x-t*w, y-t*h) <= max(.01, self.stroke/2-margin)
        if not (margin <= x <= w-margin and margin <= y <= h-margin):
            return False
        if self.geometry == 'ellipse':
            return ((x-w/2)/(w/2-margin))**2+((y-h/2)/(h/2-margin))**2 <= 1
        if self.geometry == 'triangle':
            return abs(x-w/2) <= (y-margin)/h*(w/2-margin)
        if self.geometry == 'roundRect':
            r = min(w, h)/6
            return math.hypot(max(r-x, x-w+r, 0), max(r-y, y-h+r, 0)) <= r-margin
        return True


class Reference:
    def __init__(self, deck, slide):
        self.width, self.height = deck.slide_width/12700, deck.slide_height/12700
        self.regions, self.frames, self.text_boxes = [], [], []
        self.exclusions = []
        master = slide.slide_layout.slide_master
        theme_part = next(r.target_part for r in master.part.rels.values() if r.reltype.endswith('/theme'))
        self.theme = ET.fromstring(theme_part.blob)
        scheme = self.theme.find('.//' + qn('a:clrScheme'))
        self.palette = {local(item): next(iter(item)) for item in scheme}
        self.placeholder = None
        mapping = child(master._element, 'p:clrMap')
        self.mapping = dict(mapping.attrib) if mapping is not None else {}
        override = child(child(slide._element, 'p:clrMapOvr'), 'a:overrideClrMapping')
        if override is not None:
            self.mapping.update(override.attrib)
        self.background = Paint('solid', (*WHITE, 255))
        for owner in (master, slide.slide_layout, slide):
            bg = child(child(owner._element, 'p:cSld'), 'p:bg')
            if bg is not None:
                props = child(bg, 'p:bgPr')
                if props is None:
                    self.background = self.style_fill(child(bg, 'p:bgRef'), owner.part)
                else:
                    self.background = self.fill(props, owner.part) or Paint('solid', (*WHITE, 255))
        self.walk(slide.shapes)

    def color(self, element):
        kind = local(element)
        value = element.get('val')
        if kind == 'schemeClr':
            color = self.placeholder if value == 'phClr' else self.color(self.palette[self.mapping.get(value, value)])
            if color is None:
                raise ValueError('unresolved phClr theme placeholder')
        elif kind in ('srgbClr', 'sysClr'):
            color = (*bytes.fromhex(element.get('lastClr') if kind == 'sysClr' else value), 255)
        else:
            raise ValueError(f'reference color not implemented: {kind}')
        rgb, alpha = list(map(float, color[:3])), float(color[3])
        for transform in element:
            kind, amount = local(transform), int(transform.get('val', 0))/100000
            if kind == 'alpha':
                alpha = 255*amount
            elif kind == 'alphaMod':
                alpha *= amount
            elif kind in ('tint', 'shade'):
                rgb = ([v+(255-v)*amount for v in rgb] if kind == 'tint' else [v*amount for v in rgb])
            elif kind in ('lumMod', 'lumOff', 'satMod'):
                h, light, sat = colorsys.rgb_to_hls(*(v/255 for v in rgb))
                light = light*amount if kind == 'lumMod' else light+amount if kind == 'lumOff' else light
                sat = sat*amount if kind == 'satMod' else sat
                rgb = [v*255 for v in colorsys.hls_to_rgb(h, max(0, min(1, light)), max(0, min(1, sat)))]
            else:
                raise ValueError(f'reference color transform not implemented: {kind}')
        return (*rgb, alpha)

    def style_fill(self, ref, part):
        if ref is None:
            raise ValueError('missing theme fill reference')
        index = int(ref.get('idx', 0))
        if not index:
            return None
        tag, offset = ('a:bgFillStyleLst', 1001) if index >= 1001 else ('a:fillStyleLst', 1)
        styles = self.theme.find('.//' + qn(tag))
        props = ET.Element(qn('p:spPr'))
        props.append(copy.deepcopy(styles[index-offset]))
        previous = self.placeholder
        self.placeholder = self.color(next(iter(ref)))
        try:
            return self.fill(props, part)
        finally:
            self.placeholder = previous

    def fill(self, props, part):
        if props is None:
            return None
        solid = child(props, 'a:solidFill')
        if solid is not None:
            return Paint('solid', self.color(next(iter(solid))))
        gradient = child(props, 'a:gradFill')
        if gradient is not None:
            line = child(gradient, 'a:lin')
            if line is None:
                raise ValueError('reference implements linear gradients only')
            stops = sorted((int(stop.get('pos'))/100000, self.color(next(iter(stop))))
                           for stop in child(gradient, 'a:gsLst'))
            return Paint('gradient', stops, int(line.get('ang', 0))/60000*math.pi/180,
                         line.get('scaled', '0') in ('1', 'true'))
        blip = child(props, 'a:blipFill')
        if blip is None:
            blip = child(props, 'p:blipFill')
        if blip is not None:
            rel = child(blip, 'a:blip').get(qn('r:embed'))
            image = Image.open(BytesIO(part.related_part(rel).blob)).convert('RGBA')
            if child(blip, 'a:tile') is not None:
                tile = child(blip, 'a:tile')
                if any(tile.get(k, default) != default for k, default in (('sx', '100000'), ('sy', '100000'),
                       ('tx', '0'), ('ty', '0'), ('flip', 'none'), ('algn', 'tl'))):
                    raise ValueError('reference implements untransformed top-left image tile only')
                return Paint('tile', image)
            crop = child(blip, 'a:srcRect')
            return Paint('image', (image, tuple(int(crop.get(k, 0))/100000 if crop is not None else 0
                                                for k in ('l', 't', 'r', 'b'))))
        for tag in ('a:pattFill', 'a:grpFill'):
            if child(props, tag) is not None:
                raise ValueError(f'reference fill not implemented: {tag}')
        return None

    def text(self, frame, region):
        if not frame.text.strip():
            return
        self.text_boxes.append(region.bounds)
        # Reference-only conservative exclusion: all paragraph rows, full width.
        # This affects color sampling only; the coverage assertion still uses
        # the full, unshrunk python-pptx shape frame, including text-only shapes.
        sizes = [r.font.size.pt if r.font.size else p.font.size.pt if p.font.size else 24
                 for p in frame.paragraphs for r in p.runs]
        size = max(sizes, default=24)
        lines = sum(max(1, math.ceil(len(p.text)*size*.65/max(1, region.width-20))) for p in frame.paragraphs)
        height = min(region.height, lines*size*1.7+20)
        anchor = frame.vertical_anchor
        y = region.height-height if anchor == 4 else (region.height-height)/2 if anchor == 3 else 0
        self.exclusions.append(box(compose(region.matrix, (1, 0, 0, 1, 0, y)), region.width, height))

    def walk(self, shapes, parent=IDENTITY):
        for shape in shapes:
            x, y, w, h = [getattr(shape, key)/12700 for key in ('left', 'top', 'width', 'height')]
            if (not w or not h) and shape.shape_type != 9:
                raise ValueError(f'zero-area reference shape: {shape.name}')
            matrix = compose(parent, (1, 0, 0, 1, x, y))
            xf = shape._element.find('.//' + qn('a:xfrm'))
            angle = math.radians(shape.rotation)
            if angle or (xf is not None and any(xf.get(k) in ('1', 'true') for k in ('flipH', 'flipV'))):
                c, s = math.cos(angle), math.sin(angle)
                fx, fy = [-1 if xf is not None and xf.get(k) in ('1', 'true') else 1 for k in ('flipH', 'flipV')]
                a, b, c, d = c*fx, s*fx, -s*fy, c*fy
                matrix = compose(matrix, (a, b, c, d, w/2-a*w/2-c*h/2, h/2-b*w/2-d*h/2))
            self.frames.append(box(matrix, w, h))
            if shape.shape_type == 6:
                xf = shape._element.grpSpPr.xfrm
                sx, sy = xf.ext.cx/xf.chExt.cx, xf.ext.cy/xf.chExt.cy
                group = compose(matrix, (sx, 0, 0, sy, -xf.chOff.x/12700*sx, -xf.chOff.y/12700*sy))
                self.walk(shape.shapes, group)
                continue
            if shape.has_table:
                table = shape.table
                props = table._tbl.tblPr
                if child(props, 'a:tableStyleId') is not None or table.first_row or table.horz_banding:
                    raise ValueError('reference table preset styling not implemented')
                top = 0
                for row_idx, row in enumerate(table.rows):
                    left = 0
                    for col_idx, col in enumerate(table.columns):
                        cell = table.cell(row_idx, col_idx)
                        if not cell.is_spanned:
                            cw = sum(table.columns[i].width for i in range(col_idx, col_idx+cell.span_width))/12700
                            ch = sum(table.rows[i].height for i in range(row_idx, row_idx+cell.span_height))/12700
                            cell_matrix = compose(matrix, (1, 0, 0, 1, left, top))
                            region = Region(f'{shape.name}/cell{row_idx},{col_idx}', cell_matrix, cw, ch,
                                            'rect', self.fill(cell._tc.tcPr, shape.part), bool(cell.text.strip()))
                            self.regions.append(region)
                            self.text(cell.text_frame, region)
                        left += col.width/12700
                    top += row.height/12700
                continue
            props = child(shape._element, 'p:spPr')
            geometry = child(props, 'a:prstGeom')
            kind = 'line' if shape.shape_type == 9 else geometry.get('prst') if geometry is not None else 'rect'
            if kind not in ('rect', 'ellipse', 'roundRect', 'triangle', 'line') or child(props, 'a:custGeom') is not None:
                raise ValueError(f'reference geometry not implemented: {kind} ({shape.name})')
            paint = self.fill(props, shape.part)
            if shape.shape_type == 13:
                paint = self.fill(shape._element, shape.part)
            line = child(props, 'a:ln')
            if kind == 'line':
                paint = self.fill(line, shape.part)
            region = Region(shape.name, matrix, w, h, kind, paint, shape.has_text_frame and bool(shape.text.strip()))
            if kind == 'line':
                region.stroke = int(line.get('w', 12700))/12700 if line is not None else 1
            self.regions.append(region)
            if region.text:
                self.text(shape.text_frame, region)
            style = child(shape._element, 'p:style')
            fill_ref = child(style, 'a:fillRef')
            if paint is None and child(props, 'a:noFill') is None and fill_ref is not None and int(fill_ref.get('idx', 0)):
                region.paint = self.style_fill(fill_ref, shape.part)
            if shape.shape_type not in (1, 9, 13, 14, 17):
                raise ValueError(f'reference shape type not implemented: {shape.shape_type}')

    def expected(self, x, y):
        result = self.background.rgba(x+.5, y+.5, self.width, self.height)
        rgb = [result[i]*result[3]/255+255*(1-result[3]/255) for i in range(3)]
        for region in self.regions:
            if region.paint is not None and region.contains(x+.5, y+.5):
                u, v = inverse(region.matrix, x+.5, y+.5)
                rgba = region.paint.rgba(u, v, region.width, region.height)
                rgb = [rgba[i]*rgba[3]/255+rgb[i]*(1-rgba[3]/255) for i in range(3)]
        return tuple(max(0, min(255, math.floor(v+.5))) for v in rgb)

    def samples(self):
        pools = []
        # One pool per painted primitive, plus the page. Round-robin retains
        # all six theme accents and samples real shape interiors before white.
        for region in [r for r in self.regions if r.paint is not None] + [None]:
            points = []
            for fy in (.85, .55, .25, .7, .4, .15, .95, .05):
                for fx in (.75, .45, .15, .6, .9, .3, .05, .95):
                    if region and region.geometry == 'line':
                        fy = fx
                    x, y = (point(region.matrix, region.width*fx, region.height*fy) if region
                            else (self.width*fx, self.height*fy))
                    x, y = math.floor(x), math.floor(y)
                    if not (0 <= x < self.width and 0 <= y < self.height):
                        continue
                    if region and not region.contains(x+.5, y+.5, .5 if region.geometry == 'line' else 5):
                        continue
                    if any(l-4 <= x <= r+4 and t-4 <= y <= b+4 for l, t, r, b in self.exclusions):
                        continue
                    # Reject silhouette/overlap boundaries and image edges.
                    if any(r.paint is not None and r.geometry != 'line' and r.contains(x+.5, y+.5) != r.contains(x+.5, y+.5, 4)
                           for r in self.regions):
                        continue
                    expected = self.expected(x, y)
                    if any(max(abs(a-b) for a, b in zip(expected, self.expected(x+dx, y+dy))) > 4
                           for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))):
                        continue
                    points.append((x, y))
            pools.append(points)
        result = []
        while any(pools) and len(result) < 12:
            for pool in pools:
                if pool:
                    p = pool.pop(0)
                    if p not in result:
                        result.append(p)
                    if len(result) == 12:
                        break
        if len(result) != 12:
            raise ValueError(f'only {len(result)} reference color points; need twelve distinct, text-free points')
        return [(x, y, self.expected(x, y)) for x, y in result]


def metrics(reference, image, textless):
    expected_box = union(reference.frames)
    if expected_box:
        expected_box = (max(0, expected_box[0]), max(0, expected_box[1]),
                        min(image.width, expected_box[2]), min(image.height, expected_box[3]))
    actual_box = ImageChops.difference(image, Image.new('RGB', image.size, WHITE)).getbbox()
    coverage = (expected_box is None and actual_box is None) or bool(actual_box and expected_box and
        actual_box[0] <= expected_box[0]+4 and actual_box[1] <= expected_box[1]+4 and
        actual_box[2] >= expected_box[2]-4 and actual_box[3] >= expected_box[3]-4)
    samples = []
    for x, y, expected in reference.samples():
        actual = image.getpixel((x, y))
        delta = max(abs(a-b) for a, b in zip(actual, expected))
        samples.append(dict(x=x, y=y, actual=actual, expected=expected, delta=delta, ok=delta <= 4))
    diff = ImageChops.difference(image, textless).convert('L').point(lambda v: 255 if v else 0)
    mask = Image.new('L', image.size)
    draw = ImageDraw.Draw(mask)
    for l, t, r, b in reference.text_boxes:
        draw.rectangle((max(0, math.floor(l)), max(0, math.floor(t)),
                        min(image.width-1, math.ceil(r)), min(image.height-1, math.ceil(b))), fill=255)
    glyph_pixels = ImageChops.multiply(diff, mask).histogram()[255]
    text = not reference.text_boxes or glyph_pixels > 0
    colors = sum(p['ok'] for p in samples)
    return dict(coverage=coverage, expected_bbox=expected_box, actual_bbox=actual_box,
                colors=colors, samples=samples, text=text, has_text=bool(reference.text_boxes),
                glyph_pixels=glyph_pixels, color_scope='fills-and-background' if any(r.paint for r in reference.regions) else 'background-only',
                ok=coverage and colors >= 10 and text)


def check_file(engine, path, entry, output, repeats):
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    status, code, warning, doc = opened(engine, path=path)
    result = dict(file=path.name, sha256=sha, status=status, code=code, warning=warning, pages=[], ok=False)
    print(f'{path.name} open status={status} code={code} warning={warning!r}')
    baseline = None
    try:
        expected_error = entry.get('expected_status')
        if expected_error is not None:
            result['ok'] = status == code == expected_error and status in (5, 6) and not doc.value and bool(warning)
            result['error_name'] = {5: 'EXR_FORMAT', 6: 'EXR_LIMIT'}.get(status, 'UNEXPECTED')
            print(f"{path.name} bad={'ok' if result['ok'] else 'FAIL'} {result['error_name']} status={status} message={warning!r}")
            return result
        if entry.get('sha256') and entry['sha256'] != sha:
            raise ValueError('manifest SHA256 differs from corpus bytes')
        deck = Presentation(BytesIO(data))
        result['python_slides'] = len(deck.slides)
        if status != 0 or code != 0 or not doc.value:
            raise ValueError(f'open failed status={status} code={code}')
        count = C.c_size_t()
        pages = engine.lib.exr_fixed_pages(doc, C.byref(count))
        result['engine_slides'] = count.value
        file_ok = count.value == len(deck.slides) == entry['slides'] and font_warnings_only(warning)
        print(f'{path.name} slides engine={count.value} python-pptx={len(deck.slides)} manifest={entry["slides"]} warnings={"ok" if font_warnings_only(warning) else "FAIL"}')
        clean_status, clean_code, clean_warning, baseline = opened(engine, data=without_text(data))
        if clean_status or clean_code or not baseline.value or not font_warnings_only(clean_warning):
            raise ValueError(f'textless open failed: {clean_status} {clean_warning}')
        clean_count = C.c_size_t()
        engine.lib.exr_fixed_pages(baseline, C.byref(clean_count))
        if clean_count.value != count.value:
            raise ValueError('textless baseline page count changed')
        times = []
        for index, slide in enumerate(deck.slides):
            page = dict(slide=index+1, ok=False)
            result['pages'].append(page)
            try:
                if index >= count.value:
                    raise ValueError('engine page missing')
                reference = Reference(deck, slide)
                image, ms = render(engine, doc, index)
                clean, _ = render(engine, baseline, index)
                expected_size = (math.ceil(reference.width), math.ceil(reference.height))
                if image.size != expected_size or clean.size != image.size:
                    raise ValueError(f'bitmap dimensions={image.size}, reference={expected_size}')
                page.update(metrics(reference, image, clean))
                page['render_ms'] = ms
                page['geometry_bounds'] = list(pages[index].geometry.bounds)
                if any(abs(a-b) > .01 for a, b in zip(page['geometry_bounds'], (0, 0, reference.width, reference.height))):
                    page['ok'] = False
                    page['geometry_error'] = 'public page geometry differs from python-pptx'
                print(f'{path.name}#{index+1} coverage={"ok" if page["coverage"] else "FAIL"} color={page["colors"]}/12 text={"ok" if page["text"] else "FAIL"}')
                if not page['coverage']:
                    print(f'  bbox actual={page["actual_bbox"]} expected={page["expected_bbox"]} tolerance=4px')
                for sample in page['samples']:
                    if not sample['ok']:
                        print(f'  color ({sample["x"]},{sample["y"]}) actual={sample["actual"]} expected={sample["expected"]} delta={sample["delta"]}')
                if not page['text']:
                    print(f'  text glyph_pixels={page["glyph_pixels"]} expected>0')
                if output:
                    target = output / path.stem
                    target.mkdir(parents=True, exist_ok=True)
                    image.save(target / f'{index+1:02}.png')
                    clean.save(target / f'{index+1:02}-textless.png')
                if entry.get('benchmark'):
                    # Measure the unmodified document's public render only,
                    # including allocation, excluding Python copying and oracle.
                    measures = [ms]
                    for _ in range(repeats-1):
                        _, elapsed = render(engine, doc, index)
                        measures.append(elapsed)
                    page['render_samples_ms'] = measures
                    times.extend(measures)
            except Exception as exc:
                page['error'] = str(exc)
                print(f'{path.name}#{index+1} coverage=FAIL color=FAIL/12 text=FAIL error={exc}')
            file_ok &= page['ok']
        if times:
            result['performance'] = dict(repeats=repeats, samples=len(times), median_ms=statistics.median(times),
                                         max_ms=max(times), limit_ms=200, ok=max(times) < 200)
            file_ok &= result['performance']['ok']
            print(f'{path.name} render samples={len(times)} median={statistics.median(times):.3f}ms max={max(times):.3f}ms limit=200ms')
        result['ok'] = bool(file_ok)
    except Exception as exc:
        result['error'] = str(exc)
        print(f'{path.name} FAIL {exc}')
    finally:
        if baseline and baseline.value:
            engine.lib.exr_fixed_free(baseline)
        if doc.value:
            engine.lib.exr_fixed_free(doc)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--fixtures', type=Path, default=HERE)
    parser.add_argument('--output', type=Path, help='write JSON and actual/textless PNGs')
    parser.add_argument('--file', help='select one fixture stem (all are checked by default)')
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    engine = Engine(args.library.resolve())
    manifests = sorted(args.fixtures.glob('*/manifest.json'))
    entries = [(m, json.loads(m.read_text(encoding='utf-8'))) for m in manifests]
    if args.file:
        entries = [(m, e) for m, e in entries if Path(e['file']).stem == args.file]
        if len(entries) != 1:
            parser.error('--file must select exactly one fixture')
    elif sum('expected_status' not in e for _, e in entries) < 12 or sum('expected_status' in e for _, e in entries) != 3:
        parser.error('corpus requires >=12 valid presentations and exactly three malformed files')
    results = [check_file(engine, m.parent / e['file'], e, args.output, args.repeats) for m, e in entries]
    summary = dict(python=sys.version.split()[0], platform=sys.platform,
                   library=str(args.library.resolve()), library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(),
                   coverage_tolerance_px=4, color_tolerance_per_channel=4, color_pass_minimum=10,
                   files=len(results), passed=sum(r['ok'] for r in results), results=results)
    print(f'MATRIX files={len(results)} passed={summary["passed"]} failed={len(results)-summary["passed"]}')
    if args.output:
        (args.output / 'matrix.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return 0 if all(r['ok'] for r in results) else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
