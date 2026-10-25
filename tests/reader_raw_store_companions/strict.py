"""Actions-only same-attempt authenticated original ZIP comparison."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    repo, run, attempt, source = (os.environ[k] for k in ['GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'])
    def get(path, binary=False):
        data = subprocess.check_output(['gh', 'api', 'repos/' + repo + '/' + path], timeout=240)
        return data if binary else json.loads(data)
    record = get('actions/runs/' + run + '/attempts/' + attempt)
    assert record['head_sha'] == source and record['run_attempt'] == int(attempt)
    jobs = get('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    artifacts = get('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    platforms, retained = [], []
    for platform, runner in [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022')]:
        job = [j for j in jobs if j['name'] == 'candidate (' + runner + ')']
        assert len(job) == 1 and job[0]['conclusion'] == 'success'
        found = [a for a in artifacts if a['name'] == f'reader-raw-store-companions-{platform}-{run}-{attempt}']
        assert len(found) == 1
        artifact = found[0]
        assert not artifact['expired'] and datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00')) > datetime.now(timezone.utc)
        assert artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == int(run)
        raw = get('actions/artifacts/' + str(artifact['id']) + '/zip', True)
        assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert len(z.namelist()) == len(set(z.namelist()))
            for name in z.namelist():
                path = PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name and not name.endswith('.key')
            result = json.loads(z.read('result.json'))
            assert result['accepted'] and not result['adopted'] and not result['actual_hosts']
            assert (result['source_sha'],result['run_id'],result['attempt']) == (source,run,attempt)
            assert len(result['original_regressions']) == 6 and all(x >= 20 for x in result['original_regressions'].values())
            assert len(result['mixed_profiles_refused']) == 3 and result['off_new_symbols_absent']
            profiles = json.loads(z.read('profiles.json'))
            assert profiles['accepted'] and profiles['old_sdk_runtime'] == '3.40.0' and len(profiles['checks']) == 8
            tls = json.loads(z.read('actual-tls/result.json'))
            assert tls['accepted'] and tls['source_sha'] == source and tls['run_id'] == run and tls['attempt'] == attempt
            assert len(tls['checks']) == 9 and len(set(tls['checks'])) == 9 and len(tls['exact_wires']) == 11
            assert all(x['exact_bytes'] for x in tls['legacy']) and [x['version'] for x in tls['legacy']] == [1,2]
            assert tls['requests'] and all(x['authenticated'] for x in tls['requests'])
            for name, digest in tls['exact_wires'].items():
                assert hashlib.sha256(z.read('actual-tls/sender/expected/' + name)).hexdigest() == digest
            for prefix in ['sync-receiver', 'session-receiver', 'session-second-process']:
                assert b'PASS third process reopen' in z.read('actual-tls/' + prefix + '-sdk-reopen.log')
            retained.append(tls['exact_wires'])
        platforms.append({'platform': platform, 'producer_job': job[0]['id'],
            'artifact': {k:artifact[k] for k in ['id','name','digest','size_in_bytes','expires_at']},
            'original_regressions':result['original_regressions'], 'tls_checks':tls['count'], 'profile_checks':profiles['checks']})
    assert retained[0] == retained[1]
    result = {'accepted':True, 'source_sha':source, 'run_id':run, 'attempt':attempt, 'adopted':False,
        'platforms':platforms, 'cross_platform_exact_wires_equal':True,
        'scope':'explicit installed commands/sync/session raw-store companion candidate only',
        'actual_hosts':False, 'actual_android_apple_interop':False, 'complete_product':False}
    out = Path('build/raw-store-companions-summary');out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)

if __name__ == '__main__': main()

