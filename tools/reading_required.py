#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Join same-run reading evidence. Never publish or grant whole-product credit."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from check_parallel_integration import fetch, pages, require, required_artifacts
from measure_reading_core import sha256

GROUPS = {'protocol', 'native', 'profiles', 'platforms', 'corpus', 'performance'}
REGISTRATION = 'ea5c13e081cfba86d9f6dd759439894463e51126'
MANIFEST = Path('tools/reading_corpus/real-v1.json')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def expected_artifacts(run, attempt):
    return ({f'reading-{profile}-{run}-{attempt}' for profile in ('reading-core', 'reading-library')} |
            {f'reading-platform-{host}-{profile}-{run}-{attempt}'
             for host in ('Windows', 'macOS') for profile in ('reading-core', 'reading-library')} |
            {f'r2-real-corpus-{run}-{attempt}', f'reading-real-{run}-{attempt}'} |
            required_artifacts('native', '', {'id': run, 'run_attempt': attempt}))


def expected_jobs():
    return ({'protocol', 'corpus / R2 real document acceptance', 'performance / reading-performance'} |
            {f'native / desktop ({host})' for host in ('windows-latest', 'ubuntu-22.04', 'macos-15')} |
            {'native / ' + name for name in ('sanitizers', 'fuzz', 'android', 'apple-mobile')} |
            {f'profiles / reading ({profile})' for profile in ('reading-core', 'reading-library')} |
            {f'platforms / reading {host} ({profile})' for host in ('windows-2022', 'macos-15')
             for profile in ('reading-core', 'reading-library')})


def verify_jobs(workflow_head, run, attempt, jobs):
    required = expected_jobs()
    require(len({item['id'] for item in jobs}) == len(jobs) and
            len({item['name'] for item in jobs}) == len(jobs) and
            {item['name'] for item in jobs} == required | {'reading-required'},
            'missing, unexpected or duplicated same-attempt job')
    for item in jobs:
        require(str(item['run_id']) == str(run) and str(item['run_attempt']) == str(attempt) and
                item['head_sha'] == workflow_head, 'job belongs to another source/run/attempt')
        if item['name'] != 'reading-required':
            require(item['status'] == 'completed' and item['conclusion'] == 'success',
                    'upstream job failed, was skipped or did not finish')
    return [{key: item[key] for key in ('id', 'name', 'run_attempt', 'head_sha', 'status', 'conclusion')}
            for item in jobs]


def verify_publisher(check, workflow_head, ruleset):
    rules = [item for item in ruleset['rules'] if item['type'] == 'required_status_checks']
    require(len(rules) == 1 and rules[0]['parameters']['required_status_checks'] ==
            [{'context': 'reading-required', 'integration_id': 15368}], 'required publisher is not pinned')
    require(check['name'] == 'reading-required' and check['head_sha'] == workflow_head and
            check['app']['id'] == 15368 and check['app']['slug'] == 'github-actions',
            'required check was issued by another publisher/source')
    return {'integration_id': check['app']['id'], 'publisher': check['app']['slug'], 'check_id': check['id']}


def workflow_identity(record, source, run, attempt, parents):
    require(str(record['id']) == str(run) and str(record['run_attempt']) == str(attempt) and
            record['path'].split('@')[0] == '.github/workflows/reading-required.yml',
            'wrong enclosing workflow/run/attempt')
    if record['event'] == 'pull_request':
        # The immutable run metadata names the PR head. Checkout/GITHUB_SHA
        # names GitHub's tested merge. Bind both through that merge's parents.
        require(len(parents) == 2 and parents[1] == record['head_sha'],
                'tested PR merge is not a merge of the recorded workflow head')
    else:
        require(record['event'] in ('push', 'workflow_dispatch') and record['head_sha'] == source,
                'workflow head differs from the tested source')
    return record['head_sha']


def verify_metadata(source, run, attempt, needs, artifacts, workflow_head=None):
    require(set(needs) == GROUPS and all(item.get('result') == 'success' for item in needs.values()),
            'missing, failed, skipped or cancelled upstream group')
    require(len({item['id'] for item in artifacts}) == len(artifacts) and
            len({item['name'] for item in artifacts}) == len(artifacts), 'duplicate cloud artifacts')
    required = expected_artifacts(run, attempt)
    records = [item for item in artifacts if item['name'] in required]
    require({item['name'] for item in records} == required, 'same-attempt evidence missing')
    for item in records:
        require(item['expired'] is False and item['size_in_bytes'] > 0 and
                item['workflow_run']['head_sha'] == (workflow_head or source) and str(item['workflow_run']['id']) == str(run) and
                re.fullmatch(r'sha256:[0-9a-f]{64}', item.get('digest', '')), 'invalid artifact identity/digest')
    return [{key: item[key] for key in ('id', 'name', 'size_in_bytes', 'digest')} for item in records]


def one(root, name):
    matches = list(root.rglob(name))
    require(len(matches) == 1, 'missing or duplicate report: ' + name)
    return matches[0]


def ci_identity(report, source, run, attempt, nested=False):
    require(report.get('source_sha') == source, 'report source differs from workflow checkout')
    identity = report.get('ci', {}) if nested else report
    keys = ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT') if nested else ('run_id', 'run_attempt')
    require(str(identity.get(keys[0])) == str(run) and str(identity.get(keys[1])) == str(attempt),
            'report belongs to another run/attempt')


def reports(root, source, run, attempt):
    identities = []
    for profile in ('reading-core', 'reading-library'):
        folder = root / f'reading-{profile}-{run}-{attempt}'
        path = one(folder, 'candidate.json'); candidate = read(path)
        ci_identity(candidate, source, run, attempt, True)
        require(candidate.get('accepted') is True and candidate.get('profile') == profile and
                candidate.get('published') is False and candidate.get('quality_accepted') is False,
                'installed candidate was not sealed independently of quality/publication')
        archive = path.parent / candidate['archive']
        require(archive.parent == path.parent and archive.stat().st_size == candidate['bytes'] and
                sha256(archive) == candidate['sha256'], 'sealed SDK archive changed')
        manifest = read(path.parent / 'release-manifest.json')
        require(sha256(path.parent / 'release-manifest.json') == candidate['manifest_sha256'] and
                manifest['source_sha'] == source and manifest['profile'] == profile and
                manifest['identity'] == candidate['identity'] and
                len(manifest['files']) == candidate['file_count'] > 0, 'SDK manifest identity changed')
        license_report = read(one(folder, 'licenses.json'))
        require(license_report.get('source_sha') == source and license_report.get('profile') == profile and
                license_report.get('release_ready') is True and license_report.get('materials_check_passed') is True and
                license_report.get('failures') == [] and license_report.get('pending') == [] and
                license_report.get('mandatory_missing') == [], 'release license materials rejected')
        identities.append(candidate['identity'])
    require(identities[0]['sdk_version'] == identities[1]['sdk_version'] and
            identities[0]['abi'] == identities[1]['abi'] and identities[0]['library_schema'] is None and
            identities[1]['library_schema'] == 7, 'profile versions/ABI or actual library schema differ')
    for host in ('Windows', 'macOS'):
        for profile in ('reading-core', 'reading-library'):
            folder = root / f'reading-platform-{host}-{profile}-{run}-{attempt}'
            report = read(one(folder, 'platform-evidence.json'))
            ci_identity(report, source, run, attempt, True)
            require(report.get('accepted') is True and report.get('problems') == [] and
                    report.get('profile') == profile and report.get('host') == host,
                    'platform dependency/execution/toolchain check rejected')
            rejection = read(one(folder, 'rejection-regression.json'))
            require(rejection.get('accepted') is True and rejection.get('profile') == profile and
                    rejection.get('platform') == host and
                    rejection.get('cases', 0) == rejection.get('passed', -1) > 0 and
                    all(item.get('passed') is True for item in rejection['results']), 'platform refusal regression failed')
    corpus = read(one(root / f'r2-real-corpus-{run}-{attempt}', 'report.json'))
    ci_identity(corpus, source, run, attempt)
    sys.path.insert(0, str(Path('tools/reading_corpus').resolve()))
    from run import validate_report
    manifest = read(MANIFEST)
    require(corpus.get('accepted') is True and validate_report(corpus) and
            corpus['registration_sha'] == REGISTRATION and corpus['manifest_sha256'] == sha256(MANIFEST),
            'real-document declaration or complete acceptance rejected')
    require([(row['id'], row['sha256']) for row in corpus['documents']] ==
            [(row['id'], row['sha256']) for row in manifest['files']], 'real-document coverage changed')
    performance_path = root / f'reading-real-{run}-{attempt}' / 'reading-real/summary.json'
    performance = read(performance_path)
    ci_identity(performance, source, run, attempt)
    from measure_reading_real import audit, read as real_read, CONTRACT, BUDGETS
    require(performance.get('accepted') is True and performance.get('measurement_valid') is True and
            performance.get('problems') == [] and
            performance.get('corpus_registration_sha') == REGISTRATION and
            performance.get('corpus_manifest_sha256') == corpus['manifest_sha256'] and
            performance.get('contract_path') == 'tests/reading_real/contract.json' and
            performance.get('budget_path') == 'tests/reading_real/budgets.json' and
            performance.get('contract_sha256') == sha256(CONTRACT) and
            performance.get('budget_sha256') == sha256(BUDGETS), 'strict frozen performance evidence missing')
    require(performance.get('refusal_regression', {}).get('passed') is True,
            'performance evidence refusal regression missing')
    audit(performance, performance_path.parent, real_read(BUDGETS))
    return {'sdk_version': identities[0]['sdk_version'], 'abi': identities[0]['abi'],
            'library_schema': 7, 'sdk_candidate': performance['sdk_candidate'],
            'manifest_sha256': corpus['manifest_sha256'], 'contract_sha256': performance['contract_sha256'],
            'budget_sha256': performance['budget_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('needs', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'required reading gate runs only in cloud')
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    result = {'schema': 1, 'source_sha': source, 'run_id': run, 'run_attempt': attempt,
              'accepted': False, 'published': False, 'complete_product': False, 'wp16_cpu_credit_seconds': 0,
              'scope': 'native reading SDK and the fixed representative real-v1 corpus', 'problems': []}
    try:
        require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == source,
                'workflow and checkout source differ')
        require(subprocess.run(['git', 'diff', '--quiet', 'HEAD']).returncode == 0, 'tracked source changed')
        record = fetch(f'actions/runs/{run}')
        parents = subprocess.check_output(['git', 'rev-list', '--parents', '-n', '1', source], text=True).split()[1:]
        workflow_head = workflow_identity(record, source, run, attempt, parents)
        result['workflow_head_sha'] = workflow_head
        result['tested_source_parents'] = parents
        result['jobs'] = verify_jobs(workflow_head, run, attempt,
                                    pages(f'actions/runs/{run}/attempts/{attempt}/jobs', 'jobs'))
        own_job = next(item for item in result['jobs'] if item['name'] == 'reading-required')
        result['publisher'] = verify_publisher(fetch('check-runs/' + str(own_job['id'])), workflow_head,
                                              read('docs/reading-required-ruleset.json'))
        result['artifacts'] = verify_metadata(source, run, attempt, read(args.needs),
                                             pages(f'actions/runs/{run}/artifacts', 'artifacts'), workflow_head)
        result['identity'] = reports(args.evidence, source, run, attempt)
        result['accepted'] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result['problems'].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(result, allow_nan=False))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
