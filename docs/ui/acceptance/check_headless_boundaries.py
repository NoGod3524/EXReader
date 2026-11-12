#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify protected files and reuse page evidence only for a byte-identical SDK."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROTECTED = {
    'tests/check_reading_release.py': '6eb22a304686b2160d1f283a709936bfdfd65c3b0f5e10bb060f457c4faffb2b',
    'tools/version_literal_exceptions.json': '6d2ab944c7c624b1f82ffa61b0c742fb1cb731b88bd700b245bac644aa247fc2',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = [json.loads(gzip.decompress((ROOT / p).read_bytes())) for p in
               ('evidence/simplified-20261110/realbooks-after.json.gz',
                'evidence/opds-20261110/realbooks-after.json.gz')]
    old, current = reports
    assert len(old['books']) == len(current['books']) == 19
    byid = {b['id']: b for b in old['books']}
    pages, changed = 0, 0
    for book in current['books']:
        previous = byid[book['id']]
        assert previous['sha256'] == book['sha256']
        assert previous['page_count'] == book['page_count'] == len(book['pages'])
        assert previous['status'] == book['status'] == 'ok'
        pages += book['page_count']
        changed += sum(a['pixel_sha256'] != b['pixel_sha256'] for a, b in
                       zip(previous['pages'], book['pages'], strict=True))
    assert pages == 11318 and changed == 0
    dll = sha(args.dll)
    assert dll == current['dll_sha256'], 'SDK changed: rerender the books before reusing this evidence'
    manifest = json.loads((ROOT / 'tools/regress/corpus.json').read_text(encoding='utf-8'))
    assert {b['id'] for b in manifest['books']} == set(byid)
    for book in manifest['books']:
        path = Path(book['path'])
        if not path.is_absolute():
            path = ROOT / 'tools/regress' / path
        assert sha(path) == book['sha256'] == byid[book['id']]['sha256']
    for path, expected in PROTECTED.items():
        assert sha(ROOT / path) == expected, path
    result = dict(books=19, pages=pages, changed_page_hashes=changed, dll_sha256=dll,
                  method='Prior page evidence reused for byte-identical SDK; original books rehashed, no rerender this round.',
                  protected=PROTECTED)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'PASS 19/19 source book hashes; {pages} prior pages, {changed} changed hashes; SDK byte-identical')
    print('PASS protected reading gate and version exception manifest SHA256 unchanged')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
