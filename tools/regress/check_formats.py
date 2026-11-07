"""Small executable checks for multi-format policy and comparison failures."""
import copy
import argparse
from pathlib import Path
from run_formats import compare
from run_realbooks import read_json, write_json
from merge_format_runs import merge


def main():
    old = dict(schema=1, pixel_contract='test', layout={}, alternate_layout={},
               font_sha256='font', environment={}, books=[
                   dict(id='pixels', sha256='a', regression='hash', status='ok', page_count=1,
                        pages=[dict(pixel_sha256='one', width=10, height=10)]),
                   dict(id='observed', sha256='b', regression='count', status='ok', page_count=3, pages=[]),
                   dict(id='unsupported', sha256='c', regression='count', status='error', page_count=0,
                        error=dict(stage='open', code=11), pages=[])])
    assert not compare(old, copy.deepcopy(old))['needs_review']
    changed = copy.deepcopy(old)
    changed['books'][0]['pages'][0]['pixel_sha256'] = 'two'
    diff = compare(old, changed)
    assert diff['needs_review'] and diff['hash_changed_pages'] == 1
    changed = copy.deepcopy(old)
    changed['books'][1]['page_count'] = 9
    changed['books'][1]['pages'] = [dict(pixel_sha256='ignored')]
    diff = compare(old, changed)
    assert not diff['needs_review'] and diff['hash_changed_pages'] == 0
    assert diff['books'][0]['observed_changes'] == ['page_count']
    for book, field, value in [(0, 'sha256', 'changed'), (1, 'regression', 'hash'),
                                (2, 'error', dict(stage='open', code=5)), (0, 'status', 'error')]:
        changed = copy.deepcopy(old)
        changed['books'][book][field] = value
        assert compare(old, changed)['needs_review'], (book, field)
    changed = copy.deepcopy(old)
    changed['books'].pop()
    assert compare(old, changed)['removed_books'] == ['unsupported']
    for field in ('layout', 'alternate_layout', 'font_sha256', 'environment', 'pixel_contract'):
        changed = copy.deepcopy(old)
        changed[field] = 'different'
        assert not compare(old, changed)['comparable']
    combined = copy.deepcopy(old)
    for key in ('source_revision', 'engine_version', 'abi_version', 'dll_sha256',
                'driver_sha256', 'shared_driver_sha256'):
        combined[key] = 'same'
    manifest = {'books': copy.deepcopy(combined['books'])}
    assert merge(manifest, [combined])['books'] == combined['books']
    retry = copy.deepcopy(combined)
    retry['books'] = [retry['books'][0]]
    retry['books'][0]['pages'][0]['pixel_sha256'] = 'measured-again'
    assert merge(manifest, [combined, retry])['books'][0]['pages'][0]['pixel_sha256'] == 'measured-again'
    for field in ('sha256', 'regression'):
        invalid = copy.deepcopy(retry)
        invalid['books'][0][field] = 'different'
        try:
            merge(manifest, [combined, invalid])
        except AssertionError:
            pass
        else:
            raise AssertionError('merge accepted altered ' + field)
    for invalid_runs in ([retry], [combined, dict(retry, dll_sha256='different')]):
        try:
            merge(manifest, invalid_runs)
        except AssertionError:
            pass
        else:
            raise AssertionError('merge accepted incomplete coverage')
    print('formats comparator: idempotence, pixels, observation-only counts, source/policy/status/error changes, removal, conditions passed')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--repeat', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.baseline:
        run = read_json(args.baseline)
        books = run['books']
        assert len(books) == len({b['id'] for b in books})
        for b in books:
            if b['regression'] == 'hash':
                assert b['status'] == 'ok', b['id']
                assert b['page_count'] == b['rendered_page_count'] == len(b['pages']), b['id']
                assert b['alternate']['status'] == 'ok', b['id']
                assert all(len(p['pixel_sha256']) == 64 for p in b['pages']), b['id']
                assert b.get('text_matches_source', True), b['id']
            else:
                assert all('pixel_sha256' not in p for p in b['pages']), b['id']
        summary = dict(run['summary'], hash_pages=sum(len(b['pages']) for b in books if b['regression'] == 'hash'))
        if args.repeat:
            diff = compare(run, read_json(args.repeat))
            assert not diff['needs_review'], diff
            summary['repeat_hash_changed_pages'] = diff['hash_changed_pages']
        if args.output:
            write_json(args.output, summary)
        print(summary)


if __name__ == '__main__':
    main()
