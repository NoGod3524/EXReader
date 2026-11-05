"""Judge a consumer report: only a real public-API readback can pass.

A report that was produced from SQL or file scanning (no resolved exr_* symbols,
no recorded API calls, no loaded SDK path) is refused, and the module carries its
own negative self-test so the judge cannot silently degrade into a rubber stamp.
"""
import argparse
import copy
import json
import pathlib
import sys

REQUIRED_SYMBOLS = (
    'exr_library_open', 'exr_library_close', 'exr_library_books', 'exr_books_free',
    'exr_library_source', 'exr_library_progress_get', 'exr_anchor_free', 'exr_library_notes',
    'exr_notes_free', 'exr_library_fixed_notes', 'exr_fixed_notes_free',
    'exr_library_epub_info_get', 'exr_library_epub_notes', 'exr_epub_notes_free',
    'exr_version', 'exr_abi_version')
REQUIRED_CALLS = ('exr_library_open', 'exr_library_books', 'exr_library_source',
                  'exr_library_progress_get', 'exr_library_notes')
FORBIDDEN_KEYS = ('sql', 'tables', 'db_sha256', 'file_sha256', 'rows_from_sql')
ANCHOR_FOUND, ANCHOR_LEGACY = 1, 3


def text(value):
    return bytes.fromhex(value).decode('utf-8')


def normalize(report):
    """The readback values the public ABI returned, in a comparable form."""
    books = []
    for book in report.get('books', []):
        progress = book.get('progress', {})
        books.append({
            'id': book.get('id'), 'format': book.get('format'),
            'title': text(book.get('title_hex', '')), 'author': text(book.get('author_hex', '')),
            'tags': text(book.get('tags_hex', '')), 'favorite': book.get('favorite'),
            'status': book.get('status'), 'position': book.get('position'),
            'source': {key: book.get('source', {}).get(key) for key in ('status', 'size', 'read', 'sha256', 'complete', 'reads')},
            'progress': {'status': progress.get('status'), 'state': progress.get('state'), 'start': progress.get('start'),
                         'end': progress.get('end'), 'exact': text(progress.get('exact_hex', '')),
                         'exact_present': progress.get('exact_present'),
                         'prefix': text(progress.get('prefix_hex', '')),
                         'suffix': text(progress.get('suffix_hex', '')),
                         'chapter_present': progress.get('chapter_present'),
                         'chapter': text(progress.get('chapter_hex', ''))},
            'notes_status': book.get('notes', {}).get('status'),
            'notes_count': book.get('notes', {}).get('count'),
            'notes': [{'id': row['id'], 'start': row['start'], 'end': row['end'], 'text': text(row['text_hex'])}
                      for row in book.get('notes', {}).get('rows', [])]})
    return books


def validate(report, expect):
    """Return a list of refusal reasons; empty means a genuine, matching readback."""
    why = []
    if report.get('schema') != 'c08-public-api-readback-1':
        why.append('not a public-API consumer report')
    for key in FORBIDDEN_KEYS:
        if key in report:
            why.append('report carries SQL/file-scan evidence key %r, which is not API evidence' % key)
    symbols = {row.get('symbol'): row.get('resolved') for row in report.get('symbols', [])}
    for name in REQUIRED_SYMBOLS:
        if symbols.get(name) is not True:
            why.append('public symbol %s was not resolved from the loaded SDK' % name)
    owners = {row.get('symbol'): row.get('object') for row in report.get('symbols', [])}
    if any(owners.get(name) != report.get('loaded_from') for name in REQUIRED_SYMBOLS):
        why.append('not every resolved public symbol belongs to the actual loaded SDK object')
    if not report.get('loaded_from') or not report.get('library_path'):
        why.append('no loaded SDK library path recorded')
    elif not str(report['loaded_from']).endswith('libexreader.so'):
        why.append('loaded SDK object is not libexreader.so: %r' % report['loaded_from'])
    calls = {}
    for row in report.get('calls', []):
        calls.setdefault(row.get('call'), []).append(row.get('status'))
    for name in REQUIRED_CALLS:
        if name not in calls:
            why.append('API call %s was never made' % name)
        elif any(status != 0 for status in calls[name]):
            why.append('API call %s returned non-OK statuses %r' % (name, calls[name]))
    if not report.get('api_calls') or report.get('api_failures') != 0 or report.get('complete') is not True:
        why.append('consumer did not complete its API calls cleanly: calls=%r failures=%r complete=%r'
                   % (report.get('api_calls'), report.get('api_failures'), report.get('complete')))
    if report.get('sdk_version') != expect['sdk_version'] or report.get('abi_version') != expect['abi_version']:
        why.append('actual loaded SDK version or ABI differs from the frozen producer')
    process = report.get('process', {})
    if not process.get('pid') or not process.get('uid') or process.get('uid') != process.get('euid') or not process.get('selinux') or \
            process.get('executable') != '/data/local/tmp/c08/c08_consumer':
        why.append('consumer actual process identity or program origin is missing or differs')
    if report.get('book_count') != 1 or len(report.get('books', [])) != 1:
        why.append('expected exactly one book, SDK returned %r' % report.get('book_count'))
        return why
    try:
        book = normalize(report)[0]
    except (KeyError, ValueError, TypeError) as error:
        return why + ['malformed actual API values: ' + str(error)]
    if 'book_id' in expect and book['id'] != expect['book_id']:
        why.append('public SDK book ID differs from the actual UI book ID')
    if book['format'] != expect['format']:
        why.append('format %r != %r' % (book['format'], expect['format']))
    if expect['title_stem'] not in book['title']:
        why.append('title %r does not carry %r' % (book['title'], expect['title_stem']))
    source = book['source']
    if source['status'] != 0 or source['sha256'] != expect['sha256'] or source['size'] != expect['bytes'] or \
            source['read'] != expect['bytes'] or source['complete'] is not True:
        why.append('original bytes read through exr_library_source differ: %r' % source)
    offset = 0
    for row in source.get('reads') or []:
        if row.get('offset') != offset or not isinstance(row.get('returned'), int) or \
                not 0 < row['returned'] <= row.get('requested', 0):
            why.append('public original read_at transcript is inconsistent')
            break
        offset += row['returned']
    if offset != expect['bytes']:
        why.append('public original read_at calls do not cover the complete original')
    progress = book['progress']
    if progress['status'] != 0 or progress['state'] not in (ANCHOR_FOUND, ANCHOR_LEGACY):
        why.append('reading progress state %r is neither FOUND nor LEGACY' % progress['state'])
    if not progress['start'] or progress['start'] <= 0:
        why.append('reading progress has no positive persisted offset: %r (the public API does not return a page number)' % progress['start'])
    if progress['end'] < progress['start']:
        why.append('public progress selector range is reversed')
    wanted = expect.get('notes', [])
    got = [row['text'] for row in book['notes']]
    if got != wanted:
        why.append('notes %r != expected %r' % (got, wanted))
    if book['notes_status'] != 0 or book['notes_count'] != len(book['notes']) or len(book['notes']) != len(wanted):
        why.append('public notes status/count/rows do not match the required user note')
    if any(row['id'] <= 0 or row['end'] <= row['start'] for row in book['notes']):
        why.append('required user note has no actual ID or nonempty selection range')
    return why


def synthetic_good(expect):
    def hexed(value):
        return value.encode('utf-8').hex()
    symbols = [{'symbol': name, 'resolved': True, 'object': '/x/libexreader.so'} for name in REQUIRED_SYMBOLS]
    return {
        'schema': 'c08-public-api-readback-1', 'mode': 'selftest', 'library_path': '/x/libexreader.so',
        'symbols': symbols, 'loaded_from': '/x/libexreader.so', 'sdk_version': '3.41.0', 'abi_version': 1,
        'process': {'pid': 123, 'uid': 2000, 'euid': 2000, 'selinux': 'u:r:shell:s0', 'executable': '/data/local/tmp/c08/c08_consumer'},
        'books': [{'id': 1, 'format': expect['format'], 'title_hex': hexed(expect['title_stem']),
                   'author_hex': '', 'tags_hex': '', 'favorite': 0, 'status': 0, 'position': 4000,
                   'source': {'status': 0, 'size': expect['bytes'], 'read': expect['bytes'], 'complete': True,
                              'reads': [{'offset': 0, 'requested': expect['bytes'], 'returned': expect['bytes']}],
                              'sha256': expect['sha256']},
                   'progress': {'status': 0, 'state': ANCHOR_FOUND, 'start': 4000, 'end': 4010,
                                'exact_hex': hexed('x'), 'prefix_hex': '', 'suffix_hex': ''},
                   'notes': {'status': 0, 'count': len(expect['notes']), 'rows': [
                       {'id': index + 1, 'start': 1, 'end': 2, 'text_hex': hexed(note)} for index, note in enumerate(expect['notes'])]}}],
        'book_count': 1, 'api_calls': 5, 'api_failures': 0, 'complete': True,
        'calls': [{'call': name, 'status': 0, 'a': 0, 'b': 0} for name in REQUIRED_CALLS]}


def selftest(expect):
    """Every negative must be refused and the positive control accepted."""
    good = synthetic_good(expect)
    results = {'positive_control': validate(good, expect) == []}

    def refused(name, mutate):
        report = copy.deepcopy(good)
        mutate(report)
        results['refuses_' + name] = bool(validate(report, expect))

    refused('sql_scan_only', lambda r: (r.pop('symbols'), r.pop('calls'), r.update(sql='SELECT * FROM book_progress')))
    refused('file_hash_only', lambda r: (r.pop('calls'), r.update(db_sha256='0' * 64, api_calls=0)))
    refused('no_calls_recorded', lambda r: (r.update(calls=[], api_calls=0)))
    refused('unresolved_symbol', lambda r: r['symbols'][2].update(resolved=False))
    refused('wrong_sdk_object', lambda r: r.update(loaded_from='/system/lib64/libsqlite.so'))
    refused('symbol_from_other_object', lambda r: r['symbols'][0].update(object='/system/lib64/libsqlite.so'))
    refused('wrong_sdk_version', lambda r: r.update(sdk_version='3.40.0'))
    refused('wrong_abi_version', lambda r: r.update(abi_version=99))
    refused('no_process_identity', lambda r: r.pop('process'))
    refused('root_process', lambda r: r['process'].update(uid=0, euid=0))
    refused('wrong_original_bytes', lambda r: r['books'][0]['source'].update(sha256='1' * 64))
    refused('truncated_original', lambda r: r['books'][0]['source'].update(size=1, complete=False))
    refused('missing_progress', lambda r: r['books'][0]['progress'].update(state=0, start=0))
    refused('api_failure', lambda r: r['calls'][3].update(status=3))
    refused('source_value_status_failure', lambda r: r['books'][0]['source'].update(status=3))
    refused('progress_value_status_failure', lambda r: r['books'][0]['progress'].update(status=3))
    refused('notes_value_status_failure', lambda r: r['books'][0]['notes'].update(status=3))
    refused('missing_required_note', lambda r: r['books'][0]['notes'].update(rows=[], count=0))
    refused('bad_note_count', lambda r: r['books'][0]['notes'].update(count=2))
    refused('partial_read_at_transcript', lambda r: r['books'][0]['source'].update(reads=[]))
    refused('unexpected_note', lambda r: r['books'][0]['notes'].update(
        rows=[{'id': 1, 'start': 1, 'end': 2, 'text_hex': '61'}], count=1))
    refused('two_books', lambda r: r.update(book_count=2))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--contract', type=pathlib.Path, default=pathlib.Path('tests/reader_next_c08/contract.json'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/c08-selftest/validate-selftest.json'))
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding='utf-8'))
    fixture = contract['fixture']
    expect = {'format': fixture['format'], 'title_stem': fixture['title_stem'], 'sha256': fixture['sha256'],
              'bytes': fixture['bytes'], 'ui_page': contract['expected_page'], 'notes': [contract['expected_note']],
              'sdk_version': contract['expected_sdk_version'], 'abi_version': contract['expected_abi_version']}
    results = selftest(expect)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(results, indent=2, sort_keys=True))
    if not all(results.values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
