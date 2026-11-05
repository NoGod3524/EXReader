#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run artifact summary for reader-library-health.yml (Actions only)."""
import hashlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require  # noqa: E402
from check_health import REQUIRED_ADVERSARIAL_CHECKS

PLATFORMS = (
    ('Linux', 'ubuntu-22.04'),
    ('Windows', 'windows-2022'),
    ('macOS', 'macos-15'),
)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    source = os.environ['GITHUB_SHA']
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        'accepted': False,
        'source_sha': source,
        'run_id': run_id,
        'attempt': attempt,
        'workflow': '.github/workflows/reader-library-health.yml',
        'artifacts': [],
        'jobs': [],
        'granted_platforms': [],
        'problems': [],
        'complete_product': False,
        'host_wired': False,
        'performance_claimed': False,
        'repair_performed': False,
    }
    try:
        run = fetch('actions/runs/%d' % run_id)
        require(run['head_sha'] == source and run['run_attempt'] == attempt and
                run['path'] == '.github/workflows/reader-library-health.yml',
                'caller identity differs')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
        artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
        outcomes = []
        for platform, runner in PLATFORMS:
            name = 'reader-library-health-%s-%d-%d' % (platform, run_id, attempt)
            job_name = 'library health consumers (%s)' % runner
            matches = [a for a in artifacts if a['name'] == name]
            require(len(matches) == 1, 'missing/duplicate artifact ' + name)
            artifact = matches[0]
            job_matches = [j for j in jobs if j['name'] == job_name]
            require(len(job_matches) == 1, 'missing/duplicate job ' + job_name)
            job = job_matches[0]
            require(job['head_sha'] == source and job['run_attempt'] == attempt and
                    job['conclusion'] == 'success', 'upstream failed or different source')
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and
                    artifact['workflow_run']['head_sha'] == source and
                    artifact['workflow_run']['id'] == run_id,
                    'artifact identity differs')
            require(isinstance(artifact.get('expires_at'), str) and artifact['expires_at'],
                    'artifact has no validity window')
            require(datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
                    'artifact validity window ended')
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact['size_in_bytes'] and
                    'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'],
                    'ZIP bytes/digest differ')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate ZIP member')
                names = [entry for entry in archive.namelist()
                         if entry.endswith('lh-evidence/result.json')]
                require(len(names) == 1, 'result.json missing or duplicated in ' + name)
                report = json.loads(archive.read(names[0]))
                raw_names = [entry for entry in archive.namelist() if entry.endswith('lh-work/ev/adversarial.json')]
                require(len(raw_names) == 1, 'raw adversarial report missing or duplicated')
                raw = json.loads(archive.read(raw_names[0]))
                checks = raw.get('checks', [])
                require(len(checks) == len({c['id'] for c in checks}) and
                        set(REQUIRED_ADVERSARIAL_CHECKS) <= {c['id'] for c in checks} and
                        all(c.get('passed') is True for c in checks), 'raw cancellation/reentry outcomes incomplete')
                for key, binary in (('probe', 'library-health-probe'), ('cpp_consumer', 'library-health-cpp-consumer')):
                    suffix = 'lh-consumer/' + binary + ('.exe' if platform == 'Windows' else '')
                    matches = [entry for entry in archive.namelist() if entry.endswith(suffix)]
                    require(len(matches) == 1, 'actual installed consumer missing or duplicated')
                    executable = archive.read(matches[0])
                    require(report['identity']['executables'][key] ==
                            {'bytes': len(executable), 'sha256': hashlib.sha256(executable).hexdigest()},
                            'actual installed consumer differs from report')
            require(report.get('accepted') is True, 'platform report is not accepted')
            require(report.get('source_sha') == source and int(report.get('run_id', 0)) == run_id
                    and int(report.get('attempt', 0)) == attempt, 'report identity differs')
            require(report.get('granted_platform') == platform.lower(), 'platform grant differs')
            require(report.get('complete_product') is False and report.get('host_wired') is False
                    and report.get('performance_claimed') is False and
                    report.get('repair_performed') is False, 'scope flags differ')
            rows = report.get('rows', {})
            require(rows.get('count') == 2202 and
                    re_fullmatch(rows.get('digest', '')) and
                    bool(rows.get('verdicts')), 'row summary is incomplete')
            require(all(check.get('passed') for check in report.get('checks', [])),
                    'a named check failed in ' + name)
            outcomes.append({'digest': rows['digest'], 'verdicts': rows['verdicts'],
                             'count': rows['count']})
            summary['artifacts'].append({key: artifact[key] for key in
                                         ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['jobs'].append({key: job[key] for key in ('id', 'name', 'conclusion')})
            summary['granted_platforms'].append(platform.lower())
        require(len(outcomes) == 3 and outcomes[0] == outcomes[1] == outcomes[2],
                'platform row outcomes differ')
        summary['rows'] = outcomes[0]
        summary['accepted'] = True
    except Exception as error:  # noqa: BLE001 - every failure is retained as evidence
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n',
                                     encoding='utf-8')
    print(json.dumps(summary, sort_keys=True))
    raise SystemExit(0 if summary['accepted'] else 1)


def re_fullmatch(value):
    return isinstance(value, str) and len(value) == 64 and all(
        character in '0123456789abcdef' for character in value)


if __name__ == '__main__':
    main()
