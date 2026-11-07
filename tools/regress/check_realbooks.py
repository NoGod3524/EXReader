"""Small comparator/pixel checks and optional full-run acceptance verification."""
import argparse
import copy
import ctypes as c
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from run_realbooks import (Bitmap, compare, file_hash, fingerprint, pixel_hash,
                           read_json, render_book, write_json)


def self_check():
    pixels = c.create_string_buffer(bytes(range(24)))
    bitmap = Bitmap(2, 2, 12, c.addressof(pixels), 4)
    import hashlib
    assert pixel_hash(bitmap) == hashlib.sha256(bytes(range(8)) + bytes(range(12, 20))).hexdigest()
    page = dict(page=0, width=2, height=2, channels=4, glyph_count=3, pixel_sha256='a')
    book = dict(id='one', sha256='source', status='ok', page_count=1, glyph_count=3, pages=[page])
    old = dict(schema=1, books=[book])
    assert not compare(old, copy.deepcopy(old))['needs_review']
    new = copy.deepcopy(old)
    new['books'][0]['pages'][0]['pixel_sha256'] = 'b'
    assert compare(old, new)['books'][0]['hash_changed_pages'] == [0]
    new['books'][0]['pages'].append(dict(page, page=1))
    new['books'][0]['page_count'] = 2
    assert compare(old, new)['books'][0]['added_pages'] == [1]
    assert compare(new, old)['books'][0]['removed_pages'] == [1]
    new = copy.deepcopy(old)
    new['books'][0]['page_count'] = 2
    diff = compare(old, new)
    assert diff['books'][0]['page_count_changed'] and diff['hash_changed_pages'] == 0
    new = copy.deepcopy(old)
    new['font_sha256'] = 'different'
    assert not compare(old, new)['comparable']
    new = copy.deepcopy(old)
    new['books'][0]['sha256'] = 'different'
    assert compare(old, new)['books'][0]['source_changed']
    new['books'][0]['status'] = 'missing'
    assert compare(old, new)['failed_books'] == ['one']
    new = copy.deepcopy(old)
    new['books'].append(dict(book, id='two'))
    assert compare(old, new)['added_books'] == ['two']
    assert compare(new, old)['removed_books'] == ['two']
    with tempfile.TemporaryDirectory(prefix='exr-w2-missing-') as temporary:
        missing = render_book(dict(id='missing', path=str(Path(temporary) / 'absent.epub')),
                              None, None, {})
        assert missing['status'] == 'missing' and missing['page_count'] == 0
    print('pixel padding and comparator self-checks passed', flush=True)


def verify(args):
    baseline, repeat = read_json(args.baseline), read_json(args.repeat)
    assert len(baseline['books']) == 19
    assert all(b['status'] == 'ok' and b['page_count'] == len(b['pages']) > 0
               for b in baseline['books'])
    diff = compare(baseline, repeat)
    assert not diff['needs_review'], diff
    assert fingerprint(baseline['books']) == fingerprint(repeat['books'])
    for key in ('dll_sha256', 'font_sha256', 'layout', 'source_revision', 'driver_sha256'):
        assert baseline[key] == repeat[key], key
    assert file_hash(args.dll) == baseline['dll_sha256']
    assert file_hash(args.font) == baseline['font_sha256']
    assert read_json(args.layout) == baseline['layout']
    manifest = read_json(args.manifest)
    original = next(b for b in manifest['books'] if b['id'] == 'the-house-on-mango-street')
    source = Path(original['path'])
    if not source.is_absolute():
        source = args.manifest.parent / source
    # Change the actual EPUB in an external temp directory. Persist no text or image.
    with tempfile.TemporaryDirectory(prefix='exr-w2-negative-') as temporary:
        modified = Path(temporary) / source.name
        changed_entry = False
        with zipfile.ZipFile(source) as archive, zipfile.ZipFile(modified, 'w') as out:
            for item in archive.infolist():
                data = archive.read(item.filename)
                if not changed_entry and item.filename.lower().endswith(('.xhtml', '.html', '.htm')):
                    tree = ET.fromstring(data)
                    body = next((n for n in tree.iter() if n.tag.split('}')[-1] == 'body'), None)
                    if body is not None and len(''.join(body.itertext())) > 1000:
                        namespace = body.tag[:-4]
                        paragraph = ET.Element(namespace + 'p')
                        paragraph.text = 'W2 deliberate regression control.'
                        body.insert(0, paragraph)
                        data = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
                        changed_entry = True
                out.writestr(item, data)
        assert changed_entry
        book = dict(original, path=str(modified), sha256=file_hash(modified))
        mutated = render_book(book, args.dll.resolve(), args.font.resolve(), baseline['layout'])
        assert mutated['status'] == 'ok', mutated.get('error')
        candidate = copy.deepcopy(baseline)
        candidate['books'] = [mutated if b['id'] == original['id'] else b for b in baseline['books']]
        candidate_path = Path(temporary) / 'candidate.json'
        diff_path = Path(temporary) / 'diff.json'
        write_json(candidate_path, candidate)
        process = subprocess.run([sys.executable, str(Path(__file__).with_name('run_realbooks.py')),
                                  '--baseline', str(args.baseline), '--candidate', str(candidate_path),
                                  '--output', str(diff_path)], capture_output=True, text=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        assert process.returncode == 1, (process.returncode, process.stderr)
        negative = read_json(diff_path)
        affected = [b for b in negative['books'] if b['hash_changed_pages']]
        assert [b['id'] for b in affected] == [original['id']], negative
        assert affected[0]['source_changed'] and negative['needs_review']
        result = {
            'self_checks': 'passed', 'covered_books': len(baseline['books']),
            'idempotence': {'passed': True, 'compared_pages': baseline['summary']['total_pages'],
                            'hash_changed_pages': diff['hash_changed_pages'],
                            'content_fingerprint': fingerprint(baseline['books']),
                            'repeat_wall_seconds': repeat['summary']['wall_seconds'],
                            'repeat_sum_book_seconds': repeat['summary']['sum_book_seconds']},
            'negative_control': {'passed': True, 'method': 'insert paragraph into one real EPUB body',
                                 'cli_exit_code': process.returncode,
                                 'other_books': 'reuse unchanged baseline results',
                                 'book': original['id'], 'original_sha256': original['sha256'],
                                 'modified_sha256': mutated['sha256'],
                                 'elapsed_seconds': mutated['elapsed_seconds'],
                                 'difference': affected[0]},
        }
        write_json(args.output, result)
        print(f"Full idempotence passed: {baseline['summary']['total_pages']} pages; "
              f"negative control detected {negative['hash_changed_pages']} changed pages in one book.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'repeat', 'manifest', 'dll', 'font', 'layout', 'output'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    self_check()
    if args.baseline:
        if not all((args.repeat, args.manifest, args.dll, args.font, args.layout, args.output)):
            parser.error('full verification requires all seven paths')
        verify(args)
