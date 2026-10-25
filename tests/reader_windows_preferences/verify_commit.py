"""Actions-only raw artifact authentication for the narrow cancellation repair."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip, require

EXPECTED = [role + suffix for role in ('empty', 'txt', 'epub', 'pdf')
            for suffix in ('-before-save-cancel-retains', '-after-save-cancel-publishes', '-reopened-committed-choice')]
EXPECTED += ['old-post-save-veto-control-rejected']


def validate(report, source, run, attempt, candidate, control):
    require(report.get('accepted') is True and report.get('source_sha') == source and
            str(report.get('run_id')) == str(run) and str(report.get('attempt')) == str(attempt), 'identity/acceptance')
    rows = report.get('checks', [])
    require(report.get('count') == 13 and [row.get('name') for row in rows] == EXPECTED and
            all(row.get('passed') is True and isinstance(row.get('pid'), int) and row['pid'] > 0 for row in rows), 'named original boundary checks')
    require(report.get('consumer_sha256') == candidate and report.get('control_sha256') == control and
            candidate != control, 'actual binary identity')
    require(report.get('complete_product') is False and report.get('original_f3_suite_accepted') is False and
            not report.get('failure'), 'scope/failure')


def selftest():
    good = dict(accepted=True, source_sha='source', run_id='run', attempt='1', count=13,
                checks=[dict(name=name, passed=True, pid=1) for name in EXPECTED],
                consumer_sha256='candidate', control_sha256='control', complete_product=False,
                original_f3_suite_accepted=False)
    validate(good, 'source', 'run', '1', 'candidate', 'control')
    for mutation in (dict(accepted=False), dict(source_sha='other'), dict(attempt='2'), dict(count=12),
                     dict(checks=good['checks'][:-1]), dict(consumer_sha256='other'),
                     dict(complete_product=True), dict(original_f3_suite_accepted=True), dict(failure='injected')):
        bad = copy.deepcopy(good); bad.update(mutation)
        try:
            validate(bad, 'source', 'run', '1', 'candidate', 'control')
        except Exception:
            continue
        raise AssertionError('protocol negative admitted: ' + str(mutation))


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    selftest()
    if '--self-test' in sys.argv:
        print('9 rejection controls passed')
        return
    source, run, attempt = os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    out = ROOT / 'build/prefs-commit-summary'; out.mkdir(parents=True, exist_ok=True)
    result = dict(accepted=False, source_sha=source, run_id=run, attempt=attempt,
                  complete_product=False, original_f3_suite_accepted=False)
    try:
        metadata = fetch('actions/runs/' + run)
        require(metadata['head_sha'] == source and metadata['path'] == '.github/workflows/reader-windows-preferences-commit.yml' and
                str(metadata['run_attempt']) == attempt, 'workflow source')
        jobs = fetch('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
        producers = [j for j in jobs if j['name'] == 'windows']
        require(len(producers) == 1 and producers[0]['conclusion'] == 'success', 'producer incomplete or failed')
        artifacts = fetch('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
        matches = [a for a in artifacts if a['name'] == 'windows-preferences-commit-' + run + '-' + attempt]
        require(len(matches) == 1, 'artifact missing or duplicate')
        artifact = matches[0]
        require(not artifact['expired'] and datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'expired artifact')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(artifact['id'], stream)
            stream.seek(0); raw = stream.read()
        require(len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest'], 'raw ZIP differs')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist(); require(len(names) == len(set(names)), 'duplicate ZIP member')
            report = json.loads(archive.read('ui/report.json'))
            candidate = hashlib.sha256(archive.read('package/EXReader/EXReader.exe')).hexdigest()
            control = hashlib.sha256(archive.read('control.exe')).hexdigest()
            validate(report, source, run, attempt, candidate, control)
        result.update(accepted=True, checks=13, producer_job=producers[0]['id'], artifact=artifact,
                      consumer_sha256=candidate, control_sha256=control)
    except Exception as error:
        result['failure'] = type(error).__name__ + ': ' + str(error)
    (out / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    require(result['accepted'], 'actual cancellation acceptance refused')


if __name__ == '__main__':
    main()
