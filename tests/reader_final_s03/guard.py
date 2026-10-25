#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud guard: package scope, pinned producer/SDK sources and tool capability.

Runs on a cheap runner before the macOS job so a wrong assumption about the
producer commit or the workflow trigger fails in minutes instead of after a full
SDK and .app build. It never writes outside build/s03-guard/.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import spec

ALLOWED_PATHS = (
    'tests/reader_final_s03/',
    'docs/reader-final-s03/',
    '.github/workflows/reader-final-s03.yml',
    'HANDOFF-RESULT.md',
)
PACKAGE_FILES = ('spec.py', 'bundle.py', 'identity.py', 'smoke.py', 'aggregate.py',
                 'guard.py', 'check_spec.py', 'README.md')
WORKFLOW = REPO / '.github/workflows/reader-final-s03.yml'
VALIDATION = REPO / 'docs/reader-final-s03/validation.json'
GUARD_OUTPUT = REPO / 'build/s03-guard'
PROTECTED_PATHS = ('include', 'src', 'cmake', 'CMakeLists.txt', 'bindings', 'licenses',
                   'tests/fixtures', 'apps', 'examples', 'extras')


def git(*arguments):
    done = subprocess.run(['git', *arguments], cwd=str(REPO), capture_output=True, text=True,
                          errors='replace')
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def workflow_problems(text):
    problems = []
    if 'branches: [codex/reader-fw-s03]' not in text:
        problems.append('workflow_branch_scope')
    if re.search(r'(?m)^\s*pull_request\s*:', text):
        problems.append('workflow_pull_request_trigger')
    for token in sorted(set(re.findall(r'codex/[A-Za-z0-9._-]+', text))):
        if token != spec.BRANCH:
            problems.append('workflow_foreign_branch:' + token)
    match = re.search(r'(?m)^\s*paths:\s*\n((?:\s*-\s*.+\n)+)', text)
    if match is None:
        problems.append('workflow_paths_missing')
    else:
        entries = [line.strip()[1:].strip().strip("'\"")
                   for line in match.group(1).splitlines() if line.strip()]
        if not entries:
            problems.append('workflow_paths_empty')
        for entry in entries:
            if not entry.startswith(('tests/reader_final_s03/', '.github/workflows/reader-final-s03.yml')):
                problems.append('workflow_path_scope:' + entry)
    if 'runs-on: macos-15' not in text:
        problems.append('workflow_runner')
    if 'timeout-minutes:' not in text:
        problems.append('workflow_timeout')
    if 'actions/upload-artifact@v4' not in text:
        problems.append('workflow_artifact')
    if 'fetch-depth: 0' not in text:
        problems.append('workflow_fetch_depth')
    return problems


def validation_problems(value):
    problems = []
    if not isinstance(value, dict):
        return ['validation_json_root']
    accepted = value.get('accepted')
    if not isinstance(accepted, bool):
        problems.append('validation_accepted_flag')
    if value.get('complete_product') is not False:
        problems.append('validation_complete_product')
    if accepted:
        if not value.get('source_sha'):
            problems.append('validation_source_sha')
        if not value.get('runs'):
            problems.append('validation_runs')
    else:
        if not value.get('pending'):
            problems.append('validation_pending_list')
    return problems


def main():
    problems = []
    guard = {'schema': 1, 'package': 'tests/reader_final_s03', 'branch': spec.BRANCH,
             'start_sha': spec.START_SHA, 'producer_sha': spec.PRODUCER_SHA,
             'sdk_source_sha': spec.SDK_SHA, 'sdk_version': spec.SDK_VERSION,
             'runner': {'sha': os.environ.get('GITHUB_SHA'),
                        'ref': os.environ.get('GITHUB_REF_NAME'),
                        'run': os.environ.get('GITHUB_RUN_ID'),
                        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}}

    head = git('rev-parse', 'HEAD')
    if head[0] != 0 or head[1] != os.environ.get('GITHUB_SHA'):
        problems.append('head_is_not_the_triggering_commit')
    reference = os.environ.get('GITHUB_REF_NAME')
    if reference and reference != spec.BRANCH:
        problems.append('branch:' + reference)

    code, changed, _ = git('diff', '--name-only', spec.START_SHA, 'HEAD')
    if code != 0:
        problems.append('start_sha_diff_failed')
        changed = ''
    files = [line for line in changed.splitlines() if line.strip()]
    for path in files:
        if not path.startswith(ALLOWED_PATHS) and path not in ALLOWED_PATHS:
            problems.append('write_outside_package:' + path)
    if not files:
        problems.append('package_changes_missing')
    guarded = [path for path in files
               if path.startswith(tuple(item + '/' for item in PROTECTED_PATHS))
               or path in PROTECTED_PATHS]
    if guarded:
        problems.append('protected_path_written:' + ','.join(guarded))

    for relative in PACKAGE_FILES:
        if not (HERE / relative).is_file():
            problems.append('package_file_missing:' + relative)

    for sha, label in ((spec.PRODUCER_SHA, 'producer'), (spec.SDK_SHA, 'sdk'),
                       (spec.FROZEN_SDK_340, 'frozen_sdk')):
        code, _, _ = git('cat-file', '-e', sha + '^{commit}')
        if code != 0:
            problems.append('commit_missing:' + label)
    code, _, _ = git('merge-base', '--is-ancestor', spec.SDK_SHA, spec.PRODUCER_SHA)
    if code != 0:
        problems.append('sdk_is_not_an_ancestor_of_the_producer')

    code, sdk_diff, _ = git('diff', '--name-only', spec.SDK_SHA, spec.PRODUCER_SHA, '--',
                            *spec.SDK_SOURCE_PATHS)
    if code != 0 or sdk_diff.strip():
        problems.append('producer_sdk_tree_differs:' + sdk_diff.replace('\n', ','))

    for relative, flag in spec.PRODUCER_REQUIRED_FLAGS:
        code, text, _ = git('show', spec.PRODUCER_SHA + ':' + relative)
        if code != 0:
            problems.append('producer_tool_missing:' + relative)
        elif flag not in text:
            problems.append('producer_tool_flag_missing:' + relative + ':' + flag)
    for relative in spec.PRODUCER_REQUIRED_FILES:
        code, _, _ = git('cat-file', '-e', spec.PRODUCER_SHA + ':' + relative)
        if code != 0:
            problems.append('producer_file_missing:' + relative)
    code, self_test, _ = git('show', spec.PRODUCER_SHA + ':examples/apple/LegacySelfTest.swift')
    if code != 0 or spec.SELF_TEST_MINIMUM_MARKER not in self_test:
        problems.append('producer_self_test_marker_missing')

    artifact = spec.PRODUCER_ARTIFACT
    if not (isinstance(artifact.get('bytes'), int) and artifact['bytes'] > 0):
        problems.append('pinned_artifact_bytes')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest', '')):
        problems.append('pinned_artifact_digest')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', artifact.get('expires_at', '')):
        problems.append('pinned_artifact_expiry')

    if WORKFLOW.is_file():
        problems += workflow_problems(WORKFLOW.read_text(encoding='utf-8'))
    else:
        problems.append('workflow_missing')

    value = None
    if VALIDATION.is_file():
        try:
            value = json.loads(VALIDATION.read_text(encoding='utf-8'))
        except ValueError:
            problems.append('validation_json_parse')
        else:
            problems += validation_problems(value)
            for key in ('producer_source_sha', 'sdk_source_sha'):
                recorded = value.get(key)
                expected = spec.PRODUCER_SHA if key == 'producer_source_sha' else spec.SDK_SHA
                if recorded is not None and recorded != expected:
                    problems.append('validation_' + key + ':' + str(recorded))
    else:
        problems.append('validation_json_missing')

    guard['changed_paths'] = files
    guard['validation_state'] = None if value is None else {
        'accepted': value.get('accepted'), 'source_sha': value.get('source_sha'),
        'runs': len(value.get('runs') or []), 'pending': len(value.get('pending') or [])}
    guard['producer_artifact'] = artifact
    guard['accepted'] = not problems
    guard['problems'] = problems
    GUARD_OUTPUT.mkdir(parents=True, exist_ok=True)
    (GUARD_OUTPUT / 'guard.json').write_text(json.dumps(guard, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(guard, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
