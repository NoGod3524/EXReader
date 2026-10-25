"""Actions-only rejection checks for exact Apple projections and new guard provenance."""
import copy
import hashlib
import os

from guard import (BASE, BRANCH, FAMILY, HERE, KIND, NEW_FILES, ROOT, SDK, SELF_TEST,
                   SPECS, project_workflow, require, validate_record, validate_tree, workflow_identity)


def rejects(call, label):
    try:
        call()
    except (ValueError, KeyError):
        return
    raise AssertionError('Guard accepted mutation: ' + label)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    checks = []
    for mode, spec in SPECS.items():
        original = (ROOT / '.github/workflows' / spec[0]).read_text(encoding='utf-8')
        text = (ROOT / '.github/workflows' / spec[1]).read_text(encoding='utf-8')

        def validate(candidate):
            require(project_workflow(mode, candidate) == original, 'Original full workflow differs')

        validate(text)
        edits = {
            'dropped_new_selfcheck': (SELF_TEST, ''),
            'permissions': ('contents: read', 'contents: write'),
            'changed_actual_branch': (BRANCH, 'codex/fake-branch'),
            'skipped_common_guard': ('python3 ' + HERE + 'guard.py', 'echo accepted'),
            'skipped_common_verify': ('python3 ' + HERE + 'verify.py', 'echo accepted'),
        }
        if mode == 'records':
            edits.update({
                'case180': ('-default-test-execution-time-allowance 180', '-default-test-execution-time-allowance 181'),
                'case300': ('-maximum-test-execution-time-allowance 300', '-maximum-test-execution-time-allowance 301'),
                'sdk_selection': ("&& '3.41.0'", "&& '3.40.0'"),
                'theme_selection': ("&& 'ON'", "&& 'OFF'"),
                'native19': ('python3 tests/apple_host/reading/run_native.py', 'echo skipped'),
                'collector': ('python3 tests/apple_host/reading/collect_reading_evidence.py', 'echo skipped'),
                'original_strict': ('python3 tests/apple_host/reading/summarize.py', 'echo skipped'),
                'seven_case_source': ('tests/apple_host/reading/ui', 'tests/fake-ui'),
            })
        elif mode == 'macos':
            edits.update({'complete_raw_runner': ('python3 tests/apple_host/raw3/run.py', 'echo skipped'),
                          'native_budget': ('timeout-minutes: 60', 'timeout-minutes: 61')})
        else:
            edits.update({'original_OFF7_raw6': ('python3 tests/reader_apple_records_ready/raw3_driver.py', 'echo skipped'),
                          'original_strict': ('python3 tests/apple_host/raw3/ios/reading/verify.py', 'echo skipped'),
                          'ui_budget': ('timeout-minutes: 75', 'timeout-minutes: 76'),
                          'theme_ON': ("EXR_APPLE_PAGE_THEME: 'ON'", "EXR_APPLE_PAGE_THEME: 'OFF'")})
        for label, (old, new) in edits.items():
            mutant = text.replace(old, new)
            require(mutant != text, 'Inactive rejection: ' + label)
            rejects(lambda: validate(mutant), mode + ':' + label)
            checks.append(mode + ':' + label)
        source, run, attempt = 'a' * 40, '123', '1'
        record = dict(guard_kind=KIND, mode=mode, target='macos', source_sha=source,
                      run_id=run, attempt=attempt, composition_source=BASE, sdk_source=SDK,
                      exact_raw_family_source=FAMILY, sdk_version='3.41.0', sdk_abi=1,
                      branch=BRANCH, original_guard_executed=False,
                      all_existing_blobs_and_modes_unchanged=True, original_full_workflow_projection_exact=True,
                      accepted=False, complete_product=False, physical_device_execution=False,
                      guard_sha256=hashlib.sha256((ROOT / HERE / 'guard.py').read_bytes()).hexdigest(),
                      **workflow_identity(mode))
        validate_record(record, mode, 'macos', source, run, attempt)
        for field, value in (('guard_kind', 'old-historical-guard'), ('source_sha', 'b' * 40),
                             ('original_guard_executed', True), ('workflow', spec[0]),
                             ('guard_sha256', '0' * 64), ('target', 'iphonesimulator'),
                             ('attempt', '2'), ('accepted', True)):
            mutant = copy.deepcopy(record)
            mutant[field] = value
            rejects(lambda: validate_record(mutant, mode, 'macos', source, run, attempt), mode + ':' + field)
            checks.append(mode + ':guard:' + field)
    baseline = {'original-driver.py': '100644 blob ' + '1' * 40}
    current = dict(baseline, **{path: '100644 blob ' + '2' * 40 for path in NEW_FILES})
    validate_tree(baseline, current)
    extension = 'tests/another_reviewed_wrapper/guard.py'
    extended = dict(current, **{extension: '100644 blob ' + '5' * 40})
    validate_tree(baseline, extended, {extension})
    rejects(lambda: validate_tree(baseline, extended), 'extension_without_explicit_review')
    rejects(lambda: validate_tree(baseline, current, {extension}), 'missing_reviewed_extension')
    checks.extend(('extension_without_explicit_review', 'missing_reviewed_extension'))
    for label, candidate in (
            ('changed_driver_blob', dict(current, **{'original-driver.py': '100644 blob ' + '3' * 40})),
            ('changed_driver_mode', dict(current, **{'original-driver.py': '100755 blob ' + '1' * 40})),
            ('unowned_file', dict(current, **{'apps/reader/fake.c': '100644 blob ' + '4' * 40})),
            ('missing_original', {key: value for key, value in current.items() if key != 'original-driver.py'}),
            ('missing_wrapper', {key: value for key, value in current.items() if key != HERE + 'verify.py'})):
        rejects(lambda: validate_tree(baseline, candidate), label)
        checks.append(label)
    print({'accepted': True, 'scope': 'new common Apple guard rejection tests only', 'checks': checks}, flush=True)


if __name__ == '__main__':
    main()
