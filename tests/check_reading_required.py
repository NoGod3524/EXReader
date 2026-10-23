#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic metadata protocol checks, not SDK or real-document acceptance."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from reading_required import GROUPS, ci_identity, expected_artifacts, verify_metadata

source, run, attempt = 'a' * 40, '12', '3'
needs = {key: {'result': 'success'} for key in GROUPS}
artifacts = [{'id': index, 'name': name, 'expired': False, 'size_in_bytes': 10,
              'workflow_run': {'head_sha': source, 'id': int(run)}, 'digest': 'sha256:' + 'b' * 64}
             for index, name in enumerate(sorted(expected_artifacts(run, attempt)))]
assert len(verify_metadata(source, run, attempt, needs, artifacts)) == 8
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
print(json.dumps({'accepted': True, 'checks': checks, 'sdk_credit': 0, 'real_document_credit': 0}))
