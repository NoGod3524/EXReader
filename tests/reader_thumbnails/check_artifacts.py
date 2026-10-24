# SPDX-License-Identifier: MIT
"""Actions-only strict same-source evidence for the three thumbnail consumer jobs."""
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

PLATFORMS = [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022'), ('macOS', 'macos-15')]


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id, attempt, source = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA']
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt,
               'artifacts': [], 'jobs': [], 'problems': [], 'granted_platforms': [], 'measurements': {},
               'performance_claimed': False, 'host_ui_accepted': False, 'six_platform_accepted': False,
               'complete_product': False, 'sdk_changed': False, 'schema_changed': False}
    try:
        run = fetch(f'actions/runs/{run_id}')
        require(run['head_sha'] == source and run['run_attempt'] == attempt and run['path'] == '.github/workflows/reader-thumbnails.yml', 'caller identity differs')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        names = []
        for platform, runner in PLATFORMS:
            name = f'reader-thumbnails-{platform}-{run_id}-{attempt}'
            job_name = f'thumbnail consumers ({runner})'
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
                report = json.loads(archive.read('thumbnail-evidence/result.json'))
            require(report.get('accepted') is True and report['source_sha'] == source and int(report['run_id']) == run_id and int(report['attempt']) == attempt, 'report identity/refusal')
            require(report['granted_platform'] == platform.lower() and report['performance_claimed'] is False and report['six_platform_accepted'] is False, 'platform grant differs')
            require(report['checks'] > 0 and len(report['check_names']) == report['checks'], 'report is empty')
            names.append((platform, sorted(report['check_names'])))
            summary['measurements'][platform] = report['measurements']
            summary['artifacts'].append({k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['jobs'].append({k: job[k] for k in ('id', 'name', 'conclusion')})
            summary['granted_platforms'].append(platform.lower())
        # The deterministic suite names must agree everywhere; the Windows thread check
        # is the one named difference (thread count is not measured there).
        def comparable(values):
            return [n for n in values if not n.startswith('threads:')]
        base = comparable(names[0][1])
        for platform, values in names[1:]:
            require(comparable(values) == base, 'check names differ on ' + platform)
        summary['accepted'] = True
    except Exception as error:
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8'); print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__': main()
