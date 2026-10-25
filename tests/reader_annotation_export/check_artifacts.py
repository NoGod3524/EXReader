# SPDX-License-Identifier: MIT
"""Actions-only strict same-source evidence for the three annotation-export consumer jobs."""
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

PLATFORMS = [('Linux', 'ubuntu-22.04', 'linux'), ('Windows', 'windows-2022', 'windows'), ('macOS', 'macos-15', 'darwin')]
SHARED_SKIPS = {'windows_locked_target_publish_failure', 'posix_rlimit_fsize_mid_stream_write_failure'}
# Each platform runs exactly one of these two write-failure checks and declares the other skipped.
WRITE_FAILURE = {'linux': 'mid_stream_write_failure_rlimit_fsize_keeps_previous_export',
                 'darwin': 'mid_stream_write_failure_rlimit_fsize_keeps_previous_export',
                 'windows': 'locked_target_publish_failure_keeps_previous_export'}
OPTIONS = set(WRITE_FAILURE.values())


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id, attempt, source = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA']
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt, 'artifacts': [], 'jobs': [],
               'problems': [], 'granted_platforms': [], 'skipped': {}, 'cross_platform_identical_outputs': False,
               'host_ui_accepted': False, 'six_platform_accepted': False, 'complete_product': False,
               'import_or_conflict_resolution': False, 'performance_claimed': False, 'sdk_changed': False, 'schema_changed': False}
    try:
        run = fetch(f'actions/runs/{run_id}')
        require(run['head_sha'] == source and run['run_attempt'] == attempt and run['path'] == '.github/workflows/reader-annotation-export.yml', 'caller identity differs')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        outcomes, check_sets = [], []
        for platform, runner, granted in PLATFORMS:
            name = f'reader-annotation-export-{platform}-{run_id}-{attempt}'
            job_name = f'annotation export ({runner})'
            matches = [a for a in artifacts if a['name'] == name]
            require(len(matches) == 1, 'missing/duplicate artifact ' + name); artifact = matches[0]
            matches = [j for j in jobs if j['name'] == job_name]
            require(len(matches) == 1, 'missing/duplicate job ' + job_name); job = matches[0]
            require(job['head_sha'] == source and job['run_attempt'] == attempt and job['conclusion'] == 'success', 'upstream failed or different source')
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and artifact['workflow_run']['head_sha'] == source, 'artifact identity differs')
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0); data = stream.read()
            require(len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'ZIP bytes/digest differ')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                report = json.loads(archive.read('ae-evidence/result.json'))
            require(report.get('accepted') is True and report['source_sha'] == source and int(report['run_id']) == run_id and int(report['attempt']) == attempt, 'report identity/refusal')
            require(report['granted_platform'] == granted, 'platform grant differs')
            require(report['count'] == len(report['checks']) > 0 and len(set(report['checks'])) == len(report['checks']), 'check list is empty or duplicated')
            require(report['database_unchanged'] is True and report['sdk_changed'] is False and report['schema_changed'] is False
                    and report['import_or_conflict_resolution'] is False and report['performance_claimed'] is False, 'report claims differ')
            require(all(s['name'] in SHARED_SKIPS for s in report['skipped']), 'unexpected skipped case')
            outcomes.append({'cases': {c['id']: c for c in report['cases'] if c['id'].startswith('export-')}, 'digests': report['digests']})
            require(WRITE_FAILURE[granted] in report['checks'], 'platform write-failure check missing')
            require(len(OPTIONS & set(report['checks'])) == 1, 'a platform ran the wrong write-failure check')
            check_sets.append(set(report['checks']) - OPTIONS)
            summary['skipped'][granted] = report['skipped']
            summary['artifacts'].append({k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['jobs'].append({k: job[k] for k in ('id', 'name', 'conclusion')})
            summary['granted_platforms'].append(granted)
        require(len(outcomes) == 3 and all(o['cases'] == outcomes[0]['cases'] and o['digests'] == outcomes[0]['digests'] for o in outcomes), 'platform export outcomes or output digests differ')
        require(all(s == check_sets[0] for s in check_sets), 'platform check lists differ')
        summary['cross_platform_identical_outputs'] = True
        summary['accepted'] = True
    except Exception as error:
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__': main()
