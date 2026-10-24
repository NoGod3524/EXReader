# SPDX-License-Identifier: MIT
"""Actions-only strict same-source native/SDK evidence for reading anchor v2."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id, attempt, source = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA']
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt,
               'artifacts': [], 'problems': [], 'sdk_changed': False, 'schema_changed': False,
               'host_ui_accepted': False, 'webdav_roundtrip_accepted': False, 'six_platform_accepted': False, 'complete_product': False,
               'scope': 'Windows/Linux SDK captures and original export over real native HTTPS fixture; no host UI'}
    try:
        run = fetch(f'actions/runs/{run_id}')
        require(run['head_sha'] == source and run['run_attempt'] == attempt and run['path'] == '.github/workflows/reader-reading-v2.yml', 'caller identity differs')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        normalized = []
        for platform, runner in [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022')]:
            for kind, name, job_name, path in [
                ('native', f'reader-commands-{platform}-{run_id}-{attempt}', f'native / installed typed product commands ({runner})', 'reading-v2-protocol/result.json'),
                ('sdk', f'reader-reading-v2-{platform}-{run_id}-{attempt}', f'real v2 capture ({runner})', 'v2-sdk-evidence/result.json')]:
                matches = [a for a in artifacts if a['name'] == name]
                require(len(matches) == 1, 'missing/duplicate artifact ' + name); artifact = matches[0]
                matches = [j for j in jobs if j['name'] == job_name]
                require(len(matches) == 1, 'missing/duplicate job ' + job_name); job = matches[0]
                require(job['head_sha'] == source and job['run_attempt'] == attempt and job['conclusion'] == 'success', 'upstream failed or different source')
                require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and artifact['workflow_run']['head_sha'] == source, 'artifact identity differs')
                # The authenticated downloader writes through an OS descriptor.
                with tempfile.TemporaryFile() as stream:
                    download_artifact_zip(artifact['id'], stream)
                    stream.seek(0); data = stream.read()
                require(len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'ZIP bytes/digest differ')
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    report = json.loads(archive.read(path))
                    require(report.get('accepted') is True and report['source_sha'] == source and int(report['run_id']) == run_id and int(report['attempt']) == attempt, 'report identity/refusal')
                    if kind == 'native':
                        require(report['count'] == 28 and len(set(report['checks'])) == 28, 'native cases missing')
                        listing = json.loads(archive.read('reading-v2-annotations/result.json'))
                        require(listing.get('accepted') is True and listing['source_sha'] == source and int(listing['run_id']) == run_id and int(listing['attempt']) == attempt, 'annotation page report identity/refusal')
                        require(listing['count'] == 10 and len(set(listing['checks'])) == 10 and listing['entities'] == 235, 'annotation page cases missing')
                        entities = json.loads(archive.read('reading-v2-entities/result.json'))
                        require(entities.get('accepted') is True and entities['source_sha'] == source and int(entities['run_id']) == run_id and int(entities['attempt']) == attempt, 'remote entity discovery report identity/refusal')
                        require(entities['count'] == 12 and len(set(entities['checks'])) == 12 and entities['tag_entities'] == 235 and entities['kinds'] == 7, 'remote entity discovery cases missing')
                        for relative, count in [('sync-source-evidence/result.json', 77 if platform == 'Linux' else 76), ('sync-protocol-evidence/result.json', 59),
                                                ('sync-evidence/result.json', 33), ('projection-evidence/result.json', 32), ('commands-evidence/result.json', 33), ('metadata-evidence/result.json', 29), ('session-evidence/result.json', 20)]:
                            original = json.loads(archive.read(relative))
                            require(original.get('accepted') is True and original['source_sha'] == source and len(original['checks']) == count, 'retained suite missing/refused ' + relative)
                    else:
                        require(report['legacy_checks'] == 121 and len(report['cases']) == 18 and report['receiver_found'] == 17 and report['receiver_mislocated'] == 0, 'SDK outcomes differ')
                        exported = json.loads(archive.read('v2-export-evidence/result.json'))
                        require(exported.get('accepted') is True and exported['source_sha'] == source and int(exported['run_id']) == run_id and int(exported['attempt']) == attempt, 'original export report identity/refusal')
                        require(exported['count'] == 14 and len(set(exported['checks'])) == 14 and set(exported['originals']) == {'txt', 'epub', 'pdf', 'cbz'}, 'original export cases missing')
                        transported = json.loads(archive.read('v2-webdav-evidence/result.json'))
                        require(transported.get('accepted') is True and transported['source_sha'] == source and int(transported['run_id']) == run_id and int(transported['attempt']) == attempt, 'SDK WebDAV report identity/refusal')
                        require(transported['originals_exported'] == 4 and transported['network_pushed'] == 22 and transported['network_pulled'] >= 22 and transported['request_count'] > 0, 'native transfer missing')
                        require(len(transported['cases']) == 18 and transported['receiver_found'] == 17 and transported['receiver_mislocated'] == 0, 'transported reading outcomes differ')
                        fields = ('id', 'mode', 'kind', 'part', 'start', 'end', 'state')
                        require([{k: c[k] for k in fields} for c in transported['cases']] == [{k: c[k] for k in fields} for c in report['cases']], 'native transport changes SDK capture outcomes')
                        normalized.append([{k: c[k] for k in ('id', 'mode', 'kind', 'part', 'start', 'end', 'state')} for c in report['cases']])
                summary['artifacts'].append({k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        require(len(normalized) == 2 and normalized[0] == normalized[1], 'platform capture outcomes differ')
        summary['webdav_roundtrip_accepted'] = True
        summary['accepted'] = True
    except Exception as error:
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__': main()
