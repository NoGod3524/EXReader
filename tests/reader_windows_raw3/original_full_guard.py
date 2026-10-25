"""Exact f355 workflow projection plus the existing raw3/default-OFF source guard."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08'
ORIGINAL = 'f355525b74ae261db536c56200e46643919ef323'
OLD_WORKFLOW = '.github/workflows/reader-windows-compact.yml'
WORKFLOW = '.github/workflows/reader-windows-raw3-original-full.yml'
GUARD = 'tests/reader_windows_raw3/guard.py'
GUARD_ENTRY = "'.github/workflows/reader-windows-raw3-original-full.yml',"
NEW_FILES = {WORKFLOW, 'tests/reader_windows_raw3/original_full.py',
             'tests/reader_windows_raw3/original_full_guard.py'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def project_workflow(text):
    # Only these exact substitutions are permitted. Comparing the resulting
    # committed bytes retains every original job, step, condition, timeout,
    # build flag, budget, upload member, environment and strict judge invocation.
    changes = (
        ('name: Windows raw3 source complete original OFF F3 atomic13 chain',
         'name: Windows native compact library and reading candidate', 1),
        ('branches: [codex/reader-windows-original-raw3]',
         'branches: [codex/reader-windows-compact]', 1),
        ('python3 tests/reader_windows_raw3/original_full_guard.py',
         'python3 tests/reader_windows_compact/guard.py', 2),
        ('        run: python3 tests/reader_windows_raw3/original_full.py\n',
         '        run: python3 tests/reader_windows_compact/verify.py\n', 1),
        ("    if: github.event_name == 'push' || (github.event_name == 'workflow_dispatch' && inputs.mode == 'full')\n",
         "    if: github.event_name == 'workflow_dispatch' && inputs.mode == 'full'\n", 1),
        ("    if: always() && (github.event_name == 'push' || (github.event_name == 'workflow_dispatch' && inputs.mode == 'full'))\n",
         "    if: always() && github.event_name == 'workflow_dispatch' && inputs.mode == 'full'\n", 1),
    )
    for current, previous, count in changes:
        if text.count(current) != count:
            raise RuntimeError('Workflow substitution count differs: ' + current)
        text = text.replace(current, previous)
    return text


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    source = git('rev-parse', 'HEAD').decode().strip()
    if source != os.environ['GITHUB_SHA']:
        raise RuntimeError('Checkout differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    # No new wrapper may change an existing test, original workflow, driver,
    # native owner, SDK, or any other source from the root candidate base.
    changed = set(git('diff', '--name-only', BASE, 'HEAD').decode().splitlines())
    if not changed <= NEW_FILES | {GUARD}:
        raise RuntimeError('Full-chain wrapper changed an unowned file: ' + repr(sorted(changed)))
    baseline_guard = git('show', BASE + ':' + GUARD)
    current_guard = git('show', 'HEAD:' + GUARD)
    marker = GUARD_ENTRY.encode()
    if current_guard.count(marker) != 1 or current_guard.replace(marker, b'', 1) != baseline_guard:
        raise RuntimeError('Existing raw3 guard changed beyond the one workflow ownership entry')
    for path in NEW_FILES:
        if git('ls-tree', '--name-only', BASE, '--', path):
            raise RuntimeError('Wrapper overwrote an existing file: ' + path)
    original = git('show', ORIGINAL + ':' + OLD_WORKFLOW)
    if git('show', 'HEAD:' + OLD_WORKFLOW) != original:
        raise RuntimeError('Original compact workflow changed')
    current = git('show', 'HEAD:' + WORKFLOW)
    if project_workflow(current.decode('utf-8')).encode('utf-8') != original:
        raise RuntimeError('Full original workflow projection differs')
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', GUARD, *sorted(NEW_FILES)], cwd=ROOT, check=True)

    spec = importlib.util.spec_from_file_location('raw3_original_full_source_guard', ROOT / GUARD)
    original_guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original_guard)
    original_guard.main()  # Includes exact default-OFF projection, SDK and seven raw module pins.

    out = ROOT / 'build/windows-341-guard'
    out.mkdir(parents=True, exist_ok=True)
    report = dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'],
        attempt=os.environ['GITHUB_RUN_ATTEMPT'], workflow=WORKFLOW,
        original_workflow_source=ORIGINAL, root_candidate_base=BASE,
        original_workflow_sha256=hashlib.sha256(original).hexdigest(),
        projected_workflow_sha256=hashlib.sha256(project_workflow(current.decode()).encode()).hexdigest(),
        workflow_projection_exact=True, original_tests_unchanged=True,
        raw3_source_guard_passed=True, push_runs_full=True, dispatch_full_requires_mode_full=True,
        accepted=False, complete_product=False,
        scope='source/workflow projection only; runtime requires the entire original three-job chain')
    (out / 'raw3-original-full.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
