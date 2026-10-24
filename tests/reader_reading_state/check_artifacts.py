# SPDX-License-Identifier: MIT
"""Verify this run's reading-state artifacts in Actions.

Downloads each same-run ZIP through the GitHub API, compares its real size and
SHA-256 with the API record, and binds the summary and report it contains to
this exact source, run and attempt. Nothing here runs on a developer machine.
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
    for system in ('Linux', 'Windows'):
        name = f'reader-reading-state-{system}-{run}-{attempt}'
        found = [a for a in listed if a['name'] == name]
        if len(found) != 1:
            problems.append(f'{name}: expected one artifact, got {len(found)}')
            continue
        artifact = found[0]
        data = api(f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip', binary=True)
        digest = 'sha256:' + hashlib.sha256(data).hexdigest()
        record = {'name': name, 'id': artifact['id'], 'api_bytes': artifact['size_in_bytes'], 'zip_bytes': len(data),
                  'api_digest': artifact.get('digest'), 'zip_digest': digest, 'expired': artifact['expired'],
                  'workflow_run': artifact.get('workflow_run', {})}
        if artifact['expired'] or len(data) != artifact['size_in_bytes'] or artifact.get('digest') != digest:
            problems.append(f'{name}: size/digest/expiry mismatch')
        if str(artifact.get('workflow_run', {}).get('head_sha')) != source:
            problems.append(f'{name}: artifact head SHA differs from this source')
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = set(archive.namelist())
        summary_name = next((n for n in names if n.endswith('rs-evidence/summary.json')), None)
        report_name = next((n for n in names if n.endswith('rs-evidence/report.json')), None)
        if not summary_name or not report_name:
            problems.append(f'{name}: summary/report missing')
        else:
            summary = json.loads(archive.read(summary_name))
            report_sha = hashlib.sha256(archive.read(report_name)).hexdigest()
            identity = summary.get('identity', {})
            record.update({'summary_sha256': hashlib.sha256(archive.read(summary_name)).hexdigest(), 'report_sha256': report_sha,
                           'identity': identity, 'problems': summary.get('problems'),
                           'v1_highlight_roundtrip_accepted': summary.get('v1_highlight_roundtrip_accepted'),
                           'reading_state_sync_complete': summary.get('reading_state_sync_complete'),
                           'checks_total': summary.get('checks_total'), 'checks_failed': summary.get('checks_failed'),
                           'receiver_found': summary.get('receiver_found'), 'receiver_mislocated': summary.get('receiver_mislocated'),
                           'unresolved_writes': summary.get('unresolved_writes'), 'revisions_exchanged': summary.get('revisions_exchanged'),
                           'originals': summary.get('originals'), 'sdk_ids': summary.get('sdk_ids'), 'sqlite': summary.get('sqlite')})
            if (identity.get('GITHUB_SHA'), identity.get('GITHUB_RUN_ID'), identity.get('GITHUB_RUN_ATTEMPT')) != (source, run, attempt):
                problems.append(f'{name}: summary identity differs from this run')
            if summary.get('report_sha256') != report_sha:
                problems.append(f'{name}: report hash differs from summary')
            if summary.get('problems') or summary.get('v1_highlight_roundtrip_accepted') is not True or summary.get('reading_state_sync_complete') is not False:
                problems.append(f'{name}: upstream judgement not accepted')
        records.append(record)
    originals = [r.get('originals') for r in records if r.get('originals')]
    if len(originals) == 2 and originals[0] != originals[1]:
        problems.append('Linux and Windows generated different original bytes')
    result = {'source': source, 'run_id': run, 'run_attempt': attempt, 'artifacts': records, 'problems': problems,
              'v1_highlight_roundtrip_accepted': not problems, 'reading_state_sync_complete': False}
    Path(output).mkdir(parents=True, exist_ok=True)
    (Path(output) / 'reading-state-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
