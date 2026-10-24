#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify this run's OCR overlay artifacts inside GitHub Actions.

Downloads each same-run ZIP through the GitHub API, compares its real size and
SHA-256 with the API record, recomputes every digest the summary claims (report,
results table, fixtures, models, consumer binaries) and rejects a missing,
expired, cross-source, cross-attempt or tampered artifact.
"""
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import time
import zipfile

STATUSES = {'PASS', 'FAIL', 'SKIP', 'PENDING'}
ALLOWED_SKIPS = {'windows_host_scope', 'mobile_host_scope', 'model_chi_sim'}


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


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def member(names, suffix):
    found = sorted(name for name in names if name == suffix or name.endswith('/' + suffix))
    return found[0] if len(found) == 1 else None


def main(output):
    repo = os.environ['GITHUB_REPOSITORY']
    run = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']
    source = os.environ['GITHUB_SHA']
    platforms = [item.strip() for item in os.environ.get('J15_PLATFORMS', 'Linux,macOS').split(',') if item.strip()]
    if not platforms:
        raise SystemExit('J15_PLATFORMS declares no platform')
    listed = api(f'repos/{repo}/actions/runs/{run}/artifacts?per_page=100')['artifacts']
    problems, records = [], []
    for system in platforms:
        name = f'reader-ocr-overlay-{system}-{run}-{attempt}'
        found = [artifact for artifact in listed if artifact['name'] == name]
        if len(found) != 1:
            problems.append(f'{name}: expected exactly one artifact, got {len(found)}')
            continue
        artifact = found[0]
        data = api(f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip', binary=True)
        digest = 'sha256:' + sha256(data)
        record = {'name': name, 'id': artifact['id'], 'api_bytes': artifact['size_in_bytes'],
                  'zip_bytes': len(data), 'api_digest': artifact.get('digest'), 'zip_digest': digest,
                  'expired': artifact['expired'], 'head_sha': artifact.get('workflow_run', {}).get('head_sha')}
        if artifact['expired']:
            problems.append(f'{name}: artifact is expired')
        if len(data) != artifact['size_in_bytes']:
            problems.append(f'{name}: downloaded bytes differ from the API size')
        if artifact.get('digest') != digest:
            problems.append(f'{name}: downloaded digest differs from the API digest')
        if str(record['head_sha']) != source:
            problems.append(f'{name}: artifact head SHA differs from this source')
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = archive.namelist()
        summary_name = member(names, 'evidence/summary.json')
        report_name = member(names, 'evidence/report.json')
        results_name = member(names, 'evidence/results.tsv')
        manifest_name = member(names, 'fixtures/manifest.json')
        identity_name = member(names, 'models/identity.json')
        missing = [label for label, value in (('summary', summary_name), ('report', report_name),
                                              ('results', results_name), ('manifest', manifest_name),
                                              ('model identity', identity_name)) if value is None]
        if missing:
            problems.append(f'{name}: missing ' + ', '.join(missing))
            records.append(record)
            continue
        summary = json.loads(archive.read(summary_name))
        report = json.loads(archive.read(report_name))
        results = archive.read(results_name)
        manifest = json.loads(archive.read(manifest_name))
        model_identity = json.loads(archive.read(identity_name))
        record.update({'summary_sha256': sha256(archive.read(summary_name)),
                       'report_sha256': sha256(archive.read(report_name)),
                       'results_sha256': sha256(results),
                       'checks_total': summary.get('checks_total'),
                       'checks_failed': summary.get('checks_failed'),
                       'checks_skipped': summary.get('checks_skipped'),
                       'checks_pending': summary.get('checks_pending'),
                       'accepted': summary.get('accepted'),
                       'model_repository': model_identity.get('repository'),
                       'model_commit': model_identity.get('commit'),
                       'model_license': model_identity.get('license')})
        identity = summary.get('identity') or {}
        if (summary.get('source'), identity.get('GITHUB_SHA'), identity.get('GITHUB_RUN_ID'),
                identity.get('GITHUB_RUN_ATTEMPT')) != (source, source, run, attempt):
            problems.append(f'{name}: summary identity differs from this run')
        if summary.get('report_sha256') != record['report_sha256']:
            problems.append(f'{name}: report digest differs from the summary claim')
        if summary.get('results_sha256') != record['results_sha256']:
            problems.append(f'{name}: results digest differs from the summary claim')
        if summary.get('problems') or summary.get('accepted') is not True:
            problems.append(f'{name}: upstream judgement is not accepted')
        rows, statuses = 0, {}
        for line in results.decode('utf-8').splitlines():
            if not line.strip():
                continue
            columns = line.split('\t')
            if len(columns) != 3:
                problems.append(f'{name}: results row without three columns')
                continue
            rows += 1
            statuses[columns[0]] = columns[1]
            if columns[1] not in STATUSES:
                problems.append(f'{name}: unknown verdict status {columns[1]}')
        if rows != summary.get('checks_total') or statuses != (summary.get('verdict_statuses') or {}):
            problems.append(f'{name}: results table differs from the summary verdicts')
        failing = sorted(key for key, value in statuses.items() if value in ('FAIL', 'PENDING'))
        if failing:
            problems.append(f'{name}: failing or unreached verdicts: ' + ', '.join(failing))
        undeclared = sorted({key for key, value in statuses.items() if value == 'SKIP'} - ALLOWED_SKIPS)
        if undeclared:
            problems.append(f'{name}: undeclared skips: ' + ', '.join(undeclared))
        if (summary.get('checks_failed'), summary.get('checks_pending')) != (0, 0):
            problems.append(f'{name}: counts report failures or pending cases')
        for filename, claim in (summary.get('fixtures') or {}).items():
            location = member(names, 'fixtures/' + filename)
            if not location:
                problems.append(f'{name}: fixture {filename} was not uploaded')
            elif sha256(archive.read(location)) != claim['sha256']:
                problems.append(f'{name}: fixture {filename} digest differs from the summary')
        for key, image in (manifest.get('images') or {}).items():
            claim = (summary.get('fixtures') or {}).get(image.get('path'))
            if not claim or claim['sha256'] != image.get('sha256'):
                problems.append(f'{name}: manifest image {key} is not bound to the uploaded fixture')
        for filename, claim in (summary.get('models') or {}).items():
            location = member(names, 'models/' + filename)
            if not location:
                problems.append(f'{name}: model file {filename} was not uploaded')
            elif sha256(archive.read(location)) != claim['sha256']:
                problems.append(f'{name}: model file {filename} digest differs from the summary')
        for filename, claim in (model_identity.get('files') or {}).items():
            location = member(names, 'models/' + filename)
            if not location or sha256(archive.read(location)) != claim:
                problems.append(f'{name}: model identity for {filename} does not match the uploaded bytes')
        for key, claim in (summary.get('binaries') or {}).items():
            location = member(names, 'binaries/' + pathlib.Path(claim['path']).name)
            if not location:
                problems.append(f'{name}: consumer binary {key} was not uploaded')
            elif sha256(archive.read(location)) != claim['sha256']:
                problems.append(f'{name}: consumer binary {key} digest differs from the summary')
        record['verdicts'] = statuses
        record['lines'] = [line.get('text') for line in (manifest.get('lines') or [])]
        record['binaries'] = summary.get('binaries')
        records.append(record)
    for artifact in listed:
        if artifact['name'].startswith('reader-ocr-overlay-') and artifact['name'].endswith(f'-{run}-{attempt}') and \
                not any(record['name'] == artifact['name'] for record in records) and \
                not artifact['name'].startswith('reader-ocr-overlay-evidence-'):
            problems.append(f'undeclared same-run artifact: {artifact["name"]}')
    if len(records) == 2:
        if records[0]['verdicts'] != records[1]['verdicts']:
            problems.append('the two platforms reported different verdict names or statuses')
        if records[0]['lines'] != records[1]['lines']:
            problems.append('the two platforms generated different fixture text lines')
        if records[0]['model_commit'] != records[1]['model_commit']:
            problems.append('the two platforms used different traineddata commits')
        if records[0]['binaries'] and records[1]['binaries'] and records[0]['binaries']['probe']['sha256'] == records[1]['binaries']['probe']['sha256']:
            problems.append('both platforms uploaded the same probe binary digest')
    if not records:
        problems.append('no platform artifact was verified')
    result = {'id': 'J15', 'component': 'reader_ocr_overlay', 'source': source, 'run_id': run,
              'run_attempt': attempt, 'platforms': platforms, 'artifacts': records,
              'accepted': not problems, 'problems': problems}
    pathlib.Path(output).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(output) / 'artifacts.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
