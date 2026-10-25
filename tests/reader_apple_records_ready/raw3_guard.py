"""Pin the ordinary merge; original raw business runner projects exactly to72."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MERGE = '4749131d722f4f585be767207ed16b32dd9d9b3d'
RAW = '72c6bbdd14ebf3be453fa7f0da81119d52675eb5'
READY = '7c457fb68a24d917ac3bd60aa1f961b16fe9ae6b'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
FAMILY = '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275'
BRANCH = 'codex/reader-apple-raw3-ios-ready'
WORKFLOW = '.github/workflows/reader-apple-raw3-ios-ready.yml'
DRIVER = 'tests/reader_apple_records_ready/raw3_driver.py'
PREPARATION = """    sys.path.insert(0, str(ROOT / 'tests/apple_host/page_theme'))
    from simulator_ready import prepare_service
    prepare_service(udid, evidence)
"""
VERIFY = """      - name: Bind original full raw strict to actual bounded native readiness
        run: python3 tests/reader_apple_records_ready/raw3_verify.py
"""
NEW_OUTPUT = ('          path: |\n            build/raw3-ios-summary/summary.json\n'
              '            build/raw3-ios-summary/native-readiness.json')


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True)


def validate_driver(text, original):
    require(text.count(PREPARATION) == 1, 'readiness insertion differs')
    text = text.replace(PREPARATION, '', 1)
    text = text.replace('ROOT = Path(__file__).resolve().parents[2]', 'ROOT = Path(__file__).resolve().parents[5]', 1)
    text = text.replace("HERE = ROOT / 'tests/apple_host/raw3/ios/reading'\nsys.path.insert(0, str(HERE))",
                        'HERE = Path(__file__).resolve().parent', 1)
    require(text == original, 'original OFF7/raw6 runner, budgets or judgments changed')


def validate_workflow(text, original):
    require(text.count(VERIFY) == 1 and text.count(NEW_OUTPUT) == 1, 'readiness evidence output differs')
    text = text.replace(VERIFY, '', 1).replace(NEW_OUTPUT, '          path: build/raw3-ios-summary/summary.json', 1)
    text = text.replace('name: Actual iPhone iPad raw3 with bounded native readiness',
                        'name: Independent actual iPhone iPad raw3 host candidate', 1)
    text = text.replace('branches: [' + BRANCH + ']', 'branches: [codex/reader-apple-raw3-ios]', 1)
    text = text.replace('python3 tests/reader_apple_records_ready/raw3_guard.py',
                        'python3 tests/apple_host/raw3/ios/reading/guard.py', 1)
    text = text.replace('python3 ' + DRIVER, 'python3 tests/apple_host/raw3/ios/reading/driver.py', 1)
    require(text == original, 'original complete raw workflow or budgets changed')


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    require(os.environ.get('GITHUB_REF_NAME') == BRANCH, 'actual candidate branch required')
    require(git('rev-parse', 'HEAD').strip() == os.environ['GITHUB_SHA'], 'source differs')
    for ancestor in (MERGE, RAW, READY):
        subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', ancestor, 'HEAD'], check=True)
    allowed = {WORKFLOW, DRIVER, 'tests/reader_apple_records_ready/raw3_guard.py',
               'tests/reader_apple_records_ready/raw3_verify.py',
               'docs/READER-APPLE-RAW3-IOS-READY.md', 'docs/validation/reader-apple-raw3-ios-ready.json'}
    changed = git('diff', '--name-only', MERGE, 'HEAD').splitlines()
    require(set(changed) <= allowed, 'original merged production/tests/judges changed')
    for path in ('examples/apple', 'apps', 'extras', 'tools', 'tests/apple_host/raw3',
                 'tests/apple_host/reading', 'tests/apple_host/make_xcodeproj.rb'):
        require(git('rev-parse', 'HEAD:' + path) == git('rev-parse', RAW + ':' + path), 'raw72 tree differs: ' + path)
    path = 'tests/apple_host/page_theme'
    require(git('rev-parse', 'HEAD:' + path) == git('rev-parse', READY + ':' + path), 'readiness source differs')
    for path in ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures',
                 '.github/workflows/native.yml', '.github/workflows/reliability.yml'):
        require(git('rev-parse', 'HEAD:' + path) == git('rev-parse', SDK + ':' + path), 'SDK differs: ' + path)
    for name in ('revisions', 'reading-state', 'reading-commands', 'annotation-view', 'commands', 'sync', 'session'):
        path = 'apps/reader/' + name
        require(git('rev-parse', 'HEAD:' + path) == git('rev-parse', FAMILY + ':' + path), 'raw family differs: ' + name)
    driver = (ROOT / DRIVER).read_text()
    original_driver = git('show', RAW + ':tests/apple_host/raw3/ios/reading/driver.py')
    workflow = (ROOT / WORKFLOW).read_text()
    original_workflow = git('show', RAW + ':.github/workflows/reader-apple-raw3-ios.yml')
    validate_driver(driver, original_driver)
    validate_workflow(workflow, original_workflow)
    negatives = []
    for name, mutant, validator, expected in (
        ('changed_original180', driver.replace("'180' if mode", "'181' if mode"), validate_driver, original_driver),
        ('changed_raw600', driver.replace("else '600'", "else '601'"), validate_driver, original_driver),
        ('missing_query_preparation', driver.replace(PREPARATION, ''), validate_driver, original_driver),
        ('skipped_original_controls', driver.replace("phases = [ui('control'", "phases = [ui('raw'"), validate_driver, original_driver),
        ('omitted_strict', workflow.replace('python3 tests/apple_host/raw3/ios/reading/verify.py', 'echo accepted'), validate_workflow, original_workflow),
        ('changed_job_budget', workflow.replace('timeout-minutes: 75', 'timeout-minutes: 76'), validate_workflow, original_workflow),
    ):
        require(mutant != (driver if validator == validate_driver else workflow), 'inactive negative: ' + name)
        try:
            validator(mutant, expected)
        except ValueError:
            negatives.append(name)
        else:
            raise ValueError('altered original controls accepted: ' + name)
    result = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], ordinary_merge_source=MERGE,
                  raw_producer_source=RAW, readiness_source=READY, sdk_source=SDK,
                  exact_raw_family_source=FAMILY, original_runner_projection_exact=True,
                  original_workflow_projection_exact=True, original_ui_cases=7, raw_ui_phases=6,
                  negative_checks=negatives, accepted=False, physical_device_execution=False, complete_product=False)
    out = ROOT / 'build/raw3-ios-ready-guard.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
