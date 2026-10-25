"""Exact candidate merge/configuration boundary; retain the complete original job."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

BASE = 'f9671923a854901d19bddd0396073dbc90fab222'
ORIGINAL = '07ebe8786434ef384c97ccdb451242d3c6aee6cb'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
WORKFLOW = '.github/workflows/reader-composition-341.yml'
REPLACEMENTS = (
    ('python3 tests/reader_hosts_integration/guard.py', 'python3 tests/reader_hosts_341/guard_composition.py'),
    ('-DCMAKE_PREFIX_PATH="$prefix" -DCMAKE_INSTALL_PREFIX=', '-DEXR_SDK_VERSION="$EXR_SDK_VERSION" -DCMAKE_PREFIX_PATH="$prefix" -DCMAKE_INSTALL_PREFIX='),
    ('-DEXR_MODULE_PREFIX="$COMP_WS/build/prefix-sdk-only"', '-DEXR_SDK_VERSION="$EXR_SDK_VERSION" -DEXR_MODULE_PREFIX="$COMP_WS/build/prefix-sdk-only"'),
    ('-DEXR_MODULE_PREFIX="$COMP_PREFIX"', '-DEXR_SDK_VERSION="$EXR_SDK_VERSION" -DEXR_MODULE_PREFIX="$COMP_PREFIX"'),
    ('-DEXR_MODULE_PREFIX="$COMP_WS/build/prefix-relocated"', '-DEXR_SDK_VERSION="$EXR_SDK_VERSION" -DEXR_MODULE_PREFIX="$COMP_WS/build/prefix-relocated"'),
    ('tests/reader_hosts_integration/aggregate.py composition', 'tests/reader_hosts_341/aggregate_composition.py'),
)


def git(*args):
    return subprocess.check_output(['git', *args], text=True).replace('\r\n', '\n')


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = os.environ['GITHUB_SHA']
    assert git('rev-parse', 'HEAD').strip() == source
    assert os.environ['EXR_SDK_VERSION'] == '3.41.0'
    for ancestor in (BASE, ORIGINAL, SDK):
        subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, 'HEAD'], check=True)
    subprocess.run(['git', 'diff', '--exit-code', SDK, 'HEAD', '--',
                    'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures'], check=True)
    for folder in ('apps', 'examples', 'extras'):
        subprocess.run(['git', 'diff', '--exit-code', BASE, 'HEAD', '--', folder], check=True)
    paths = git('diff', '--name-only', BASE, 'HEAD').splitlines()
    assert all(path.startswith('tests/reader_hosts_341/') or path in
               (WORKFLOW, 'docs/READER-HOSTS-341-FINAL.md') for path in paths), paths
    old = git('show', ORIGINAL + ':.github/workflows/reader-hosts-integration.yml')
    expected = old[old.index('  compose:\n'):old.index('  search:\n')]
    for before, after in REPLACEMENTS:
        assert before in expected, before
        expected = expected.replace(before, after)
    current = Path(WORKFLOW).read_text()
    assert current[current.index('  compose:\n'):] == expected, 'an original compose/aggregate step changed or vanished'
    assert '  EXR_SDK_VERSION: 3.41.0\n' in current
    # Original cloud source/ownership rules still apply to the real implementation.
    spec = importlib.util.spec_from_file_location('cloud_guard', Path('tests/reader_webdav_import/check_guards.py'))
    cloud = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cloud)
    controls = cloud.selftest()
    sources = sorted(path for path in Path('apps/reader/cloud-import').rglob('*') if path.suffix in ('.c', '.h'))
    assert len(sources) >= 2
    joined = ''
    for path in sources:
        text = path.read_text(encoding='utf-8')
        joined += text
        assert not [pattern for pattern in cloud.FORBIDDEN if re.search(pattern, text)
                    and not (pattern == 'Authorization' and path.suffix == '.h')], str(path)
    assert all(re.search(pattern, joined) for pattern, _ in cloud.BOUNDARY)
    assert 'EXR_SIDELOAD_STREAM_LIMIT' in joined and 'EXR_SIDELOAD_MEMORY_LIMIT' in joined
    result = dict(accepted=True, source_sha=source, run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], baseline=BASE, sdk_source=SDK,
                  sdk_version='3.41.0', schema_changed=False, cloud_adapter_source_guard=True,
                  cloud_source_controls=controls, original_complete_job_preserved=True,
                  host_ui_accepted=False, complete_product=False)
    target = Path('build/hosts-input.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
