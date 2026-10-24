# SPDX-License-Identifier: MIT
"""Verify this run's annotation-view artifacts in Actions.

Downloads each same-run ZIP through the GitHub API, compares its real size and
SHA-256 with the API record, and binds the summary it contains to this exact
source, run and attempt. Nothing here runs on a developer machine.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

PLATFORMS = ('Linux', 'Windows', 'macOS')


def api(path, binary=False):
    for attempt in range(4):
        result = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path], capture_output=True)
        if result.returncode == 0:
            return result.stdout if binary else json.loads(result.stdout)
        message = result.stderr.decode('utf-8', 'replace')
        if attempt == 3 or not any(code in message for code in ('HTTP 500', 'HTTP 502', 'HTTP 503', 'HTTP 504')):
            raise SystemExit(f'gh api {path} failed: {message}')
        time.sleep(10 * (attempt + 1))
    raise SystemExit('unreachable')


def main(output):
    repo, run, attempt, source = (os.environ[k] for k in ('GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'))
    listed = api(f'repos/{repo}/actions/runs/{run}/artifacts?per_page=100')['artifacts']
    problems, records = [], []
    for system in PLATFORMS:
        name = f'reader-annotation-view-{system}-{run}-{attempt}'
        found = [a for a in listed if a['name'] == name]
        if len(found) != 1:
            problems.append(f'{name}: expected one artifact, got {len(found)}')
            continue
        artifact = found[0]
        data = api(f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip', binary=True)
        digest = 'sha256:' + hashlib.sha256(data).hexdigest()
        record = {'name': name, 'id': artifact['id'], 'api_bytes': artifact['size_in_bytes'], 'zip_bytes': len(data),
                  'api_digest': artifact.get('digest'), 'zip_digest': digest, 'expired': artifact['expired'],
                  'expires_at': artifact.get('expires_at'), 'workflow_run': artifact.get('workflow_run', {})}
        if artifact['expired'] or len(data) != artifact['size_in_bytes'] or artifact.get('digest') != digest or not len(data):
            problems.append(f'{name}: size/digest/expiry mismatch')
        if str(artifact.get('workflow_run', {}).get('head_sha')) != source:
            problems.append(f'{name}: artifact head SHA differs from this source')
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = set(archive.namelist())
        summary_name = next((n for n in names if n.endswith('av-evidence/summary.json')), None)
        report_name = next((n for n in names if n.endswith('av-evidence/work/report.json')), None)
        if not summary_name or not report_name:
            problems.append(f'{name}: summary/report missing')
        else:
            summary = json.loads(archive.read(summary_name))
            identity = summary.get('identity', {})
            record.update({'summary_sha256': hashlib.sha256(archive.read(summary_name)).hexdigest(),
                           'report_sha256': hashlib.sha256(archive.read(report_name)).hexdigest(), 'identity': identity,
                           'problems': summary.get('problems'), 'checks_total': summary.get('checks_total'),
                           'checks_failed': summary.get('checks_failed'), 'book_a_final': summary.get('book_a_final'),
                           'c_consumer': summary.get('c_consumer'), 'probe_sha256': summary.get('probe_sha256'),
                           'c_consumer_sha256': summary.get('c_consumer_sha256')})
            if (identity.get('GITHUB_SHA'), identity.get('GITHUB_RUN_ID'), identity.get('GITHUB_RUN_ATTEMPT')) != (source, run, attempt):
                problems.append(f'{name}: summary identity differs from this run')
            if identity.get('RUNNER_OS') != system:
                problems.append(f'{name}: summary platform differs')
            if summary.get('report_sha256') != record['report_sha256']:
                problems.append(f'{name}: report hash differs from summary')
            if summary.get('problems') or summary.get('annotation_view_accepted_on_this_platform') is not True or summary.get('checks_failed') != 0:
                problems.append(f'{name}: platform judgement not accepted')
        records.append(record)
    totals = {r.get('checks_total') for r in records}
    if len(records) == len(PLATFORMS) and len(totals) != 1:
        problems.append('platforms ran different check counts')
    result = {'source': source, 'run_id': run, 'run_attempt': attempt, 'artifacts': records, 'problems': problems,
              'three_desktop_platforms_accepted': not problems and len(records) == len(PLATFORMS)}
    Path(output).mkdir(parents=True, exist_ok=True)
    (Path(output) / 'annotation-view-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
