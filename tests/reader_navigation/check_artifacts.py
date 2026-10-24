# SPDX-License-Identifier: MIT
"""Actions-only strict same-source evidence for the two navigation consumer jobs."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile
from check_navigation import REQUIRED_CHECKS
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id, attempt, source = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA']
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt,
               'artifacts': [], 'jobs': [], 'problems': [], 'granted_platforms': [], 'macos_accepted': False,
               'performance_claimed': False, 'host_ui_accepted': False, 'six_platform_accepted': False,
               'complete_product': False, 'sdk_changed': False, 'schema_changed': False}
    try:
        run = fetch(f'actions/runs/{run_id}')
        require(run['head_sha'] == source and run['run_attempt'] == attempt and run['path'] == '.github/workflows/reader-navigation.yml', 'caller identity differs')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        outcomes = []
        for platform, runner in [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022')]:
            name = f'reader-navigation-{platform}-{run_id}-{attempt}'
            job_name = f'navigation consumers ({runner})'
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
                report = json.loads(archive.read('navigation-evidence/result.json'))
                require(report.get('accepted') is True and report['source_sha'] == source and int(report['run_id']) == run_id and int(report['attempt']) == attempt, 'report identity/refusal')
                require(report['granted_platform'] == platform.lower() and report['macos_accepted'] is False and report['performance_claimed'] is False, 'platform grant differs')
                require(report['checks'] > 0 and len(report['cases']) > 0, 'report is empty')
                probe = json.loads(archive.read('navigation-evidence/probe.json'))
                checks = probe['checks']; names = [c['name'] for c in checks]
                require(probe['failures'] == 0 and report['checks'] == len(checks) and all(c['pass'] is True for c in checks), 'raw probe checks failed or differ')
                require(len(names) == len(set(names)) and set(REQUIRED_CHECKS) <= set(names), 'required probe checks missing or duplicated')
                require(probe['cases'] == report['cases'], 'raw navigation outcomes differ')
                suffix = '.exe' if platform == 'Windows' else ''
                for file, field in [('navigation-probe', 'probe_sha256'), ('navigation-c-consumer', 'c_consumer_sha256')]:
                    require(hashlib.sha256(archive.read('navigation-consumer/' + file + suffix)).hexdigest() == report[field], 'actual installed consumer differs')
                for installed in report['installed_files']:
                    contents = archive.read('navigation-stage/' + installed['path'])
                    require(len(contents) == installed['bytes'] and hashlib.sha256(contents).hexdigest() == installed['sha256'], 'actual installed package differs')
                outcomes.append([{k: c[k] for k in ('id', 'rows', 'roots', 'depth_levels', 'text_bytes', 'ok', 'part_only', 'needs_host', 'unresolved', 'range', 'ambiguous', 'other', 'mislocated', 'digest')} for c in report['cases']])
            summary['artifacts'].append({k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['jobs'].append({k: job[k] for k in ('id', 'name', 'conclusion')})
            summary['granted_platforms'].append(platform.lower())
        require(len(outcomes) == 2 and outcomes[0] == outcomes[1], 'platform navigation outcomes differ')
        summary['accepted'] = True
    except Exception as error:
        summary['problems'].append(str(error))
        summary['granted_platforms'] = []
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__': main()
