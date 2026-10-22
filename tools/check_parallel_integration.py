#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only gate for same-source package CI. Does not grant WP16 CPU credit."""
import copy
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

WORKFLOWS = {
    'native': ('native.yml', 7), 'ocr': ('wp11-ocr.yml', 3),
    'corpus': ('compat-corpus.yml', 1), 'linux': ('wp13-linux.yml', 1),
    'windows_evidence': ('wp13-windows-evidence.yml', 1),
    'windows_worker': ('wp13-windows-worker.yml', 1),
    'migration': ('wp12-migration.yml', 3), 'opds': ('wp15-opds.yml', 2),
    'apple': ('wp13-apple.yml', 8),
    'android': ('wp13-android.yml', 1),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def required_artifacts(kind, source, run):
    return {
        'native': {'EXReader-C-Windows', 'EXReader-C-Linux', 'EXReader-C-macOS',
                   'EXReader-C-Android-arm64', 'EXReader-C-iOS-iPadOS-arm64',
                   'EXReader-reference-Windows', 'EXReader-reference-macOS',
                   'EXReader-reference-iPhone-iPad', 'sanitizer-native-tests', 'reliability-native-smoke'},
        'ocr': {'WP11-OCR-release', 'WP11-OCR-sanitizers', 'WP11-OCR-cloud-audit'},
        'corpus': {f"compatibility-corpus-{run['id']}-{run['run_attempt']}"},
        'linux': {'WP13-Linux-' + source},
        'windows_evidence': {'EXReader-WP13-Windows-Evidence-Review'},
        'windows_worker': {'EXReader-WP13-Windows-WorkerReview'},
        'migration': {'wp12-evidence-linux', 'wp12-evidence-windows', 'wp12-migration-review-summary'},
        'opds': {'wp15-opds-Linux', 'wp15-opds-Windows'},
        'apple': {'wp13-apple-sdk-macos', 'wp13-apple-sdk-iphonesimulator',
                  'wp13-apple-sdk-iphoneos', 'wp13-apple-macos', 'wp13-apple-iphone',
                  'wp13-apple-ipad', 'wp13-apple-package', 'wp13-apple-validation'},
        'android': {'EXReader-WP13-Android'},
    }[kind]


def verify(kind, source, run, jobs, artifacts):
    workflow, expected_jobs = WORKFLOWS[kind]
    require(run['head_sha'] == source and run['status'] == 'completed' and run['conclusion'] == 'success', kind + ': run did not succeed at the required source')
    require(run['path'].split('@')[0] == '.github/workflows/' + workflow, kind + ': wrong workflow')
    require(len(jobs) == expected_jobs and len({job['id'] for job in jobs}) == expected_jobs, kind + ': missing or duplicate jobs')
    require(all(job['head_sha'] == source and job['status'] == 'completed' and job['conclusion'] == 'success' for job in jobs), kind + ': failed, incomplete or cross-source job')
    require(len({artifact['id'] for artifact in artifacts}) == len(artifacts) and
            len({artifact['name'] for artifact in artifacts}) == len(artifacts), kind + ': duplicate artifacts')
    require(required_artifacts(kind, source, run) <= {artifact['name'] for artifact in artifacts}, kind + ': required evidence missing')
    for artifact in artifacts:
        require(artifact['expired'] is False and artifact['size_in_bytes'] > 0 and
                artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == run['id'] and
                re.fullmatch('sha256:[0-9a-f]{64}', artifact.get('digest', '')) is not None,
                kind + ': expired, empty or mismatched artifact identity')
    return {'run_id': run['id'], 'attempt': run['run_attempt'], 'workflow': workflow,
            'jobs': len(jobs), 'artifacts': [{key: artifact[key] for key in ('id', 'name', 'digest', 'size_in_bytes')} for artifact in artifacts]}


def fetch(path):
    request = urllib.request.Request('https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def pages(path, key):
    records, total, page = [], None, 1
    while total is None or len(records) < total:
        response = fetch(path + f'?per_page=100&page={page}')
        if total is None:
            total = response['total_count']
        require(type(total) is int and 0 <= total <= 10000 and response['total_count'] == total, 'unstable pagination count')
        batch = response[key]
        require(isinstance(batch, list) and (batch or len(records) == total), 'incomplete API pagination')
        records.extend(batch)
        require(len(records) <= total, 'pagination exceeds the declared count')
        page += 1
    return records


def selftest():
    source = 'a' * 40
    run = {'head_sha': source, 'status': 'completed', 'conclusion': 'success', 'path': '.github/workflows/native.yml', 'id': 123, 'run_attempt': 1}
    jobs = [{'id': i, 'head_sha': source, 'status': 'completed', 'conclusion': 'success'} for i in range(7)]
    artifacts = [{'id': i, 'name': name, 'expired': False, 'size_in_bytes': 1, 'digest': 'sha256:' + 'b' * 64,
                  'workflow_run': {'head_sha': source, 'id': 123}} for i, name in enumerate(sorted(required_artifacts('native', source, run)))]
    verify('native', source, run, jobs, artifacts)
    changes = [
        ('wrong source', lambda r, j, a: r.update(head_sha='0' * 40)),
        ('run not complete', lambda r, j, a: r.update(status='in_progress')),
        ('wrong workflow', lambda r, j, a: r.update(path='.github/workflows/reliability.yml')),
        ('missing job', lambda r, j, a: j.pop()),
        ('duplicate job', lambda r, j, a: j.__setitem__(1, j[0])),
        ('failed upstream', lambda r, j, a: j[0].update(conclusion='failure')),
        ('cancelled upstream', lambda r, j, a: j[0].update(conclusion='cancelled')),
        ('missing artifact', lambda r, j, a: a.pop()),
        ('duplicate artifact', lambda r, j, a: a.append(a[0])),
        ('expired artifact', lambda r, j, a: a[0].update(expired=True)),
        ('empty artifact', lambda r, j, a: a[0].update(size_in_bytes=0)),
        ('missing digest', lambda r, j, a: a[0].pop('digest')),
        ('wrong artifact source', lambda r, j, a: a[0]['workflow_run'].update(head_sha='0' * 40)),
        ('artifact from another run', lambda r, j, a: a[0]['workflow_run'].update(id=124)),
    ]
    for name, change in changes:
        r, j, a = copy.deepcopy((run, jobs, artifacts))
        change(r, j, a)
        try:
            verify('native', source, r, j, a)
        except ValueError:
            continue
        raise AssertionError(name + ' was accepted')
    apple_run = dict(run, path='.github/workflows/wp13-apple.yml')
    apple_jobs = [dict(jobs[0], id=i) for i in range(8)]
    apple_artifacts = [dict(artifacts[0], id=i, name=name) for i, name in
                       enumerate(sorted(required_artifacts('apple', source, apple_run)))]
    verify('apple', source, apple_run, apple_jobs, apple_artifacts)
    for kind in ('summary missing', 'summary failed'):
        copied_jobs, copied_artifacts = copy.deepcopy((apple_jobs, apple_artifacts))
        if kind == 'summary missing':
            copied_artifacts = [a for a in copied_artifacts if a['name'] != 'wp13-apple-validation']
        else:
            copied_jobs[-1]['conclusion'] = 'failure'
        try:
            verify('apple', source, apple_run, copied_jobs, copied_artifacts)
        except ValueError:
            continue
        raise AssertionError('Apple ' + kind + ' was accepted')
    android_run = dict(run, path='.github/workflows/wp13-android.yml')
    android_jobs = [dict(jobs[0], id=900)]
    android_artifacts = [dict(artifacts[0], id=900, name='EXReader-WP13-Android')]
    verify('android', source, android_run, android_jobs, android_artifacts)
    for failure in ('missing acceptance artifact', 'failed host'):
        copied_jobs, copied_artifacts = copy.deepcopy((android_jobs, android_artifacts))
        if failure == 'missing acceptance artifact':
            copied_artifacts.clear()
        else:
            copied_jobs[0]['conclusion'] = 'failure'
        try:
            verify('android', source, android_run, copied_jobs, copied_artifacts)
        except ValueError:
            continue
        raise AssertionError('Android ' + failure + ' was accepted')
    return {'passed': True, 'checks': 7 + len(changes), 'integration_accepted': False,
            'source_sha': os.environ['GITHUB_SHA'], 'scope': 'gate protocol only'}


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Run only in GitHub Actions')
    output = Path(sys.argv[2])
    require(not output.exists(), 'Preserve previous evidence')
    output.parent.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == 'selftest':
        report = selftest()
    else:
        source = os.environ['EXPECTED_SOURCE']
        report = {'accepted': False, 'source_sha': source, 'scope': 'declared integrated package scopes only',
                  'complete_product': False, 'wp16_accepted': False, 'wp16_cpu_credit_seconds': 0, 'runs': {}}
        try:
            require(re.fullmatch('[0-9a-f]{40}', source) is not None, 'Require an immutable full source SHA')
            requested = json.loads(os.environ['SOURCE_RUNS'])
            require(set(requested) == set(WORKFLOWS) and len(set(requested.values())) == len(WORKFLOWS) and
                    all(type(value) is int and value > 0 for value in requested.values()), 'Require all ten distinct workflow run IDs')
            for kind, run_id in requested.items():
                path = f'actions/runs/{run_id}'
                run = fetch(path)
                jobs = pages(path + f"/attempts/{run['run_attempt']}/jobs", 'jobs')
                artifacts = pages(path + '/artifacts', 'artifacts')
                report['runs'][kind] = verify(kind, source, run, jobs, artifacts)
            report['accepted'] = True
        except (ValueError, KeyError, TypeError, OSError) as error:
            report['refusal'] = str(error)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('runs',)}))
    return 0 if report.get('accepted', report.get('passed', False)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
