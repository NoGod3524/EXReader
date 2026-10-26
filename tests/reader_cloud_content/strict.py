"""Authenticate ordinary same-run regression evidence without a D13 grant."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, pages, download_artifact_zip
sys.path.insert(0, str(ROOT / 'tests/reader_webdav_import'))
from check_artifacts import require_report, negative_selftest


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    metadata = fetch('actions/runs/' + run + '/attempts/' + attempt)
    assert metadata['head_sha'] == source and str(metadata['run_attempt']) == attempt
    assert metadata['path'].split('@')[0] == '.github/workflows/reader-cloud-content-binding.yml'
    jobs = pages('actions/runs/' + run + '/attempts/' + attempt + '/jobs', 'jobs')
    artifacts = pages('actions/runs/' + run + '/artifacts', 'artifacts')
    records = []
    for platform, version in [('Windows', '3.40.0'), ('Linux', '3.40.0'),
                              ('macOS', '3.40.0'), ('Linux', '3.41.0')]:
        job, = [item for item in jobs if item['name'] == 'ordinary import ' + platform + ' SDK ' + version]
        assert job['head_sha'] == source and str(job['run_attempt']) == attempt
        assert job['status'] == 'completed' and job['conclusion'] == 'success'
        item, = [item for item in artifacts if item['name'] == 'cloud-pinned-' + platform + '-' + version + '-' + run + '-' + attempt]
        assert not item['expired'] and item['workflow_run']['head_sha'] == source
        assert str(item['workflow_run']['id']) == run
        assert datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        raw = download_artifact_zip(item['id'])
        assert len(raw) == item['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == item['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names))
            result = json.loads(archive.read('result.json'))
            assert (result['source_sha'], result['run_id'], result['attempt'], result['platform'], result['sdk_version']) == (source, run, attempt, platform, version)
            assert result['ordinary_regression_accepted'] is True
            assert result['d13_accepted'] is False and result['path_replacement_experiment_executed'] is False
            assert result['cleanup_requires_private_stable_directory'] is True
            assert {name for name in names if not name.endswith('/')} == set(result['files']) | {'result.json'}
            for name, identity in result['files'].items():
                data = archive.read(name)
                assert len(data) == identity['bytes'] and hashlib.sha256(data).hexdigest() == identity['sha256'], name
            report = json.loads(archive.read('ordinary/result.json'))
            require_report(report, source, run, attempt)
            require_report(json.loads(archive.read('legacy/result.json')), source, run, attempt)
            assert 'observed_bytes_redirect_collision_retry_and_cancellation' in {c['id'] for c in report['checks']}
            assert report['probe_sha256'] == result['programs']['cloud-probe']['sha256']
            assert report['review_probe_sha256'] == result['programs']['cloud-review-probe']['sha256']
            for program in result['programs'].values():
                assert result['files'][program['member']] == {key: program[key] for key in ('bytes', 'sha256')}
        records.append({'platform': platform, 'sdk_version': version, 'checks': report['count'],
                        'artifact': {key: item[key] for key in ('id','name','size_in_bytes','digest','expires_at')}})
    output = ROOT / 'build/cloud-pinned-summary'
    output.mkdir(parents=True)
    (output / 'result.json').write_text(json.dumps({'source_sha': source, 'run_id': run, 'attempt': attempt,
        'ordinary_regression_accepted': True, 'd13_accepted': False,
        'path_replacement_experiment_executed': False,
        'original_report_negative_controls': negative_selftest(), 'profiles': records}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
