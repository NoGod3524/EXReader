#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate original same-run artifact ZIPs and native evidence in Actions."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import plistlib
import sys
import zipfile
from contract import BASE, CASES
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    out = ROOT / 'build/ios-organization-authentication'; out.mkdir(parents=True, exist_ok=True)
    report = {'accepted': False, 'source_sha': source, 'run_id': run, 'attempt': attempt, 'common_base': BASE,
              'sdk_version': '3.42.0', 'physical_device_execution': False, 'complete_product_accepted': False,
              'artifacts': [], 'problems': []}
    try:
        jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
        expected = {'iOS organization iphone', 'iOS organization ipad'}
        producers = [j for j in jobs if j['name'] in expected]
        assert len(producers) == 2 and {j['name'] for j in producers} == expected
        assert all(j['head_sha'] == source and j['conclusion'] == 'success' for j in producers)
        artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
        for platform in ('iphone', 'ipad'):
            name = f'ios-organization-{platform}-{run}-{attempt}'
            found = [a for a in artifacts if a['name'] == name]
            assert len(found) == 1
            item = found[0]
            assert not item['expired'] and item['workflow_run']['head_sha'] == source
            raw = download_artifact_zip(item['id'])
            digest = hashlib.sha256(raw).hexdigest()
            assert len(raw) == item['size_in_bytes'] and item['digest'] == 'sha256:' + digest
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = archive.namelist()
                assert len(names) == len(set(names))
                assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
                result = json.loads(archive.read('organization-ui.json'))
                assert all(result[k] == v for k, v in [('source_sha', source), ('run_id', run), ('attempt', attempt),
                    ('platform', platform), ('common_base', BASE), ('sdk_version', '3.42.0')])
                assert result['accepted'] is True and result['problems'] == []
                assert result['physical_device_execution'] is False and result['complete_product_accepted'] is False
                assert len(result['cases']) == len(CASES) and all(c['result'] == 'Passed' for c in result['cases'])
                assert {re.findall(r'\btest[A-Za-z0-9_]+\b', c['name'])[0] for c in result['cases']} == set(CASES)
                assert len(result['retained']) == len(CASES) * 3 + 4
                for path, expected_digest in result['retained'].items():
                    assert hashlib.sha256(archive.read(path)).hexdigest() == expected_digest, path
                guard = json.loads(archive.read('source-guard.json'))
                assert guard['sdk_package_identity']['product']['sdk_version'] == '3.42.0'
                assert guard['sdk_package_identity']['source_sha'] == source
                with zipfile.ZipFile(io.BytesIO(archive.read('EXReaderHost.zip'))) as program:
                    members = program.namelist()
                    assert len(members) == len(set(members))
                    assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in members)
                    prefix = 'EXReaderHost.app/'
                    info = plistlib.loads(program.read(prefix + 'Info.plist'))
                    assert info['EXRSourceSHA'] == source and info['EXRSDKVersion'] == '3.42.0'
                    assert hashlib.sha256(program.read(prefix + 'EXReaderHost')).hexdigest() == result['executable_sha256']
                    assert hashlib.sha256(program.read(prefix + 'Frameworks/libexreader.3.42.0.dylib')).hexdigest() == result['runtime_sha256']
                    for filename, checksum in guard['fixtures'].items():
                        assert hashlib.sha256(program.read(prefix + filename)).hexdigest() == checksum, filename
            report['artifacts'].append({'id': item['id'], 'name': name, 'sha256': digest, 'platform': platform})
        report['accepted'] = True
    except Exception as error:
        report['problems'].append(type(error).__name__ + ': ' + str(error))
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    assert report['accepted'], 'iOS organization original artifacts not accepted'

if __name__ == '__main__': main()
