"""Refuse a foreign source file, altered judges, modes and truncated full workflows."""
import os
from pathlib import Path
import guard


def refused(call):
    try:
        call()
    except RuntimeError:
        return
    raise AssertionError('Malformed common-source wrapper accepted')


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    baseline = {'src/owner.c': '100644 blob original', 'tests/old_judge.py': '100644 blob judge'}
    valid = {**baseline, **{path: '100644 blob wrapper' for path in guard.NEW_FILES}}
    guard.validate_tree(baseline, valid)
    for path in baseline:
        bad = dict(valid); bad[path] = '100644 blob changed'
        refused(lambda: guard.validate_tree(baseline, bad))
        bad = dict(valid); del bad[path]
        refused(lambda: guard.validate_tree(baseline, bad))
    for mode in ('120000', '100755', '160000'):
        bad = dict(valid); bad[guard.WORKFLOW] = mode + ' blob wrapper'
        refused(lambda: guard.validate_tree(baseline, bad))
    bad = dict(valid); bad['examples/new_owner.c'] = '100644 blob added'
    refused(lambda: guard.validate_tree(baseline, bad))
    bad = dict(valid); del bad[guard.WORKFLOW]
    refused(lambda: guard.validate_tree(baseline, bad))
    original = guard.git('show', guard.BASE + ':' + guard.ORIGINAL).decode('utf-8')
    current = (guard.ROOT / guard.WORKFLOW).read_text(encoding='utf-8')
    assert guard.project_workflow(current) == original
    # Projection must expose changed budgets, removed original checks and short timeouts.
    for before, after in (
        ('timeout-minutes: 240', 'timeout-minutes: 2'),
        ('python3 tests/reader_windows_preferences/check_commit.py', 'echo omitted-atomic13'),
        ('EXR_SDK_VERSION', 'FORGED_SDK_VERSION'),
    ):
        assert before in current
        assert guard.project_workflow(current.replace(before, after, 1)) != original
    refused(lambda: guard.project_workflow(current.replace(guard.SELF_TEST_STEP, '', 1)))
    print('Common-source projection refusal controls passed; no runtime grant', flush=True)


if __name__ == '__main__':
    main()
