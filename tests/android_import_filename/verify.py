"""Actions-only independent assertions on unmodified real-host import regression evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
raw = Path('build/android-host-import/ui/result.json').read_bytes()
r = json.loads(raw)
identity = {k: os.environ[v] for k, v in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
assert all(r[k] == v for k, v in identity.items())
assert r['accepted'] is True and r['api'] == 34 and r['checks'] == 20
expected = {'epub': 'Fixture Book.epub', 'pdf': 'Fixture.pdf', 'short': 'Short Reads.txt', 'evil': '......evil..name.txt', 'seekable': 'Seekable.txt', 'slow': 'Slow.txt', 'rotating': 'Rotating.txt', 'stable': 'StablePartial.txt', 'ready': 'Ready.txt', 'published': 'Published.txt'}
observed = []
for phase in r['phases']:
    for item in phase['observations']:
        if 'book' not in item:
            continue
        role, book = item['role'], item['book']
        assert book['title'] == expected[role], (phase['phase'], role, book['title'], expected[role])
        observed.append({'phase': phase['phase'], 'pid': phase['pid'], 'role': role, 'title': book['title'], 'original_sha256': book['sha256'], 'original_bytes': book['bytes'], 'source_key': book['key']})
assert set(expected) == {item['role'] for item in observed}
assert {'recover-copy', 'recover-stable', 'recover-ready', 'recover-published'} <= {item['phase'] for item in observed}
assert len({x['pid'] for x in r['phases']}) == len(r['phases'])
assert any(x['name'] == 'system-documentsui' and x['package'] == 'com.android.documentsui' for x in r['captures'])
result = {**identity, 'accepted': True, 'original_checks': r['checks'], 'original_evidence_sha256': hashlib.sha256(raw).hexdigest(), 'filename_observations': observed, 'selector': 'Real Android DocumentsUI with test DocumentsProvider; no selector replacement', 'physical_device': False, 'scope': 'Host opt-in retains sanitized provider display filename across real imports and fresh-process recovery; default module API remains legacy'}
(a.output / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(json.dumps(result, ensure_ascii=False))
