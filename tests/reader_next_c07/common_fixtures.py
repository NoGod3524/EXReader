"""Actions-only: freeze one byte-exact four-format set used by both Android and macOS."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true'
PDF = '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
ROLES = ('txt', 'epub', 'pdf', 'cbz')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package(source, target):
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    rows = [row for row in manifest['books'] if row['role'] in ROLES]
    assert [row['role'] for row in rows] == list(ROLES), rows
    target.mkdir(parents=True, exist_ok=False)
    out = []
    for row in rows:
        data = (source / row['file']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256'] and 0 < len(data) < 32 * 1024 ** 2
        if row['role'] == 'pdf':
            assert len(data) == 8845 and sha(data) == PDF
        shutil.copyfile(source / row['file'], target / row['file'])
        out.append({'role': row['role'], 'file': row['file'], 'format': row['format'], 'bytes': len(data), 'sha256': sha(data)})
    shutil.copyfile(source / 'manifest.json', target / 'manifest.json')
    (target / 'common.json').write_text(json.dumps({'schema': 1, 'originals': out}, indent=2) + '\n')
    return out


def install(common, destination):
    """Overwrite a generated fixture directory with the frozen bytes (same names, same roles)."""
    shared = json.loads((common / 'common.json').read_text())['originals']
    manifest_path = destination / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert [row['role'] for row in manifest['books']] == list(ROLES)
    for frozen, row in zip(shared, manifest['books']):
        assert frozen['role'] == row['role'] and frozen['file'] == row['file']
        data = (common / frozen['file']).read_bytes()
        assert len(data) == frozen['bytes'] and sha(data) == frozen['sha256']
        (destination / row['file']).write_bytes(data)
        row['bytes'], row['sha256'] = len(data), sha(data)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return shared


if __name__ == '__main__':
    command = sys.argv[1]
    if command == 'package':
        print(json.dumps(package(Path('build/android-raw3/fixtures'), Path('build/c07/common-fixtures'))))
    elif command == 'install':
        print(json.dumps(install(Path(sys.argv[2]), Path(sys.argv[3]))))
    else:
        raise SystemExit('unknown command')
