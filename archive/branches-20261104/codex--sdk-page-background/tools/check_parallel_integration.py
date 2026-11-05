#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only gate for same-source package CI. Does not grant WP16 CPU credit."""
import base64
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
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

# New capabilities introduced by the integrated core, verified at the same source and kept
# outside the ten-package threshold instead of replacing any package check.
SUPPLEMENTAL = {'acroform': ('acroform.yml', 5), 'spacing': ('wp5-border-spacing.yml', 2)}
SUPPLEMENTAL_ARTIFACTS = {
    'acroform': {'EXReader-acroform-corpus', 'EXReader-acroform-Linux',
                 'EXReader-acroform-Windows', 'EXReader-acroform-sanitizer'},
    'spacing': set(),
}
REQUIRED_RUNS = dict(WORKFLOWS, **SUPPLEMENTAL)

# Public SDK surface shared by every package that consumes the default SDK install.
PROTECTED_TREES = ('src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures',
                   '.github/workflows/native.yml', '.github/workflows/reliability.yml', 'bindings')
BASELINE_FILE = 'docs/validation/sdk-baseline.json'
BASELINE_EVIDENCE = {
    'native': '.github/workflows/native.yml',
    'acroform': '.github/workflows/acroform.yml',
    'spacing': '.github/workflows/wp5-border-spacing.yml',
}
# Every package-level SDK guard must name the registered baseline, not a mutable HEAD.
# The Android guard joins this list as soon as its delivery is in the tree; the registry
# records it as pending until then, and a pending guard that already exists is refused.
ANDROID_CONTRACT = ('tools/android_host_evidence.py', r"SDK_BASE\s*=\s*'([0-9a-f]{40})'")
BASELINE_CONTRACTS = (
    ('.github/workflows/wp15-opds.yml', r'BASELINE:\s*([0-9a-f]{40})'),
    ANDROID_CONTRACT,
)


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


def verify_supplemental(kind, source, run, jobs, artifacts):
    workflow, expected_jobs = SUPPLEMENTAL[kind]
    require(run['head_sha'] == source and run['status'] == 'completed' and run['conclusion'] == 'success', kind + ': supplemental run did not succeed at the required source')
    require(run['path'].split('@')[0] == '.github/workflows/' + workflow, kind + ': wrong supplemental workflow')
    require(len(jobs) == expected_jobs and len({job['id'] for job in jobs}) == expected_jobs, kind + ': missing or duplicate supplemental jobs')
    require(all(job['head_sha'] == source and job['status'] == 'completed' and job['conclusion'] == 'success' for job in jobs), kind + ': failed, incomplete or cross-source supplemental job')
    names = {artifact['name'] for artifact in artifacts}
    require(SUPPLEMENTAL_ARTIFACTS[kind] <= names, kind + ': required capability evidence missing')
    require(len({artifact['id'] for artifact in artifacts}) == len(artifacts), kind + ': duplicate capability artifacts')
    for artifact in artifacts:
        require(artifact['expired'] is False and artifact['size_in_bytes'] > 0 and
                artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == run['id'] and
                re.fullmatch('sha256:[0-9a-f]{64}', artifact.get('digest', '')) is not None,
                kind + ': expired, empty or mismatched capability artifact')
    return {'run_id': run['id'], 'attempt': run['run_attempt'], 'workflow': workflow, 'jobs': expected_jobs,
            'artifacts': [{key: artifact[key] for key in ('id', 'name', 'digest', 'size_in_bytes')} for artifact in artifacts]}


def fetch(path):
    url = 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY']
    request = urllib.request.Request(url + ('/' + path if path else ''),
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def download_artifact_zip(artifact_id, output=None):
    """Keep gh authentication/redirect handling; retry only explicit transient HTTP errors."""
    require(type(artifact_id) is int and artifact_id > 0, 'Positive artifact ID required')
    command = ['gh', 'api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/artifacts/{artifact_id}/zip']
    for attempt in range(3):
        if output is not None:
            output.seek(0)
            output.truncate()
        try:
            return subprocess.run(command, stdout=output if output is not None else subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=True, timeout=120).stdout
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or b'').decode('utf-8', errors='replace')
            print(detail, file=sys.stderr, end='')
            status = re.search(r'(?m)^gh: (?:HTTP (429|502|503|504)(?:\s|$)|[^\r\n]*\(HTTP (429|502|503|504)\)\s*$)', detail)
            if status is None or attempt == 2:
                raise
            delay = 2 ** (attempt + 1)
            print(json.dumps({'artifact_retry': {'artifact_id': artifact_id, 'attempt': attempt + 1,
                  'status': int(status.group(1) or status.group(2)), 'delay_seconds': delay}}), flush=True)
            time.sleep(delay)


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


def tree_at(ref, path, cache):
    """Resolve one repository path to its git object SHA at a commit, descending only that path."""
    if (ref, path) in cache:
        return cache[(ref, path)]
    current = fetch('commits/' + ref)['commit']['tree']['sha']
    parts = path.split('/')
    for index, part in enumerate(parts):
        entries = {entry['path']: entry for entry in fetch('git/trees/' + current)['tree']}
        require(part in entries, path + ': missing at ' + ref)
        if index < len(parts) - 1:
            require(entries[part]['type'] == 'tree', path + ': path component is not a tree')
        current = entries[part]['sha']
    cache[(ref, path)] = current
    return current


def baseline_problems(registry, source, protected, contracts, pending=()):
    """Pure comparison against the registered SDK baseline candidate."""
    baseline = registry.get('sdk_baseline') or ''
    require(re.fullmatch('[0-9a-f]{40}', baseline) is not None, 'baseline: require an immutable full SHA')
    require(baseline != source, 'baseline: must be separately accepted, not the summarised source')
    require(set(registry.get('protected_trees') or {}) == set(PROTECTED_TREES), 'baseline: protected tree set drifted')
    require(set(registry.get('evidence') or {}) == set(BASELINE_EVIDENCE), 'baseline: evidence set drifted')
    require(set(pending) <= {ANDROID_CONTRACT[0]}, 'baseline: only the Android guard may be pending')
    require(not (set(pending) & {path for path, _ in contracts}), 'baseline: a contract cannot be active and pending')
    for path in PROTECTED_TREES:
        require(protected.get(path) == registry['protected_trees'][path], 'baseline: ' + path + ' differs from the accepted SDK candidate')
    for path, expected in contracts:
        require(expected == baseline, 'baseline contract: ' + path + ' does not name the registered candidate')
    return baseline


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
    checked = 1 + len(changes)
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
    checked += 1
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
    checked += 2
    android_run = dict(run, path='.github/workflows/wp13-android.yml')
    android_jobs = [dict(jobs[0], id=900)]
    android_artifacts = [dict(artifacts[0], id=900, name='EXReader-WP13-Android')]
    verify('android', source, android_run, android_jobs, android_artifacts)
    checked += 1
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
    checked += 2
    acroform_run = dict(run, path='.github/workflows/acroform.yml')
    acroform_jobs = [dict(jobs[0], id=800 + i) for i in range(5)]
    acroform_artifacts = [dict(artifacts[0], id=1000 + i, name=name)
                          for i, name in enumerate(sorted(SUPPLEMENTAL_ARTIFACTS['acroform']))]
    verify_supplemental('acroform', source, acroform_run, acroform_jobs, acroform_artifacts)
    checked += 1
    spacing_run = dict(run, path='.github/workflows/wp5-border-spacing.yml')
    spacing_jobs = [dict(jobs[0], id=700 + i) for i in range(2)]
    verify_supplemental('spacing', source, spacing_run, spacing_jobs, [])
    checked += 1
    for failure in ('missing supplemental job', 'failed supplemental job', 'wrong supplemental workflow',
                    'supplemental at another source', 'missing capability artifact', 'expired capability artifact',
                    'capability artifact from another run'):
        r, j, a = copy.deepcopy((acroform_run, acroform_jobs, acroform_artifacts))
        if failure == 'missing supplemental job':
            j.pop()
        elif failure == 'failed supplemental job':
            j[0]['conclusion'] = 'failure'
        elif failure == 'wrong supplemental workflow':
            r['path'] = '.github/workflows/native.yml'
        elif failure == 'supplemental at another source':
            r['head_sha'] = '0' * 40
        elif failure == 'missing capability artifact':
            a.pop()
        elif failure == 'expired capability artifact':
            a[0]['expired'] = True
        else:
            a[0]['workflow_run']['id'] = 124
        try:
            verify_supplemental('acroform', source, r, j, a)
        except ValueError:
            continue
        raise AssertionError('Supplemental ' + failure + ' was accepted')
    checked += 7
    baseline = 'c' * 40
    trees = {path: 'd' * 40 for path in PROTECTED_TREES}
    registry = {'sdk_baseline': baseline, 'protected_trees': dict(trees),
                'evidence': {kind: 1 for kind in BASELINE_EVIDENCE}}
    contracts = [(path, baseline) for path, _ in BASELINE_CONTRACTS]
    baseline_problems(registry, source, trees, contracts)
    checked += 1
    baseline_changes = [
        ('baseline is the summarised source', lambda g, t, c: g.update(sdk_baseline=source)),
        ('baseline is not immutable', lambda g, t, c: g.update(sdk_baseline='c' * 12)),
        ('protected tree changed', lambda g, t, c: t.update(src='e' * 40)),
        ('protected path unregistered', lambda g, t, c: (g['protected_trees'].pop('include'), t.pop('include'))),
        ('protected path added', lambda g, t, c: (g['protected_trees'].update(extra='d' * 40), t.update(extra='d' * 40))),
        ('evidence set drifted', lambda g, t, c: g['evidence'].pop('spacing')),
        ('a package guard still names the old baseline', lambda g, t, c: c.__setitem__(0, (c[0][0], 'a' * 40))),
    ]
    for name, change in baseline_changes:
        g, t, c = copy.deepcopy((registry, trees, contracts))
        change(g, t, c)
        try:
            baseline_problems(g, source, t, c)
        except ValueError:
            continue
        raise AssertionError('SDK baseline: ' + name + ' was accepted')
    checked += 1 + len(baseline_changes)
    checked += 1
    for name, pending, extra in (('a pending guard is also active', (ANDROID_CONTRACT[0],), []),
                                 ('a foreign guard is pending', ('tools/other_guard.py',), [])):
        try:
            baseline_problems(registry, source, trees, contracts + [(path, baseline) for path in extra], pending)
        except ValueError:
            continue
        raise AssertionError('SDK baseline: ' + name + ' was accepted')
    checked += 2
    return {'passed': True, 'checks': checked,
            'integration_accepted': False, 'source_sha': os.environ['GITHUB_SHA'],
            'scope': 'gate protocol only'}


def verify_baseline(source):
    registry = json.loads(Path(BASELINE_FILE).read_text(encoding='utf-8'))
    baseline = registry.get('sdk_baseline') or ''
    require(re.fullmatch('[0-9a-f]{40}', baseline) is not None, 'baseline: require an immutable full SHA')
    comparison = fetch('compare/' + baseline + '...' + source)
    require(comparison.get('status') in ('ahead', 'identical') and comparison.get('merge_base_commit', {}).get('sha') == baseline,
            'baseline: source does not descend from the accepted SDK candidate')
    cache = {}
    protected = {path: tree_at(source, path, cache) for path in PROTECTED_TREES}
    pending = tuple(registry.get('pending_contracts') or ())
    for path in pending:
        require(not Path(path).exists(), 'baseline contract: ' + path + ' is present but still registered as pending')
    contracts = []
    for path, pattern in BASELINE_CONTRACTS:
        require(Path(path).is_file(), 'baseline contract: missing ' + path)
        found = re.search(pattern, Path(path).read_text(encoding='utf-8'), re.MULTILINE)
        require(found is not None, 'baseline contract: no fixed SDK baseline in ' + path)
        contracts.append((path, found.group(1)))
    baseline = baseline_problems(registry, source, protected, contracts, pending)
    evidence, seen = {}, set()
    for kind, workflow in BASELINE_EVIDENCE.items():
        run_id = registry['evidence'][kind]
        require(type(run_id) is int and run_id > 0 and run_id not in seen, 'baseline evidence: duplicate or invalid run id')
        seen.add(run_id)
        run = fetch('actions/runs/' + str(run_id))
        require(run['head_sha'] == baseline and run['path'].split('@')[0] == workflow and
                run['status'] == 'completed' and run['conclusion'] == 'success',
                'baseline evidence: ' + kind + ' did not succeed at the registered candidate')
        evidence[kind] = {'run_id': run_id, 'attempt': run['run_attempt'], 'workflow': workflow, 'head_sha': run['head_sha']}
    header = base64.b64decode(fetch('contents/include/exr/base.h?ref=' + baseline)['content']).decode('utf-8')
    version = re.search(r'#define EXR_VERSION "([^"]+)"', header)
    abi = re.search(r'#define EXR_ABI_VERSION (\d+)u', header)
    require(version is not None and abi is not None, 'baseline: no public version or ABI declaration')
    require(registry.get('sdk_version') == version.group(1) and registry.get('sdk_abi') == int(abi.group(1)),
            'baseline: registered SDK version or ABI does not match the candidate headers')
    return {'candidate': baseline, 'protected_trees': protected, 'contracts': dict(contracts),
            'pending_contracts': list(pending), 'evidence': evidence,
            'sdk_version': version.group(1), 'sdk_abi': int(abi.group(1))}


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Run only in GitHub Actions')
    output = Path(sys.argv[2])
    require(not output.exists(), 'Preserve previous evidence')
    output.parent.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == 'selftest':
        report = selftest()
    elif sys.argv[1] == 'baseline':
        source = os.environ['EXPECTED_SOURCE']
        report = {'accepted': False, 'source_sha': source, 'scope': 'registered SDK baseline chain only',
                  'complete_product': False, 'wp16_accepted': False, 'wp16_cpu_credit_seconds': 0}
        try:
            require(re.fullmatch('[0-9a-f]{40}', source) is not None, 'Require an immutable full source SHA')
            report['sdk_baseline'] = verify_baseline(source)
            report['accepted'] = True
        except (ValueError, KeyError, TypeError, OSError) as error:
            report['refusal'] = str(error)
    else:
        source = os.environ['EXPECTED_SOURCE']
        report = {'accepted': False, 'source_sha': source, 'scope': 'declared integrated package scopes only',
                  'complete_product': False, 'wp16_accepted': False, 'wp16_cpu_credit_seconds': 0, 'runs': {}}
        try:
            require(re.fullmatch('[0-9a-f]{40}', source) is not None, 'Require an immutable full source SHA')
            requested = json.loads(os.environ['SOURCE_RUNS'])
            require(set(requested) == set(REQUIRED_RUNS) and len(set(requested.values())) == len(REQUIRED_RUNS) and
                    all(type(value) is int and value > 0 for value in requested.values()),
                    'Require all ten package run IDs plus the supplemental capability runs')
            report['sdk_baseline'] = verify_baseline(source)
            report['supplemental'] = {}
            for kind, run_id in requested.items():
                path = f'actions/runs/{run_id}'
                run = fetch(path)
                jobs = pages(path + f"/attempts/{run['run_attempt']}/jobs", 'jobs')
                artifacts = pages(path + '/artifacts', 'artifacts')
                if kind in SUPPLEMENTAL:
                    report['supplemental'][kind] = verify_supplemental(kind, source, run, jobs, artifacts)
                    continue
                report['runs'][kind] = verify(kind, source, run, jobs, artifacts)
            report['accepted'] = True
        except (ValueError, KeyError, TypeError, OSError) as error:
            report['refusal'] = str(error)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('runs',)}))
    return 0 if report.get('accepted', report.get('passed', False)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
