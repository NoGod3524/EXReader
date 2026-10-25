# SPDX-License-Identifier: MIT
"""Authenticate this run's S16 artifacts in Actions.

Downloads each same-run ZIP through the GitHub API, compares its real size and
SHA-256 with the API record, rebinds every summary inside it to this exact
source, run and attempt, checks that the uploaded probe is the binary the
summary hashed, and requires the two runners to agree on originals, stored-wire
cases, lifecycle steps and both no-write verdicts. Nothing here runs on a
developer machine.
"""
import copy
import difflib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_raw import REQUIRED, SEMANTICS, STABLE_NO_WRITE
from run import original_projection


def json_load(data):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


def complete_bindings(archive, result, platform, overrides=None):
    """Recompute default compatibility and all executable/archive bindings."""
    def get(path):
        return (overrides or {}).get(path, archive.read(entry(archive, path)))
    def need(ok, message):
        if not ok:
            raise ValueError(message)
    suffix = '.exe' if platform == 'Windows' else ''
    expected = {
        'raw_probe': 'build/raw-consumer/s16-raw-probe',
        'raw_c_consumer': 'build/raw-consumer/s16-c-consumer',
        'default_c_consumer': 'build/default-consumer/s16-c-consumer',
        'original_probe': 'build/original-default-consumer/jump-history-probe',
        'original_c_consumer': 'build/original-default-consumer/jump-history-c-consumer',
        'baseline_probe': 'build/original-baseline-consumer/jump-history-probe',
        'baseline_c_consumer': 'build/original-baseline-consumer/jump-history-c-consumer',
        'original_raw_probe': 'build/original-raw-consumer/jump-history-probe',
        'original_raw_c_consumer': 'build/original-raw-consumer/jump-history-c-consumer',
    }
    need(set(result['programs']) == set(expected), 'exact nine native program roles')
    binaries = {}
    for role, stem in expected.items():
        record = result['programs'][role]
        path = stem + suffix
        data = get(path)
        need(record.get('member') == path and record.get('bytes') == len(data) > 0 and
             record.get('sha256') == hashlib.sha256(data).hexdigest(), 'actual program binding: ' + role)
        need(data.startswith(b'MZ' if platform == 'Windows' else b'\x7fELF'), 'native executable: ' + role)
        binaries[role] = record
    summaries = {}
    archives = {}
    headers = {}
    context = {key: os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')}
    need((result.get('source_sha'), str(result.get('run_id')), str(result.get('run_attempt')), result.get('platform')) ==
         (context['GITHUB_SHA'], context['GITHUB_RUN_ID'], context['GITHUB_RUN_ATTEMPT'], platform),
         'complete producer result identity')
    for family, stage, probe, consumer in (
            ('original-baseline', 'baseline', 'baseline_probe', 'baseline_c_consumer'),
            ('original-default', 'default', 'original_probe', 'original_c_consumer'),
            ('original-raw', 'raw', 'original_raw_probe', 'original_raw_c_consumer')):
        summary = json_load(get('evidence/' + family + '/summary.json'))
        report_bytes = get('evidence/' + family + '/report.json')
        report = json_load(report_bytes)
        checks = report['checks']
        names = [check['name'] for check in checks]
        need(all(summary['identity'].get(key) == value for key, value in context.items()) and
             summary.get('platform') == platform, 'original suite full identity: ' + family)
        need(summary.get('jump_history_module_accepted') is True and not summary.get('problems') and
             summary.get('checks_failed') == 0 and summary.get('checks_total') == len(checks) >= 149 and
             len(names) == len(set(names)) and all(check.get('pass') is True for check in checks),
             'complete original suite: ' + family)
        need(summary.get('report_sha256') == hashlib.sha256(report_bytes).hexdigest() and
             summary.get('probe_sha256') == binaries[probe]['sha256'] and
             summary.get('c_consumer_sha256') == binaries[consumer]['sha256'], 'suite program/report: ' + family)
        for key in ('cases', 'lifecycle', 'books', 'moves', 'sdk_version', 'parser_version',
                    'jump_history_version', 'reading_state_version', 'revisions_version'):
            need(summary.get(key) == report.get(key), 'suite projection differs from actual report: ' + key)
        header = get('families/' + stage + '-stage/include/reader_jump_history.h')
        library = 'reader_jump_history.lib' if platform == 'Windows' else 'libreader_jump_history.a'
        data = get('families/' + stage + '-stage/lib/' + library)
        need(data.startswith(b'!<arch>\n') and summary['installed']['library_sha256'] == hashlib.sha256(data).hexdigest()
             and summary['installed']['header_sha256'] == hashlib.sha256(header).hexdigest(),
             'actual installed header/archive: ' + stage)
        headers[stage], archives[stage], summaries[stage] = header, data, summary
    need(original_projection(summaries['baseline']) == original_projection(summaries['default']),
         'recomputed baseline/default equivalence')
    need(headers['default'] == headers['raw'], 'same capability-guarded installed header')
    before, after = (headers[key].decode('utf-8').splitlines() for key in ('baseline', 'default'))
    inserted = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes():
        need(tag in ('equal', 'insert'), 'baseline header line modified')
        if tag == 'insert':
            inserted.extend(after[j1:j2])
    need(0 < len(inserted) <= 70 and 'EXR_READER_SELECTOR_BYTES_CANDIDATE' in '\n'.join(inserted),
         'bounded guarded pure header insertions')
    for symbol in (b'reader_jh_commit_fixed_v3', b'reader_jh_commit_wire_raw_v3', b'reader_rs_decode_raw_v3'):
        need(symbol not in archives['default'] and symbol in archives['raw'], 'actual archive capability symbols')
    return {'program_roles': sorted(binaries), 'default_equals_baseline_recomputed': True,
            'default_archive_no_raw_symbols_recomputed': True, 'original_suites': 3}

PLATFORMS = ('Linux', 'Windows')
WORKFLOW = '.github/workflows/reader-next-s16.yml'
JOB_PREFIX = 'S16 consumers ('
CASE_FIELDS = ('id', 'book', 'mode', 'kind', 'outcome', 'stored_wire_bytes', 'accounted_bytes', 'book_key',
               'anchor_version', 'start', 'end', 'exact_bytes', 'prefix_bytes', 'suffix_bytes', 'part',
               'part_path', 'page', 'page_id')


def job_problems(metadata, jobs, source, run, attempt):
    problems = []
    if (str(metadata.get('id')), metadata.get('head_sha'), str(metadata.get('run_attempt')),
            (metadata.get('path') or '').split('@')[0]) != (run, source, attempt, WORKFLOW):
        problems.append('run source, attempt or workflow differs')
    expected = {JOB_PREFIX + platform + ')' for platform in PLATFORMS}
    upstream = [job for job in jobs if job.get('name') != 'strict S16 evidence']
    if len(upstream) != len(PLATFORMS) or {job.get('name') for job in upstream} != expected:
        problems.append('missing or duplicate platform job')
    for job in upstream:
        if (job.get('head_sha'), str(job.get('run_attempt')), job.get('status'), job.get('conclusion')) != (
                source, attempt, 'completed', 'success'):
            problems.append('upstream job failed, unfinished or belongs to another source/attempt')
    return problems


def check_problems(report, summary):
    problems = []
    checks = report.get('checks', [])
    names = [check.get('name') for check in checks]
    if not checks or len(names) != len(set(names)):
        problems.append('raw named checks are missing or duplicated')
    if not set(REQUIRED).issubset(names):
        problems.append('required raw checks missing: ' + repr(sorted(set(REQUIRED) - set(names))))
    if any(check.get('pass') is not True for check in checks):
        problems.append('a raw named check is not a literal true')
    if summary.get('probe_checks_total') != len(checks):
        problems.append('the summary probe check count differs from the raw checks')
    if summary.get('checks_failed') != 0:
        problems.append('the summary reports failed checks')
    if summary.get('accepted') is not True or summary.get('problems'):
        problems.append('the raw judgement is not accepted')
    if summary.get('host_wiring_accepted') is not False or summary.get('gui_accepted') is not False:
        problems.append('the raw summary must not accept host wiring or a GUI')
    return problems


def binding_problems(record, summary, report_bytes, probe_bytes):
    problems = []
    if record.get('expired'):
        problems.append('the artifact is expired')
    if record.get('zip_bytes') != record.get('api_bytes'):
        problems.append('the downloaded size differs from the API record')
    if record.get('api_digest') != record.get('zip_digest'):
        problems.append('the downloaded digest differs from the API record')
    identity = summary.get('identity', {})
    if (identity.get('GITHUB_SHA'), identity.get('GITHUB_RUN_ID'), identity.get('GITHUB_RUN_ATTEMPT')) != (
            os.environ.get('GITHUB_SHA'), os.environ.get('GITHUB_RUN_ID'), os.environ.get('GITHUB_RUN_ATTEMPT')):
        problems.append('the summary identity differs from this run')
    if summary.get('platform') != record.get('platform'):
        problems.append('the summary platform is ' + repr(summary.get('platform')))
    if summary.get('report_sha256') != hashlib.sha256(report_bytes).hexdigest():
        problems.append('the report hash differs from the summary')
    if summary.get('probe_sha256') != hashlib.sha256(probe_bytes).hexdigest():
        problems.append('the uploaded probe is not the binary the summary hashed')
    no_write = summary.get('no_write') or {}
    if no_write.get('databases_unchanged') is not True or no_write.get('control_write_changed') is not True:
        problems.append('the no-write measurement is not sensitive or the databases changed')
    for key in ('revision_rows', 'outbox_rows', 'raw_revision_rows', 'raw_outbox_rows', 'sdk_progress_records',
                'sdk_notes', 'sdk_fixed_notes', 'sdk_epub_notes'):
        if no_write.get(key) != 0:
            problems.append('the no-write field ' + key + ' is ' + repr(no_write.get(key)))
    semantics = summary.get('raw_semantics') or {}
    for key in SEMANTICS:
        if semantics.get(key) is not True:
            problems.append('the raw semantic flag ' + key + ' is ' + repr(semantics.get(key)))
    versions = summary.get('versions') or {}
    if versions != {'install': '0.2.0', 'jump_history': '0.1.0', 'reading_state': '0.2.0',
                    'revisions': '0.4.0', 'sdk': '3.41.0'}:
        problems.append('the raw versions are ' + repr(versions))
    if summary.get('cases_total') != len(summary.get('cases', [])):
        problems.append('the stored-wire case count differs')
    return problems


def case_projection(cases):
    return [{key: case.get(key) for key in CASE_FIELDS} for case in cases]


def protocol_selftest():
    metadata = dict(id=7, head_sha='source', run_attempt=1, path=WORKFLOW)
    jobs = [dict(name=JOB_PREFIX + platform + ')', head_sha='source', run_attempt=1, status='completed',
                 conclusion='success') for platform in PLATFORMS]
    rejected = 0
    assert job_problems(metadata, jobs, 'source', '7', '1') == []
    for key, value in (('id', 8), ('head_sha', 'foreign'), ('run_attempt', 2), ('path', 'foreign.yml')):
        bad = dict(metadata)
        bad[key] = value
        if job_problems(bad, jobs, 'source', '7', '1'):
            rejected += 1
        else:
            raise AssertionError('accepted foreign ' + key)
    cases = [jobs[:-1], jobs + [jobs[0]]]
    for key, value in (('head_sha', 'foreign'), ('run_attempt', 2), ('status', 'in_progress'),
                       ('conclusion', 'failure'), ('conclusion', 'skipped'), ('name', jobs[1]['name'])):
        bad = copy.deepcopy(jobs)
        bad[0][key] = value
        cases.append(bad)
    for bad in cases:
        if job_problems(metadata, bad, 'source', '7', '1'):
            rejected += 1
        else:
            raise AssertionError('accepted invalid upstream jobs')
    report = dict(checks=[dict(name=name, **{'pass': True}) for name in REQUIRED])
    summary = dict(probe_checks_total=len(REQUIRED), checks_failed=0, accepted=True, problems=[],
                   host_wiring_accepted=False, gui_accepted=False)
    assert check_problems(report, summary) == []
    bad_cases = [(dict(checks=[]), summary), (report, dict(summary, probe_checks_total=0)),
                 (report, dict(summary, checks_failed=1)), (report, dict(summary, accepted=False)),
                 (report, dict(summary, problems=['x'])), (report, dict(summary, host_wiring_accepted=True)),
                 (report, dict(summary, gui_accepted=True))]
    duplicated = copy.deepcopy(report)
    duplicated['checks'].append(duplicated['checks'][0])
    bad_cases.append((duplicated, dict(summary, probe_checks_total=len(duplicated['checks']))))
    short = copy.deepcopy(report)
    short['checks'].pop()
    bad_cases.append((short, dict(summary, probe_checks_total=len(short['checks']))))
    for value in (False, 'true', 1):
        bad = copy.deepcopy(report)
        bad['checks'][0]['pass'] = value
        bad_cases.append((bad, summary))
    for bad, counted in bad_cases:
        if check_problems(bad, counted):
            rejected += 1
        else:
            raise AssertionError('accepted invalid raw checks')
    source = os.environ.get('GITHUB_SHA', 'source')
    run = os.environ.get('GITHUB_RUN_ID', '7')
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    record = dict(platform='Linux', expired=False, zip_bytes=10, api_bytes=10, api_digest='sha256:a',
                  zip_digest='sha256:a')
    good_summary = dict(identity=dict(GITHUB_SHA=source, GITHUB_RUN_ID=run, GITHUB_RUN_ATTEMPT=attempt),
                        platform='Linux', report_sha256=hashlib.sha256(b'report').hexdigest(),
                        probe_sha256=hashlib.sha256(b'probe').hexdigest(),
                        no_write={key: (0 if key not in ('databases_unchanged', 'control_write_changed') else True)
                                  for key in STABLE_NO_WRITE + ('raw_revision_rows', 'raw_outbox_rows')},
                        raw_semantics={key: True for key in SEMANTICS},
                        versions={'install': '0.2.0', 'jump_history': '0.1.0', 'reading_state': '0.2.0',
                                  'revisions': '0.4.0', 'sdk': '3.41.0'},
                        cases=[], cases_total=0)
    assert binding_problems(record, good_summary, b'report', b'probe') == []
    for key, value in (('expired', True), ('zip_bytes', 11), ('api_digest', 'sha256:b'), ('platform', 'Windows')):
        bad = dict(record)
        bad[key] = value
        if binding_problems(bad, good_summary, b'report', b'probe'):
            rejected += 1
        else:
            raise AssertionError('accepted invalid artifact record ' + key)
    for key, value in (('identity', dict(GITHUB_SHA='foreign', GITHUB_RUN_ID='7', GITHUB_RUN_ATTEMPT='1')),
                       ('report_sha256', '0' * 64), ('probe_sha256', '0' * 64),
                       ('no_write', dict(good_summary['no_write'], databases_unchanged=False)),
                       ('no_write', dict(good_summary['no_write'], control_write_changed=False)),
                       ('no_write', dict(good_summary['no_write'], sdk_notes=1)),
                       ('raw_semantics', dict(good_summary['raw_semantics'], nul_suffix_preserved=False)),
                       ('versions', dict(good_summary['versions'], install='0.1.0')),
                       ('cases_total', 1)):
        bad = dict(good_summary)
        bad[key] = value
        if binding_problems(record, bad, b'report', b'probe'):
            rejected += 1
        else:
            raise AssertionError('accepted invalid summary ' + key)
    print(json.dumps(dict(protocol_negative_cases=rejected, accepted=True)))
    try:
        json_load('{"accepted":false,"accepted":true}')
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate JSON key accepted')


def api(path, binary=False):
    for attempt in range(4):
        result = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path], capture_output=True)
        if result.returncode == 0:
            return result.stdout if binary else json_load(result.stdout)
        message = result.stderr.decode('utf-8', 'replace')
        if attempt == 3 or not any(code in message for code in ('HTTP 500', 'HTTP 502', 'HTTP 503', 'HTTP 504')):
            raise SystemExit('gh api ' + path + ' failed: ' + message)
        time.sleep(10 * (attempt + 1))
    raise SystemExit('unreachable')


def entry(archive, suffix):
    names = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(names) != 1:
        raise ValueError('expected one ' + suffix + ', got ' + repr(names))
    return names[0]


def main(output):
    repo, run, attempt, source = (os.environ[k] for k in
                                   ('GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'))
    problems, records = [], []
    metadata = api('repos/' + repo + '/actions/runs/' + run)
    jobs = api('repos/' + repo + '/actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    problems += job_problems(metadata, jobs, source, run, attempt)
    listed = api('repos/' + repo + '/actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    for platform in PLATFORMS:
        name = 'reader-next-s16-' + platform + '-' + run + '-' + attempt
        found = [a for a in listed if a['name'] == name]
        if len(found) != 1:
            problems.append(name + ': expected one artifact, got ' + str(len(found)))
            continue
        artifact = found[0]
        data = api('repos/' + repo + '/actions/artifacts/' + str(artifact['id']) + '/zip', binary=True)
        digest = 'sha256:' + hashlib.sha256(data).hexdigest()
        record = {'platform': platform, 'name': name, 'id': artifact['id'],
                  'api_bytes': artifact['size_in_bytes'], 'zip_bytes': len(data),
                  'api_digest': artifact.get('digest'), 'zip_digest': digest,
                  'expired': artifact['expired'], 'workflow_run': artifact.get('workflow_run', {}),
                  'created_at': artifact.get('created_at'), 'expires_at': artifact.get('expires_at')}
        if str(artifact.get('workflow_run', {}).get('head_sha')) != source:
            problems.append(name + ': artifact head SHA differs from this source')
        if str(artifact.get('workflow_run', {}).get('id')) != run or datetime.fromisoformat(
                artifact['expires_at'].replace('Z', '+00:00')) <= datetime.now(timezone.utc):
            problems.append(name + ': artifact run/expiry differs')
        archive = zipfile.ZipFile(io.BytesIO(data))
        members = archive.namelist()
        if len(members) != len(set(members)) or any(
                info.orig_filename.startswith('/') or '..' in info.orig_filename.split('/') or
                '\\' in info.orig_filename or ':' in info.orig_filename for info in archive.infolist()):
            raise ValueError('duplicate or unsafe ZIP members')
        try:
            raw_summary_name = entry(archive, 'evidence/raw/summary.json')
            raw_report_name = entry(archive, 'evidence/raw/report.json')
            default_summary_name = entry(archive, 'evidence/default/summary.json')
            original_summary_name = entry(archive, 'evidence/original-raw/summary.json')
            baseline_summary_name = entry(archive, 'evidence/original-baseline/summary.json')
            result_name = entry(archive, 'result.json')
            probe_name = entry(archive, 's16-raw-probe') if platform == 'Linux' else entry(archive, 's16-raw-probe.exe')
        except ValueError as error:
            problems.append(name + ': ' + str(error))
            records.append(record)
            continue
        raw_summary = json_load(archive.read(raw_summary_name))
        report_bytes = archive.read(raw_report_name)
        report = json_load(report_bytes)
        probe_bytes = archive.read(probe_name)
        default_summary = json_load(archive.read(default_summary_name))
        original_summary = json_load(archive.read(original_summary_name))
        baseline_summary = json_load(archive.read(baseline_summary_name))
        result = json_load(archive.read(result_name))
        record['root_bindings'] = complete_bindings(archive, result, platform)
        for role in result['programs']:
            altered = copy.deepcopy(result)
            altered['programs'][role]['sha256'] = '0' * 64
            try:
                complete_bindings(archive, altered, platform)
            except ValueError:
                continue
            raise ValueError('tampered program accepted: ' + role)
        for stage in ('baseline', 'default', 'raw'):
            library = 'reader_jump_history.lib' if platform == 'Windows' else 'libreader_jump_history.a'
            path = 'families/' + stage + '-stage/lib/' + library
            try:
                complete_bindings(archive, result, platform, {path: b'!<arch>\ncorrupt'})
            except ValueError:
                continue
            raise ValueError('tampered module archive accepted: ' + stage)
        for family in ('original-baseline', 'original-default', 'original-raw'):
            path = 'evidence/' + family + '/summary.json'
            altered = json_load(archive.read(entry(archive, path)))
            altered['identity']['GITHUB_SHA'] = '0' * 40
            try:
                complete_bindings(archive, result, platform, {path: json.dumps(altered).encode()})
            except ValueError:
                continue
            raise ValueError('foreign original suite accepted: ' + family)
        for label, problem in (('raw', check_problems(report, raw_summary)),
                               ('raw binding', binding_problems(record, raw_summary, report_bytes, probe_bytes))):
            problems += [name + ': ' + label + ': ' + item for item in problem]
        if (default_summary.get('accepted') is not True or default_summary.get('problems')
                or default_summary.get('checks_failed') != 0 or default_summary.get('mode') != 'default'
                or (default_summary.get('installed') or {}).get('jump_history_version') != '0.1.0'):
            problems.append(name + ': the default-install consumer is not accepted')
        for label, summary in (('original raw', original_summary), ('original default', default_summary)):
            if summary.get('identity', {}).get('GITHUB_SHA') != source:
                problems.append(name + ': ' + label + ' identity differs from this source')
        for label, summary in (('original raw', original_summary), ('original baseline', baseline_summary)):
            if summary.get('jump_history_module_accepted') is not True or summary.get('checks_failed') != 0:
                problems.append(name + ': the ' + label + ' suite is not accepted')
        if original_summary.get('checks_total', 0) < 149:
            problems.append(name + ': the raw-install original suite ran ' + str(original_summary.get('checks_total')))
        if result.get('accepted') is not True:
            problems.append(name + ': the build result is not accepted')
        for flag in ('default_equals_baseline', 'header_pure_insertions', 'default_install_has_no_raw_symbol'):
            if result.get(flag) is not True:
                problems.append(name + ': the result flag ' + flag + ' is ' + repr(result.get(flag)))
        for flag in ('host_wiring_accepted', 'gui_accepted', 'adopted'):
            if result.get(flag) is not False:
                problems.append(name + ': the result flag ' + flag + ' must stay false')
        negatives = result.get('mixed_install_negatives', [])
        if len(negatives) != 4 or any(item.get('accepted') is not False for item in negatives):
            problems.append(name + ': the mixed-install negatives are incomplete')
        programs = result.get('programs', {})
        if (programs.get('raw_probe') or {}).get('sha256') != hashlib.sha256(probe_bytes).hexdigest():
            problems.append(name + ': the uploaded probe differs from the recorded program hash')
        record.update({'summary_sha256': hashlib.sha256(archive.read(raw_summary_name)).hexdigest(),
                       'report_sha256': hashlib.sha256(report_bytes).hexdigest(),
                       'probe_sha256': hashlib.sha256(probe_bytes).hexdigest(),
                       'identity': raw_summary.get('identity'),
                       'accepted': raw_summary.get('accepted'),
                       'checks_total': raw_summary.get('checks_total'),
                       'cases_total': raw_summary.get('cases_total'),
                       'moves': raw_summary.get('moves'),
                       'versions': raw_summary.get('versions'),
                       'no_write': raw_summary.get('no_write'),
                       'raw_semantics': raw_summary.get('raw_semantics'),
                       'originals': raw_summary.get('originals'),
                       'case_ids': sorted(case.get('id') for case in raw_summary.get('cases', [])),
                       'cases': case_projection(raw_summary.get('cases', [])),
                       'steps': sorted(step.get('step') for step in raw_summary.get('lifecycle', [])),
                       'lifecycle': raw_summary.get('lifecycle'),
                       'original_checks_total': original_summary.get('checks_total'),
                       'default_equals_baseline': result.get('default_equals_baseline'),
                       'mixed_install_negatives': [item.get('name') for item in negatives],
                       'programs': programs})
        records.append(record)
    if len(records) == len(PLATFORMS):
        for field in ('originals', 'case_ids', 'cases', 'steps', 'lifecycle', 'versions'):
            values = [json.dumps(record.get(field), sort_keys=True) for record in records]
            if len(set(values)) != 1:
                problems.append('the two runners disagree on ' + field)
        verdicts = [json.dumps({key: (record.get('no_write') or {}).get(key) for key in STABLE_NO_WRITE},
                               sort_keys=True) for record in records]
        if len(set(verdicts)) != 1:
            problems.append('the two runners disagree on the no-write proof')
        semantics = [json.dumps(record.get('raw_semantics'), sort_keys=True) for record in records]
        if len(set(semantics)) != 1:
            problems.append('the two runners disagree on the raw semantics')
    else:
        problems.append('only ' + str(len(records)) + ' platform artifacts were authenticated')
    result = {'source': source, 'run_id': run, 'run_attempt': attempt, 'artifacts': records,
              'checks_total': records[0].get('checks_total') if records else None,
              'cases_total': records[0].get('cases_total') if records else None,
              'moves': records[0].get('moves') if records else None,
              'jobs': [{'name': job.get('name'), 'id': job.get('id'), 'status': job.get('status'),
                        'conclusion': job.get('conclusion'), 'head_sha': job.get('head_sha'),
                        'run_attempt': job.get('run_attempt')} for job in jobs],
              'jump_history_raw_candidate_accepted': not problems,
              'host_wiring_accepted': False, 'gui_accepted': False, 'adopted': False,
              'problems': problems}
    Path(output).mkdir(parents=True, exist_ok=True)
    (Path(output) / 's16-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                                    encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    if sys.argv[1:] == ['--protocol-selftest']:
        protocol_selftest()
    else:
        sys.exit(main(sys.argv[1]))
