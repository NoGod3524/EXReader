# SPDX-License-Identifier: MIT
"""Check this lane against its actual origin/main starting commit."""
from collections import Counter
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
baseline = '38a70318'
catalog = 'docs/reader-total-progress/catalog.json'
before = json.loads(subprocess.check_output(['git', 'show', baseline + ':' + catalog], cwd=root))
after = json.loads((root / catalog).read_text(encoding='utf-8'))
assert {k: v for k, v in before.items() if k != 'requirements'} == {
    k: v for k, v in after.items() if k != 'requirements'}
old, new = before['requirements'], after['requirements']
assert len(old) == len(new) == 108
assert [r['id'] for r in old] == [r['id'] for r in new]
allowed = {'F11', 'F12', 'H.ipad.annotation_exchange'}
changed = set()
for original, current in zip(old, new):
    assert all(ref in after['evidence'] for ref in current['evidence'])
    if original != current:
        changed.add(current['id'])
        assert current['id'] in allowed
        assert {k: v for k, v in original.items() if k not in {'state', 'evidence', 'note'}} == {
            k: v for k, v in current.items() if k not in {'state', 'evidence', 'note'}}
    if current['id'] in allowed:
        assert 'acceptance' not in current and current['state'] == 'pending'
assert changed == allowed
assert Counter(r['group'] for r in new) == {'foundation': 12, 'host': 84, 'final': 12}
assert not subprocess.check_output(['git', 'diff', baseline, '--', 'tests/check_reading_release.py'], cwd=root)
print('catalog changed only:', ', '.join(sorted(changed)))
print('registered evidence references valid; titles/IDs/top-level catalog unchanged')
print('denominator=108; groups=', dict(Counter(r['group'] for r in new)))
print('states=', dict(Counter(r['state'] for r in new)))
print('tests/check_reading_release.py unchanged')
