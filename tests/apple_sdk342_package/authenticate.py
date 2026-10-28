#!/usr/bin/env python3
"""Authenticate the two original same-run package artifacts in Actions."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    out = ROOT / 'build/apple-sdk342-summary'
    out.mkdir(parents=True, exist_ok=True)
    result = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'accepted': False, 'artifacts': [], 'failure': None}
    try:
        jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
        expected = {'Apple SDK 3.42 macos package', 'Apple SDK 3.42 iphonesimulator package'}
        def producer_name(name):
            return name.removeprefix('apple / ')
        producers = [j for j in jobs if producer_name(j['name']) in expected]
        assert len(producers) == 2 and {producer_name(j['name']) for j in producers} == expected
        assert all(j['head_sha'] == source and j['conclusion'] == 'success' for j in producers)
        artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
        for target in ('macos', 'iphonesimulator'):
            name = f'apple-sdk342-{target}-{run}-{attempt}'
            matches = [a for a in artifacts if a['name'] == name]
            assert len(matches) == 1
            item = matches[0]
            assert not item['expired'] and item['workflow_run']['head_sha'] == source
            raw = download_artifact_zip(item['id'])
            digest = hashlib.sha256(raw).hexdigest()
            assert len(raw) == item['size_in_bytes'] and item['digest'] == 'sha256:' + digest
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = archive.namelist()
                assert len(names) == len(set(names))
                assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
                identity = json.loads(archive.read('identity.json'))
                assert (identity['source_sha'], identity['run_id'], identity['attempt'], identity['target']) == (source, run, attempt, target)
                assert identity['sdk_content_candidate'] == '8357eafa28423a7ab93ba08b823af80f01ad1505'
                assert identity['sdk_content_paths'] == ['src', 'include', 'cmake', 'CMakeLists.txt', 'bindings']
                assert identity['product']['sdk_version'] == '3.42.0'
                package = archive.read('EXReader.zip')
                assert hashlib.sha256(package).hexdigest() == identity['archive_sha256']
                with zipfile.ZipFile(io.BytesIO(package)) as bundle:
                    executable = 'EXReader.app/Contents/MacOS/EXReader' if target == 'macos' else 'EXReader.app/EXReader'
                    assert hashlib.sha256(bundle.read(executable)).hexdigest() == identity['executable_sha256']
            result['artifacts'].append({'id': item['id'], 'name': name, 'sha256': digest})
        result['accepted'] = True
    except Exception as error:
        result['failure'] = str(error)
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    assert result['accepted'], 'Apple SDK package authentication failed'

if __name__ == '__main__':
    main()
