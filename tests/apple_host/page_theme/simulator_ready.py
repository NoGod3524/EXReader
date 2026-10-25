"""Authenticate native startup preparation; original UI business runner projects exactly."""
import subprocess
import json
import os
import time

BASE = '25bc0c67971f81491f50e0a3caaaf7e509bb7e35'
BRANCH = 'codex/reader-apple-simulator-ready'
WORKFLOW = '.github/workflows/reader-apple-simulator-ready.yml'
ORIGINAL = '.github/workflows/reader-apple-page-theme.yml'
RUNNER = 'tests/apple_host/page_theme/run_ui.py'
PREPARATION = '''    if udid:
        from simulator_ready import prepare_service
        prepare_service(udid, out)
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
                original_appearance_timeout_seconds=45, query_only_readiness_limit_seconds=180,
                diagnostic_run=40208997832)


def prepare_service(udid, out):
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    evidence=dict(ready=False,diagnostic_run=40208997832,query_only=True,
                  source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'],device=udid,commands=[])
    path=out/'appearance-service-preparation.json'
    def save():
        path.write_text(json.dumps(evidence,indent=2)+'\n')
    def execute(argv,timeout):
        started=time.monotonic()
        row=dict(argv=argv,timeout_seconds=timeout)
        try:
            proc=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
            row.update(exit_code=proc.returncode,stdout=proc.stdout,stderr=proc.stderr)
        except subprocess.TimeoutExpired:
            row.update(exit_code=None,timed_out=True)
        row['elapsed_seconds']=time.monotonic()-started
        evidence['commands'].append(row)
        save()
        print('NATIVE-APPEARANCE-PREPARATION',json.dumps(row),flush=True)
        return row
    require(execute(['open','-a','Simulator','--args','-CurrentDeviceUDID',udid],45).get('exit_code')==0,
            'Native Simulator launch failed')
    require(execute(['xcrun','simctl','bootstatus',udid,'-b'],180).get('exit_code')==0,
            'Post-window device boot check failed')
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            break
        row=execute(['xcrun','simctl','ui',udid,'appearance'],min(45,remaining))
        if row.get('exit_code')==0 and row.get('stdout','').strip() in ('light','dark'):
            evidence['ready']=True
            break
    save()
    # No setter is issued here. Every formal light/dark setter still executes
    # exactly once through the unchanged original command(...,timeout=45).
    require(evidence['ready'],'Appearance service did not become ready inside preparation180s')
