"""Actions-only common Windows caller: unchanged reviewed production and judges."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '436c5bd57b2b6acc0076a0942e7c7f93f38fcb96'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
FROZEN = '9854061be331fe603a1822d9b2b36ee357154927'
WORKFLOW = '.github/workflows/reader-windows-341-common.yml'


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = os.environ['GITHUB_SHA']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == source
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, source], check=True)
    subprocess.run(['git', 'diff', '--exit-code', BASE, source, '--', 'apps', 'examples', 'extras', 'tools'], check=True)
    subprocess.run(['git', 'diff', '--exit-code', SDK, source, '--', 'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures'], check=True)
    # Keep every original assertion and fixture byte: only new caller paths move.
    for path in subprocess.check_output(['git', 'diff', '--name-only', BASE, source], text=True).splitlines():
        assert path.startswith(('tests/reader_windows_341/', 'docs/READER-WINDOWS-341-COMMON',
                                'docs/validation/reader-windows-341-common')) or path == WORKFLOW, path
    header = (ROOT / 'apps/reader/revisions/include/reader_revisions.h').read_text()
    assert '#define READER_REVISION_ANCHOR_MAX_VERSION 2u' in header
    workflow = (ROOT / WORKFLOW).read_text()
    for required in ('-DEXR_SDK_VERSION=3.41.0', '-DEXR_READER_WINDOWS_PREFERENCES=ON',
                     '-DEXR_READER_WINDOWS_IMPORT_ORGANIZE=ON', '-DEXR_READER_PREFS_COMMIT_REVIEW_BUILD=ON',
                     'check_commit.py', 'check_ui.py', FROZEN):
        assert required in workflow, required
    out = ROOT / 'build/windows-341-guard'; out.mkdir(parents=True, exist_ok=True)
    (out / 'source.json').write_text(json.dumps(dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'],
        attempt=os.environ['GITHUB_RUN_ATTEMPT'], base=BASE, sdk_source=SDK, frozen_source=FROZEN,
        production_unchanged=True, original_judges_unchanged=True, sdk_version='3.41.0',
        complete_product=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
