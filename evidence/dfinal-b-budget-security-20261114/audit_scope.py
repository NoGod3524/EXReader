"""Record the three-item ledger diff and bind tested implementation bytes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = 'e2d6f4d0aa58ea03135f3af1a7d4b9626190fa08'
CATALOG = 'docs/reader-total-progress/catalog.json'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    before = json.loads(git('show', BASE + ':' + CATALOG))
    after = json.loads((ROOT / CATALOG).read_bytes())
    rows = after['requirements']
    assert len(rows) == 108 and len({r['id'] for r in rows}) == 108
    assert {k: v for k, v in before.items() if k != 'requirements'} == {
        k: v for k, v in after.items() if k != 'requirements'}
    changed = []
    for old, new in zip(before['requirements'], rows, strict=True):
        assert old['id'] == new['id']
        if old != new:
            changed.append(new['id'])
            assert new['id'] in {'F08', 'F09', 'F10'}
            assert {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)} <= {'state', 'evidence', 'note'}
            assert new['state'] == 'pending'
            assert '缺' in new['note']
    assert set(changed) == {'F08', 'F09', 'F10'}
    assert all(ref in after['evidence'] for row in rows for ref in row['evidence'])
    forbidden = 'tests/check_reading_release.py'
    assert (ROOT / forbidden).read_bytes() == git('show', BASE + ':' + forbidden)
    implementation = {}
    for path in git('diff', '--name-only', BASE, '--', '.github', 'examples', 'tests').decode().splitlines():
        data = (ROOT / path).read_bytes()
        # Apply the repository's normal Git text filters (the manifest is CRLF locally).
        assert git('hash-object', '--path', path, path).strip() == git('rev-parse', args.source + ':' + path).strip(), path
        implementation[path] = hashlib.sha256(data).hexdigest()
    report = dict(base=BASE, branch=git('branch', '--show-current').decode().strip(), tested_source=args.source,
                  catalog_blob=git('hash-object', CATALOG).decode().strip(), denominator=108,
                  states={state: sum(r['state'] == state for r in rows) for state in ['verified', 'partial', 'pending']},
                  groups=dict(Counter(r['group'] for r in rows)),
                  changed=changed, other_entries_unchanged=True, top_level_unchanged=True,
                  release_test_unchanged=True, implementation_matches_tested_commit_after_git_filters=True,
                  implementation_sha256=implementation)
    for key, filename in [('local_ctest', 'ctest.xml'), ('actions_ctest', 'actions/ctest.xml')]:
        junit = OUT / filename
        if junit.exists():
            report[key] = ET.parse(junit).getroot().attrib
            assert int(report[key]['tests']) > 0
            assert int(report[key].get('failures', 0)) == int(report[key].get('skipped', 0)) == 0
    report['prepush'] = json.loads((OUT / 'prepush-exit.json').read_text(encoding='utf-8-sig'))
    assert report['prepush']['exit'] == 0
    report['frozen_books'] = []
    for book in json.loads((ROOT / 'tests/reader_perf_windows/render-corpus.json').read_bytes())['books']:
        data = (OUT / 'frozen-books' / book['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == book['sha256']
        report['frozen_books'].append(dict(book, bytes=len(data)))
    report['uia_probe'] = json.loads((OUT / 'F09-control-summary.json').read_bytes())
    assert report['uia_probe']['name_role_passed'] is False
    for key, filename in [('local_render', 'F08-realbooks.json'), ('actions_render', 'actions/f08-realbooks.json')]:
        if (OUT / filename).exists():
            rendered = json.loads((OUT / filename).read_bytes())
            report[key] = {field: rendered[field] for field in ['source', 'passed', 'accepted', 'product_budget_accepted']}
            assert report[key]['source'] == args.source
            assert not report[key]['accepted'] and not report[key]['product_budget_accepted']
    report['binary_sha256'] = {name: hashlib.sha256((ROOT / 'build/audit-msvc' / name).read_bytes()).hexdigest()
                               for name in ['check_sync.exe', 'EXReaderAudit.exe', 'exreader-shell-selection-test.exe']}
    (OUT / 'audit-scope.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'catalog.diff').write_bytes(git('diff', BASE, '--', CATALOG))
    print(json.dumps({k: report[k] for k in ['base', 'tested_source', 'denominator', 'states', 'groups', 'changed',
                                            'other_entries_unchanged', 'release_test_unchanged']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
