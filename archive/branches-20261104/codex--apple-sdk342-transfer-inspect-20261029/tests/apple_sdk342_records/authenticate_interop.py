#!/usr/bin/env python3
"""Prepared Actions-only authentication for the raw annotation proof."""
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
    out = ROOT / 'build/apple-sdk342-annotation-summary'; out.mkdir(parents=True, exist_ok=True)
    summary = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'accepted': False, 'failure': None}
    try:
        jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
        matches = [j for j in jobs if j['name'] == 'Actual Apple 3.41 export and 3.42 receiver']
        assert len(matches) == 1 and matches[0]['head_sha'] == source and matches[0]['conclusion'] == 'success'
        name = f'apple-sdk342-annotation-interop-{run}-{attempt}'
        items = [a for a in fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts'] if a['name'] == name]
        assert len(items) == 1
        item = items[0]
        assert not item['expired'] and item['workflow_run']['head_sha'] == source
        raw = download_artifact_zip(item['id']); digest = hashlib.sha256(raw).hexdigest()
        assert len(raw) == item['size_in_bytes'] and item['digest'] == 'sha256:' + digest
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = z.namelist()
            assert len(names) == len(set(names))
            assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
            result = json.loads(z.read('result.json'))
            assert (result['source_sha'], result['run_id'], result['attempt'], result['accepted']) == (source, run, attempt, True)
            assert result['sdk_sources'] == {'old': ['3.41.0', '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'], 'new': ['3.42.0', '8357eafa28423a7ab93ba08b823af80f01ad1505']}
            assert not result['android_sender'] and not result['physical_device'] and not result['ui_accepted']
            expected_test_only = os.environ.get('EXPECT_TEST_ONLY', 'false') == 'true'
            assert result['test_only_policy'] == expected_test_only, 'Owner proof scope differs'
            for path, expected in result['files'].items():
                data = z.read(path)
                assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256']
            for label, version in [('old', '3.41.0'), ('new', '3.42.0')]:
                report = json.loads(z.read(label + '-result.json'))
                assert (report['source_sha'], report['run_id'], report['attempt'], report['sdk'], report['accepted']) == (source, run, attempt, version, True)
                assert ('APPLE_PARSER_MATRIX sdk=' + version + ' known=6 invalid=14').encode() in z.read(label + '-matrix-run.log')
                assert hashlib.sha256(z.read('annotation-' + label)).hexdigest() == result['programs'][label]['sha256']
                assert hashlib.sha256(z.read('matrix-' + label)).hexdigest() == result['programs'][label]['matrix_sha256']
            assert len(json.loads(z.read('old-result.json'))['checks']) == 2
            assert len(json.loads(z.read('new-result.json'))['checks']) == 7
        summary.update(accepted=True, artifact_id=item['id'], zip_sha256=digest, test_only_policy=expected_test_only,
                       scope='macOS native processes; real 3.41 RAW3 export and 3.42 import, not Android or physical devices')
    except Exception as error:
        summary['failure'] = str(error)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    assert summary['accepted'], 'Apple raw annotation interop authentication failed'

if __name__ == '__main__': main()
