#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate deterministic 100+ page real-world, image-heavy, and vector-heavy PDF fixtures.

Sources:
- C:/Users/Oscar/OneDrive/Desktop/课件.pdf (21-page real PowerPoint courseware)
- tests/fixtures/pdf-ppt/deck.pdf (15-page lecture deck)
- tests/fixtures/pdf-hybrid-real/{word-5,pptx-20,excel-1,chinese,image-only}.pdf
- Synthesized stress pages for varied full-page images and dense vector/clip geometry
"""
import argparse
import hashlib
import json
import math
import re
import zlib
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    StreamObject,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COURSEWARE = Path(r'C:\Users\Oscar\OneDrive\Desktop\课件.pdf')
DEFAULT_OUT_DIR = ROOT / 'tests' / 'fixtures' / 'pdf-large'


def normalize_courseware(path: Path, scratch_path: Path) -> Path:
    """Normalize PatternType 2 shading patterns in courseware to /Shading + sh operator.

    ISO 32000-1 PatternType 2 fills the current path with a shading dictionary.
    Converting `/Pattern cs /Pxx scn <rect> re f*` into `q <rect> re W* n /Pxx sh Q`
    preserves exact visual output while allowing baseline main to render every page.
    """
    reader = PdfReader(str(path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    def convert_stream(res_obj, stream_obj):
        if '/Pattern' not in res_obj:
            return
        pats = res_obj['/Pattern'].get_object()
        shadings = res_obj.get('/Shading', DictionaryObject()).get_object()
        if not isinstance(shadings, DictionaryObject):
            shadings = DictionaryObject()
        for key, val in pats.items():
            pobj = val.get_object()
            if pobj.get('/PatternType') == 2 and '/Shading' in pobj:
                shadings[NameObject(key)] = pobj['/Shading']
        res_obj[NameObject('/Shading')] = shadings
        raw = stream_obj.get_data().decode('latin1')

        def repl(match):
            pat_name = match.group(1)
            gs_part = match.group(2) or ''
            rect_part = match.group(3)
            return f'{gs_part}q\n{rect_part}\nW* n\n{pat_name} sh\nQ'

        new_raw = re.sub(
            r'/Pattern\s+cs\s+(/\S+)\s+scn\s*\r?\n((?:/\S+\s+gs\s*\r?\n)?)([^\r\n]+re)\s*\r?\nf\*',
            repl,
            raw,
        )
        encoded = new_raw.encode('latin1')
        if getattr(stream_obj, 'decoded_self', None) is not None:
            stream_obj.decoded_self.set_data(encoded)
        stream_obj.set_data(encoded)

    for obj in writer._objects:
        if isinstance(obj, DictionaryObject) and '/Resources' in obj:
            res = obj['/Resources'].get_object()
            if isinstance(obj, StreamObject):
                convert_stream(res, obj)
            elif '/Contents' in obj:
                c_obj = obj['/Contents'].get_object()
                convert_stream(res, c_obj)

    scratch_path.parent.mkdir(parents=True, exist_ok=True)
    with open(scratch_path, 'wb') as handle:
        writer.write(handle)
    return scratch_path


def make_image_xobject(writer: PdfWriter, width: int, height: int, seed: int, with_smask: bool = False):
    """Create a deterministic Flate-compressed RGB image XObject (and optional soft mask)."""
    raw = bytearray(width * height * 3)
    for y in range(height):
        row_off = y * width * 3
        by = (y // 8 + seed * 5) & 0xFF
        for x in range(width):
            off = row_off + x * 3
            bx = (x // 8 + seed * 11) & 0xFF
            raw[off] = bx
            raw[off + 1] = by
            raw[off + 2] = (bx + by + seed * 17) & 0xFF

    img = DecodedStreamObject()
    img.set_data(bytes(raw))
    img[NameObject('/Type')] = NameObject('/XObject')
    img[NameObject('/Subtype')] = NameObject('/Image')
    img[NameObject('/Width')] = NumberObject(width)
    img[NameObject('/Height')] = NumberObject(height)
    img[NameObject('/ColorSpace')] = NameObject('/DeviceRGB')
    img[NameObject('/BitsPerComponent')] = NumberObject(8)
    img[NameObject('/Interpolate')] = BooleanObject(True)

    if with_smask:
        mask_raw = bytearray(width * height)
        for y in range(height):
            my = y * width
            vy = (y // 8) * 7
            for x in range(width):
                mask_raw[my + x] = 64 + (((x // 8) * 5 + vy + seed * 11) & 0x7F)
        smask = DecodedStreamObject()
        smask.set_data(bytes(mask_raw))
        smask[NameObject('/Type')] = NameObject('/XObject')
        smask[NameObject('/Subtype')] = NameObject('/Image')
        smask[NameObject('/Width')] = NumberObject(width)
        smask[NameObject('/Height')] = NumberObject(height)
        smask[NameObject('/ColorSpace')] = NameObject('/DeviceGray')
        smask[NameObject('/BitsPerComponent')] = NumberObject(8)
        img[NameObject('/SMask')] = writer._add_object(smask.flate_encode())

    return writer._add_object(img.flate_encode())


def add_synthetic_image_page(writer: PdfWriter, variant: int):
    """Add a synthetic full-page / multi-image stress page with varied image dimensions."""
    page = writer.add_blank_page(width=720, height=540)
    res = DictionaryObject()
    xobjs = DictionaryObject()

    # Vary dimensions across pages so image cache and scaling paths see diverse sizes
    dims = [
        (960, 720, True),
        (1200, 675, False),
        (800, 600, True),
        (1024, 512, False),
        (720, 540, True),
    ]
    w1, h1, has_mask = dims[variant % len(dims)]
    xobjs[NameObject('/ImBg')] = make_image_xobject(writer, w1, h1, variant * 3 + 1, with_smask=has_mask)
    xobjs[NameObject('/ImTile1')] = make_image_xobject(writer, 320 + (variant % 7) * 16, 240, variant * 3 + 2, with_smask=False)
    xobjs[NameObject('/ImTile2')] = make_image_xobject(writer, 256, 192 + (variant % 5) * 16, variant * 3 + 3, with_smask=True)

    res[NameObject('/XObject')] = xobjs
    page[NameObject('/Resources')] = res

    ops = [
        'q 0.95 0.96 0.98 rg 0 0 720 540 re f Q',
        'q 20 20 680 500 re W* n 680 0 0 500 20 20 cm /ImBg Do Q',
        'q 40 40 300 220 re W n 300 0 0 220 40 40 cm /ImTile1 Do Q',
        'q 380 260 300 220 re W* n 300 0 0 220 380 260 cm /ImTile2 Do Q',
    ]
    stream = DecodedStreamObject()
    stream.set_data('\n'.join(ops).encode('latin1'))
    page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())


def add_synthetic_vector_page(writer: PdfWriter, variant: int):
    """Add a synthetic vector-dense page with complex clips, curves, strokes, and dashes."""
    page = writer.add_blank_page(width=720, height=540)
    page[NameObject('/Resources')] = DictionaryObject()

    ops = ['q 0.98 0.98 0.97 rg 0 0 720 540 re f Q']
    # Non-rectangular polygon clip + grid + cubic bezier waves + filled polygons
    ops.append('q')
    ops.append('30 30 m 690 20 l 700 510 l 20 520 l h W n')
    for idx in range(60):
        y = 35.0 + idx * 7.8
        r = ((idx * 17 + variant * 13) % 200) / 255.0
        g = ((idx * 31 + variant * 7) % 200) / 255.0
        b = ((idx * 47 + variant * 23) % 200) / 255.0
        ops.append(f'{r:.3f} {g:.3f} {b:.3f} RG 1.2 w')
        if idx % 3 == 0:
            ops.append('[4 2] 1 d')
        else:
            ops.append('[] 0 d')
        ops.append(
            f'40 {y:.2f} m 240 {y + 18.0:.2f} 480 {y - 18.0:.2f} 680 {y:.2f} c S'
        )
    # Overlapping semi-complex polygons with even-odd and non-zero fills
    for idx in range(25):
        cx = 90.0 + (idx % 5) * 135.0
        cy = 80.0 + (idx // 5) * 95.0
        rad = 36.0
        r = ((idx * 43 + variant * 19) % 220) / 255.0
        g = ((idx * 29 + variant * 41) % 220) / 255.0
        b = ((idx * 61 + variant * 11) % 220) / 255.0
        pts = []
        for k in range(12):
            ang = k * math.pi / 6.0 + (variant * 0.1)
            rr = rad if k % 2 == 0 else rad * 0.48
            px = cx + rr * math.cos(ang)
            py = cy + rr * math.sin(ang)
            pts.append((px, py))
        path_cmds = [f'{pts[0][0]:.2f} {pts[0][1]:.2f} m']
        for px, py in pts[1:]:
            path_cmds.append(f'{px:.2f} {py:.2f} l')
        path_cmds.append('h')
        ops.append(f'q {r:.3f} {g:.3f} {b:.3f} rg 0.2 0.2 0.2 RG 0.8 w ' + ' '.join(path_cmds) + ' B* Q')
    ops.append('Q')

    stream = DecodedStreamObject()
    stream.set_data('\n'.join(ops).encode('latin1'))
    page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def build_fixtures(courseware_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    norm_courseware = normalize_courseware(courseware_path, out_dir / '.normalized-courseware.pdf')

    cw_reader = PdfReader(str(norm_courseware))
    deck_reader = PdfReader(str(ROOT / 'tests/fixtures/pdf-ppt/deck.pdf'))
    word_reader = PdfReader(str(ROOT / 'tests/fixtures/pdf-hybrid-real/word-5.pdf'))
    pptx_reader = PdfReader(str(ROOT / 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf'))
    excel_reader = PdfReader(str(ROOT / 'tests/fixtures/pdf-hybrid-real/excel-1.pdf'))
    chinese_reader = PdfReader(str(ROOT / 'tests/fixtures/pdf-hybrid-real/chinese.pdf'))
    imgonly_reader = PdfReader(str(ROOT / 'tests/fixtures/pdf-hybrid-real/image-only.pdf'))

    manifest = {}

    # 1. real-mixed-120.pdf: 120 pages of real mixed documents
    # 21 (courseware) + 30 (2x deck) + 25 (5x word-5) + 40 (2x pptx-20) + 2 (excel-1) + 2 (chinese) = 120 pages
    mixed_writer = PdfWriter()
    for p in cw_reader.pages:
        mixed_writer.add_page(p)
    for _ in range(2):
        for p in deck_reader.pages:
            mixed_writer.add_page(p)
    for _ in range(5):
        for p in word_reader.pages:
            mixed_writer.add_page(p)
    for _ in range(2):
        for p in pptx_reader.pages:
            mixed_writer.add_page(p)
    for _ in range(2):
        mixed_writer.add_page(excel_reader.pages[0])
        mixed_writer.add_page(chinese_reader.pages[0])

    mixed_path = out_dir / 'real-mixed-120.pdf'
    with open(mixed_path, 'wb') as f:
        mixed_writer.write(f)
    manifest['real-mixed-120'] = {
        'file': mixed_path.as_posix(),
        'pages': len(mixed_writer.pages),
        'bytes': mixed_path.stat().st_size,
        'sha256': sha256_file(mixed_path),
    }

    # 2. image-heavy-100.pdf: 100 pages of image-dense documents
    # 10 (image-rich courseware slides: 1,2,3,12,17 x2) + 30 (2x deck) + 20 (4x word-5) + 10 (image-only) + 30 (synthetic multi-image) = 100 pages
    img_writer = PdfWriter()
    for _ in range(2):
        for pno in (1, 2, 3, 12, 17):
            img_writer.add_page(cw_reader.pages[pno - 1])
    for _ in range(2):
        for p in deck_reader.pages:
            img_writer.add_page(p)
    for _ in range(4):
        for p in word_reader.pages:
            img_writer.add_page(p)
    for _ in range(10):
        img_writer.add_page(imgonly_reader.pages[0])
    for idx in range(30):
        add_synthetic_image_page(img_writer, idx)

    img_path = out_dir / 'image-heavy-100.pdf'
    with open(img_path, 'wb') as f:
        img_writer.write(f)
    manifest['image-heavy-100'] = {
        'file': img_path.as_posix(),
        'pages': len(img_writer.pages),
        'bytes': img_path.stat().st_size,
        'sha256': sha256_file(img_path),
    }

    # 3. vector-heavy-100.pdf: 100 pages of vector/clip/shading/text-dense documents
    # 10 (courseware vector/table slides: 6,8,9,10,11,13,14,18,20,21) + 15 (excel-1) + 40 (2x pptx-20) + 35 (synthetic dense vector) = 100 pages
    vec_writer = PdfWriter()
    for pno in (6, 8, 9, 10, 11, 13, 14, 18, 20, 21):
        vec_writer.add_page(cw_reader.pages[pno - 1])
    for _ in range(15):
        vec_writer.add_page(excel_reader.pages[0])
    for _ in range(2):
        for p in pptx_reader.pages:
            vec_writer.add_page(p)
    for idx in range(35):
        add_synthetic_vector_page(vec_writer, idx)

    vec_path = out_dir / 'vector-heavy-100.pdf'
    with open(vec_path, 'wb') as f:
        vec_writer.write(f)
    manifest['vector-heavy-100'] = {
        'file': vec_path.as_posix(),
        'pages': len(vec_writer.pages),
        'bytes': vec_path.stat().st_size,
        'sha256': sha256_file(vec_path),
    }

    norm_courseware.unlink(missing_ok=True)
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--courseware', type=Path, default=DEFAULT_COURSEWARE)
    ap.add_argument('--out-dir', type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()
    manifest = build_fixtures(args.courseware, args.out_dir)
    for name, info in manifest.items():
        print(f"{name}: {info['pages']} pages, {info['bytes']} bytes, sha256={info['sha256'][:16]}...")


if __name__ == '__main__':
    main()
