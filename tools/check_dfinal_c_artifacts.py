# SPDX-License-Identifier: MIT
"""Download exact Actions ZIPs and check their digest, source and original files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import time
import zipfile

API = 'repos/NoGod3524/EXReader/'


def api(path):
    for attempt in range(3):
        try:
            return subprocess.check_output(['gh', 'api', API + path], timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run = json.loads(api(f'actions/runs/{args.run}'))
    jobs = json.loads(api(f'actions/runs/{args.run}/jobs'))
    artifacts = json.loads(api(f'actions/runs/{args.run}/artifacts'))
    for name, data in [('run', run), ('jobs', jobs), ('artifacts', artifacts)]:
        (args.output / (name + '.json')).write_text(json.dumps(data, indent=2), encoding='utf-8')
    assert run['status'] == 'completed' and run['conclusion'] == 'success', run['conclusion']
    assert len(jobs['jobs']) == 3 and all(j['conclusion'] == 'success' for j in jobs['jobs'])
    assert len(artifacts['artifacts']) == 3
    rows = []
    for artifact in artifacts['artifacts']:
        assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == run['head_sha']
        blob = api(f"actions/artifacts/{artifact['id']}/zip")
        digest = hashlib.sha256(blob).hexdigest()
        assert artifact['digest'] == 'sha256:' + digest and len(blob) == artifact['size_in_bytes']
        (args.output / (str(artifact['id']) + '.zip')).write_bytes(blob)
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            manifests = [n for n in archive.namelist() if n.endswith('mobile-evidence/manifest.json')]
            if manifests:
                assert len(manifests) == 1
                manifest = json.loads(archive.read(manifests[0]))
                assert manifest['source'] == run['head_sha'] and manifest['run'] == str(args.run)
                assert manifest['tier'] == 'sdk-build-only' and not manifest['physical_device_verified']
                prefix = manifests[0].removesuffix('mobile-evidence/manifest.json') + 'mobile-stage/'
                for name, expected in manifest['files'].items():
                    assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == expected, name
                count = len(manifest['files'])
                (args.output / (manifest['target'] + '-manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            else:
                names = [n for n in archive.namelist() if n.endswith('/results/result.json')]
                assert len(names) == 1
                result = json.loads(archive.read(names[0]))
                assert result['passed'] and not result['failed'] and result['source'] == run['head_sha']
                count = result['count']
                (args.output / 'model-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            rows.append({'id': artifact['id'], 'name': artifact['name'], 'bytes': len(blob),
                         'zip_sha256': digest, 'checked_files_or_model_assertions': count})
    result = {'run': args.run, 'source': run['head_sha'], 'jobs_passed': 3, 'artifacts': rows, 'passed': True}
    (args.output / 'verified.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
