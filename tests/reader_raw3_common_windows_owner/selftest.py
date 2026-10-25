"""Actions-only actual-tree and exact-projection refusal controls."""
import json
import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

import guard
from projection import (OLD_AUTH, OLD_WORKFLOW, ORIGINAL, WORKFLOW, adapt_auth, project_auth,
                        project_workflow, current_producer_identity)

TREE_CASES = {
    'sdk': ('include/exr/base.h', '100644', b'changed SDK\n', 'component:sdk:'),
    'raw_module': ('apps/reader/revisions/include/reader_revisions.h', '100644', b'changed raw\n', 'component:raw_seven:'),
    'owner': ('apps/reader/desktop/windows_records_owner.cpp', '100644', b'changed owner\n', 'component:windows_owner:'),
    'host_driver': ('tests/reader_windows_raw3/host_build.py', '100644', b'pass\n', 'component:original_suites_and_drivers:'),
    'old_auth': (OLD_AUTH, '100644', b'pass\n', 'old_entry_changed:'),
    'unknown_path': ('tests/reader_raw3_common_windows_owner_extra/a.py', '100644', b'pass\n', 'unapproved:'),
    'symlink': ('tests/reader_raw3_common_windows_owner/README.md', '120000', b'../../src/core.c', 'mode_or_deletion:'),
    'executable': ('tests/reader_raw3_common_windows_owner/README.md', '100755', b'document\n', 'mode_or_deletion:'),
}
WORKFLOW_CASES = {
    'driver_removed': ('python tests/reader_windows_raw3/host_build.py', 'echo fake-host'),
    'guard_removed': ('python tests/reader_raw3_common_windows_owner/guard.py', 'echo no-guard'),
    'timeout_changed': ('timeout-minutes: 90', 'timeout-minutes: 91'),
    'artifact_relaxed': ('if-no-files-found: error', 'if-no-files-found: warn'),
    'strict_removed': ('python tests/reader_raw3_common_windows_owner/strict.py', 'echo no-auth'),
    'source_override': ('--source "$GITHUB_SHA"', '--source "old-source"'),
}
EXPECTED = set(TREE_CASES) | set(WORKFLOW_CASES) | {'event_identity', 'auth_body_changed', 'auth_old_entry_retained'}


def mutation(source, path, mode, data):
    with tempfile.TemporaryDirectory(prefix='common-owner-negative-') as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'index'))
        guard.git('read-tree', source, env=env)
        oid = guard.git('hash-object', '-w', '--stdin', data=data).decode().strip()
        guard.git('update-index', '--add', '--cacheinfo', mode + ',' + oid + ',' + path, env=env)
        return guard.git('write-tree', env=env).decode().strip()


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    source = guard.git('rev-parse', 'HEAD').decode().strip()
    guard.event_identity(source, os.environ['GITHUB_SHA'])
    original_index = guard.git('write-tree')
    if guard.inspect_tree(source)['errors']:
        raise RuntimeError('positive common composition is not approved')
    workflow = guard.git('show', source + ':' + WORKFLOW).decode('utf-8')
    original_workflow = guard.git('show', ORIGINAL + ':' + OLD_WORKFLOW).decode('utf-8')
    original_auth = guard.git('show', ORIGINAL + ':' + OLD_AUTH).decode('utf-8')
    adapted = adapt_auth(original_auth)
    if project_workflow(workflow) != original_workflow or project_auth(adapted) != original_auth:
        raise RuntimeError('positive source projection differs')
    controls = []
    for name, (path, mode, body, prefix) in TREE_CASES.items():
        tree = mutation(source, path, mode, body)
        errors = guard.inspect_tree(tree)['errors']
        if not any(item.startswith(prefix) for item in errors):
            raise RuntimeError('actual Git tree mutation accepted: ' + name)
        controls.append({'name': name, 'tree': tree, 'rejected': True})
    for name, (before, after) in WORKFLOW_CASES.items():
        if before not in workflow:
            raise RuntimeError('negative workflow marker missing: ' + name)
        try:
            projected = project_workflow(workflow.replace(before, after, 1))
        except RuntimeError:
            projected = None
        if projected == original_workflow:
            raise RuntimeError('workflow mutation accepted: ' + name)
        controls.append({'name': name, 'rejected': True})
    try:
        guard.event_identity(source, '0' * 40)
    except RuntimeError:
        pass
    else:
        raise RuntimeError('event source override accepted')
    context = {'source_sha': 'synthetic-source', 'run_id': '123', 'attempt': '1', 'job': 'authenticate'}
    args = SimpleNamespace(source='synthetic-source', run=123)
    run = {'head_sha': args.source, 'run_attempt': 1, 'status': 'in_progress', 'conclusion': None, 'path': WORKFLOW}
    jobs = {'total_count': 2, 'jobs': [
        {'name': 'host', 'head_sha': args.source, 'run_attempt': 1, 'status': 'completed', 'conclusion': 'success'},
        {'name': 'authenticate', 'head_sha': args.source, 'run_attempt': 1, 'status': 'in_progress', 'conclusion': None}]}
    if current_producer_identity(run, args, context, jobs)[0] != 1:
        raise RuntimeError('positive current-entry metadata refused')
    bad = []
    for key, value in [('head_sha', 'foreign'), ('run_attempt', 2), ('status', 'completed'), ('path', OLD_WORKFLOW)]:
        changed = dict(run, **{key: value})
        bad.append((changed, jobs))
    for index, field, value in [(0, 'conclusion', 'failure'), (0, 'run_attempt', 2),
                                (1, 'status', 'completed')]:
        changed = copy.deepcopy(jobs)
        changed['jobs'][index][field] = value
        bad.append((run, changed))
    bad.append((run, {'total_count': 1, 'jobs': jobs['jobs'][:1]}))
    for wrong_run, wrong_jobs in bad:
        try:
            current_producer_identity(wrong_run, args, context, wrong_jobs)
        except RuntimeError:
            pass
        else:
            raise RuntimeError('foreign/stale/failed/current-job metadata accepted')
    controls.append({'name': 'event_identity', 'rejected': True, 'current_entry_metadata_refusals': len(bad)})
    marker = "need(value['ok'] is True"
    if marker not in adapted or project_auth(adapted.replace(marker, "need(value['ok'] is False", 1)) == original_auth:
        raise RuntimeError('changed owner evidence assertion was accepted')
    controls.append({'name': 'auth_body_changed', 'rejected': True})
    try:
        project_auth(original_auth)
    except RuntimeError:
        pass
    else:
        raise RuntimeError('unadapted standalone run entry was accepted')
    controls.append({'name': 'auth_old_entry_retained', 'rejected': True})
    if guard.git('write-tree') != original_index or guard.git('rev-parse', 'HEAD').decode().strip() != source:
        raise RuntimeError('negative controls changed checkout/index')
    report = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'negative_controls_passed': True,
              'checkout_and_index_unchanged': True, 'controls': controls,
              'accepted': False, 'complete_product': False}
    out = guard.ROOT / 'build/windows-raw3-preflight'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'common-negative.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
