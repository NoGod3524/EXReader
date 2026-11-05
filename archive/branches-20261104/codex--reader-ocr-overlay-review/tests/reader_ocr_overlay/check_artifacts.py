#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify this run's OCR overlay artifacts inside GitHub Actions.

Authenticates the run (head SHA, attempt) and the completed producer jobs that
own each platform artifact, requires a real future expires_at, downloads each
same-run ZIP through the GitHub API, compares its real size and SHA-256 with the
API record, refuses duplicate/unsafe/oversized ZIP members, recomputes every
digest the summary claims (report, results table, fixtures, models, consumer
binaries) and rejects a missing, expired, cross-source, cross-attempt or
tampered artifact.

`--selftest <dir>` runs deterministic protocol negatives against synthetic
inputs (no network) and must be executed in Actions before the real check.
"""
import datetime
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import time
import warnings
import zipfile

STATUSES = {'PASS', 'FAIL', 'SKIP', 'PENDING'}
ALLOWED_SKIPS = {'windows_host_scope', 'mobile_host_scope', 'model_chi_sim'}
# Bounded unpack: the real artifacts are ~5 MB zipped; these leave wide margin
# while refusing a ZIP bomb or an unbounded member.
MAX_MEMBER_BYTES = 64 << 20
MAX_TOTAL_BYTES = 256 << 20
MAX_MEMBERS = 2000
# Platform -> producer job name and the steps that must have succeeded in it.
PLATFORM_JOBS = {'Linux': 'overlay (ubuntu-24.04)', 'macOS': 'overlay (macos-14)'}
REQUIRED_STEPS = ('Run the installed probe and judge every named verdict',
                  'Preserve fixtures, models, licences, logs, binaries and verdicts')


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


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else None


def check_expiry(name, artifact, now):
    """Reject an expired flag, a missing/malformed expires_at, or one not in the future."""
    problems = []
    if artifact.get('expired') is not False:
        problems.append(f'{name}: artifact is expired')
    stamp = parse_time(artifact.get('expires_at'))
    if stamp is None:
        problems.append(f'{name}: expires_at is missing or malformed')
    elif stamp <= now:
        problems.append(f'{name}: expires_at {artifact.get("expires_at")} is not in the future')
    return problems


def check_run(run_json, run, attempt, source):
    problems = []
    if str(run_json.get('id')) != str(run):
        problems.append('run record id differs from this run')
    if run_json.get('head_sha') != source:
        problems.append('run record head SHA differs from this source')
    if str(run_json.get('run_attempt')) != str(attempt):
        problems.append('run record attempt differs from this attempt')
    return problems


def check_jobs(jobs, platforms, run, attempt, source):
    """Each platform needs exactly one completed, successful producer job of this
    run/attempt/head SHA whose probe and upload steps succeeded."""
    problems = []
    for system in platforms:
        job_name = PLATFORM_JOBS.get(system)
        if job_name is None:
            problems.append(f'{system}: no producer job is declared for this platform')
            continue
        found = [job for job in jobs if job.get('name') == job_name]
        if len(found) != 1:
            problems.append(f'{job_name}: expected exactly one producer job, got {len(found)}')
            continue
        job = found[0]
        if job.get('status') != 'completed' or job.get('conclusion') != 'success':
            problems.append(f'{job_name}: producer job is {job.get("status")}/{job.get("conclusion")}, not completed/success')
        if job.get('head_sha') != source:
            problems.append(f'{job_name}: producer job head SHA differs from this source')
        if str(job.get('run_id')) != str(run):
            problems.append(f'{job_name}: producer job belongs to another run')
        if str(job.get('run_attempt')) != str(attempt):
            problems.append(f'{job_name}: producer job belongs to another attempt')
        steps = {step.get('name'): step.get('conclusion') for step in job.get('steps') or []}
        for step in REQUIRED_STEPS:
            if steps.get(step) != 'success':
                problems.append(f'{job_name}: required step "{step}" did not succeed')
    return problems


def open_zip(data, max_member=MAX_MEMBER_BYTES, max_total=MAX_TOTAL_BYTES, max_members=MAX_MEMBERS):
    """Return (archive, problems). Problems are structural: bad ZIP, duplicate or
    unsafe member names, too many members, oversized member or total, bad CRC."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        return None, [f'not a readable ZIP: {error}']
    problems, infos = [], archive.infolist()
    if len(infos) > max_members:
        problems.append(f'ZIP has {len(infos)} members, above the {max_members} bound')
    seen, total = set(), 0
    for info in infos:
        name = info.filename
        if name in seen:
            problems.append(f'duplicate ZIP member: {name}')
        seen.add(name)
        parts = name.replace('\\', '/').split('/')
        if name.startswith('/') or '\\' in name or '..' in parts or ':' in parts[0]:
            problems.append(f'unsafe ZIP member name: {name}')
        if info.file_size > max_member:
            problems.append(f'ZIP member {name} declares {info.file_size} bytes, above the {max_member} bound')
        total += info.file_size
    if total > max_total:
        problems.append(f'ZIP declares {total} unpacked bytes, above the {max_total} bound')
    if not problems:
        bad = archive.testzip()
        if bad:
            problems.append(f'ZIP member {bad} fails its CRC')
    return archive, problems


class Reader:
    """Bounded, cached member reads: a header that understates its size cannot
    make us unpack more than max_member bytes of a member."""

    def __init__(self, archive, max_member=MAX_MEMBER_BYTES):
        self.archive, self.limit, self.cache = archive, max_member, {}

    def read(self, name):
        if name not in self.cache:
            with self.archive.open(name) as handle:
                data = handle.read(self.limit + 1)
            if len(data) > self.limit:
                raise ValueError(f'member {name} exceeds {self.limit} bytes')
            self.cache[name] = data
        return self.cache[name]


def verify_platform(name, artifact, data, run, attempt, source, now, **bounds):
    """Verify one downloaded platform ZIP. Returns (record, problems)."""
    digest = 'sha256:' + sha256(data)
    record = {'name': name, 'id': artifact.get('id'), 'api_bytes': artifact.get('size_in_bytes'),
              'zip_bytes': len(data), 'api_digest': artifact.get('digest'), 'zip_digest': digest,
              'expired': artifact.get('expired'), 'expires_at': artifact.get('expires_at'),
              'head_sha': (artifact.get('workflow_run') or {}).get('head_sha'),
              'workflow_run_id': (artifact.get('workflow_run') or {}).get('id')}
    problems = check_expiry(name, artifact, now)
    if not data:
        problems.append(f'{name}: artifact ZIP is empty')
    if len(data) != artifact.get('size_in_bytes'):
        problems.append(f'{name}: downloaded bytes differ from the API size')
    if artifact.get('digest') != digest:
        problems.append(f'{name}: downloaded digest differs from the API digest')
    if str(record['head_sha']) != source:
        problems.append(f'{name}: artifact head SHA differs from this source')
    if str(record['workflow_run_id']) != str(run):
        problems.append(f'{name}: artifact belongs to another workflow run')
    archive, structural = open_zip(data, **bounds)
    problems.extend(f'{name}: {item}' for item in structural)
    if archive is None or structural:
        return record, problems
    reader = Reader(archive, bounds.get('max_member', MAX_MEMBER_BYTES))
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
        return record, problems
    try:
        summary = json.loads(reader.read(summary_name))
        results = reader.read(results_name)
        manifest = json.loads(reader.read(manifest_name))
        model_identity = json.loads(reader.read(identity_name))
        report_bytes = reader.read(report_name)
    except (ValueError, UnicodeDecodeError) as error:
        problems.append(f'{name}: unreadable evidence member: {error}')
        return record, problems
    record.update({'summary_sha256': sha256(reader.read(summary_name)),
                   'report_sha256': sha256(report_bytes),
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
            identity.get('GITHUB_RUN_ATTEMPT')) != (source, source, str(run), str(attempt)):
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

    def digest_of(location):
        return sha256(reader.read(location))

    for filename, claim in (summary.get('fixtures') or {}).items():
        location = member(names, 'fixtures/' + filename)
        if not location:
            problems.append(f'{name}: fixture {filename} was not uploaded')
        elif digest_of(location) != claim['sha256']:
            problems.append(f'{name}: fixture {filename} digest differs from the summary')
    for key, image in (manifest.get('images') or {}).items():
        claim = (summary.get('fixtures') or {}).get(image.get('path'))
        if not claim or claim['sha256'] != image.get('sha256'):
            problems.append(f'{name}: manifest image {key} is not bound to the uploaded fixture')
    for filename, claim in (summary.get('models') or {}).items():
        location = member(names, 'models/' + filename)
        if not location:
            problems.append(f'{name}: model file {filename} was not uploaded')
        elif digest_of(location) != claim['sha256']:
            problems.append(f'{name}: model file {filename} digest differs from the summary')
    for filename, claim in (model_identity.get('files') or {}).items():
        location = member(names, 'models/' + filename)
        if not location or digest_of(location) != claim:
            problems.append(f'{name}: model identity for {filename} does not match the uploaded bytes')
    for key, claim in (summary.get('binaries') or {}).items():
        location = member(names, 'binaries/' + pathlib.Path(claim['path']).name)
        if not location:
            problems.append(f'{name}: consumer binary {key} was not uploaded')
        elif digest_of(location) != claim['sha256']:
            problems.append(f'{name}: consumer binary {key} digest differs from the summary')
    record['verdicts'] = statuses
    record['lines'] = [line.get('text') for line in (manifest.get('lines') or [])]
    record['binaries'] = summary.get('binaries')
    return record, problems


def cross_platform(records):
    problems = []
    if len(records) == 2 and all('verdicts' in record for record in records):
        if records[0]['verdicts'] != records[1]['verdicts']:
            problems.append('the two platforms reported different verdict names or statuses')
        if records[0]['lines'] != records[1]['lines']:
            problems.append('the two platforms generated different fixture text lines')
        if records[0]['model_commit'] != records[1]['model_commit']:
            problems.append('the two platforms used different traineddata commits')
        if records[0]['binaries'] and records[1]['binaries'] and records[0]['binaries']['probe']['sha256'] == records[1]['binaries']['probe']['sha256']:
            problems.append('both platforms uploaded the same probe binary digest')
    return problems


def main(output):
    repo = os.environ['GITHUB_REPOSITORY']
    run = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']
    source = os.environ['GITHUB_SHA']
    platforms = [item.strip() for item in os.environ.get('J15_PLATFORMS', 'Linux,macOS').split(',') if item.strip()]
    if not platforms:
        raise SystemExit('J15_PLATFORMS declares no platform')
    now = datetime.datetime.now(datetime.timezone.utc)
    problems = []
    problems += check_run(api(f'repos/{repo}/actions/runs/{run}/attempts/{attempt}'), run, attempt, source)
    jobs_json = api(f'repos/{repo}/actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')
    jobs = jobs_json.get('jobs') or []
    if jobs_json.get('total_count') != len(jobs):
        problems.append('producer job listing is paginated or incomplete')
    problems += check_jobs(jobs, platforms, run, attempt, source)
    listing = api(f'repos/{repo}/actions/runs/{run}/artifacts?per_page=100')
    listed = listing['artifacts']
    if listing.get('total_count') != len(listed):
        problems.append('artifact listing is paginated or incomplete')
    records = []
    for system in platforms:
        name = f'reader-ocr-overlay-{system}-{run}-{attempt}'
        found = [artifact for artifact in listed if artifact['name'] == name]
        if len(found) != 1:
            problems.append(f'{name}: expected exactly one artifact, got {len(found)}')
            continue
        data = api(f'repos/{repo}/actions/artifacts/{found[0]["id"]}/zip', binary=True)
        record, found_problems = verify_platform(name, found[0], data, run, attempt, source, now)
        records.append(record)
        problems += found_problems
    for artifact in listed:
        if artifact['name'].startswith('reader-ocr-overlay-') and artifact['name'].endswith(f'-{run}-{attempt}') and \
                not any(record['name'] == artifact['name'] for record in records) and \
                not artifact['name'].startswith('reader-ocr-overlay-evidence-'):
            problems.append(f'undeclared same-run artifact: {artifact["name"]}')
    problems += cross_platform(records)
    if not records:
        problems.append('no platform artifact was verified')
    result = {'id': 'J15', 'component': 'reader_ocr_overlay', 'source': source, 'run_id': run,
              'run_attempt': attempt, 'platforms': platforms, 'artifacts': records,
              'jobs': [{'name': job.get('name'), 'id': job.get('id'), 'conclusion': job.get('conclusion'),
                        'head_sha': job.get('head_sha'), 'run_attempt': job.get('run_attempt')}
                       for job in jobs if job.get('name') in {PLATFORM_JOBS.get(p) for p in platforms}],
              'accepted': not problems, 'problems': problems}
    pathlib.Path(output).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(output) / 'artifacts.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


# ---------------------------------------------------------------- self-test

SELF_RUN, SELF_ATTEMPT, SELF_SOURCE = '4242', '1', 'a' * 40
SELF_NOW = datetime.datetime(2026, 10, 25, tzinfo=datetime.timezone.utc)


def build_zip(mutate=None, duplicate=None, extra=None):
    """A minimal synthetic artifact that satisfies every real check."""
    files = {
        'fixtures/scan.png': b'png-bytes',
        'models/eng.traineddata': b'model-bytes',
        'binaries/reader-ocr-overlay-probe': b'probe-bytes',
        'binaries/reader-ocr-overlay-c-consumer': b'c-bytes',
    }
    verdicts = [('recognize_page_ok', 'PASS', 'ok'), ('windows_host_scope', 'SKIP', 'scope')]
    results = ''.join('\t'.join(row) + '\n' for row in verdicts).encode()
    report = b'{"report": true}'
    files['models/identity.json'] = json.dumps({
        'repository': 'tesseract-ocr/tessdata_fast', 'commit': 'c' * 40, 'license': 'Apache-2.0',
        'files': {'eng.traineddata': sha256(files['models/eng.traineddata'])}}).encode()
    files['fixtures/manifest.json'] = json.dumps({
        'images': {'scan': {'path': 'scan.png', 'sha256': sha256(files['fixtures/scan.png'])}},
        'lines': [{'text': 'line'}]}).encode()
    summary = {
        'source': SELF_SOURCE, 'accepted': True, 'problems': [],
        'identity': {'GITHUB_SHA': SELF_SOURCE, 'GITHUB_RUN_ID': SELF_RUN, 'GITHUB_RUN_ATTEMPT': SELF_ATTEMPT},
        'checks_total': 2, 'checks_failed': 0, 'checks_skipped': 1, 'checks_pending': 0,
        'verdict_statuses': {'recognize_page_ok': 'PASS', 'windows_host_scope': 'SKIP'},
        'report_sha256': sha256(report), 'results_sha256': sha256(results),
        'fixtures': {'scan.png': {'sha256': sha256(files['fixtures/scan.png'])}},
        'models': {'eng.traineddata': {'sha256': sha256(files['models/eng.traineddata'])}},
        'binaries': {'probe': {'path': 'build/x/reader-ocr-overlay-probe', 'sha256': sha256(files['binaries/reader-ocr-overlay-probe'])},
                     'c_consumer': {'path': 'build/x/reader-ocr-overlay-c-consumer', 'sha256': sha256(files['binaries/reader-ocr-overlay-c-consumer'])}}}
    files['evidence/report.json'] = report
    files['evidence/results.tsv'] = results
    if mutate:
        mutate(files, summary)
    files['evidence/summary.json'] = json.dumps(summary).encode()
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for key, value in files.items():
                archive.writestr(key, value)
            for key, value in (extra or {}).items():
                archive.writestr(key, value)
            if duplicate:
                archive.writestr(duplicate, b'second copy with different bytes')
    return buffer.getvalue()


def synthetic_artifact(data, **override):
    artifact = {'id': 7, 'name': 'reader-ocr-overlay-Linux-4242-1', 'size_in_bytes': len(data),
                'digest': 'sha256:' + sha256(data), 'expired': False, 'expires_at': '2027-01-01T00:00:00Z',
                'workflow_run': {'id': int(SELF_RUN), 'head_sha': SELF_SOURCE}}
    artifact.update(override)
    return artifact


def synthetic_jobs():
    steps = [{'name': step, 'conclusion': 'success'} for step in REQUIRED_STEPS]
    return [{'name': name, 'status': 'completed', 'conclusion': 'success', 'head_sha': SELF_SOURCE,
             'run_id': int(SELF_RUN), 'run_attempt': int(SELF_ATTEMPT), 'steps': [dict(s) for s in steps]}
            for name in PLATFORM_JOBS.values()]


def selftest(output):
    name = 'reader-ocr-overlay-Linux-4242-1'
    cases = []

    def artifact_case(label, expect, data=None, bounds=None, **override):
        data = build_zip() if data is None else data
        _, problems = verify_platform(name, synthetic_artifact(data, **override), data, SELF_RUN, SELF_ATTEMPT,
                                      SELF_SOURCE, SELF_NOW, **(bounds or {}))
        cases.append((label, expect, problems))

    def job_case(label, expect, jobs, platforms=('Linux', 'macOS')):
        cases.append((label, expect, check_jobs(jobs, platforms, SELF_RUN, SELF_ATTEMPT, SELF_SOURCE)))

    def tamper(files, summary):
        files['binaries/reader-ocr-overlay-probe'] = b'tampered'

    artifact_case('positive_artifact_accepted', None)
    job_case('positive_jobs_accepted', None, synthetic_jobs())
    cases.append(('positive_run_accepted', None, check_run(
        {'id': 4242, 'head_sha': SELF_SOURCE, 'run_attempt': 1}, SELF_RUN, SELF_ATTEMPT, SELF_SOURCE)))

    cases.append(('run_wrong_head_sha_rejected', 'run record head SHA', check_run(
        {'id': 4242, 'head_sha': 'b' * 40, 'run_attempt': 1}, SELF_RUN, SELF_ATTEMPT, SELF_SOURCE)))
    cases.append(('run_wrong_attempt_rejected', 'run record attempt', check_run(
        {'id': 4242, 'head_sha': SELF_SOURCE, 'run_attempt': 2}, SELF_RUN, SELF_ATTEMPT, SELF_SOURCE)))

    jobs = synthetic_jobs(); jobs[0]['conclusion'] = 'failure'
    job_case('job_failed_rejected', 'not completed/success', jobs)
    jobs = synthetic_jobs(); jobs[1]['status'] = 'in_progress'; jobs[1]['conclusion'] = None
    job_case('job_incomplete_rejected', 'not completed/success', jobs)
    jobs = synthetic_jobs(); jobs[0]['head_sha'] = 'b' * 40
    job_case('job_wrong_head_sha_rejected', 'producer job head SHA', jobs)
    jobs = synthetic_jobs(); jobs[0]['run_attempt'] = 2
    job_case('job_wrong_attempt_rejected', 'another attempt', jobs)
    jobs = synthetic_jobs(); jobs[1]['run_id'] = 1
    job_case('job_wrong_run_rejected', 'another run', jobs)
    job_case('job_missing_rejected', 'expected exactly one producer job', synthetic_jobs()[:1])
    job_case('job_duplicate_rejected', 'expected exactly one producer job', synthetic_jobs() + synthetic_jobs()[:1])
    jobs = synthetic_jobs(); jobs[0]['steps'][1]['conclusion'] = 'skipped'
    job_case('job_upload_step_unsuccessful_rejected', 'did not succeed', jobs)
    job_case('job_unknown_platform_rejected', 'no producer job is declared', synthetic_jobs(), ('Windows',))

    artifact_case('artifact_flagged_expired_rejected', 'is expired', expired=True)
    artifact_case('artifact_expires_at_past_rejected', 'not in the future', expires_at='2026-10-24T00:00:00Z')
    artifact_case('artifact_expires_at_missing_rejected', 'missing or malformed', expires_at=None)
    artifact_case('artifact_expires_at_malformed_rejected', 'missing or malformed', expires_at='soon')
    artifact_case('artifact_expires_at_naive_rejected', 'missing or malformed', expires_at='2027-01-01T00:00:00')
    artifact_case('artifact_wrong_head_sha_rejected', 'artifact head SHA', workflow_run={'id': int(SELF_RUN), 'head_sha': 'b' * 40})
    artifact_case('artifact_wrong_run_rejected', 'another workflow run', workflow_run={'id': 1, 'head_sha': SELF_SOURCE})
    artifact_case('artifact_digest_mismatch_rejected', 'differs from the API digest', digest='sha256:' + '0' * 64)
    artifact_case('artifact_size_mismatch_rejected', 'differ from the API size', size_in_bytes=1)
    artifact_case('artifact_tampered_binary_rejected', 'consumer binary probe digest', data=build_zip(tamper))
    artifact_case('artifact_duplicate_member_rejected', 'duplicate ZIP member',
                  data=build_zip(duplicate='binaries/reader-ocr-overlay-probe'))
    artifact_case('artifact_duplicate_summary_rejected', 'duplicate ZIP member',
                  data=build_zip(duplicate='evidence/summary.json'))
    artifact_case('artifact_path_traversal_rejected', 'unsafe ZIP member name', data=build_zip(extra={'../escape.txt': b'x'}))
    artifact_case('artifact_absolute_member_rejected', 'unsafe ZIP member name', data=build_zip(extra={'/abs.txt': b'x'}))
    artifact_case('artifact_member_over_bound_rejected', 'above the 1000 bound', bounds={'max_member': 1000},
                  data=build_zip(extra={'binaries/big.bin': b'\0' * 5000}))
    artifact_case('artifact_total_over_bound_rejected', 'unpacked bytes, above the', bounds={'max_total': 100},
                  data=build_zip())
    artifact_case('artifact_member_count_over_bound_rejected', 'above the 3 bound', bounds={'max_members': 3},
                  data=build_zip())
    artifact_case('artifact_not_a_zip_rejected', 'not a readable ZIP', data=b'not a zip at all')
    artifact_case('artifact_empty_rejected', 'artifact ZIP is empty', data=b'')

    def missing_binary(files, summary):
        del files['binaries/reader-ocr-overlay-c-consumer']
    artifact_case('artifact_missing_consumer_rejected', 'consumer binary c_consumer was not uploaded', data=build_zip(missing_binary))

    def wrong_identity(files, summary):
        summary['identity']['GITHUB_RUN_ATTEMPT'] = '2'
    artifact_case('artifact_cross_attempt_summary_rejected', 'summary identity differs', data=build_zip(wrong_identity))

    def tamper_model(files, summary):
        files['models/eng.traineddata'] = b'other-model'
    artifact_case('artifact_tampered_model_rejected', 'model file eng.traineddata digest differs', data=build_zip(tamper_model))

    report, failed = [], []
    for label, expect, problems in cases:
        if expect is None:
            passed = not problems
        else:
            passed = any(expect in problem for problem in problems)
        report.append({'case': label, 'expect': expect or 'accepted', 'result': 'PASS' if passed else 'FAIL',
                       'problems': problems})
        if not passed:
            failed.append(label)
    pathlib.Path(output).mkdir(parents=True, exist_ok=True)
    result = {'selftest': 'j15-artifact-protocol', 'total': len(report), 'failed': failed, 'cases': report}
    (pathlib.Path(output) / 'selftest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    for item in report:
        print(f'SELFTEST {item["case"]}: {item["result"]}')
    print(f'SELFTEST total={len(report)} failed={len(failed)}')
    return 0 if not failed else 1


if __name__ == '__main__':
    if sys.argv[1] == '--selftest':
        sys.exit(selftest(sys.argv[2]))
    sys.exit(main(sys.argv[1]))
