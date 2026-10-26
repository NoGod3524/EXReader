# SPDX-License-Identifier: MIT
"""Case-level diagnostics and immutable identity checks for S20 delivery."""
import re

TARGETS = ('windows', 'linux', 'macos', 'android', 'iphone', 'ipad')
TEST_EVENT = re.compile(
    r"Test Case '-\[(?P<suite>[\w.]+) (?P<name>\w+)\]' "
    r"(?P<result>started|passed|failed)")
ASSERTION = re.compile(r'XCTAssert\w*.*failed|Assertion Failure|error:.*(?:failed|XCT)|failed -', re.I)
SHA256 = re.compile(r'^[0-9a-f]{64}$')


def xctest_log(text):
    """Keep each observed verdict; a later retry cannot erase a failed attempt."""
    lines = text.splitlines()
    tests, failures, active = [], [], None
    for index, line in enumerate(lines):
        event = TEST_EVENT.search(line)
        if event and event['result'] == 'started':
            active = {'suite': event['suite'], 'name': event['name'], 'start_line': index + 1}
        if ASSERTION.search(line):
            failure = dict(active or {'suite': None, 'name': None})
            failure.update({'line': index + 1, 'assertion': line,
                            'context': lines[max(0, index - 3):index + 4]})
            failures.append(failure)
        if event and event['result'] != 'started':
            record = {'suite': event['suite'], 'name': event['name'],
                      'result': event['result'].capitalize(), 'line': index + 1}
            if event['result'] == 'failed':
                start = (active or {}).get('start_line', index + 1)
                record['first_assertion'] = next(
                    (failure for failure in failures
                     if start <= failure['line'] <= index + 1
                     and failure['name'] == record['name']
                     and failure['suite'] == record['suite']), None)
                record['context'] = lines[max(start - 1, index - 8):index + 1]
            tests.append(record)
            active = None
    failed = [test for test in tests if test['result'] == 'Failed']
    return {'tests': tests,
            'passed': sum(test['result'] == 'Passed' for test in tests),
            'failed': len(failed), 'failed_cases': failed,
            'first_assertion': failures[0] if failures else None,
            'assertions': failures}


def android_cases(validation, expected_total=45):
    """Read named case verdicts independently of instrumentation process exits."""
    cases = validation.get('cases') or []
    summary = validation.get('summary') or {}
    names = [case.get('id') for case in cases]
    problems = []
    counts = {name: sum(case.get('status') == status for case in cases)
              for name, status in (('passed', 'pass'), ('failed', 'fail'), ('skipped', 'skip'))}
    if len(cases) != expected_total:
        problems.append('expected %s named cases, observed %s' % (expected_total, len(cases)))
    if any(not name for name in names) or len(set(names)) != len(names):
        problems.append('case ids are missing or duplicated')
    for key, count in dict(counts, total=len(cases)).items():
        if summary.get(key) != count:
            problems.append('summary %s differs from named case verdicts' % key)
    if counts['passed'] != len(cases) or not cases:
        problems.append('not every named case passed')
    failed = [case for case in cases if case.get('status') != 'pass']
    return dict(counts, total=len(cases), failed_cases=failed,
                first_failure=failed[0] if failed else None,
                accepted=not problems, problems=problems)


def candidate_identity(manifest, unpack, report, *, source_sha, run_id, attempt,
                       sdk_version):
    """Validate required identities, including missing run/attempt provenance."""
    problems = []
    expected = {'source_sha': source_sha, 'sdk_version': sdk_version}
    target = manifest.get('target')
    if target not in TARGETS:
        problems.append('manifest target is unknown')
    for label, document in (('manifest', manifest), ('unpack', unpack), ('report', report)):
        for key, value in dict(expected, target=target).items():
            if not value or document.get(key) != value:
                problems.append(label + ' ' + key + ' is missing or differs from candidate')
        provenance = document if label == 'report' else document.get('provenance') or {}
        for key, value in (('run_id', run_id), ('attempt', attempt)):
            if not value or str(provenance.get(key, '')) != str(value):
                problems.append(label + ' ' + key + ' is missing or differs from candidate')
    archive = manifest.get('archive') or {}
    unpack_archive = unpack.get('archive') or {}
    report_archive = (report.get('package') or {}).get('archive') or {}
    for key in ('name', 'bytes', 'sha256'):
        value = archive.get(key)
        if not value or unpack_archive.get(key) != value or report_archive.get(key) != value:
            problems.append('original ZIP ' + key + ' is missing or differs across records')
    if not SHA256.fullmatch(str(archive.get('sha256', ''))):
        problems.append('original ZIP SHA-256 is malformed')
    entry = manifest.get('entry')
    digest = (manifest.get('files') or {}).get(entry, {}).get('sha256')
    if not SHA256.fullmatch(str(digest or '')):
        problems.append('program SHA-256 is missing or malformed')
    for label, document in (('unpack', unpack), ('report', report)):
        if not entry or document.get('entry') != entry or document.get('entry_sha256') != digest:
            problems.append(label + ' program identity differs from manifest')
    return problems


def matrix_markdown(index):
    """Render all six targets even when their artifacts or verdicts are missing."""
    lines = ['| 目标 | 验收 | 原 ZIP SHA-256 | 程序 SHA-256 | 问题 |',
             '|---|---|---|---|---|']
    for target in TARGETS:
        record = (index.get('targets') or {}).get(target) or {}
        problems = '; '.join(map(str, record.get('problems') or []))
        values = (target, '通过' if record.get('accepted') is True else '未通过',
                  (record.get('archive') or {}).get('sha256') or '缺失',
                  record.get('entry_sha256') or '缺失', problems or '—')
        lines.append('| ' + ' | '.join(str(value).replace('|', '\\|').replace('\n', ' ')
                                       for value in values) + ' |')
    return '\n'.join(lines) + '\n'
