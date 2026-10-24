"""Actions-only authentication of reviewed trees and explicit integration edits."""
import json
import os
from pathlib import Path
import subprocess


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    spec = json.loads(Path(__file__).with_name('inputs.json').read_text())
    sha = os.environ['GITHUB_SHA']
    assert git('rev-parse', 'HEAD') == sha
    subprocess.run(['git', 'merge-base', '--is-ancestor', spec['start'], sha], check=True)
    protected = ['src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings',
                 '.github/workflows/native.yml', '.github/workflows/reliability.yml']
    subprocess.run(['git', 'diff', '--exit-code', spec['sdk'], sha, '--', *protected], check=True)
    subprocess.run(['git', 'diff', '--exit-code', spec['start'], sha, '--',
                    'apps/reader/store/001_catalog.sql'], check=True)
    expected = {}
    for entry in spec['inputs']:
        delivery = entry['delivery']
        subprocess.run(['git', 'merge-base', '--is-ancestor', delivery, sha], check=True)
        for path in git('diff', '--name-only', spec['start'], delivery).splitlines():
            blob = git('rev-parse', delivery + ':' + path)
            assert path not in expected or expected[path] == blob, 'conflicting reviewed inputs: ' + path
            expected[path] = blob
    # This separate, fixed commit contains only the scoped codec transfer,
    # three package dependencies and explicit SDK links in SDK-using probes.
    amendment = spec['amendments']
    subprocess.run(['git', 'merge-base', '--is-ancestor', amendment, sha], check=True)
    for path in git('diff-tree', '--no-commit-id', '--name-only', '-r', amendment).splitlines():
        expected[path] = git('rev-parse', amendment + ':' + path)
    for path in git('diff', '--name-only', spec['start'], sha).splitlines():
        if path in expected:
            assert git('rev-parse', sha + ':' + path) == expected[path], 'reviewed bytes changed: ' + path
        else:
            assert any(path.startswith(p) if p.endswith('/') else path == p
                       for p in spec['new_paths']), 'unreviewed path: ' + path
    for path, blob in expected.items():
        assert git('rev-parse', sha + ':' + path) == blob, 'reviewed input missing: ' + path
    report = dict(accepted=True, source_sha=sha, run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], reviewed_files=len(expected),
                  sdk_changed=False, schema_changed=False, inputs=spec['inputs'])
    out = Path('build/composition/input-guard.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
