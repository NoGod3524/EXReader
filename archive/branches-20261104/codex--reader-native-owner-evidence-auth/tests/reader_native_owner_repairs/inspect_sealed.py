"""One read-only inspection of sealed producer evidence; identities stay distinct."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

import guard

ROOT = guard.ROOT
SOURCE = '4bdf59ade3389b9a3e454511f6a30de7d0ddc112'
RUN = 40245803457
ATTEMPT = 1
INSPECTION_WORKFLOW = '.github/workflows/reader-native-owner-evidence-auth.yml'
SEALED_STRICT = 'tests/reader_native_owner_repairs/strict.py'
HISTORY = 'f535474db5af7993ac911c9941e685abee32f6e7'
OUTPUT = ROOT / 'build/native-owner-inspection'
INSPECTION_PATHS = {
    INSPECTION_WORKFLOW, 'tests/reader_native_owner_repairs/inspect_sealed.py',
    '.github/workflows/reader-native-owner-repairs.yml',
    'docs/reader-native-owner-repairs/PLAN.md',
    'docs/reader-native-owner-repairs/result.json',
    'docs/reader-native-owner-repairs/AUTHENTICATION.md',
    'docs/reader-native-owner-repairs/inspection-result.json',
}
sys.path.insert(0, str(ROOT / 'tests/reader_hosts_integration'))
from final import Bundle, fetch, pages, require


def save(name, value):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def tree(ref):
    result = {}
    for row in git('ls-tree', '-rz', ref).split(b'\0'):
        if row:
            metadata, path = row.split(b'\t', 1)
            result[path.decode()] = metadata.decode()
    return result


def producer_source_proof():
    """Inspect immutable producer Git objects; do not call a runtime entry guard."""
    subprocess.run(['git', 'merge-base', '--is-ancestor', guard.BASE, SOURCE], cwd=ROOT, check=True)
    rows = [line.split('\t', 1) for line in git('diff', '--name-status', guard.BASE, SOURCE).decode().splitlines()]
    guard.validate(rows)
    owners = {path: hashlib.sha256(git('show', SOURCE + ':' + path)).hexdigest() for path in sorted(guard.OWNERS)}
    return dict(guard_kind='native-owner-repairs', source_sha=SOURCE, run_id=str(RUN), attempt=str(ATTEMPT),
        base_sha=guard.BASE, legacy_guard_executed=False, accepted=False, runtime_accepted=False,
        source_preflight_passed=True, owner_sha256=owners, changed_paths=rows,
        frozen_scope='All base paths other than eight enumerated native owner files remain byte-identical, including SDK, seven raw packages, schemas, budgets and original tests')


def inspection_source_proof():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.version_info >= (3, 12), 'Actions Python3.12+ required')
    inspection = os.environ['GITHUB_SHA']
    require(git('rev-parse', 'HEAD').decode().strip() == inspection and inspection != SOURCE, 'actual distinct inspection checkout required')
    subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE, inspection], cwd=ROOT, check=True)
    old, current = tree(SOURCE), tree(inspection)
    changed = {path for path in old.keys() | current.keys() if old.get(path) != current.get(path)}
    require(changed <= INSPECTION_PATHS and INSPECTION_WORKFLOW in changed
            and 'tests/reader_native_owner_repairs/inspect_sealed.py' in changed, 'inspection changed runtime, SDK, raw module or original judge bytes')
    for path in changed:
        require(path in current and current[path].startswith('100644 blob '), 'inspection removed or changed mode/type')
    history_path = 'docs/reader-native-owner-repairs/result.json'
    require(git('show', inspection + ':' + history_path) == git('show', HISTORY + ':' + history_path), 'original accepted:false history changed')
    body = json.loads(git('show', HISTORY + ':' + history_path))
    require(body['accepted'] is False and body['run_conclusion'] == 'failure', 'failed history must remain failed')
    run = fetch('actions/runs/' + os.environ['GITHUB_RUN_ID'])
    require(run['head_sha'] == inspection and run['path'].split('@')[0] == INSPECTION_WORKFLOW
            and run['run_attempt'] == int(os.environ['GITHUB_RUN_ATTEMPT'])
            and run['status'] == 'in_progress' and run['conclusion'] is None, 'actual inspection workflow identity differs')
    jobs = pages('actions/runs/%s/attempts/%s/jobs' % (os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']), 'jobs')
    require(len(jobs) == 1 and jobs[0]['name'] == 'inspect' and jobs[0]['status'] == 'in_progress'
            and jobs[0]['head_sha'] == inspection and jobs[0]['run_attempt'] == int(os.environ['GITHUB_RUN_ATTEMPT'])
            and os.environ['GITHUB_JOB'] == 'inspect', 'one actual read-only inspection job required')
    return dict(source_sha=inspection, run_id=int(os.environ['GITHUB_RUN_ID']),
                attempt=int(os.environ['GITHUB_RUN_ATTEMPT']), job_id=jobs[0]['id'],
                python_version=sys.version,
                workflow=INSPECTION_WORKFLOW, changed_inspection_paths=sorted(changed),
                runtime_source_unchanged=True, environment_identity_rewritten=False)


def validate_producer(run, jobs):
    require(run['id'] == RUN and run['head_sha'] == SOURCE and run['run_attempt'] == ATTEMPT
            and run['path'].split('@')[0] == guard.WORKFLOW
            and run['status'] == 'completed' and run['conclusion'] == 'failure', 'sealed failed producer run changed')
    expected = {'windows': (121326987256, 'success'), 'gtk': (121326987701, 'success'),
                'authenticate': (121330899113, 'failure')}
    require(len(jobs) == 3 and {row['name'] for row in jobs} == set(expected), 'original producer topology differs')
    for row in jobs:
        job_id, conclusion = expected[row['name']]
        require(row['id'] == job_id and row['head_sha'] == SOURCE and row['run_attempt'] == ATTEMPT
                and row['status'] == 'completed' and row['conclusion'] == conclusion, 'original producer job identity/state differs')
        if row['name'] != 'authenticate':
            require(all(step['conclusion'] in ('success', 'skipped') for step in row['steps']), 'hidden runtime failure')


def failed_authentication_proof():
    meta = fetch('actions/artifacts/12618794197')
    require(meta['workflow_run']['id'] == RUN and meta['workflow_run']['head_sha'] == SOURCE
            and meta['size_in_bytes'] == 550
            and meta['digest'] == 'sha256:604f6600009f6b8e7f489e5ebe8af7b5081c64af01ec99be333a5474539ab9da', 'original failed authenticator artifact changed')
    bundle = Bundle(meta)
    try:
        value = bundle.report('failure.json')
        require(value['accepted'] is False and value['source_sha'] == SOURCE and str(value['run_id']) == str(RUN)
                and str(value['attempt']) == str(ATTEMPT)
                and "AttributeError: module 'hashlib' has no attribute 'file_digest'" in value['failure'], 'original strict failure was erased or replaced')
        save('original-failed-authentication.json', value)
        return {key: meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
    finally:
        bundle.close()


def load_sealed_judges(proof):
    original = git('show', SOURCE + ':' + SEALED_STRICT).decode()
    replacements = (
        ("actual_owner = guard.inspect_source()['owner_sha256']['apps/reader/desktop/windows_records_owner.cpp']",
         "actual_owner = producer_source_proof()['owner_sha256']['apps/reader/desktop/windows_records_owner.cpp']"),
        ('        expected = guard.inspect_source()\n', '        expected = producer_source_proof()\n'),
    )
    adapted = original
    for before, after in replacements:
        require(adapted.count(before) == 1, 'sealed source-context substitution differs')
        adapted = adapted.replace(before, after, 1)
    reversed_source = adapted
    for before, after in reversed(replacements):
        require(reversed_source.count(after) == 1, 'sealed source-context reverse substitution differs')
        reversed_source = reversed_source.replace(after, before, 1)
    require(reversed_source == original, 'a sealed native business assertion changed')
    namespace = dict(__name__='sealed_native_owner_business_judges', __file__=str(ROOT / SEALED_STRICT),
                     producer_source_proof=lambda: proof)
    exec(compile(adapted, SEALED_STRICT + ' [explicit sealed producer context]', 'exec'), namespace)
    return namespace, dict(source=SOURCE, path=SEALED_STRICT,
        sha256=hashlib.sha256(original.encode()).hexdigest(), reverse_projection_exact=True,
        substitutions=[dict(before=before, after=after) for before, after in replacements])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--producer-run', type=int, required=True)
    parser.add_argument('--producer-attempt', type=int, required=True)
    parser.add_argument('--producer-source', required=True)
    args = parser.parse_args()
    require((args.producer_run, args.producer_attempt, args.producer_source) == (RUN, ATTEMPT, SOURCE), 'only the authorized sealed third round is accepted')
    environment_before = {key: os.environ.get(key) for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB', 'GITHUB_WORKFLOW')}
    inspection = inspection_source_proof()
    proof = producer_source_proof()
    run = fetch('actions/runs/' + str(RUN))
    jobs = pages('actions/runs/%d/attempts/%d/jobs' % (RUN, ATTEMPT), 'jobs')
    validate_producer(run, jobs)
    failures = []
    for key, replacement in [('head_sha', '0' * 40), ('run_attempt', 2), ('conclusion', 'success'), ('path', INSPECTION_WORKFLOW)]:
        bad = copy.deepcopy(run);bad[key] = replacement
        try:
            validate_producer(bad, jobs)
        except ValueError:
            failures.append(key)
        else:
            raise ValueError('sealed producer identity admitted ' + key)
    failed_artifact = failed_authentication_proof()
    sealed, sealed_projection = load_sealed_judges(proof)
    spec = importlib.util.spec_from_file_location('original_owner_entry_projection', ROOT / 'tests/reader_raw3_common_windows_owner/projection.py')
    projection = importlib.util.module_from_spec(spec);spec.loader.exec_module(projection)
    original = git('show', projection.ORIGINAL + ':' + projection.OLD_AUTH).decode()
    require((ROOT / projection.OLD_AUTH).read_text(encoding='utf-8') == original, 'original Windows business judge changed')
    changes = list(projection.AUTH_CHANGES)
    changes[-1] = (changes[-1][0], changes[-1][1].replace('guard_kind="common-windows-owner"', 'guard_kind="native-owner-repairs-sealed-inspection"'))
    adapted = original
    for before, after in changes:
        require(adapted.count(before) == 1, 'original Windows entry substitution differs')
        adapted = adapted.replace(before, after, 1)
    reverse = adapted
    for before, after in reversed(changes):
        require(reverse.count(after) == 1, 'original Windows inverse entry differs')
        reverse = reverse.replace(after, before, 1)
    require(reverse == original, 'an original Windows owner/kill/capture assertion changed')

    def closed_producer(actual_run, target):
        require(target.run == RUN and target.source == SOURCE, 'original judge received foreign producer arguments')
        actual_jobs = pages('actions/runs/%d/attempts/%d/jobs' % (RUN, ATTEMPT), 'jobs')
        validate_producer(actual_run, actual_jobs)
        return ATTEMPT, next(row for row in actual_jobs if row['name'] == 'windows')

    namespace = dict(__name__='sealed_original_windows_authentication', __file__=str(ROOT / projection.OLD_AUTH),
        common_current_producer=closed_producer, common_source_provenance=sealed['source_provenance'])
    exec(compile(adapted, projection.OLD_AUTH + ' [closed producer entry]', 'exec'), namespace)
    sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
    previous_argv = sys.argv
    try:
        sys.argv = [projection.OLD_AUTH, '--run', str(RUN), '--source', SOURCE]
        namespace['main']()
    finally:
        sys.argv = previous_argv
    sealed['gtk_proof'](RUN, ATTEMPT, SOURCE)
    windows = json.loads((ROOT / 'build/windows-owner-authentication/report.json').read_text())
    gtk = json.loads((ROOT / 'build/native-owner-authentication/gtk.json').read_text())
    require(windows['accepted'] is True and gtk['accepted'] is True, 'sealed native business authentication incomplete')
    patch = git('diff', '--binary', guard.BASE, SOURCE, '--', *sorted(guard.OWNERS))
    (OUTPUT / 'owner.diff').write_bytes(patch)
    require(environment_before == {key: os.environ.get(key) for key in environment_before}, 'inspection rewrote an Actions identity')
    result = dict(accepted=True, runtime_authentication_only=True, producer_source_sha=SOURCE,
        producer_run_id=RUN, producer_attempt=ATTEMPT, original_run_conclusion='failure',
        original_authentication_conclusion='failure', original_history_accepted=False,
        original_same_run_success_granted=False, inspection=inspection,
        producer_jobs=[{key: row[key] for key in ('id', 'name', 'conclusion', 'head_sha', 'run_attempt')} for row in jobs],
        failed_authentication_artifact=failed_artifact, producer_source_policy=proof,
        producer_commit_inspected_without_runtime_guard_entry=True, sealed_native_judge_projection=sealed_projection,
        original_windows_judge=dict(source=projection.ORIGINAL, path=projection.OLD_AUTH,
            sha256=hashlib.sha256(original.encode()).hexdigest(), business_body_reverse_projection_exact=True),
        producer_identity_refusals=failures, windows=windows, gtk=gtk,
        exact_owner_patch=dict(base=guard.BASE, source=SOURCE, paths=sorted(guard.OWNERS),
            bytes=len(patch), sha256=hashlib.sha256(patch).hexdigest(), file='owner.diff'),
        complete_gui_rounds=3, additional_gui_or_build_execution=False,
        original_gtk_off35_rerun=False, original_windows_off_f3_atomic13_rerun=False,
        screen_reader_accepted=False, dpi_150_200_accepted=False, six_platform_accepted=False,
        same_source_bidirectional_accepted=False, complete_product=False)
    save('result.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        save('failure.json', dict(accepted=False, inspection_source_sha=os.environ.get('GITHUB_SHA'),
            inspection_run_id=os.environ.get('GITHUB_RUN_ID'), inspection_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
            producer_source_sha=SOURCE, producer_run_id=RUN, producer_attempt=ATTEMPT,
            original_run_conclusion='failure', complete_product=False, failure=traceback.format_exc()))
        raise
