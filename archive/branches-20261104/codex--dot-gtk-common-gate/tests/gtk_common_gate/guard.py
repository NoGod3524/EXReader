"""Current common-source GTK admission; no historical source or runtime grant."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = 'aefe6107f8f073847f0ed590f0ad9602fa720f3d'
SDK = '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'
PRIOR = 'c63c860d9a346fa9973689f14a5fd82908a190ce'
ORIGINAL = '.github/workflows/reader-d26-accessibility.yml'
WORKFLOW = '.github/workflows/reader-gtk-common-gate.yml'
FILES = {WORKFLOW, 'tests/gtk_common_gate/guard.py', 'tests/gtk_common_gate/collect.py'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def validate_changes(changed):
    if set(changed) != FILES:
        raise ValueError('Unexpected common-source change set: ' + repr(sorted(changed)))


def expected_workflow():
    text = subprocess.check_output(['git', 'show', BASE + ':' + ORIGINAL], cwd=ROOT).decode()
    text = text.replace('name: D26 GTK retained accessibility and native regression',
                        'name: Current common source GTK full native acceptance', 1)
    text = text.replace('branches: [codex/reader-history-gtk-composition, codex/reader-integrated-progress, codex/dot-d26-gtk-accessibility, codex/gtk-annotation-export]',
                        'branches: [codex/dot-gtk-common-gate]', 1)
    a = text.index('          test "$(git rev-parse HEAD)"')
    b = text.index('      - name: Check independent current driver', a)
    text = text[:a] + '          python3 tests/gtk_common_gate/guard.py\n' + text[b:]
    text = text.replace('            build/c10-drop-backend/',
                        '            build/gtk-common-source.json\n            build/c10-drop-backend/', 1)
    text = text.replace('python3 tests/reader_d26_accessibility/identity_current.py --artifact',
                        'python3 tests/gtk_common_gate/collect.py --artifact', 1)
    a = text.index('  authenticate:')
    pos = text.index('      - uses: actions/checkout@v4\n', a) + len('      - uses: actions/checkout@v4\n')
    return text[:pos] + '        with:\n          fetch-depth: 0\n' + text[pos:]


def inspect():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    source = git('rev-parse', 'HEAD')
    assert source == os.environ['GITHUB_SHA'], 'Foreign checkout'
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], cwd=ROOT, check=True)
    validate_changes(git('diff', '--name-only', BASE, source).splitlines())
    subprocess.run(['git', 'diff', '--exit-code', source, '--', '.'], cwd=ROOT, check=True)
    # Every prior source blob and mode is immutable. Only the three wrapper additions exist.
    for path in FILES:
        assert git('ls-tree', source, path).startswith('100644 blob '), path
        assert not git('ls-tree', BASE, path), 'Wrapper must be new: ' + path
    subprocess.run(['git', 'diff', '--exit-code', SDK, source, '--',
                    'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings'], cwd=ROOT, check=True)
    # Successful historical producer is provenance only, not reusable runtime evidence.
    subprocess.run(['git', 'diff', '--exit-code', PRIOR, BASE, '--',
                    'examples/linux', 'tests/reader_d26_accessibility',
                    'tests/reader_gtk_raw3', ORIGINAL], cwd=ROOT, check=True)
    actual = (ROOT / WORKFLOW).read_text()
    assert actual == expected_workflow(), 'Original jobs, assertions, or budgets changed'
    for mutation in (FILES - {WORKFLOW}, FILES | {'src/opentype.c'}):
        try:
            validate_changes(mutation)
        except ValueError:
            pass
        else:
            raise AssertionError('Source refusal control failed')
    return dict(schema=1, source_sha=source, run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], composition_source=BASE,
                sdk_source=SDK, prior_producer_source=PRIOR, prior_run=40629490157,
                source_admitted=True, runtime_accepted=False, existing_blobs_unchanged=True,
                original_workflow=ORIGINAL, workflow=WORKFLOW,
                workflow_sha256=hashlib.sha256(actual.encode()).hexdigest(),
                sdk_trees={p: git('rev-parse', source + ':' + p) for p in ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings')},
                gtk_host_tree=git('rev-parse', source + ':examples/linux'),
                wrapper_files=sorted(FILES), source_refusal_controls=2)


if __name__ == '__main__':
    report = inspect()
    path = ROOT / 'build/gtk-common-source.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
