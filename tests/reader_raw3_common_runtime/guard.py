"""Pin the complete composed source and exact original Windows workflow projection."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
ORIGINAL = '.github/workflows/reader-windows-raw3-original-full.yml'
WORKFLOW = '.github/workflows/reader-raw3-common-windows.yml'
NEW_FILES = {
    WORKFLOW,
    'tests/reader_raw3_common_runtime/guard.py',
    'tests/reader_raw3_common_runtime/test_guard.py',
    'tests/reader_raw3_common_runtime/windows_verify.py',
    'docs/reader-raw3-common-runtime/README.md',
}
SELF_TEST_STEP = '''      - name: Check common-source workflow guards and refusal cases in Actions
        run: |
          python3 -m py_compile tests/reader_raw3_common_runtime/*.py
          python3 tests/reader_raw3_common_runtime/test_guard.py
'''


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def tree(ref):
    values = {}
    for row in git('ls-tree', '-rz', ref).split(b'\0'):
        if row:
            metadata, path = row.split(b'\t', 1)
            values[path.decode('utf-8')] = metadata.decode('ascii')
    return values


def validate_tree(baseline, current):
    for path, identity in baseline.items():
        if current.get(path) != identity:
            raise RuntimeError('Existing common-source file changed: ' + path)
    added = set(current) - set(baseline)
    if added != NEW_FILES:
        raise RuntimeError('Runtime wrapper file set differs: ' + repr(sorted(added)))
    if any(current[path].split()[0] != '100644' for path in added):
        raise RuntimeError('Runtime wrapper is not a regular non-executable file')


def project_workflow(text):
    substitutions = (
        ('name: Common raw3 source complete Windows original OFF F3 atomic13 chain',
         'name: Windows raw3 source complete original OFF F3 atomic13 chain', 1),
        ('branches: [codex/reader-raw3-common-runtime]',
         'branches: [codex/reader-windows-original-raw3]', 1),
        ('python3 tests/reader_raw3_common_runtime/guard.py',
         'python3 tests/reader_windows_raw3/original_full_guard.py', 2),
        ('run: python3 tests/reader_raw3_common_runtime/windows_verify.py',
         'run: python3 tests/reader_windows_raw3/original_full.py', 1),
        (SELF_TEST_STEP, '', 1),
    )
    for replacement, original, count in substitutions:
        if text.count(replacement) != count:
            raise RuntimeError('Workflow projection substitution differs: ' + replacement)
        text = text.replace(replacement, original)
    return text


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    source = git('rev-parse', 'HEAD').decode().strip()
    if source != os.environ['GITHUB_SHA']:
        raise RuntimeError('Checkout and Actions source differ')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    validate_tree(tree(BASE), tree('HEAD'))
    # No fake Actions source or historical guard-success file is generated.
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', '.'], cwd=ROOT, check=True)
    original = git('show', BASE + ':' + ORIGINAL)
    current = git('show', 'HEAD:' + WORKFLOW).decode('utf-8')
    if project_workflow(current).encode('utf-8') != original:
        raise RuntimeError('Original Windows jobs, steps, options or judges changed')
    out = ROOT / 'build/windows-341-guard'
    out.mkdir(parents=True, exist_ok=True)
    record = dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'],
        attempt=os.environ['GITHUB_RUN_ATTEMPT'], composition_source=BASE,
        workflow=WORKFLOW, original_workflow=ORIGINAL,
        baseline_tree=git('rev-parse', BASE + '^{tree}').decode().strip(),
        original_workflow_sha256=hashlib.sha256(original).hexdigest(),
        all_existing_blobs_and_modes_unchanged=True,
        original_windows_workflow_projection_exact=True,
        accepted=False, complete_product=False,
        scope='common-source and full Windows workflow projection; runtime not yet granted')
    (out / 'common-runtime-source.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
