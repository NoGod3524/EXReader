"""Actions-only authentication and component-by-component inspection of prior C04 ZIPs."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

RUNS = {
    40226933116: ('2bc682da196e8f737fa44b66fcc33dea69b442f8', {12612560327, 12612025078, 12611906192, 12611730900, 12611224502}),
    40227936319: ('255871b38f3b3252a917e920a11641255cc2b485', {12612590453, 12612361524, 12611907317, 12611802102, 12611697795}),
    40234424624: ('bfc6447798d533c4d5d5fe7ca02e9a54fc928999', None),
}


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = ROOT / 'build/c04-inspect'
    out.mkdir(parents=True, exist_ok=True)
    result = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'accepted': False,
              'scope': 'authenticated historical artifacts only; no SDK candidate execution or acceptance', 'runs': []}
    for run, (source, expected_ids) in RUNS.items():
        metadata = fetch(f'actions/runs/{run}/attempts/1')
        assert metadata['head_sha'] == source and metadata['status'] == 'completed' and metadata['conclusion'] == 'failure'
        artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
        if expected_ids is not None:
            assert {row['id'] for row in artifacts} == expected_ids
        else:
            required = {f'reader-next-c04-{part}-{run}-1' for part in ('guard', 'diagnose', 'ubuntu-22.04', 'windows-latest')}
            assert required <= {row['name'] for row in artifacts} <= required | {f'reader-next-c04-aggregate-{run}-1'}
        record = {'run_id': run, 'attempt': 1, 'source_sha': source, 'conclusion': 'failure', 'artifacts': []}
        for artifact in artifacts:
            assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == run
            assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
            body = download_artifact_zip(artifact['id'])
            assert len(body) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(body).hexdigest() == artifact['digest']
            retained = out / str(run) / artifact['name']
            retained.mkdir(parents=True)
            (retained / 'original.zip').write_bytes(body)
            entry = {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
            entry['files'] = {}
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                names = archive.namelist()
                assert len(names) == len(set(names)) and len(names) <= 1000
                assert sum(info.file_size for info in archive.infolist()) <= 64 * 1024 * 1024
                for name in names:
                    path = PurePosixPath(name)
                    assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
                    if name.endswith('/'):
                        continue
                    data = archive.read(name)
                    target = retained / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    basename = path.name
                    if basename in ('compare.json', 'summary-base.json', 'summary-cand.json', 'aggregate.json', 'guard.json', 'scan.json') or \
                            basename.startswith('boundary-') or basename.endswith(('.stderr.txt', '.stdout.json', '.exit')):
                        try:
                            value = json.loads(data)
                        except (ValueError, UnicodeDecodeError):
                            value = data.decode('utf-8', 'replace')
                        entry['files'][name] = value
                        if run == 40234424624 and basename == 'compare.json':
                            print('C04-ROOT-COMPARE ' + json.dumps({'artifact': artifact['name'], 'files': value['files']}, ensure_ascii=False), flush=True)
            record['artifacts'].append(entry)
            # Never concatenate boundary-base.err and boundary-cand.err: an
            # expected base refusal must remain distinguishable from candidate failure.
            brief = {'historical_run': run, 'artifact': artifact['name'], 'id': artifact['id'], 'files': {}}
            for name, value in entry['files'].items():
                if name.endswith(('compare.json', 'ctest.exit', 'boundary-base.exit', 'boundary-cand.exit',
                                  'boundary-base.err', 'boundary-cand.err', 'boundary-cand.out',
                                  '.stderr.txt', '.stdout.json', '.exit')) and not name.endswith('scan.json'):
                    brief['files'][name] = value
                if name.endswith('aggregate.json'):
                    brief['files'][name] = {'candidate_checks_passed': value['candidate_checks_passed'],
                                            'failed': [row for row in value['checks'] if not row['ok']]}
            print(json.dumps(brief, ensure_ascii=False), flush=True)
        result['runs'].append(record)
    (out / 'inspection.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
