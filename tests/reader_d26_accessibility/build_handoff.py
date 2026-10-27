"""Same-run source-bound build handoff; no second build for retained regressions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('mode', choices=('create', 'restore'))
p.add_argument('--root', type=Path, required=True)
a = p.parse_args()
root = a.root.resolve()
meta = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
            attempt=os.environ['GITHUB_RUN_ATTEMPT'])
name = 'reader-d26-current-%s-%s' % (meta['run_id'], meta['attempt'])
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()
if a.mode == 'create':
    files = {}
    for f in root.rglob('*'):
        if not f.is_file() or f.name == 'd26-build-handoff.json':
            continue
        # Upload-artifact dereferences files; provenance binds delivered bytes.
        files[f.relative_to(root).as_posix()] = dict(bytes=f.stat().st_size,
            sha256=sha(f), mode=stat.S_IMODE(f.stat().st_mode))
    assert files
    (root / 'd26-build-handoff.json').write_text(json.dumps(dict(meta, files=files), indent=2) + '\n')
else:
    listing = json.loads(subprocess.check_output(['gh', 'api', 'repos/%s/actions/runs/%s/artifacts' %
                         (os.environ['GITHUB_REPOSITORY'], meta['run_id'])], text=True))
    rows = [row for row in listing['artifacts'] if row['name'] == name]
    assert len(rows) == 1 and not rows[0]['expired']
    row = rows[0]
    archive = Path('d26-current-handoff.zip')
    with archive.open('wb') as out:
        subprocess.run(['gh', 'api', 'repos/%s/actions/artifacts/%s/zip' %
                        (os.environ['GITHUB_REPOSITORY'], row['id'])], stdout=out, check=True)
    assert row['digest'] == 'sha256:' + sha(archive)
    assert row['size_in_bytes'] == archive.stat().st_size
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (root / info.filename).resolve()
            assert target.is_relative_to(root), info.filename
        z.extractall(root)
    proof = json.loads((root / 'd26-build-handoff.json').read_text())
    assert all(proof[key] == value for key, value in meta.items())
    for relative, expected in proof['files'].items():
        f = (root / relative).resolve()
        assert f.is_relative_to(root) and f.is_file(), relative
        assert f.stat().st_size == expected['bytes'] and sha(f) == expected['sha256'], relative
        f.chmod(expected['mode'])
    result = dict(meta, verified=True, files=len(proof['files']), artifact_id=row['id'],
                  artifact_digest=row['digest'], artifact_name=name)
    (root / 'd26-handoff-verified.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
