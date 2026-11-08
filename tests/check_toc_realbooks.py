"""Audit public TOC/link APIs against original EPUB XML and actual layout lines.

Books stay local. Persist only chapter labels, paths, offsets and measurements.
Run with --dll --manifest --font --layout --output (same inputs as run_realbooks).
"""
import argparse
import ctypes as c
import json
from pathlib import Path
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'regress'))
from run_realbooks import SDK, Error, file_hash, read_json, write_json

SIZE_MAX = c.c_size_t(-1).value


class Target(c.Structure):
    _fields_ = [('part', c.c_size_t), ('fragment', c.c_char_p), ('offset', c.c_size_t)]


class Toc(c.Structure):
    _fields_ = [('title', c.c_char_p), ('level', c.c_size_t), ('target', Target),
                ('source', c.c_int), ('play_order', c.c_size_t)]


class Location(c.Structure):
    _fields_ = [('part', c.c_size_t), ('offset', c.c_size_t), ('state', c.c_int)]


class Part(c.Structure):
    _fields_ = [('id', c.c_char_p), ('path', c.c_char_p), ('title', c.c_char_p),
                ('in_reading_order', c.c_int)]


class Line(c.Structure):
    _fields_ = [(k, c.c_size_t) for k in ('start', 'end', 'glyph_start', 'glyph_count')] + [
        ('y', c.c_float), ('page', c.c_size_t), ('x', c.c_float),
        ('width', c.c_float), ('height', c.c_float)]


def bind(sdk):
    ptr, size = c.c_void_p, c.c_size_t
    signatures = {
        'publication_toc': (c.c_int, [ptr, c.POINTER(c.POINTER(Toc)), c.POINTER(size), c.POINTER(Error)]),
        'publication_resolve_href': (c.c_int, [ptr, c.c_char_p, c.c_char_p, ptr, c.POINTER(Target), c.POINTER(Error)]),
        'publication_locate': (c.c_int, [ptr, c.POINTER(Target), c.POINTER(Location), c.POINTER(Error)]),
        'publication_target_at': (c.c_int, [ptr, size, size, c.POINTER(size), c.POINTER(Error)]),
        'publication_missing_targets': (c.POINTER(Target), [ptr, c.POINTER(size)]),
        'document_locate': (c.c_int, [ptr, c.c_char_p, c.POINTER(Location), c.POINTER(Error)]),
        'document_text': (c.c_char_p, [ptr, c.POINTER(size)]),
        'layout_lines': (c.POINTER(Line), [ptr, c.POINTER(size)]),
    }
    for name, (result, args) in signatures.items():
        fn = getattr(sdk.dll, 'exr_' + name)
        fn.restype, fn.argtypes = result, args
        setattr(sdk, name, fn)
    sdk.publication_parts.restype = c.POINTER(Part)


def compact(value):
    return ''.join(char for char in value if not char.isspace())


def expected_offset(xml, entry, projected):
    """Find raw heading/anchor text independently of engine anchor resolution.

    Whitespace-insensitive matching accommodates EPUB source wrapping. Require
    one occurrence of 64 source characters, including following heading context.
    The byte position comes from the independent text match, not the target.
    """
    body = next(n for n in xml.iter() if n.tag.split('}')[-1] == 'body')
    if entry.source == 3:
        raw = ''.join(body.itertext())
        title = compact(entry.title.decode())
        # The recovered label is a standalone source line, not a prose mention.
        lines = raw.splitlines(keepends=True)
        candidates = []
        for i, line in enumerate(lines):
            if compact(line) == title:
                candidates.append(compact(''.join(lines[i:]))[:64])
        assert candidates, f'No source title: {entry.title!r}'
        query = candidates[-1]
    else:
        fragment = entry.target.fragment.decode()
        anchor = body if not fragment else next(n for n in xml.iter() if fragment in (
            n.get('id'), n.get('name'), n.get('{http://www.w3.org/XML/1998/namespace}id')))
        # Empty <a id=.../> anchors precede the title; include following siblings.
        chunks, starts, position = [], {}, 0

        def visit(node):
            nonlocal position
            starts[node] = position
            if node.text:
                chunks.append(node.text)
                position += len(node.text)
            for child in node:
                visit(child)
                if child.tail:
                    chunks.append(child.tail)
                    position += len(child.tail)

        visit(body)
        query = compact(''.join(chunks)[starts[anchor]:])[:64]
    assert query, f'Empty source heading: {entry.title!r}'
    positions = [i for i, char in enumerate(projected) if not char.isspace()]
    text = compact(projected)
    at = text.find(query)
    assert at >= 0 and text.find(query, at + 1) < 0, f'Nonunique source heading: {entry.title!r}'
    return len(projected[:positions[at]].encode())


def layout_lines(sdk, document, font, config):
    pager, page = c.c_void_p(), c.c_void_p()
    result = []
    sdk.check('pager_create', document, font, c.byref(config), c.byref(pager))
    try:
        page_index = 0
        while True:
            sdk.check('pager_next', pager, c.byref(page))
            if not page:
                break
            try:
                count = c.c_size_t()
                lines = sdk.layout_lines(page, c.byref(count))
                result.extend((lines[i].start, lines[i].end, page_index, i) for i in range(count.value))
            finally:
                sdk.layout_free(page)
                page = c.c_void_p()
            page_index += 1
    finally:
        sdk.pager_free(pager)
    return result


def audit_book(sdk, book, font, config, sample):
    publication = c.c_void_p()
    documents = {}
    result = {'id': book['id'], 'sha256': file_hash(book['path'])}
    sdk.check('publication_open', book['path'].encode(), c.byref(publication))
    try:
        count, toc = c.c_size_t(), c.POINTER(Toc)()
        sdk.check('publication_toc', publication, c.byref(toc), c.byref(count))
        result.update(toc_count=count.value, max_depth=max((toc[i].level for i in range(count.value)), default=0),
                      sources=sorted({['host', 'nav', 'ncx', '正文恢复'][toc[i].source] for i in range(count.value)}))
        part_count = c.c_size_t()
        parts = sdk.publication_parts(publication, c.byref(part_count))
        paths = [parts[i].path.decode() for i in range(part_count.value)]

        def document(part):
            if part not in documents:
                doc = c.c_void_p()
                sdk.check('publication_load', publication, part, c.byref(doc))
                documents[part] = doc
            return documents[part]

        # Exercise every TOC target, not just the ten accuracy samples.
        for i in range(count.value):
            target, location = toc[i].target, Location()
            sdk.check('publication_locate', publication, c.byref(target), c.byref(location))
        with zipfile.ZipFile(book['path']) as archive:
            roots = {}
            for path in archive.namelist():
                if path.endswith(('.html', '.xhtml', '.ncx')):
                    roots[path] = ET.fromstring(archive.read(path))
            requested, missing_links = 0, []
            # Also audit every internal fragment link in nav/NCX/content, so a
            # valid TOC cannot conceal broken footnote/body links.
            for base, root in roots.items():
                for node in root.iter():
                    for key, href in node.attrib.items():
                        if key not in ('href', 'src') or '#' not in href or urllib.parse.urlsplit(href).scheme:
                            continue
                        fragment, target = c.create_string_buffer(2048), Target()
                        sdk.check('publication_resolve_href', publication, base.encode(), href.encode(), fragment, c.byref(target))
                        if target.part == SIZE_MAX:
                            continue
                        requested += 1
                        location = Location()
                        sdk.check('document_locate', document(target.part), fragment.value, c.byref(location))
                        if location.state == 1:
                            sdk.check('publication_locate', publication, c.byref(target), c.byref(location))
                            assert location.state == 1 and location.offset == 0
                            missing_links.append({'base': base, 'href': href, 'part': target.part, 'offset': location.offset})
            result['fragment_requests'] = requested
            result['missing_link_occurrences'] = len(missing_links)
            result['missing_examples'] = missing_links[:5]
            missing_count = c.c_size_t()
            sdk.publication_missing_targets(publication, c.byref(missing_count))
            result['missing_unique_targets'] = missing_count.value
            if sample:
                eligible = [i for i in range(count.value) if toc[i].source == 3 or toc[i].title.decode().startswith('Capítulo')]
                assert len(eligible) >= 10
                indices = [eligible[round(i * (len(eligible) - 1) / 9)] for i in range(10)]
                samples, line_cache = [], {}
                for index in indices:
                    entry, location = toc[index], Location()
                    sdk.check('publication_locate', publication, c.byref(entry.target), c.byref(location))
                    assert location.state == 0
                    doc = document(location.part)
                    projected = sdk.document_text(doc, None).decode()
                    expected = expected_offset(roots[paths[location.part]], entry, projected)
                    if location.part not in line_cache:
                        line_cache[location.part] = layout_lines(sdk, doc, font, config)
                    lines = line_cache[location.part]
                    projected_bytes = projected.encode()

                    def line_at(offset):
                        for i, (start, end, _, _) in enumerate(lines):
                            if start <= offset < end or start == end == offset:
                                return i
                            if offset < start:
                                # A whitespace boundary may precede a line. A
                                # hidden/unrendered title must never pass by
                                # silently selecting an unrelated later line.
                                assert projected_bytes[offset:start].decode().isspace(), (book['id'], index, offset, start)
                                return i
                        raise AssertionError(('No rendered title line', book['id'], index, offset))

                    actual_line, expected_line = line_at(location.offset), line_at(expected)
                    delta = actual_line - expected_line
                    assert abs(delta) <= 1, (book['id'], index, delta)
                    reverse = c.c_size_t()
                    sdk.check('publication_target_at', publication, location.part, location.offset, c.byref(reverse))
                    assert reverse.value == index, (book['id'], index, reverse.value)
                    samples.append({'index': index, 'title': entry.title.decode(), 'part': location.part,
                                    'offset': location.offset, 'expected_offset': expected,
                                    'line': actual_line, 'expected_line': expected_line, 'line_delta': delta,
                                    'part_page': lines[actual_line][2], 'reverse_index': reverse.value, 'passed': True})
                result['jump_samples'] = samples
                result['jumps_passed'] = sum(s['passed'] for s in samples)
        return result
    finally:
        for doc in documents.values():
            sdk.document_free(doc)
        sdk.publication_free(publication)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('dll', 'manifest', 'font', 'layout', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    sdk = SDK(args.dll.resolve())
    bind(sdk)
    config = sdk.layout_config_defaults()
    layout = read_json(args.layout)
    for key in ('width', 'height', 'margin', 'font_size', 'line_height', 'paragraph_spacing'):
        setattr(config.page, key, layout[key])
    for key in ('document_css', 'embedded_fonts', 'direction'):
        setattr(config, key, layout[key])
    font = c.c_void_p()
    sdk.check('font_open', str(args.font.resolve()).encode(), c.byref(font))
    result = {'dll_sha256': file_hash(args.dll), 'books': []}
    try:
        for book in read_json(args.manifest)['books']:
            if not book['path'].lower().endswith('.epub'):
                continue
            sample = book['id'] in ('pachinko', 'hongloumeng-24264', 'xingshihengyan-24239')
            entry = audit_book(sdk, book, font, config, sample)
            result['books'].append(entry)
            write_json(args.output, result)
            print(json.dumps({k: v for k, v in entry.items() if k not in ('jump_samples', 'missing_examples')}), flush=True)
    finally:
        sdk.font_free(font)


if __name__ == '__main__':
    main()
