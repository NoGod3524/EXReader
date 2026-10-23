#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic metadata protocol checks, not SDK or real-document acceptance."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from reading_required import (GROUPS, ci_identity, expected_artifacts, verify_metadata,
                              expected_jobs, verify_jobs, workflow_identity, verify_publisher)

source, run, attempt = 'a' * 40, '12', '3'
needs = {key: {'result': 'success'} for key in GROUPS}
artifacts = [{'id': index, 'name': name, 'expired': False, 'size_in_bytes': 10,
              'workflow_run': {'head_sha': source, 'id': int(run)}, 'digest': 'sha256:' + 'b' * 64}
             for index, name in enumerate(sorted(expected_artifacts(run, attempt)))]
assert len(verify_metadata(source, run, attempt, needs, artifacts)) == 18
checks = 1
mutations = [lambda n, a: n.pop('native'), lambda n, a: n.update(unexpected={'result': 'success'}),
             lambda n, a: a.pop(), lambda n, a: a.append(copy.deepcopy(a[0])),
             lambda n, a: a[0].update(expired=True), lambda n, a: a[0].update(size_in_bytes=0),
             lambda n, a: a[0].update(digest=None),
             lambda n, a: a[0]['workflow_run'].update(head_sha='c' * 40),
             lambda n, a: a[0]['workflow_run'].update(id=13),
             lambda n, a: a[0].update(name=a[0]['name'][:-1] + '2')]
for group in GROUPS:
    for status in ('failure', 'cancelled', 'skipped'):
        mutations.append(lambda n, a, g=group, s=status: n[g].update(result=s))
for change in mutations:
    n, a = copy.deepcopy((needs, artifacts)); change(n, a)
    try:
        verify_metadata(source, run, attempt, n, a)
    except (ValueError, KeyError, TypeError):
        checks += 1
    else:
        raise AssertionError('accepted invalid upstream evidence')
for nested in (False, True):
    row = {'source_sha': source, 'run_id': run, 'run_attempt': attempt,
           'ci': {'GITHUB_RUN_ID': run, 'GITHUB_RUN_ATTEMPT': attempt}}
    ci_identity(row, source, run, attempt, nested); checks += 1
    for field, value in (('source', 'c' * 40), ('run', '13'), ('attempt', '2')):
        changed = copy.deepcopy(row)
        if field == 'source': changed['source_sha'] = value
        elif nested: changed['ci']['GITHUB_RUN_ID' if field == 'run' else 'GITHUB_RUN_ATTEMPT'] = value
        else: changed['run_id' if field == 'run' else 'run_attempt'] = value
        try: ci_identity(changed, source, run, attempt, nested)
        except ValueError: checks += 1
        else: raise AssertionError('accepted foreign report identity')
record = {'id': int(run), 'run_attempt': int(attempt), 'path': '.github/workflows/reading-required.yml',
          'event': 'push', 'head_sha': source}
assert workflow_identity(record, source, run, attempt, ['b' * 40]) == source; checks += 1
record.update(event='pull_request', head_sha='c' * 40)
assert workflow_identity(record, source, run, attempt, ['b' * 40, 'c' * 40]) == 'c' * 40; checks += 1
pr_artifacts = copy.deepcopy(artifacts)
for item in pr_artifacts: item['workflow_run']['head_sha'] = 'c' * 40
assert len(verify_metadata(source, run, attempt, needs, pr_artifacts, 'c' * 40)) == 18; checks += 1
for changes, parents in [({}, ['b' * 40]), ({}, ['b' * 40, 'd' * 40]),
                         ({'run_attempt': 2}, ['b' * 40, 'c' * 40]),
                         ({'path': '.github/workflows/native.yml'}, ['b' * 40, 'c' * 40]),
                         ({'event': 'workflow_dispatch'}, ['b' * 40, 'c' * 40])]:
    mutant = dict(record, **changes)
    try: workflow_identity(mutant, source, run, attempt, parents)
    except ValueError: checks += 1
    else: raise AssertionError('accepted unrelated tested merge/run')
jobs = [{'id': index, 'name': name, 'run_id': int(run), 'run_attempt': int(attempt),
         'head_sha': source, 'status': 'completed', 'conclusion': 'success'}
        for index, name in enumerate(sorted(expected_jobs() | {'reading-required'}))]
assert len(verify_jobs(source, run, attempt, jobs)) == 17; checks += 1
for change in [lambda j: j.pop(), lambda j: j.append(copy.deepcopy(j[0])),
               lambda j: j[0].update(run_attempt=2), lambda j: j[0].update(run_id=13),
               lambda j: j[0].update(head_sha='d' * 40),
               lambda j: j[0].update(name='unexpected'),
               lambda j: j[0].update(status='in_progress'),
               lambda j: j[0].update(conclusion='failure'),
               lambda j: j[0].update(conclusion='skipped')]:
    mutant = copy.deepcopy(jobs); change(mutant)
    try: verify_jobs(source, run, attempt, mutant)
    except ValueError: checks += 1
    else: raise AssertionError('accepted missing or reused upstream job')
ruleset = json.loads((Path(__file__).resolve().parents[1] / 'docs/reading-required-ruleset.json').read_text())
publisher = {'id': 1, 'name': 'reading-required', 'head_sha': source,
             'app': {'id': 15368, 'slug': 'github-actions'}}
verify_publisher(publisher, source, ruleset); checks += 1
for change in [lambda p: p['app'].update(id=1), lambda p: p['app'].update(slug='foreign-app'),
               lambda p: p.update(head_sha='d' * 40), lambda p: p.update(name='other-check')]:
    mutant = copy.deepcopy(publisher); change(mutant)
    try: verify_publisher(mutant, source, ruleset)
    except ValueError: checks += 1
    else: raise AssertionError('accepted foreign check publisher')
print(json.dumps({'accepted': True, 'checks': checks, 'sdk_credit': 0, 'real_document_credit': 0}))
