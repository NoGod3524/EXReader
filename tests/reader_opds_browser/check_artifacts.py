#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only strict same-source evidence for the three OPDS consumer jobs.

Every artifact and job must belong to this run, attempt and source; the ZIP digest is
recomputed from the authenticated download; the embedded report must name the same source
and must not over-grant scope; the named case outcomes must agree on all three platforms.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require  # noqa: E402

PLATFORMS = [('linux', 'ubuntu-22.04'), ('windows', 'windows-2022'), ('macos', 'macos-15')]


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    source = os.environ['GITHUB_SHA']
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = {'accepted': False, 'package': 'EXReaderOpdsBrowser 0.1.0', 'source_sha': source,
               'run_id': run_id, 'attempt': attempt, 'artifacts': [], 'jobs': [], 'problems': [],
               'granted_platforms': [], 'macos_accepted': False, 'performance_claimed': False,
               'host_ui_accepted': False, 'sdk_changed': False, 'schema_changed': False}
    try:
        run = fetch('actions/runs/%d' % run_id)
        require(run['head_sha'] == source, 'run source differs')
        require(int(run['run_attempt']) == attempt, 'run attempt differs')
        require(run['path'] == '.github/workflows/reader-opds-browser.yml', 'caller workflow differs')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
        artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
        outcomes = {}
        for platform, runner in PLATFORMS:
            name = 'reader-opds-browser-%s-%d-%d' % (platform, run_id, attempt)
            job_name = 'opds consumers (%s)' % runner
            matches = [a for a in artifacts if a['name'] == name]
            require(len(matches) == 1, 'missing/duplicate artifact ' + name)
            artifact = matches[0]
            matches = [j for j in jobs if j['name'] == job_name]
            require(len(matches) == 1, 'missing/duplicate job ' + job_name)
            job = matches[0]
            require(job['head_sha'] == source and int(job['run_attempt']) == attempt,
                    'job identity differs for ' + job_name)
            require(job['conclusion'] == 'success', 'job failed: ' + job_name)
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0,
                    'artifact expired or empty: ' + name)
            require(artifact['workflow_run']['head_sha'] == source, 'artifact source differs: ' + name)
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact['size_in_bytes'], 'ZIP size differs: ' + name)
            require('sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'],
                    'ZIP digest differs: ' + name)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                report = json.loads(archive.read('opds-evidence/result.json'))
                names = [n for n in archive.namelist()
                         if n.startswith('opds-consumer/') and not n.endswith('/') and
                         Path(n).name in ('opds-consumer', 'opds-consumer.exe',
                                          'opds-import-consumer', 'opds-import-consumer.exe')]
                require(len(names) == 2, 'consumer binaries missing from ' + name)
                embedded = {}
                for entry in names:
                    payload = archive.read(entry)
                    embedded[Path(entry).name] = (len(payload), hashlib.sha256(payload).hexdigest())
                reported = {c['name']: (int(c['bytes']), c['sha256']) for c in report['consumers']}
                require(embedded == reported, 'consumer binaries differ from the report: ' + name)
            require(report.get('accepted') is True, 'report refused: ' + name)
            require(report['source_sha'] == source, 'report source differs: ' + name)
            require(int(report['run_id']) == run_id and int(report['attempt']) == attempt,
                    'report run identity differs: ' + name)
            require(report['platform'] == platform, 'report platform differs: ' + name)
            require(report['sdk_changed'] is False and report['schema_changed'] is False,
                    'report claims frozen tree changes')
            require(int(report['checks']) > 0 and report['cases'], 'report has no cases: ' + name)
            require(report['origin_isolation']['plain_requests_with_authorization'] == 0,
                    'credentials reached the plain origin: ' + name)
            require(report['origin_isolation']['tls_requests'] > 0, 'no TLS request served: ' + name)
            outcomes[platform] = [[c['id'], bool(c['ok'])] for c in report['cases']]
            summary['artifacts'].append({k: artifact[k] for k in
                                         ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['jobs'].append({k: job[k] for k in ('id', 'name', 'conclusion')})
            summary.setdefault('consumers', {})[platform] = sorted(
                [n, size, digest] for n, (size, digest) in embedded.items())
            summary['granted_platforms'].append(platform)
        require(len(outcomes) == 3, 'missing platform outcomes')
        reference = outcomes['linux']
        for platform in ('windows', 'macos'):
            require(outcomes[platform] == reference, 'case outcomes differ on ' + platform)
        require(len(reference) >= 30, 'too few named cases: %d' % len(reference))
        summary['macos_accepted'] = True
        summary['accepted'] = True
        summary['case_count'] = len(reference)
        summary['case_ids'] = [entry[0] for entry in reference]
    except Exception as error:  # noqa: BLE001 - every failure becomes retained evidence
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': summary['accepted'], 'problems': summary['problems']}, ensure_ascii=False))
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__':
    main()
