"""Reports media recognition, SMIL overlays and page counts for EPUBs, and saves page PNGs.

usage: python media_report.py DLL FONT LAYOUT_JSON OUTPUT_DIR BOOK.epub [BOOK.epub ...]
Writes OUTPUT_DIR/media-report.json and OUTPUT_DIR/<book>-p<N>.png for pages that show a placeholder.
"""
import ctypes as c
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'regress'))
import run_realbooks as rr  # noqa: E402
from PIL import Image  # noqa: E402

KINDS = {1: 'audio', 2: 'video', 3: 'embedded'}
STATES = {0: 'available', 1: 'missing', 2: 'unsupported', 3: 'remote', 4: 'no-source'}


class Item(c.Structure):
    _fields_ = [('kind', c.c_int), ('state', c.c_int), ('flags', c.c_uint), ('element', c.c_size_t),
                ('placeholder', c.c_size_t), ('tag', c.c_char_p), ('src', c.c_char_p), ('path', c.c_char_p),
                ('media_type', c.c_char_p), ('poster', c.c_char_p), ('duration_ms', c.c_longlong),
                ('source_count', c.c_size_t), ('label', c.c_char_p)]


class Clip(c.Structure):
    _fields_ = [('par_id', c.c_char_p), ('text_path', c.c_char_p), ('fragment', c.c_char_p),
                ('text_part', c.c_size_t), ('text_start', c.c_size_t), ('text_end', c.c_size_t),
                ('audio_path', c.c_char_p), ('clip_begin_ms', c.c_longlong), ('clip_end_ms', c.c_longlong),
                ('audio_present', c.c_int)]


class Overlay(c.Structure):
    _fields_ = [('smil_path', c.c_char_p), ('duration_ms', c.c_longlong), ('active_class', c.c_char_p),
                ('playback_active_class', c.c_char_p), ('clips', c.POINTER(Clip)), ('clip_count', c.c_size_t),
                ('missing_audio', c.c_size_t), ('unresolved_text', c.c_size_t)]


FLAGS = [(1, 'autoplay'), (2, 'loop'), (4, 'controls'), (8, 'muted'), (16, 'hidden'), (32, 'cover'),
         (64, 'background'), (128, 'duration-estimated')]
SIZE_MAX = 2 ** 64 - 1


def text(b):
    return b.decode('utf-8') if b else None


def main(dll, font_path, layout_path, out, books):
    layout = rr.read_json(layout_path)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sdk = rr.SDK(Path(dll).resolve())
    d = sdk.dll
    d.exr_document_media.restype, d.exr_document_media.argtypes = c.POINTER(Item), [c.c_void_p, c.POINTER(c.c_size_t)]
    d.exr_document_text.restype, d.exr_document_text.argtypes = c.c_char_p, [c.c_void_p, c.POINTER(c.c_size_t)]
    d.exr_publication_media_overlay.restype = c.c_int
    d.exr_publication_media_overlay.argtypes = [c.c_void_p, c.c_size_t, c.POINTER(c.POINTER(Overlay)), c.POINTER(rr.Error)]
    d.exr_media_overlay_free.restype, d.exr_media_overlay_free.argtypes = None, [c.POINTER(Overlay)]
    report = []
    font = c.c_void_p()
    sdk.check('font_open', str(font_path).encode(), c.byref(font))
    for book in books:
        book = Path(book)
        pub = c.c_void_p()
        sdk.check('publication_open', str(book).encode(), c.byref(pub))
        parts = c.c_size_t()
        sdk.publication_parts(pub, c.byref(parts))
        entry = {'book': book.name, 'parts': parts.value, 'pages': 0, 'media': [], 'overlays': [], 'screenshots': []}
        config = sdk.layout_config_defaults()
        config.page = rr.Options(**{k: layout[k] for k, _ in rr.Options._fields_})
        config.document_css, config.embedded_fonts, config.direction = layout['document_css'], layout['embedded_fonts'], layout['direction']
        for part in range(parts.value):
            doc = c.c_void_p()
            sdk.check('publication_load', pub, part, c.byref(doc))
            n = c.c_size_t()
            items = d.exr_document_media(doc, c.byref(n))
            labels = []
            for i in range(n.value):
                it = items[i]
                labels.append(text(it.label))
                entry['media'].append({
                    'part': part, 'kind': KINDS[it.kind], 'state': STATES[it.state],
                    'flags': [name for bit, name in FLAGS if it.flags & bit], 'src': text(it.src), 'path': text(it.path),
                    'media_type': text(it.media_type), 'poster': text(it.poster), 'duration_ms': it.duration_ms,
                    'source_count': it.source_count, 'label': text(it.label), 'placeholder_node': it.placeholder != SIZE_MAX})
            ov = c.POINTER(Overlay)()
            error = rr.Error()
            status = d.exr_publication_media_overlay(pub, part, c.byref(ov), c.byref(error))
            if status:
                entry['overlays'].append({'part': part, 'status': status, 'error': error.message.decode()})
            elif ov:
                o = ov.contents
                entry['overlays'].append({
                    'part': part, 'smil': text(o.smil_path), 'duration_ms': o.duration_ms, 'active_class': text(o.active_class),
                    'clips': o.clip_count, 'missing_audio': o.missing_audio, 'unresolved_text': o.unresolved_text,
                    'pairs': [{'par': text(o.clips[i].par_id), 'text': [o.clips[i].text_part, o.clips[i].text_start, o.clips[i].text_end],
                               'fragment': text(o.clips[i].fragment), 'audio': text(o.clips[i].audio_path),
                               'begin_ms': o.clips[i].clip_begin_ms, 'end_ms': o.clips[i].clip_end_ms,
                               'audio_present': bool(o.clips[i].audio_present)} for i in range(o.clip_count)]})
                size = c.c_size_t()
                body = c.string_at(d.exr_document_text(doc, c.byref(size)), size.value)
                for pair in entry['overlays'][-1]['pairs']:
                    s, e = pair['text'][1:]
                    pair['text_excerpt'] = body[s:e].decode('utf-8') if s != SIZE_MAX else None
                d.exr_media_overlay_free(ov)
            pager, page = c.c_void_p(), c.c_void_p()
            sdk.check('pager_create', doc, font, c.byref(config), c.byref(pager))
            local = 0
            while True:
                sdk.check('pager_next', pager, c.byref(page))
                if not page:
                    break
                bitmap = rr.Bitmap()
                sdk.check('render_page_color', page, sdk.layout_font(page), 0, c.byref(bitmap))
                entry['pages'] += 1
                if (any(labels) or local == 0) and local < 2:
                    img = Image.frombuffer('RGBA', (bitmap.width, bitmap.height), c.string_at(bitmap.pixels, bitmap.stride * bitmap.height),
                                           'raw', 'RGBA', bitmap.stride, 1)
                    name = f'{book.stem}-part{part}-p{local}.png'
                    img.convert('RGB').save(out / name)
                    entry['screenshots'].append(name)
                sdk.bitmap_free(c.byref(bitmap))
                sdk.layout_free(page)
                page = c.c_void_p()
                local += 1
            sdk.pager_free(pager)
            sdk.document_free(doc)
        entry['media_count'] = len(entry['media'])
        sdk.publication_free(pub)
        report.append(entry)
    sdk.font_free(font)
    (out / 'media-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for e in report:
        print(f"{e['book']}: parts={e['parts']} pages={e['pages']} media={e['media_count']} overlays={len(e['overlays'])} screenshots={e['screenshots']}")


if __name__ == '__main__':
    main(*sys.argv[1:5], sys.argv[5:])
