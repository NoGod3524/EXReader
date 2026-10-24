# SPDX-License-Identifier: MIT
"""Verify this run's reading-commands artifacts in Actions.

Downloads each same-run ZIP through the GitHub API, compares its real size and
SHA-256 with the API record and the upload step log, and binds the summary and
report it contains to this exact source, run and attempt. Never runs locally.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

SYSTEMS = {'Linux': 'ubuntu-22.04', 'Windows': 'windows-2022', 'macOS': 'macos-15'}


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
    jobs = api(f'repos/{repo}/actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    problems, records = [], []
    for system, runner in SYSTEMS.items():
        name = f'reader-reading-commands-{system}-{run}-{attempt}'
        found = [a for a in listed if a['name'] == name]
        if len(found) != 1:
            problems.append(f'{name}: expected one artifact, got {len(found)}')
            continue
        artifact = found[0]
        data = api(f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip', binary=True)
        digest = hashlib.sha256(data).hexdigest()
        record = {'name': name, 'id': artifact['id'], 'api_bytes': artifact['size_in_bytes'], 'zip_bytes': len(data),
                  'api_digest': artifact.get('digest'), 'zip_digest': 'sha256:' + digest, 'expired': artifact['expired'],
                  'expires_at': artifact.get('expires_at'), 'workflow_run': artifact.get('workflow_run', {})}
        if artifact['expired'] or not len(data) or len(data) != artifact['size_in_bytes'] or artifact.get('digest') != 'sha256:' + digest:
            problems.append(f'{name}: size/digest/expiry mismatch')
        if str(artifact.get('workflow_run', {}).get('head_sha')) != source:
            problems.append(f'{name}: artifact head SHA differs from this source')
        job = [j for j in jobs if j['name'] == f'reading commands ({runner})']
        if len(job) != 1:
            problems.append(f'{name}: expected one job for {runner}, got {len(job)}')
        else:
            record['job'] = {'id': job[0]['id'], 'conclusion': job[0]['conclusion'], 'run_attempt': job[0].get('run_attempt')}
            log = subprocess.run(['gh', 'api', f'repos/{repo}/actions/jobs/{job[0]["id"]}/logs'], capture_output=True)
            text = log.stdout.decode('utf-8', 'replace')
            logged = re.findall(r'SHA256 digest of uploaded artifact zip is ([0-9a-f]{64})', text)
            ids = re.findall(r'Artifact ID is (\d+)', text) or re.findall(r'Artifact ID (\d+)', text)
            sizes = re.findall(r'Final size is (\d+) bytes', text)
            record['upload_log'] = {'digests': logged, 'ids': ids, 'sizes': sizes}
            if log.returncode != 0 or logged[-1:] != [digest] or ids[-1:] != [str(artifact['id'])] or sizes[-1:] != [str(len(data))]:
                problems.append(f'{name}: upload log differs from the downloaded ZIP')
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = set(archive.namelist())
        summary_name = next((n for n in names if n.endswith('rc-evidence/summary.json')), None)
        report_name = next((n for n in names if n.endswith('rc-evidence/report.json')), None)
        if not summary_name or not report_name:
            problems.append(f'{name}: summary/report missing')
        else:
            summary = json.loads(archive.read(summary_name))
            report_sha = hashlib.sha256(archive.read(report_name)).hexdigest()
            identity = summary.get('identity', {})
            record.update({'summary_sha256': hashlib.sha256(archive.read(summary_name)).hexdigest(), 'report_sha256': report_sha,
                           'identity': identity, 'problems': summary.get('problems'), 'reading_commands_accepted': summary.get('reading_commands_accepted'),
                           'host_integration_accepted': summary.get('host_integration_accepted'),
                           'checks_total': summary.get('checks_total'), 'checks_failed': summary.get('checks_failed'),
                           'cases': len(summary.get('cases', [])), 'race_rounds': len(summary.get('races', [])),
                           'originals': summary.get('originals'), 'sqlite': summary.get('sqlite'), 'module_versions': summary.get('module_versions')})
            if (identity.get('GITHUB_SHA'), identity.get('GITHUB_RUN_ID'), identity.get('GITHUB_RUN_ATTEMPT')) != (source, run, attempt):
                problems.append(f'{name}: summary identity differs from this run')
            if summary.get('report_sha256') != report_sha:
                problems.append(f'{name}: report hash differs from summary')
            if summary.get('problems') or summary.get('reading_commands_accepted') is not True or summary.get('host_integration_accepted') is not False:
                problems.append(f'{name}: upstream judgement not accepted')
        records.append(record)
    originals = [r.get('originals') for r in records if r.get('originals')]
    if len(originals) != len(SYSTEMS) or any(o != originals[0] for o in originals):
        problems.append('the three systems did not generate identical original bytes')
    result = {'source': source, 'run_id': run, 'run_attempt': attempt, 'artifacts': records, 'problems': problems,
              'reading_commands_accepted': not problems, 'host_integration_accepted': False}
    Path(output).mkdir(parents=True, exist_ok=True)
    (Path(output) / 'reading-commands-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
