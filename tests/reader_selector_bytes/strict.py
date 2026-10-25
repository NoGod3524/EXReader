"""Authenticate original ZIPs and independent public-SDK bytes in Actions only."""
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    repo, run, attempt, source = (os.environ[k] for k in ['GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'])
    token = os.environ['GH_TOKEN']
    def request(url, api=True):
        if api:
            url = 'https://api.github.com/repos/' + repo + '/' + url
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.read()
    def metadata(path): return json.loads(request(path))
    record = metadata('actions/runs/' + run + '/attempts/' + attempt)
    assert record['head_sha'] == source and int(record['run_attempt']) == int(attempt)
    jobs = metadata('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    artifacts = metadata('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    results, wires = [], []
    for platform, runner in [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022')]:
        job = [j for j in jobs if j['name'] == 'candidate (' + runner + ')']
        assert len(job) == 1 and job[0]['conclusion'] == 'success', (platform, job)
        artifact = [a for a in artifacts if a['name'] == f'reader-selector-bytes-{platform}-{run}-{attempt}']
        assert len(artifact) == 1 and not artifact[0]['expired']
        a = artifact[0]
        assert datetime.fromisoformat(a['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        assert a['workflow_run']['head_sha'] == source and a['workflow_run']['id'] == int(run)
        raw = request('actions/artifacts/' + str(a['id']) + '/zip')
        assert len(raw) == a['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == a['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = z.namelist()
            assert len(names) == len(set(names))
            for name in names:
                path = PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
            result = json.loads(z.read('result.json'))
            assert result['accepted'] and result['source_sha'] == source and result['run_id'] == run and result['attempt'] == attempt
            assert result['legacy_wire_bytes_unchanged'] and result['original_regressions_passed'] and result['off_new_symbols_absent']
            program = 'candidate-consumer/selector-bytes' + ('.exe' if platform == 'Windows' else '')
            assert hashlib.sha256(z.read(program)).hexdigest() == result['consumer_sha256']
            assert len(result['protocol_checks']) >= 30 and len(result['graph_checks']) >= 11
            assert all(c['pass'] for c in result['protocol_checks'] + result['graph_checks'])
            for name, digest in result['logs'].items():
                assert '/' not in name and hashlib.sha256(z.read(name)).hexdigest() == digest
            assert hashlib.sha256(z.read('actual/original.pdf')).hexdigest() == result['pdf_sha256']
            selected = {}
            for name, role in [('progress', 'point'), ('bookmark', 'point'), ('highlight', 'range')]:
                wire = json.loads(z.read('actual/' + name + '.json'))
                location = wire['payload']['location']
                assert location['anchor_version'] == 3 and location['page_id'] == 'page-1' and location['page'] == 0
                for field in ['exact', 'prefix', 'suffix']:
                    item = location['selector'][field]
                    assert item['base64'] is not None
                    decoded = base64.b64decode(item['base64'], validate=True)
                    assert base64.b64encode(decoded).decode() == item['base64']
                    assert decoded == z.read('actual/sdk-' + role + '-' + field + '.bin') and len(decoded) == item['size']
                selected[name] = wire
            assert b'\0' in z.read('actual/sdk-point-suffix.bin') and b'\0' in z.read('actual/sdk-range-exact.bin')
            assert b'PASS second process receive' in z.read('actual-receive.log') and b'PASS third process reopen' in z.read('actual-reopen.log')
            assert b'NULL exact expression cannot grant FOUND' in z.read('actual-nullable.log')
            wires.append(selected)
        results.append({'platform': platform, 'producer_job': job[0]['id'], 'artifact': {k: a[k] for k in ['id', 'name', 'digest', 'size_in_bytes', 'expires_at']},
                        'protocol_checks': len(result['protocol_checks']), 'graph_checks': len(result['graph_checks']), 'pdf_sha256': result['pdf_sha256']})
    assert wires[0] == wires[1], 'same-source public SDK captures and exact selected wire differ between platforms'
    summary = {'accepted': True, 'adopted': False, 'source_sha': source, 'run_id': run, 'attempt': attempt,
               'scope': 'explicit installed core codec/revisions/commands/typed-view candidate only', 'platforms': results,
               'cross_platform_wire_equal': True, 'actual_android_apple_interop': False, 'physical_device': False, 'complete_product': False}
    out = Path('build/selector-bytes-summary');out.mkdir(parents=True)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)

if __name__ == '__main__':
    main()
