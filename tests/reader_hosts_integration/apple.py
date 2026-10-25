"""Authenticate six original Apple suites at one exact common production SHA."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from final import Bundle, fetch, identity, pages, require, stream_sha256

PLATFORMS = ('macos', 'iphone', 'ipad')
SPECS = {
    'records': ('reader-apple-reading-records', 'apple-reading', 7),
    'navigation': ('reader-apple-navigation', 'apple-navigation', 7),
    'search': ('reader-apple-search', 'apple-search', 7),
    'shelf': ('reader-apple-shelf', 'apple-shelf', 7),
    'mapping': ('reader-apple-import-mapping', 'apple-import-mapping', 6),
    'wp13': ('wp13-apple', 'wp13-apple', 8),
}


def check_run(kind, run, jobs, source):
    workflow, _, count = SPECS[kind]
    require(run['head_sha'] == source and run['head_branch'] == 'codex/reader-hosts-integration'
            and run['status'] == 'completed' and run['conclusion'] == 'success'
            and run['path'].split('@')[0] == '.github/workflows/' + workflow + '.yml',
            kind + ': wrong or incomplete common-source run')
    require(len(jobs) == len({j['id'] for j in jobs}) == len({j['name'] for j in jobs}) == count,
            kind + ': omitted or duplicate jobs')
    for job in jobs:
        require(job['head_sha'] == source and job['run_attempt'] == run['run_attempt']
                and job['status'] == 'completed' and job['conclusion'] == 'success',
                kind + ': failed or foreign-attempt job')
        require(all(step['conclusion'] in ('success', 'skipped') for step in job['steps']),
                kind + ': failed step hidden by continuation')
    guards = [step for job in jobs for step in job['steps']
              if step['name'] == 'Authenticate exact common-source host merge']
    require(len(guards) == (3 if kind == 'wp13' else 2)
            and all(step['conclusion'] == 'success' for step in guards),
            kind + ': common-source SDK guards missing')


def expected_artifacts(kind, run, attempt):
    stem = SPECS[kind][1]
    suffix = '-%s-%s' % (run, attempt)
    if kind == 'wp13':
        return {stem + '-' + item for item in ('sdk-macos', 'sdk-iphonesimulator', 'sdk-iphoneos',
                                               *PLATFORMS, 'package', 'validation')}
    names = {stem + '-sdk-' + target + suffix for target in ('macos', 'iphonesimulator')}
    names |= {stem + '-native' + suffix}
    names |= {stem + '-ui-' + platform + suffix for platform in PLATFORMS}
    if kind != 'mapping':
        names.add(stem + ('-validation' if kind == 'shelf' else '-summary') + suffix)
    return names


def check_artifacts(kind, artifacts, source, run, attempt):
    require(len(artifacts) == len({a['id'] for a in artifacts}) == len({a['name'] for a in artifacts})
            and {a['name'] for a in artifacts} == expected_artifacts(kind, run, attempt),
            kind + ': omitted or duplicate artifacts')
    require(all(a['workflow_run']['head_sha'] == source and a['workflow_run']['id'] == run
                for a in artifacts), kind + ': foreign artifact source/run')


def manifest(bundle, base, entries):
    require(isinstance(entries, dict) and entries, 'empty executable/attachment inventory')
    for path, digest in entries.items():
        require(isinstance(path, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'invalid file inventory')
        info = bundle.info(base + '/' + path)
        with bundle.zip.open(info) as stream:
            require(stream_sha256(stream) == digest, 'actual file differs from inventory: ' + path)


def check_ui(kind, report, source, run, attempt, platform):
    identity(report, source, run, attempt)
    require(report['accepted'] is True and report['platform'] == platform and report['problems'] == []
            and report['physical_device_execution'] is False, kind + ': actual UI failed')
    if kind == 'mapping':
        require((report['ui_cases'], report['named_steps'], report['attachments']) == (5, 22, 14),
                'mapping UI cases/steps/attachments omitted')
    else:
        require((report['ui_cases'], report['named_observations'], report['attachments'], report['originals'])
                == (7, 11, 14, 2202) and report['page_limit'] == 50
                and report['retained_ui_cache_limit'] == 150, 'shelf UI cases/bounded cache omitted')
    cases = report['cases']
    require(len(cases) == report['ui_cases'] and len({c['name'] for c in cases}) == len(cases)
            and all(c['result'] == 'Passed' for c in cases), 'actual UI cases failed/skipped/duplicated')


def verify_bundle(kind, meta, source, run, attempt):
    bundle = Bundle(meta)
    try:
        name = meta['name']
        stem = SPECS[kind][1]
        if kind in ('records', 'navigation', 'search') and name.startswith(stem + '-summary-'):
            report = bundle.report('summary.json')
            identity(report, source, run, attempt)
            require(report['accepted'] is True and report['complete_product'] is False,
                    kind + ': original strict summary rejected')
        elif kind == 'shelf' and name.startswith('apple-shelf-validation-'):
            report = bundle.report('shelf-summary.json')
            identity(report, source, run, attempt)
            require(report['accepted'] is True and report['problems'] == []
                    and set(report['platforms']) == set(PLATFORMS), 'original shelf summary rejected')
        elif kind == 'wp13' and name == 'wp13-apple-validation':
            report = bundle.report('wp13-apple-summary.json')
            require(report['source_sha'] == source and str(report['run']['id']) == str(run)
                    and str(report['run']['attempt']) == str(attempt) and report['accepted'] is True
                    and set(report['platforms']) == set(PLATFORMS)
                    and report['physical_device_execution'] is False, 'original WP13 strict summary rejected')
        elif kind in ('mapping', 'shelf') and name.startswith(stem + '-ui-'):
            platform = next(p for p in PLATFORMS if name == stem + '-ui-' + p + '-%d-%d' % (run, attempt))
            report = bundle.report('evidence/' + ('mapping-ui.json' if kind == 'mapping' else 'shelf-ui.json'))
            check_ui(kind, report, source, run, attempt, platform)
            manifest(bundle, 'evidence/program', report['program_files'])
            manifest(bundle, 'evidence/attachments', report['attachment_files'])
            for filename, record in report['databases'].items():
                raw = bundle.bytes('evidence/' + filename, 128 * 1024 * 1024)
                require(len(raw) == record['bytes'] and hashlib.sha256(raw).hexdigest() == record['sha256'],
                        'original catalog snapshot differs')
        elif kind == 'mapping' and name.startswith(stem + '-native-'):
            for path, count in (('catalog.json', 8), ('consumer/mapping-review.json', 16)):
                report = bundle.report(path)
                identity(report, source, run, attempt)
                require(report['accepted'] is True and report['failed'] == report['skipped'] == 0
                        and len(report['checks']) == len({c['id'] for c in report['checks']}) == count
                        and all(c['passed'] is True for c in report['checks']), 'mapping consumer incomplete')
            bundle.info('mapping-review')
        return {key: meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
    finally:
        bundle.close()


def self_test():
    source = 'a' * 40
    run = dict(id=1, head_sha=source, head_branch='codex/reader-hosts-integration', status='completed',
               conclusion='success', path='.github/workflows/reader-apple-import-mapping.yml', run_attempt=1)
    jobs = [dict(id=i, name=str(i), head_sha=source, run_attempt=1, status='completed', conclusion='success',
                 steps=[dict(name='Authenticate exact common-source host merge', conclusion='success')] if i < 2 else [])
            for i in range(6)]
    check_run('mapping', run, jobs, source)
    changes = [('source', 'head_sha', 'b' * 40), ('branch', 'head_branch', 'other'),
               ('workflow', 'path', '.github/workflows/other.yml'), ('failed-run', 'conclusion', 'failure'),
               ('live-run', 'status', 'in_progress')]
    rejected = 0
    for label, key, value in changes:
        wrong = {**run, key: value}
        try:
            check_run('mapping', wrong, jobs, source)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError('accepted ' + label)
    for label in ('missing-job', 'foreign-attempt', 'missing-guard', 'hidden-failure'):
        wrong = copy.deepcopy(jobs)
        if label == 'missing-job':
            wrong.pop()
        elif label == 'foreign-attempt':
            wrong[0]['run_attempt'] = 2
        elif label == 'missing-guard':
            wrong[0]['steps'] = []
        else:
            wrong[0]['steps'].append(dict(name='UI', conclusion='failure'))
        try:
            check_run('mapping', run, wrong, source)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError('accepted ' + label)
    artifacts = [dict(id=i + 1, name=name, workflow_run=dict(head_sha=source, id=1))
                 for i, name in enumerate(sorted(expected_artifacts('mapping', 1, 1)))]
    check_artifacts('mapping', artifacts, source, 1, 1)
    for label in ('missing-artifact', 'foreign-artifact', 'duplicate-artifact', 'wrong-attempt-name'):
        wrong = copy.deepcopy(artifacts)
        if label == 'missing-artifact':
            wrong.pop()
        elif label == 'foreign-artifact':
            wrong[0]['workflow_run']['head_sha'] = 'b' * 40
        elif label == 'duplicate-artifact':
            wrong[-1] = copy.deepcopy(wrong[0])
        else:
            wrong[0]['name'] = wrong[0]['name'][:-1] + '2'
        try:
            check_artifacts('mapping', wrong, source, 1, 1)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError('accepted ' + label)
    require(rejected == 13, 'cross-workflow rejection checks incomplete')
    print('Apple cross-workflow protocol: 13 actual rejections')


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    if sys.argv[1:] == ['--self-test']:
        self_test()
        return
    source = os.environ['GITHUB_SHA']
    selected = json.loads(os.environ['APPLE_RUNS'])
    require(set(selected) == set(SPECS) and all(type(n) is int and n > 0 for n in selected.values())
            and len(set(selected.values())) == 6, 'supply exactly six distinct original workflow run IDs')
    result = dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  accepted=False, complete_product=False, physical_device_execution=False,
                  performance_accepted=False, suites={}, problems=[])
    try:
        for kind, run_id in selected.items():
            run = fetch('actions/runs/' + str(run_id))
            attempt = run['run_attempt']
            jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
            check_run(kind, run, jobs, source)
            artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
            check_artifacts(kind, artifacts, source, run_id, attempt)
            verified = [verify_bundle(kind, artifact, source, run_id, attempt) for artifact in artifacts]
            result['suites'][kind] = dict(run_id=run_id, attempt=attempt, jobs=[j['id'] for j in jobs], artifacts=verified)
        result['accepted'] = True
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    output = Path('build/apple-common-evidence');output.mkdir(parents=True, exist_ok=True)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    require(result['accepted'], 'six-suite common-source Apple evidence incomplete')


if __name__ == '__main__':
    main()
