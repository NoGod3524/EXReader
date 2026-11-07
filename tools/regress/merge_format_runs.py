"""Assemble measured subsets/retries with identical rendering conditions.

Later runs replace earlier observations of the same source. Every input run and
replacement is recorded; missing inputs, altered sources or settings are errors.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from run_realbooks import file_hash, read_json, write_json


def merge(manifest, runs):
    conditions = ('schema', 'source_revision', 'engine_version', 'abi_version',
                  'dll_sha256', 'driver_sha256', 'shared_driver_sha256', 'font_sha256',
                  'layout', 'alternate_layout', 'pixel_contract', 'environment')
    first = runs[0]
    expected = {b['id']: b for b in manifest['books']}
    assert len(expected) == len(manifest['books']), 'duplicate manifest IDs'
    results = {}
    for run in runs:
        assert all(run[k] == first[k] for k in conditions), 'incompatible run conditions'
        for book in run['books']:
            original = expected[book['id']]
            assert all(book.get(k) == original.get(k) for k in
                       ('sha256', 'regression', 'max_render_pages')), 'source or policy changed'
            results[book['id']] = book
    assert results.keys() == expected.keys(), 'incomplete sample coverage'
    output = {k: v for k, v in first.items() if k not in ('books', 'summary', 'assembled_from')}
    output['created_utc'] = datetime.now(timezone.utc).isoformat()
    output['books'] = [results[b['id']] for b in manifest['books']]
    books = output['books']
    output['summary'] = dict(samples=len(books), rendered=sum(b['status'] == 'ok' for b in books),
                             hash_samples=sum(b['regression'] == 'hash' for b in books),
                             count_only_samples=sum(b['regression'] == 'count' for b in books),
                             total_pages=sum(b['page_count'] for b in books))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    runs = [read_json(p) for p in args.run]
    output = merge(read_json(args.manifest), runs)
    output['assembled_from'] = [dict(file=p.name, sha256=file_hash(p),
                                     samples=[b['id'] for b in r['books']]) for p, r in zip(args.run, runs)]
    write_json(args.output, output)
    print(output['summary'])


if __name__ == '__main__':
    main()
