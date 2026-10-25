# SPDX-License-Identifier: MIT
"""Actions-only strict same-source evidence for the C06 consumer jobs."""
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

PLATFORMS = [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022')]
WORKFLOW = '.github/workflows/reader-next-c06.yml'
MAC = {'source_sha': '15dab6b2270dc296ed6239db67ced2e22d255e65', 'run_id': 40196978163, 'artifact_id': 12600789926,
       'zip_sha256': '92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5'}


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id, attempt, source = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA']
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt, 'artifacts': [], 'jobs': [], 'problems': [],
               'cross_platform_identical_exports': False, 'adopted': False, 'host_ui': False, 'physical_device': False}
    try:
        run = fetch(f'actions/runs/{run_id}')
        require(run['head_sha'] == source and run['run_attempt'] == attempt and run['path'] == WORKFLOW, 'caller identity differs')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        reports = []
        for platform, runner in PLATFORMS:
            name = f'reader-next-c06-{platform}-{run_id}-{attempt}'
            job_name = f'c06 raw3 portable ({runner})'
            matches = [a for a in artifacts if a['name'] == name]
            require(len(matches) == 1, 'missing/duplicate artifact ' + name); artifact = matches[0]
            matches = [j for j in jobs if j['name'] == job_name]
            require(len(matches) == 1, 'missing/duplicate job ' + job_name); job = matches[0]
            require(job['head_sha'] == source and job['run_attempt'] == attempt and job['conclusion'] == 'success', 'upstream failed or different source: ' + job_name)
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and artifact['workflow_run']['head_sha'] == source, 'artifact identity differs')
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0); data = stream.read()
            require(len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'ZIP bytes/digest differ')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
                require(len(names) == len(set(names)), 'duplicate ZIP member')
                found = [n for n in names if n == 'result.json' or n.endswith('/result.json')]
                require(len(found) == 1, 'result.json missing or ambiguous')
                report = json.loads(archive.read(found[0]))
            require(report.get('accepted') is True and report['source_sha'] == source and int(report['run_id']) == run_id and int(report['attempt']) == attempt, 'report identity/refusal')
            require(report['count'] == len(report['checks']) > 0 and len(set(report['checks'])) == len(report['checks']) and not report['failed'], 'check list empty, duplicated or failed')
            require(report['legacy_default_kept'] is True and report['sdk_changed'] is False and report['schema_changed'] is False and report['adopted'] is False, 'report claims differ')
            peer = report['mac_records']['peer']
            require(all(peer[k] == v for k, v in MAC.items()) and peer['attempt'] == 1, 'certified Mac records were not consumed')
            reports.append(report)
            summary['artifacts'].append({k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['jobs'].append({k: job[k] for k in ('id', 'name', 'conclusion')})
        require(all(set(r['checks']) == set(reports[0]['checks']) for r in reports), 'platform check lists differ')
        require(all(r['raw_outputs'] == reports[0]['raw_outputs'] and r['legacy_outputs'] == reports[0]['legacy_outputs'] for r in reports), 'platform export bytes differ')
        require(all(r['mac_records']['books'] == reports[0]['mac_records']['books'] for r in reports), 'platform Mac export bytes differ')
        summary['cross_platform_identical_exports'] = True
        summary['accepted'] = True
    except Exception as error:
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__': main()
