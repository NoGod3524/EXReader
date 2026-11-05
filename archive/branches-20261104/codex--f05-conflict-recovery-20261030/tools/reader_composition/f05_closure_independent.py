"""Actions-only original-ZIP audit. Native module evidence never grants F05."""
import hashlib, io, json, os, sys, zipfile
from pathlib import Path, PurePosixPath
assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch, download_artifact_zip
sys.path.insert(0, str(Path('tests/reader_f05_closure').resolve()))
from boundaries import NEW_CHECKS, UNCOVERED_LIMITS
out = Path('build/f05-independent'); out.mkdir(parents=True, exist_ok=True)
result = dict(accepted=False, f05_accepted=False, complete_product=False, host_ui_accepted=False,
              source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
              attempt=os.environ['GITHUB_RUN_ATTEMPT'], artifacts=[])
try:
    run = result['run_id']; attempt = result['attempt']; source = result['source_sha']
    response = fetch(f'actions/runs/{run}/artifacts?per_page=100')
    assert response['total_count'] == len(response['artifacts'])
    for label, platform in [('Linux','linux'), ('Windows','win32'), ('macOS','darwin')]:
        name = f'reader-sync-resilience-{label}-{run}-{attempt}'
        matches = [a for a in response['artifacts'] if a['name'] == name]
        assert len(matches) == 1, name
        a = matches[0]
        assert not a['expired'] and a['workflow_run']['head_sha'] == source
        raw = download_artifact_zip(a['id'])
        digest = hashlib.sha256(raw).hexdigest()
        assert len(raw) == a['size_in_bytes'] and a['digest'] == 'sha256:' + digest
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = z.namelist()
            assert len(names) == len(set(names))
            assert all(not PurePosixPath(n).is_absolute() and '..' not in n.split('/') and '\\\\' not in n and ':' not in n and not n.endswith('.key') for n in names)
            files = {n:z.read(n) for n in names if not n.endswith('/')}
        def one(suffix):
            found = [v for k,v in files.items() if k == suffix or k.endswith('/'+suffix)]
            assert len(found) == 1, suffix
            return found[0]
        report = json.loads(one('f05-evidence/result.json'))
        assert report['accepted'] is True and report['platform'] == platform
        assert report['source_sha'] == source and str(report['run_id']) == run and str(report['attempt']) == attempt
        assert report['host_ui_accepted'] is False and report['complete_product'] is False
        assert report['count'] == 25 and [x['id'] for x in report['checks']] == NEW_CHECKS
        assert all(x['pass'] is True and x['expected'] and x['actual'] for x in report['checks'])
        assert report['uncovered'] == UNCOVERED_LIMITS
        for suffix, field in [('res-resilience-consumer/resilience-consumer','consumer_sha256'), ('res-revision-consumer/revision-consumer','revision_consumer_sha256')]:
            data = one(suffix + ('.exe' if label == 'Windows' else ''))
            assert hashlib.sha256(data).hexdigest() == report[field]
        requests = json.loads(one('f05-evidence/requests.json'))
        puts = [r for r in requests if r['method']=='PUT' and r['path'].startswith('/f05-peer-a/')]
        assert len(puts) == 3 and all(r['status']==201 and r['if_none_match']=='*' and r['body_sha256'] for r in puts)
        result['artifacts'].append(dict(id=a['id'], name=name, bytes=len(raw), sha256=digest, platform=platform, checks=25))
    result.update(accepted=True, scope='three-desktop native module peer-wire diagnostics only', uncovered=UNCOVERED_LIMITS)
except Exception as e:
    result['error'] = repr(e)
finally:
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
assert result['accepted'], result.get('error')
