"""Pin all original record business bytes and project only environment preparation."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '7c457fb68a24d917ac3bd60aa1f961b16fe9ae6b'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
BRANCH = 'codex/reader-apple-records-ready'
ORIGINAL = '.github/workflows/reader-apple-reading-records.yml'
WORKFLOW = '.github/workflows/reader-apple-records-ready.yml'
HEADER = ('name: Apple original records with bounded native simulator readiness\n'
          'on:\n  push:\n    branches: [' + BRANCH + ']\n  workflow_dispatch:')
OLD_HEADER = 'name: Apple native product reading records\non:\n  workflow_dispatch:'
PREPARE = """      - name: Query-only native simulator readiness before original seven UI cases
        run: python3 tests/reader_apple_records_ready/prepare.py --platform '${{ matrix.platform }}' --destination build/apple-reading-ui/destination.txt --output build/apple-reading-ui
"""
VERIFY = """      - name: Authenticate same-run bounded native readiness evidence
        env:
          GH_TOKEN: ${{ github.token }}
        run: python3 tests/reader_apple_records_ready/verify.py
"""
PROOF = '            build/apple-records-ready/guard.json\n'


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True)


def validate(text, original):
    for fragment in (HEADER, PREPARE, VERIFY, PROOF):
        require(text.count(fragment) == 1, 'missing/repeated preparation fragment')
    text = text.replace(HEADER, OLD_HEADER, 1).replace(PREPARE, '', 1).replace(VERIFY, '', 1).replace(PROOF, '', 1)
    require(text.count(BRANCH) == 4, 'branch-bound SDK selection differs')
    text = text.replace(BRANCH, 'codex/reader-hosts-341-final')
    old = 'python3 tests/apple_host/page_theme/guard.py'
    new = 'python3 tests/reader_apple_records_ready/guard.py'
    require(text.count(new) == 1, 'candidate guard entry differs')
    require(text.replace(new, old, 1) == original, 'original full workflow business bytes/budgets changed')


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    require(os.environ.get('GITHUB_REF_NAME') == BRANCH, 'actual independent candidate branch required')
    require(git('rev-parse', 'HEAD').strip() == os.environ['GITHUB_SHA'], 'source differs')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
    allowed = {WORKFLOW, 'docs/READER-APPLE-RECORDS-READY.md', 'docs/validation/reader-apple-records-ready.json'}
    changed = git('diff', '--name-only', BASE, 'HEAD').splitlines()
    require(all(path in allowed or path.startswith('tests/reader_apple_records_ready/') for path in changed),
            'original production/test/runner/judge changed')
    protected = ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures',
                 '.github/workflows/native.yml', '.github/workflows/reliability.yml')
    sdk_trees = {path: git('rev-parse', SDK + ':' + path).strip() for path in protected}
    require(all(git('rev-parse', 'HEAD:' + path).strip() == value for path, value in sdk_trees.items()), 'SDK frozen tree differs')
    original = git('show', BASE + ':' + ORIGINAL)
    text = (ROOT / WORKFLOW).read_text()
    validate(text, original)
    mutants = {
        'missing_readiness': text.replace(PREPARE, ''),
        'altered_original180': text.replace('-default-test-execution-time-allowance 180', '-default-test-execution-time-allowance 181'),
        'altered_original300': text.replace('-maximum-test-execution-time-allowance 300', '-maximum-test-execution-time-allowance 301'),
        'omitted_native': text.replace('python3 tests/apple_host/reading/run_native.py', 'echo skipped'),
        'omitted_original_strict': text.replace('python3 tests/apple_host/reading/summarize.py', 'echo accepted'),
        'changed_original_collector': text.replace('python3 tests/apple_host/reading/collect_reading_evidence.py', 'echo accepted'),
        'changed_original_cases': text.replace('tests/apple_host/reading/ui', 'tests/reader_apple_records_ready/fake-ui'),
        'write_permission': text.replace('contents: read', 'contents: write'),
    }
    for name, mutant in mutants.items():
        require(mutant != text, 'inactive negative ' + name)
        try:
            validate(mutant, original)
        except ValueError:
            continue
        raise ValueError('altered original workflow accepted: ' + name)
    result = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], fixed_preparation_source=BASE,
                  original_producer_source=BASE, sdk_source=SDK, sdk_version='3.41.0', sdk_abi=1,
                  original_full_workflow_projection_exact=True, original_ui_cases=7,
                  original_native_checks=19, sdk_targets=2, original_UI_case_seconds=180,
                  original_UI_max_case_seconds=300, original_assertion_seconds=90,
                  query_only_readiness_limit_seconds=180, negative_checks=list(mutants),
                  original_business_and_judges_unchanged=True, protected_sdk_trees=sdk_trees,
                  accepted=False, physical_device_execution=False, complete_product=False)
    out = ROOT / 'build/apple-records-ready/guard.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
