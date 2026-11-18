"""Record drawn image dictionaries and clip path operators, without decoding images."""
from pathlib import Path
import hashlib
import json
from pypdf import PdfReader
from pypdf.generic import ContentStream

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'tests/fixtures/pdf-large/image-heavy-100.pdf'
reader = PdfReader(path)
rows = []
for i, page in enumerate(reader.pages):
    if i < 10:
        continue
    objects = page['/Resources'].get('/XObject', {})
    images, clips, path_ops = [], [], []
    for args, op in ContentStream(page.get_contents(), reader).operations:
        if op == b'Do':
            ref = objects.raw_get(args[0])
            image = ref.get_object()
            if image.get('/Subtype') != '/Image':
                continue
            mask = image.get('/SMask')
            mask = mask.get_object() if mask else None
            images.append({
                'name': str(args[0]), 'object': ref.idnum,
                'width': image['/Width'], 'height': image['/Height'],
                'interpolate': str(image.get('/Interpolate', 'False')),
                'mask': None if mask is None else {
                    'width': mask['/Width'], 'height': mask['/Height'],
                    'color_space': str(mask.get('/ColorSpace')),
                    'interpolate': str(mask.get('/Interpolate', 'False')),
                    'matte': str(mask.get('/Matte')),
                },
            })
        if op in (b'm', b'l', b'c', b'v', b'y', b'h', b're'):
            path_ops.append(op.decode())
        if op in (b'W', b'W*'):
            clips.append({'rule': op.decode(), 'path_ops': path_ops.copy()})
        if op in (b'n', b'S', b's', b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*'):
            path_ops = []
    rows.append({'page': i + 1, 'images': images, 'clips': clips})
out = Path(__file__).resolve().parent / 'continuation/content.json'
out.write_text(json.dumps({'pdf_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'pages': rows}, indent=1))
for lo, hi in ((11, 70), (71, 100)):
    pages = [p for p in rows if lo <= p['page'] <= hi]
    images = [x for p in pages for x in p['images']]
    print(lo, hi, 'draws/page', sorted(set(len(p['images']) for p in pages)),
          'dimensions', sorted(set((x['width'], x['height']) for x in images)),
          'clips/page', sorted(set(len(p['clips']) for p in pages)),
          'masked draws', sum(x['mask'] is not None for x in images), '/', len(images))
