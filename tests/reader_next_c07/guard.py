"""Actions-only C07 scope, frozen-tree and harness identity guard.

Usage: guard.py <job-label>
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

TARGET = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
FAMILY = '56793e7ca4f8ecdc5f2d9c3394fce4e201aca275'
BRANCH = 'codex/reader-next-c07-root-review'
OWNED = ('tests/reader_next_c07/', 'docs/reader-next-c07/')
OWNED_FILES = {'.github/workflows/reader-next-c07.yml', 'HANDOFF-RESULT-C07.md'}
MODULES = ('revisions', 'reading-state', 'reading-commands', 'annotation-view', 'commands', 'sync', 'session')
# Original owner/harness files this package reuses unchanged. Their blob ids and
# bytes are recorded so the evidence names the exact harness, not a lookalike.
REUSED = (
    'tests/apple_host/raw3/guard.py', 'tests/apple_host/raw3/tls_fixture.py', 'tests/apple_host/raw3/RawRecordInterop.swift',
    'tests/reader_android_raw3/bundle.py', 'tests/reader_android_raw3/candidate.py', 'tests/reader_android_raw3/run_ui.py',
    'tests/reader_android_raw3/audit.py', 'tests/reader_android_raw3/extra_cases.java.inc',
    'tests/reader_android_raw3/fixtures.py', 'tests/reader_android_raw3/debug/java/org/exreader/host/Raw3Probe.java',
    'tests/reader_android_record_interop/record_cases.java.inc', 'tests/reader_android_record_interop/public_state.java.inc',
    'examples/apple/HostCatalog.swift', 'examples/apple/HostReadingRecords.swift', 'examples/apple/HostAccount.swift',
    'examples/apple/HostModel.swift', 'examples/apple/HostSDK.swift', 'examples/apple/SelectableText.swift',
    'examples/android/app/build.gradle', 'tools/apple_swift.py', 'tools/build_apple_product.py',
)


def git(*args):
    return subprocess.check_output(['git', *args], text=True, encoding='utf-8').strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    label = sys.argv[1]
    head = git('rev-parse', 'HEAD')
    assert head == os.environ['GITHUB_SHA']
    assert os.environ['GITHUB_REF_NAME'] == BRANCH, os.environ['GITHUB_REF_NAME']
    subprocess.run(['git', 'merge-base', '--is-ancestor', TARGET, 'HEAD'], check=True)
    changed = git('diff', '--name-only', TARGET, 'HEAD').splitlines()
    unowned = [path for path in changed if path not in OWNED_FILES and not path.startswith(OWNED)]
    assert not unowned, unowned
    # Frozen SDK tree, raw seven-module tree and every host/original validator stay
    # byte-identical to the target; only the exclusive C07 paths may differ.
    subprocess.run(['git', 'diff', '--exit-code', SDK, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt'], check=True)
    subprocess.run(['git', 'diff', '--exit-code', FAMILY, 'HEAD', '--', *['apps/reader/' + m for m in MODULES]], check=True)
    subprocess.run(['git', 'diff', '--exit-code', TARGET, 'HEAD', '--', 'apps', 'examples', 'extras', 'bindings', 'tools',
                    'tests/apple_host', 'tests/reader_android_raw3', 'tests/reader_android_record_interop',
                    'tests/reader_android_page_theme', 'tests/fixtures', '.github/workflows/reader-android-raw3.yml',
                    '.github/workflows/reader-apple-raw3.yml'], check=True)
    pdf = Path('tests/fixtures/pdf-public-text.pdf').read_bytes()
    assert len(pdf) == 8845 and hashlib.sha256(pdf).hexdigest() == '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    reused = {}
    for path in REUSED:
        data = Path(path).read_bytes()
        assert git('rev-parse', 'HEAD:' + path) == git('rev-parse', TARGET + ':' + path), path
        reused[path] = {'blob': git('rev-parse', 'HEAD:' + path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    own = {}
    for path in sorted(Path('tests/reader_next_c07').rglob('*')):
        if path.is_file():
            data = path.read_bytes()
            own[path.as_posix()] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    result = {'accepted': True, 'job': label, 'target_source': TARGET, 'source_sha': head, 'branch': BRANCH,
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'sdk_source': SDK, 'family_source': FAMILY, 'changed_paths': changed, 'reused_originals': reused,
              'c07_harness': own, 'sdk_and_raw_modules_unchanged': True, 'host_and_original_tests_unchanged': True}
    out = Path('build/c07') / label
    out.mkdir(parents=True, exist_ok=True)
    (out / 'guard.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('reused_originals', 'c07_harness')}), flush=True)


if __name__ == '__main__':
    main()
