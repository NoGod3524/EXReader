# SPDX-License-Identifier: MIT
"""Verify this run's jump-history artifacts in Actions.

Downloads each same-run ZIP through the GitHub API, compares its real size and
SHA-256 with the API record, rebinds the summary and report inside it to this
exact source, run and attempt, and checks that the uploaded probe binary is the
one the summary hashed. Nothing here runs on a developer machine.
"""
import hashlib
import copy
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from check_jump_history import REQUIRED

PLATFORMS = ('Linux', 'Windows', 'macOS')
WORKFLOW = '.github/workflows/reader-jump-history.yml'
# The database fingerprints contain the runner's own paths, so only the counts
# and the two verdicts are comparable across runners.
STABLE_NO_WRITE = ('revision_rows', 'outbox_rows', 'sdk_progress_records', 'sdk_notes', 'sdk_fixed_notes',
                   'sdk_epub_notes', 'databases_unchanged', 'control_write_changed')


def authenticate_jobs(metadata, jobs, source, run, attempt):
    if (str(metadata.get('id')), metadata.get('head_sha'), str(metadata.get('run_attempt')),
        metadata.get('path', '').split('@')[0]) != (run, source, attempt, WORKFLOW):
        raise ValueError('run source, attempt or workflow differs')
    expected = {'jump history consumers (' + platform + ')' for platform in PLATFORMS}
    upstream = [job for job in jobs if job.get('name') != 'strict jump-history evidence']
    if len(upstream) != 3 or {job.get('name') for job in upstream} != expected:
        raise ValueError('missing or duplicate platform job')
    for job in upstream:
        if (job.get('head_sha'), str(job.get('run_attempt')), job.get('status'), job.get('conclusion')) != (
                source, attempt, 'completed', 'success'):
            raise ValueError('upstream job failed, unfinished or belongs to another source/attempt')


def authenticate_checks(report, summary):
    checks = report.get('checks', [])
    names = [check.get('name') for check in checks]
    if (not checks or len(names) != len(set(names)) or not set(REQUIRED).issubset(names) or
            any(check.get('pass') is not True for check in checks) or summary.get('checks_total') != len(checks)):
        raise ValueError('raw named checks missing, duplicated, failing or miscounted')


def protocol_selftest():
    metadata = dict(id=7, head_sha='source', run_attempt=1, path=WORKFLOW)
    jobs = [dict(name='jump history consumers (' + platform + ')', head_sha='source',
                 run_attempt=1, status='completed', conclusion='success') for platform in PLATFORMS]
    authenticate_jobs(metadata, jobs, 'source', '7', '1')
    rejected = 0
    for key, value in (('id', 8), ('head_sha', 'foreign'), ('run_attempt', 2), ('path', 'foreign.yml')):
        bad = dict(metadata);bad[key] = value
        try: authenticate_jobs(bad, jobs, 'source', '7', '1')
        except ValueError: rejected += 1
        else: raise AssertionError('accepted foreign ' + key)
    cases = [jobs[:-1], jobs + [jobs[0]]]
    for key, value in (('head_sha', 'foreign'), ('run_attempt', 2), ('status', 'in_progress'),
                       ('conclusion', 'failure'), ('conclusion', 'skipped'), ('name', jobs[1]['name'])):
        bad = copy.deepcopy(jobs);bad[0][key] = value;cases.append(bad)
    for bad in cases:
        try: authenticate_jobs(metadata, bad, 'source', '7', '1')
        except ValueError: rejected += 1
        else: raise AssertionError('accepted invalid upstream jobs')
    report = dict(checks=[dict(name=name, **{'pass': True}) for name in REQUIRED])
    summary = dict(checks_total=len(REQUIRED));authenticate_checks(report, summary)
    cases = [(dict(checks=[]), summary), (report, dict(checks_total=0))]
    bad = copy.deepcopy(report);bad['checks'].append(bad['checks'][0]);cases.append((bad, dict(checks_total=len(bad['checks']))))
    bad = copy.deepcopy(report);bad['checks'].pop();cases.append((bad, dict(checks_total=len(bad['checks']))))
    for value in (False, 'true'):
        bad = copy.deepcopy(report);bad['checks'][0]['pass'] = value;cases.append((bad, summary))
    for bad, counted in cases:
        try: authenticate_checks(bad, counted)
        except ValueError: rejected += 1
        else: raise AssertionError('accepted invalid raw checks')
    print(json.dumps(dict(protocol_negative_cases=rejected, accepted=True)))


def api(path, binary=False):
    for attempt in range(4):
        result = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path], capture_output=True)
        if result.returncode == 0:
            return result.stdout if binary else json.loads(result.stdout)
        message = result.stderr.decode('utf-8', 'replace')
        if attempt == 3 or not any(code in message for code in ('HTTP 500', 'HTTP 502', 'HTTP 503', 'HTTP 504')):
            raise SystemExit('gh api ' + path + ' failed: ' + message)
        time.sleep(10 * (attempt + 1))
    raise SystemExit('unreachable')


def main(output):
    repo, run, attempt, source = (os.environ[k] for k in
                                 ('GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'))
    problems, records = [], []
    metadata = api('repos/' + repo + '/actions/runs/' + run)
    jobs = api('repos/' + repo + '/actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    try: authenticate_jobs(metadata, jobs, source, run, attempt)
    except ValueError as error: problems.append(str(error))
    listed = api('repos/' + repo + '/actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    for platform in PLATFORMS:
        name = 'reader-jump-history-' + platform + '-' + run + '-' + attempt
        found = [a for a in listed if a['name'] == name]
        if len(found) != 1:
            problems.append(name + ': expected one artifact, got ' + str(len(found)))
            continue
        artifact = found[0]
        data = api('repos/' + repo + '/actions/artifacts/' + str(artifact['id']) + '/zip', binary=True)
        digest = 'sha256:' + hashlib.sha256(data).hexdigest()
        record = {'platform': platform, 'name': name, 'id': artifact['id'], 'api_bytes': artifact['size_in_bytes'],
                  'zip_bytes': len(data), 'api_digest': artifact.get('digest'), 'zip_digest': digest,
                  'expired': artifact['expired'], 'workflow_run': artifact.get('workflow_run', {})}
        if artifact['expired'] or len(data) != artifact['size_in_bytes'] or artifact.get('digest') != digest:
            problems.append(name + ': size, digest or expiry mismatch')
        if str(artifact.get('workflow_run', {}).get('head_sha')) != source:
            problems.append(name + ': artifact head SHA differs from this source')
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = set(archive.namelist())
        summary_name = next((n for n in names if n.endswith('jh-evidence/summary.json')), None)
        report_name = next((n for n in names if n.endswith('jh-evidence/report.json')), None)
        binary_name = next((n for n in names if n.endswith('jump-history-probe') or n.endswith('jump-history-probe.exe')), None)
        if not summary_name or not report_name or not binary_name:
            problems.append(name + ': summary, report or probe binary missing')
            records.append(record)
            continue
        summary = json.loads(archive.read(summary_name))
        report_bytes = archive.read(report_name)
        report = json.loads(report_bytes)
        try: authenticate_checks(report, summary)
        except ValueError as error: problems.append(name + ': ' + str(error))
        report_sha = hashlib.sha256(report_bytes).hexdigest()
        probe_sha = hashlib.sha256(archive.read(binary_name)).hexdigest()
        identity = summary.get('identity', {})
        record.update({'summary_sha256': hashlib.sha256(archive.read(summary_name)).hexdigest(),
                       'report_sha256': report_sha, 'identity': identity, 'problems': summary.get('problems'),
                       'accepted': summary.get('jump_history_module_accepted'),
                       'host_wiring_accepted': summary.get('host_wiring_accepted'),
                       'checks_total': summary.get('checks_total'), 'checks_failed': summary.get('checks_failed'),
                       'moves': summary.get('moves'), 'cases_total': summary.get('cases_total'),
                       'no_write': summary.get('no_write'), 'originals': summary.get('originals'),
                       'installed': summary.get('installed'), 'probe_sha256': summary.get('probe_sha256'),
                       'uploaded_probe_sha256': probe_sha, 'case_ids': sorted(c['id'] for c in summary.get('cases', [])),
                       'steps': sorted(s['step'] for s in summary.get('lifecycle', []))})
        if (identity.get('GITHUB_SHA'), identity.get('GITHUB_RUN_ID'), identity.get('GITHUB_RUN_ATTEMPT')) != (source, run, attempt):
            problems.append(name + ': summary identity differs from this run')
        if summary.get('report_sha256') != report_sha:
            problems.append(name + ': report hash differs from the summary')
        if summary.get('probe_sha256') != probe_sha:
            problems.append(name + ': uploaded probe binary is not the one the summary hashed')
        if summary.get('platform') != platform:
            problems.append(name + ': summary platform is ' + repr(summary.get('platform')))
        if summary.get('problems') or summary.get('jump_history_module_accepted') is not True:
            problems.append(name + ': upstream judgement not accepted')
        if summary.get('host_wiring_accepted') is not False:
            problems.append(name + ': host wiring must stay unaccepted')
        if summary.get('checks_failed') != 0 or not summary.get('checks_total'):
            problems.append(name + ': named checks did not all pass')
        no_write = summary.get('no_write') or {}
        if not (no_write.get('databases_unchanged') and no_write.get('control_write_changed')
                and no_write.get('revision_rows') == 0 and no_write.get('sdk_progress_records') == 0):
            problems.append(name + ': the no-write proof is incomplete')
        records.append(record)
    if len(records) == 3:
        for field in ('originals', 'case_ids', 'steps'):
            values = [json.dumps(r.get(field), sort_keys=True) for r in records]
            if len(set(values)) != 1:
                problems.append('the three runners disagree on ' + field)
        verdicts = [json.dumps({key: (r.get('no_write') or {}).get(key) for key in STABLE_NO_WRITE}, sort_keys=True)
                    for r in records]
        if len(set(verdicts)) != 1:
            problems.append('the three runners disagree on the no-write proof')
    else:
        problems.append('only ' + str(len(records)) + ' platform artifacts were authenticated')
    result = {'source': source, 'run_id': run, 'run_attempt': attempt, 'artifacts': records,
              'cases_total': records[0].get('cases_total') if records else None,
              'checks_total': records[0].get('checks_total') if records else None,
              'moves': records[0].get('moves') if records else None,
              'jobs': jobs, 'jump_history_module_accepted': not problems, 'host_wiring_accepted': False, 'problems': problems}
    Path(output).mkdir(parents=True, exist_ok=True)
    (Path(output) / 'jump-history-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    if sys.argv[1:] == ['--protocol-selftest']:
        protocol_selftest()
    else:
        sys.exit(main(sys.argv[1]))
