"""Check the three runtime records, artifact identity, pixels and regression gate."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'evidence/platforms2-20261109'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    artifacts = read(EVIDENCE / 'artifacts.json')['artifacts']
    required = {'load', 'open', 'render', 'search', 'annotation'}
    records = {name: read(EVIDENCE / name / 'result.json') for name in ('windows-gated', 'linux', 'android')}
    for name, record in records.items():
        assert record['passed'] == 5 and set(record['checks']) == required and all(record['checks'].values()), name
        assert 'PASS platform checks=5/5' in (EVIDENCE / name / 'reopen.log').read_text(), name
    for name, platform in (('windows-gated', 'Windows'), ('linux', 'Linux')):
        actual = records[name]['library_sha256']
        assert any(x['platform'] == platform and x['source_revision'].startswith('ed252fb6') and x['sha256'] == actual for x in artifacts)
        assert records[name]['negative_moved_annotation_exit'] != 0
    android = records['android']
    assert len(set(android['pids'])) == 2
    assert any(x['path'].endswith('.apk') and x['sha256'] == android['apk_sha256'] for x in artifacts)
    engines = {Path(x['path']).name: x['sha256'] for x in artifacts if x['platform'] == 'Android' and x['arch'] == 'x86_64' and x['kind'] in ('engine', 'jni')}
    for item in artifacts:
        if item['platform'] == 'Android' and item['arch'] == 'x86_64' and item['kind'] == 'container':
            for member in item['embedded_libraries']:
                if Path(member['path']).name in engines:
                    assert member['sha256'] == engines[Path(member['path']).name]
    images = {}
    for name in (*records, 'linux-ci'):
        images[name] = {p: hashlib.sha256((EVIDENCE / name / p).read_bytes()).hexdigest()
                        for p in ('page.png', 'reopen.png', 'highlight.png', 'highlight.json')}
        assert images[name]['page.png'] == images[name]['reopen.png']
    for filename in ('page.png', 'highlight.png', 'highlight.json'):
        assert len({r[filename] for r in images.values()}) == 1, filename
    books = json.loads(gzip.decompress((EVIDENCE / 'books.json.gz').read_bytes()))
    assert books['summary']['requested_books'] == books['summary']['successful_books'] == 19
    diff = read(EVIDENCE / 'books.diff.json')
    assert diff['comparable'] and not diff['needs_review']
    assert '100% tests passed out of 234' in (EVIDENCE / 'windows-ctest.txt').read_text()
    assert '100% tests passed, 0 tests failed out of 234' in (EVIDENCE / 'linux-test-font.txt').read_text()
    changed = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=ROOT, text=True).splitlines()
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    allowed = ('tools/platforms/', 'docs/platforms/', 'evidence/platforms2-20261109/')
    outside = [p for p in (*changed, *untracked) if p != 'PLATFORMS2-OUT.txt' and not p.startswith(allowed)]
    assert not outside, outside
    result = {'source_revision': read(EVIDENCE / 'environment.json')['source_revision'],
              'runtime_platforms': 3, 'new_runtime_platforms': ['Linux', 'Android'],
              'checks': {p: '5/5' for p in ('Windows', 'Linux', 'Android')},
              'ctest': {'Windows': '234/234', 'Linux': '234/234'}, 'books': books['summary'],
              'regression_needs_review': False, 'artifact_count': len(artifacts),
              'pixel_and_annotation_bytes_identical': True, 'out_of_scope_changes': outside}
    (EVIDENCE / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
