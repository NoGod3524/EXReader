"""Authenticate this attempt's original preflight ZIP and rerun source inspection."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import PurePosixPath
import subprocess
import zipfile

import guard
from selftest import EXPECTED


def require(value, message):
    if not value:
        raise RuntimeError(message)


def api(path, binary=False):
    data = subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path])
    return data if binary else json.loads(data)


def inspect():
    guard.require_actions()
    source, run, attempt = os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    require(guard.git('rev-parse', 'HEAD').decode().strip() == source, 'actual strict checkout differs')
    metadata = api('actions/runs/' + run + '/attempts/' + attempt)
    require(metadata['head_sha'] == source and str(metadata['run_attempt']) == attempt, 'run identity differs')
    require(metadata['path'].split('@', 1)[0] == guard.WORKFLOW, 'unexpected workflow path')
    jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    producers = [row for row in jobs if row['name'] == 'composition preflight and refusal controls']
    require(len(producers) == 1 and producers[0]['status'] == 'completed'
            and producers[0]['conclusion'] == 'success' and producers[0]['head_sha'] == source
            and str(producers[0]['run_attempt']) == attempt, 'same-attempt producer did not pass')
    name = 'reader-raw3-common-preflight-' + run + '-' + attempt
    artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    matches = [item for item in artifacts if item['name'] == name]
    require(len(matches) == 1, 'exact one preflight artifact required')
    artifact = api('actions/artifacts/' + str(matches[0]['id']))
    require(not artifact['expired'] and artifact['workflow_run']['id'] == int(run)
            and artifact['workflow_run']['head_sha'] == source, 'artifact run/source differs or expired')
    require(datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
            'artifact validity ended')
    require(0 < artifact['size_in_bytes'] <= 5 * 1024 * 1024, 'artifact size is outside preflight bounds')
    body = api('actions/artifacts/' + str(artifact['id']) + '/zip', binary=True)
    digest = 'sha256:' + hashlib.sha256(body).hexdigest()
    require(len(body) == artifact['size_in_bytes'] and digest == artifact['digest'], 'original ZIP bytes/digest differ')
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        expected = {'guard.json', 'negative.json', 'guard.log', 'selftest.log'}
        require(set(archive.namelist()) == expected and len(archive.infolist()) == len(expected),
                'preflight members missing, duplicated or unexpected')
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            require(not path.is_absolute() and '..' not in path.parts
                    and (item.external_attr >> 16) & 0o170000 != 0o120000
                    and item.file_size <= 2 * 1024 * 1024, 'unsafe preflight ZIP member')
        report, negatives = json.loads(archive.read('guard.json')), json.loads(archive.read('negative.json'))
        for document in (report, negatives):
            require(document['source_sha'] == source and str(document['run_id']) == run
                    and str(document['attempt']) == attempt, 'report identity differs')
            require(document['accepted'] is False and document['complete_product'] is False,
                    'preflight must not grant product acceptance')
        require(report == guard.inspect_source(), 'uploaded source inspection differs from fresh strict inspection')
        require(report['source_preflight_passed'] is True and report['errors'] == [], 'composition did not pass')
        controls = negatives['controls']
        require({row['name'] for row in controls} == EXPECTED and len(controls) == len(EXPECTED)
                and all(row['rejected'] is True for row in controls), 'refusal controls incomplete')
        require(negatives['negative_controls_passed'] is True
                and negatives['positive_composition_passed'] is True
                and negatives['checkout_and_index_unchanged'] is True
                and negatives['event_environment_unchanged'] is True, 'negative-control protocol failed')
    return {'source_sha': source, 'run_id': run, 'attempt': attempt,
            'composition_preflight_authenticated': True, 'negative_controls': len(EXPECTED),
            'composition_base': guard.BASE, 'producer_job': producers[0]['id'],
            'artifact': {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
            'actual_zip_sha256': digest, 'accepted': False, 'complete_product': False,
            'runtime_accepted': False, 'scope': 'same-source composition preflight and refusal controls only'}


def main():
    guard.require_actions()
    try:
        result = inspect()
    except Exception as error:
        result = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'composition_preflight_authenticated': False,
                  'accepted': False, 'complete_product': False, 'error': str(error)}
    output = guard.ROOT / 'build/reader-raw3-common-strict'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, sort_keys=True), flush=True)
    if not result['composition_preflight_authenticated']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
