"""Authenticate native startup preparation; original UI business runner projects exactly."""
import subprocess

BASE = '25bc0c67971f81491f50e0a3caaaf7e509bb7e35'
BRANCH = 'codex/reader-apple-simulator-ready'
WORKFLOW = '.github/workflows/reader-apple-simulator-ready.yml'
ORIGINAL = '.github/workflows/reader-apple-page-theme.yml'
RUNNER = 'tests/apple_host/page_theme/run_ui.py'
PREPARATION = '''    if udid:
        command(['open', '-a', 'Simulator', '--args', '-CurrentDeviceUDID', udid])
        command(['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=180)
'''


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_workflow(text, original):
    projected = text.replace(
        'name: Apple page themes with native Simulator preparation',
        'name: Isolated Apple SDK3.41 native page themes', 1).replace(
        'branches: [' + BRANCH + ']', 'branches: [codex/reader-apple-page-theme]', 1)
    require(projected == original, 'original full jobs, assertions or budgets changed')


def validate_runner(text, original):
    require(text.count(PREPARATION) == 1, 'native post-boot preparation differs')
    require(text.replace(PREPARATION, '', 1) == original, 'original UI business runner or budgets changed')


def validate_candidate(root):
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], cwd=root, text=True).splitlines()
    owned = {WORKFLOW, RUNNER, 'tests/apple_host/page_theme/simulator_ready.py', 'tests/apple_host/page_theme/guard.py'}
    require(set(changed) <= owned, 'original application, SDK, UI tests or judges changed')
    original = subprocess.check_output(['git', 'show', BASE + ':' + ORIGINAL], cwd=root, text=True)
    text = (root / WORKFLOW).read_text()
    validate_workflow(text, original)
    mutants = {
        'altered_UI_budget': text.replace('timeout-minutes: 35', 'timeout-minutes: 36'),
        'skipped_original_runner': text.replace('python3 tests/apple_host/page_theme/run_ui.py', 'echo skipped'),
        'changed_summary': text.replace('python3 tests/apple_host/page_theme/summarize.py', 'echo accepted'),
        'changed_native_consumer': text.replace('python3 tests/apple_host/page_theme/run_native.py', 'echo skipped'),
    }
    for name, mutant in mutants.items():
        require(mutant != text, 'inactive negative ' + name)
        try:
            validate_workflow(mutant, original)
        except ValueError:
            continue
        raise ValueError('accepted altered full workflow: ' + name)
    runner = (root / RUNNER).read_text()
    original_runner = subprocess.check_output(['git','show',BASE+':'+RUNNER],cwd=root,text=True)
    validate_runner(runner, original_runner)
    runner_mutants = {
        'missing_post_boot_preparation': runner.replace(PREPARATION, ''),
        'increased_original45s_budget': runner.replace('timeout=45', 'timeout=46'),
        'skipped_original_appearance': runner.replace("    appearance('light')", "    pass # skipped appearance"),
    }
    for name, mutant in runner_mutants.items():
        require(mutant != runner, 'inactive runner negative '+name)
        try:
            validate_runner(mutant, original_runner)
        except ValueError:
            continue
        raise ValueError('accepted altered original runner: '+name)
    return dict(original_source=BASE, application_and_original_judges_unchanged=True,
                original_workflow_projection_exact=True, original_UI_runner_projection_exact=True,
                negative_checks=list(mutants)+list(runner_mutants),
                original_appearance_timeout_seconds=45, diagnostic_run=40205950476)
