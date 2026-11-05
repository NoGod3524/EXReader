"""Authenticate raw same-run upload bytes; not a Windows F07 symbol acceptance gate."""
from datetime import datetime, timezone
import json
import os
import shutil
import sys
import zipfile

from capture_contract import (ROOT, OUT, REPO, WORKFLOW, BRANCH, actions_only, guard, identity,
    same, require, save, file_digest, safe_members, validate_capture)
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, pages, download_artifact_zip


def main():
    actions_only()
    expected = identity()
    folder = OUT / 'authentication'
    folder.mkdir(parents=True, exist_ok=True)
    report = dict(expected, accepted=False, capture_complete=False,
        f06_identity_verified=False, f07_accepted=False, failures=[])
    try:
        guard()
        require(os.environ['PROTOCOL_RESULT'] == 'success' and
            os.environ['WINDOWS_RESULT'] == 'success', 'upstream protocol/Windows job failed')
        run, attempt = expected['run_id'], expected['attempt']
        workflow = fetch(f'actions/runs/{run}/attempts/{attempt}')
        require(workflow['id'] == int(run) and workflow['run_attempt'] == int(attempt)
            and workflow['head_sha'] == expected['source_sha']
            and workflow['head_branch'] == BRANCH and workflow['path'] == WORKFLOW,
            'workflow identity differs')
        jobs = pages(f'actions/runs/{run}/attempts/{attempt}/jobs', 'jobs')
        for name in ('capture-protocol', 'windows-capture'):
            matching = [j for j in jobs if j['name'] == name]
            require(len(matching) == 1 and matching[0]['head_sha'] == expected['source_sha']
                and matching[0]['status'] == 'completed' and matching[0]['conclusion'] == 'success',
                'required producer job incomplete/failed: ' + name)
        artifacts = pages(f'actions/runs/{run}/artifacts', 'artifacts')
        name = f'windows-f07-capture-{run}-{attempt}'
        matching = [a for a in artifacts if a['name'] == name]
        require(len(matching) == 1, 'missing/duplicate same-attempt artifact')
        artifact = matching[0]
        require(artifact['id'] == int(os.environ['CAPTURE_ARTIFACT_ID']) and not artifact['expired']
            and artifact['workflow_run']['id'] == int(run)
            and artifact['workflow_run']['head_sha'] == expected['source_sha']
            and datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
            'expired or cross-source/run upload')
        raw_path = OUT / 'downloaded-original-upload.zip'
        with raw_path.open('w+b') as stream:
            download_artifact_zip(artifact['id'], output=stream)
        raw = file_digest(raw_path)
        require(raw['bytes'] == artifact['size_in_bytes'] and
            'sha256:' + raw['sha256'] == artifact['digest'] and
            os.environ['CAPTURE_ARTIFACT_DIGEST'].removeprefix('sha256:') == raw['sha256'],
            'actual original upload size/SHA-256 differs')
        save(folder / 'github-evidence.json', dict(workflow=workflow, jobs=jobs, artifact=artifact,
            actual_upload=raw))
        with zipfile.ZipFile(raw_path) as transport:
            members = safe_members(transport)
            require(set(members) == {'snapshot.zip', 'inventory.json', 'report.json', 'source.json',
                'producer.json', 'producer-console.log'}, 'unexpected transport artifact membership')
            manifest = json.loads(transport.read('inventory.json'))
            outer = json.loads(transport.read('report.json'))
            source = json.loads(transport.read('source.json'))
            producer = json.loads(transport.read('producer.json'))
            for record in (manifest, outer, source, producer):
                same(record, expected)
            require(outer['capture_complete'] is True and outer['f06_identity_verified'] is True
                and outer['f07_accepted'] is False and producer['producer_completed'] is True,
                'producer capture did not complete')
            snapshot = OUT / 'downloaded-snapshot.zip'
            with transport.open('snapshot.zip') as source_stream, snapshot.open('wb') as destination:
                shutil.copyfileobj(source_stream, destination, 1024 * 1024)
            require(file_digest(snapshot) == manifest['archive'], 'inner snapshot bytes differ')
            with zipfile.ZipFile(snapshot) as bundle:
                recomputed = validate_capture(bundle, manifest['files'], expected)
                require(json.loads(bundle.read('capture/source.json')) == source,
                        'outer/inner source guard differs')
                require(json.loads(bundle.read('capture/producer.json')) == producer,
                        'outer/inner producer result differs')
            for key, value in recomputed.items():
                require(outer.get(key) == value, 'producer/recomputed result differs: ' + key)
            report.update(recomputed)
        report.update(accepted=True, scope='raw evidence capture and new Windows F06 byte identity only',
            artifact=dict(id=artifact['id'], name=name, **raw, expires_at=artifact['expires_at'],
                url=f'https://github.com/{REPO}/actions/runs/{run}/artifacts/{artifact["id"]}'),
            snapshot=manifest['archive'], captured_files=len(manifest['files']))
    except Exception as error:
        report['failures'].append(str(error))
    finally:
        save(folder / 'summary.json', report)
        print(json.dumps(report, indent=2), flush=True)
    require(report['accepted'], 'same-source capture authentication failed')


if __name__ == '__main__':
    main()
