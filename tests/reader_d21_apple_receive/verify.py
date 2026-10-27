# SPDX-License-Identifier: MIT
"""D21 authenticates raw same-run ZIPs only inside Actions; keeps all failures."""
import hashlib, io, json, os, sys, zipfile
from pathlib import Path, PurePosixPath
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
assert os.environ.get('GITHUB_ACTIONS') == 'true'
source, run, attempt = (os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
summary = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'accepted': False, 'artifacts': []}
try:
    jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    selected = [j for j in jobs if j['name'].startswith('D21 native receive ')]
    assert len(selected) == 3 and all(j['head_sha'] == source and j['conclusion'] == 'success' for j in selected)
    artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
    for platform in ('macos', 'iphone', 'ipad'):
        matches = [a for a in artifacts if a['name'] == f'd21-receive-{platform}-{run}-{attempt}']
        assert len(matches) == 1
        a = matches[0]
        assert not a['expired'] and a['workflow_run']['head_sha'] == source
        raw = download_artifact_zip(a['id'])
        digest = hashlib.sha256(raw).hexdigest()
        assert len(raw) == a['size_in_bytes'] and 'sha256:' + digest == a['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names))
            assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names)
            result = json.loads(archive.read('result.json'))
            assert all(result[k] == v for k, v in (('source_sha', source), ('run_id', run), ('attempt', attempt), ('platform', platform)))
            assert result['accepted'] and not result['physical_device']
            assert len(result['cases']) == 1 and all(c['result'] == 'Passed' for c in result['cases'])
            assert result['program']['bundle_source_sha'] == source and result['program']['bundle_id'] == 'org.exreader.host'
            with zipfile.ZipFile(io.BytesIO(archive.read('receive-program.zip'))) as program:
                executable = 'EXReaderHost.app/' + ('Contents/MacOS/EXReaderHost' if platform == 'macos' else 'EXReaderHost')
                payload = program.read(executable)
                assert len(payload) == result['program']['bytes']
                assert hashlib.sha256(payload).hexdigest() == result['program']['sha256']
            controls = json.loads(archive.read('ui-fault-controls.json'))
            assert len(controls) == 6 and all(x['ok'] for x in controls)
            commands = result['commands']
            required = {'native-owner-build', 'seed-upload', 'native-receive', 'hash-fault-preserves-local',
                        'interrupted-response-preserves-local', 'cancel-in-flight-download', 'restored-original-retry',
                        'native-ui', 'independent-concurrent-author', 'concurrent-history-keeps-local'}
            assert required <= {c['role'] for c in commands if c['exit'] == 0}
        summary['artifacts'].append({'id': a['id'], 'name': a['name'], 'zip_sha256': digest, 'bytes': len(raw), 'result': result})
    summary['accepted'] = True
except Exception as error:
    summary['failure'] = repr(error)
finally:
    (ROOT / 'build').mkdir(exist_ok=True)
    (ROOT / 'build/d21-summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
assert summary['accepted'], 'D21 retains receive acceptance gaps'
