"""Native Simulator window preparation; original UI runner and budgets unchanged."""
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = '25bc0c67971f81491f50e0a3caaaf7e509bb7e35'
BRANCH = 'codex/reader-apple-simulator-ready'
WORKFLOW = '.github/workflows/reader-apple-simulator-ready.yml'
ORIGINAL = '.github/workflows/reader-apple-page-theme.yml'
STEP = '''      - name: Prepare the native Simulator window before original initialization
        run: python3 tests/apple_host/page_theme/simulator_ready.py '${{ matrix.platform }}'
'''


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_workflow(text, original):
    require(text.count(STEP) == 1, 'native preparation step differs')
    projected = text.replace(STEP, '', 1).replace(
        'name: Apple page themes with native Simulator preparation',
        'name: Isolated Apple SDK3.41 native page themes', 1).replace(
        'branches: [' + BRANCH + ']', 'branches: [codex/reader-apple-page-theme]', 1)
    require(projected == original, 'original full jobs, assertions or budgets changed')


def validate_candidate(root):
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], cwd=root, text=True).splitlines()
    owned = {WORKFLOW, 'tests/apple_host/page_theme/simulator_ready.py', 'tests/apple_host/page_theme/guard.py'}
    require(set(changed) <= owned, 'original application, SDK, UI tests or judges changed')
    original = subprocess.check_output(['git', 'show', BASE + ':' + ORIGINAL], cwd=root, text=True)
    text = (root / WORKFLOW).read_text()
    validate_workflow(text, original)
    mutants = {
        'missing_preparation': text.replace(STEP, ''),
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
    return dict(original_source=BASE, application_and_original_judges_unchanged=True,
                original_workflow_projection_exact=True, negative_checks=list(mutants),
                original_appearance_timeout_seconds=45, diagnostic_run=40205950476)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    platform, = sys.argv[1:]
    require(platform in ('macos', 'iphone', 'ipad'), 'unknown platform')
    if platform == 'macos':
        print('macOS uses original native appearance path')
        return
    payload = json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','--json'], timeout=180))
    prefix = 'iPhone' if platform == 'iphone' else 'iPad'
    runtime, device, udid = max((runtime, row['name'], row['udid']) for runtime, rows in payload['devices'].items()
                              for row in rows if row.get('isAvailable') and row['name'].startswith(prefix))
    # Keep the window alive while the original runner shuts down, erases and boots
    # this exact device. No appearance retry, assertion change or timeout increase.
    subprocess.run(['open','-a','Simulator','--args','-CurrentDeviceUDID',udid], check=True, timeout=45)
    print(json.dumps(dict(platform=platform, runtime=runtime, device=device, udid=udid,
                          native_window_opened=True, original_initialization_follows=True)), flush=True)


if __name__ == '__main__':
    main()
