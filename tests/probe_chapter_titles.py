"""Locate recognized HTML titles before/after chapter pagination (public SDK)."""
import argparse
from collections import Counter
import ctypes as c
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'regress'))
from run_realbooks import SDK, Options, read_json, write_json


class Attribute(c.Structure):
    _fields_ = [('name', c.c_char_p), ('value', c.c_char_p)]


class Node(c.Structure):
    _fields_ = [('kind', c.c_int)] + [(k, c.c_size_t) for k in
        ('parent', 'first_child', 'next_sibling', 'chapter', 'start', 'end')] + [
        ('name', c.c_char_p), ('text', c.c_char_p),
        ('attributes', c.POINTER(Attribute)), ('attribute_count', c.c_size_t)]


class Line(c.Structure):
    _fields_ = [(k, c.c_size_t) for k in ('start', 'end', 'glyph_start', 'glyph_count')] + [
        ('y', c.c_float), ('page', c.c_size_t), ('x', c.c_float),
        ('width', c.c_float), ('height', c.c_float)]


def locate(dll, book, font_path, layout):
    sdk = SDK(Path(dll).resolve())
    for name, result, arguments in [
        ('document_nodes', c.POINTER(Node), [c.c_void_p, c.POINTER(c.c_size_t)]),
        ('document_text', c.c_void_p, [c.c_void_p, c.POINTER(c.c_size_t)]),
        ('layout_lines', c.POINTER(Line), [c.c_void_p, c.POINTER(c.c_size_t)]),
    ]:
        fn = getattr(sdk.dll, 'exr_' + name)
        fn.restype, fn.argtypes = result, arguments
        setattr(sdk, name, fn)
    font, pub = c.c_void_p(), c.c_void_p()
    sdk.check('font_open', str(font_path).encode('utf-8'), c.byref(font))
    sdk.check('publication_open', book['path'].encode('utf-8'), c.byref(pub))
    parts, result, global_page = c.c_size_t(), {}, 0
    sdk.publication_parts(pub, c.byref(parts))
    config = sdk.layout_config_defaults()
    config.page = Options(**{k: layout[k] for k, _ in Options._fields_})
    for k in ('document_css', 'embedded_fonts', 'direction'):
        setattr(config, k, layout[k])
    for part in range(parts.value):
        doc, pager, page = c.c_void_p(), c.c_void_p(), c.c_void_p()
        sdk.check('publication_load', pub, part, c.byref(doc))
        size = c.c_size_t()
        text = sdk.document_text(doc, c.byref(size))
        text = c.string_at(text, size.value)
        nodes = sdk.document_nodes(doc, c.byref(size))
        pending = []
        for i in range(size.value):
            node = nodes[i]
            attrs = {node.attributes[j].name: node.attributes[j].value
                     for j in range(node.attribute_count)}
            classes = set(attrs.get(b'class', b'').split())
            if node.start < node.end and (node.kind == 7 or
                    b'heading' in attrs.get(b'role', b'').split() or
                    classes & {b'title', b'chapter-title', b'chapter_title', b'chaptertitle'}):
                pending.append((i, node.start, node.end))
        sdk.check('pager_create', doc, font, c.byref(config), c.byref(pager))
        local_page = 0
        while True:
            sdk.check('pager_next', pager, c.byref(page))
            if not page:
                break
            global_page += 1
            local_page += 1
            lines = sdk.layout_lines(page, c.byref(size))
            for i, start, end in pending:
                key = f'{part}:{i}'
                if key in result:
                    continue
                for j in range(size.value):
                    if lines[j].start <= start < lines[j].end:
                        node = nodes[i]
                        result[key] = {'part': part, 'node': i,
                            'tag': node.name.decode().split('|')[-1],
                            'page': global_page, 'part_page': local_page,
                            'line': j + 1, 'text': text[start:end].decode()[:100]}
                        break
            sdk.layout_free(page)
        sdk.pager_free(pager)
        sdk.document_free(doc)
    sdk.publication_free(pub)
    sdk.font_free(font)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'font', 'manifest', 'layout', 'diff', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    changed = {b['id'] for b in read_json(args.diff)['books'] if b['page_count_changed']}
    report = []
    for book in read_json(args.manifest)['books']:
        if book['id'] not in changed or book['language'] in ('zh', 'ja'):
            continue
        old = locate(args.before, book, args.font, read_json(args.layout))
        new = locate(args.after, book, args.font, read_json(args.layout))
        moved = [{'before': old[k], 'after': new[k]} for k in old.keys() & new.keys()
                 if old[k]['line'] > 1 and new[k]['line'] == 1]
        moved.sort(key=lambda item: (item['after']['part'], item['after']['node']))
        entry = {'id': book['id'], 'located_titles': len(new),
                 'moved_from_midpage_to_first_line': len(moved),
                 'moved_tags': dict(Counter(v['after']['tag'] for v in moved)), 'moved': moved}
        report.append(entry)
        print(json.dumps({k: v for k, v in entry.items() if k != 'moved'}), flush=True)
    write_json(args.output, report)


if __name__ == '__main__':
    main()
