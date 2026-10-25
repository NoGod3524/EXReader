"""Run both original judges unchanged, then authenticate the common guard kind."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import runpy
import subprocess
import sys
import zipfile

import guard as common_guard
from selftest import EXPECTED


def require(value, message):
    if not value:
        raise RuntimeError(message)


def api(path, binary=False):
    raw = subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path])
    return raw if binary else json.loads(raw)


def authenticate_common(report, raw_guard):
    source, run, attempt = report['source_sha'], report['run_id'], report['attempt']
    record = api('actions/runs/' + run + '/attempts/' + attempt)
    require(record['head_sha'] == source and str(record['run_attempt']) == attempt
            and record['path'].split('@', 1)[0] == common_guard.WORKFLOW, 'actual workflow/source differs')
    jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    retained = []
    for stage in ('android', 'protocol'):
        producer = [job for job in jobs if job['name'] == stage]
        require(len(producer) == 1 and producer[0]['head_sha'] == source
                and producer[0]['status'] == 'completed' and producer[0]['conclusion'] == 'success'
                and str(producer[0]['run_attempt']) == attempt, 'same-attempt producer did not pass: ' + stage)
        name = 'reader-common-android-source-' + stage + '-' + run + '-' + attempt
        matches = [item for item in artifacts if item['name'] == name]
        require(len(matches) == 1, 'one common source artifact required: ' + stage)
        item = matches[0]
        require(not item['expired'] and item['workflow_run']['id'] == int(run)
                and item['workflow_run']['head_sha'] == source and 0 < item['size_in_bytes'] <= 2 * 1024**2
                and datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
                'common source artifact metadata refused')
        body = api('actions/artifacts/' + str(item['id']) + '/zip', binary=True)
        require(len(body) == item['size_in_bytes'] and 'sha256:' + hashlib.sha256(body).hexdigest() == item['digest'],
                'common source original ZIP identity differs')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            require(set(archive.namelist()) == {'guard.json', 'negative.json'} and len(archive.infolist()) == 2,
                    'unexpected common-source artifact members')
            for member in archive.infolist():
                require((member.external_attr >> 16) & 0o170000 != 0o120000 and member.file_size <= 1024**2,
                        'unsafe common-source artifact member')
            stored, controls = json.loads(archive.read('guard.json')), json.loads(archive.read('negative.json'))
        require(stored.get('producer_job_key') == stage, 'wrong source-guard producer stage')
        expected = dict(report, producer_job_key=stage)
        require(stored == expected, 'stored common source guard differs from fresh actual-source inspection')
        require(stored['guard_kind'] == 'common' and stored['legacy_guard_executed'] is False,
                'old guard success must not be impersonated')
        for document in (stored, controls):
            require(document['source_sha'] == source and document['run_id'] == run
                    and document['attempt'] == attempt and document['producer_job_key'] == stage,
                    'common source/negative identity differs')
        require(controls['negative_controls_passed'] is True
                and controls['checkout_and_index_unchanged'] is True
                and controls['event_environment_unchanged'] is True
                and {row['name'] for row in controls['controls']} == EXPECTED
                and len(controls['controls']) == len(EXPECTED)
                and all(row['rejected'] for row in controls['controls']), 'negative controls incomplete')
        if stage == 'android':
            require(raw_guard == stored, 'guard consumed by unchanged raw strict is not the authenticated common guard')
        retained.append({key: item[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
    return retained


def main():
    report = common_guard.inspect_source()
    # This is the exact first original command. No original file is patched.
    subprocess.run([sys.executable, 'tests/reader_android_record_interop/check_evidence.py'],
                   cwd=common_guard.ROOT, check=True)
    # Execute the complete unchanged second judge and retain the guard object it
    # actually read from its authenticated raw ZIP. No assertions are intercepted.
    sys.path.insert(0, str(common_guard.ROOT / 'tests/reader_android_raw3'))
    raw = runpy.run_path(str(common_guard.ROOT / 'tests/reader_android_raw3/strict.py'), run_name='__main__')
    original = raw['output']
    require(original['accepted'] is True and original['complete_product'] is False
            and original['bidirectional_interoperability_accepted'] is False,
            'original raw judge did not retain its limited acceptance')
    require([original[key] for key in ('inherited_business_checks', 'retained_default_sender_checks',
                                      'raw_checks', 'original_protocol_phases', 'java_policy_cases')]
            == [130, 8, 19, 18, 20], 'original full-chain counts differ')
    artifacts = authenticate_common(report, raw['guard'])
    result = {'source_sha': report['source_sha'], 'run_id': report['run_id'], 'attempt': report['attempt'],
              'guard_kind': 'common', 'legacy_guard_executed': False, 'original_judges_executed_unchanged': True,
              'workflow_projection_exact': True, 'common_guard_artifacts': artifacts,
              'negative_controls_per_producer': len(EXPECTED), 'original_result': original,
              'original_judges_sha256': {path: hashlib.sha256((common_guard.ROOT / path).read_bytes()).hexdigest()
                  for path in ('tests/reader_android_record_interop/check_evidence.py', 'tests/reader_android_raw3/strict.py')},
              'accepted': True, 'complete_product': False, 'physical_device': False,
              'bidirectional_interoperability_accepted': False,
              'scope': 'same-source Android complete original leaf only; fixed historical Apple peer is not common-source bidirectional acceptance'}
    output = common_guard.ROOT / 'build/reader-raw3-common-android/strict'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
