# SPDX-License-Identifier: MIT
"""Authenticate the isolated SDK3.41 host and unchanged six legacy business pipelines."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
BASE = '9ee1053b83fcf934e6f0891eb77d468fc394da1e'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
COMPATIBILITY = 'a67ad5e62f3b87e83bc9b775fa499cf30fda0cf4'
BRANCH = 'codex/reader-apple-page-theme'
WORKFLOWS = ('reader-apple-navigation.yml', 'reader-apple-search.yml',
             'reader-apple-reading-records.yml', 'reader-apple-shelf.yml',
             'reader-apple-import-mapping.yml', 'wp13-apple.yml')
ENV = ("  EXR_APPLE_SDK_VERSION: ${{ github.ref_name == '" + BRANCH + "' && '3.41.0' || '3.40.0' }}\n"
       "  EXR_APPLE_PAGE_THEME: ${{ github.ref_name == '" + BRANCH + "' && 'ON' || 'OFF' }}\n")
STEP = ("      - name: Authenticate isolated SDK3.41 Apple page-theme candidate\n"
        "        if: github.ref_name == '" + BRANCH + "'\n"
        "        run: python3 tests/apple_host/page_theme/guard.py\n")
OLD_IF = "        if: github.ref_name != 'codex/reader-hosts-integration'\n"
NEW_IF = OLD_IF.rstrip('\n') + " && github.ref_name != '" + BRANCH + "'\n"
SDK_PATHS = ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures',
             'licenses', 'tools/layers.json', '.github/workflows/native.yml', '.github/workflows/reliability.yml')
MODULE_PATHS = ('apps/reader/reading-state', 'apps/reader/search', 'apps/reader/navigation',
                'apps/reader/reading-commands', 'apps/reader/annotation-view', 'apps/reader/store/001_catalog.sql')
COMPATIBILITY_PATHS = ('examples/apple/HostReadingRecords.swift', 'tests/apple_host/record_compatibility',
                       '.github/workflows/reader-apple-record-compatibility.yml',
                       'docs/READER-APPLE-RECORD-COMPATIBILITY.md', 'docs/validation/reader-apple-record-compatibility.json')
OWNED = {'examples/apple/HostModel.swift', 'examples/apple/HostSDK.swift', 'examples/apple/HostViews.swift',
         'examples/apple/HostPageThemeViews.swift', 'tools/build_apple_product.py', 'tools/build_apple_host.py',
         'tests/apple_host/make_xcodeproj.rb', '.github/workflows/reader-apple-page-theme.yml',
         'docs/READER-APPLE-PAGE-THEME.md', 'docs/validation/reader-apple-page-theme.json'}
OWNED |= {'.github/workflows/' + name for name in WORKFLOWS}
OWNED |= set(COMPATIBILITY_PATHS)


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def normalize(text):
    for value in (ENV, STEP, NEW_IF):
        require(text.count(value) == 1, 'candidate version/default/guard declaration differs')
    return text.replace(ENV, '', 1).replace(STEP, '', 1).replace(NEW_IF, OLD_IF, 1)


def validate_workflow(text, original):
    require(normalize(text) == original, 'legacy business steps, guards, consumers or summaries changed')


def validate_trees(actual, expected):
    require(actual == expected, 'protected SDK/module tree differs')


def validate_paths(paths):
    require(all(path in OWNED or path.startswith(('tests/apple_host/page_theme/', 'tests/apple_host/record_compatibility/')) for path in paths),
            'unowned path changed')


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    require(os.environ.get('GITHUB_REF_NAME') == BRANCH, 'isolated candidate branch required')
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'checkout source differs')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', COMPATIBILITY, 'HEAD'], check=True)
    expected = {path: git('rev-parse', SDK + ':' + path) for path in SDK_PATHS}
    expected.update({path: git('rev-parse', BASE + ':' + path) for path in MODULE_PATHS})
    expected.update({path: git('rev-parse', COMPATIBILITY + ':' + path) for path in COMPATIBILITY_PATHS})
    actual = {path: git('rev-parse', 'HEAD:' + path) for path in expected}
    validate_trees(actual, expected)
    paths = git('diff', '--name-only', BASE, 'HEAD').splitlines()
    validate_paths(paths)
    checks = []

    def rejected(name, operation):
        try:
            operation()
        except ValueError:
            checks.append(name)
        else:
            raise ValueError('accepted altered candidate evidence: ' + name)

    for name in WORKFLOWS:
        path = '.github/workflows/' + name
        original = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE + ':' + path], text=True)
        text = (ROOT / path).read_text()
        validate_workflow(text, original)
        mutants = {
            'foreign_branch': text.replace(BRANCH, 'codex/foreign-theme'),
            'new_default': text.replace("|| '3.40.0'", "|| '3.41.0'"),
            'enabled_default': text.replace("|| 'OFF'", "|| 'ON'"),
            'unknown_version': text.replace("&& '3.41.0'", "&& '3.42.0'"),
            'missing_guard': text.replace(STEP, ''),
            'legacy_guard_bypassed': text.replace(NEW_IF, '        if: false\n'),
            'write_permissions': text.replace('contents: read', 'contents: write'),
            'changed_budget': text.replace('timeout-minutes: 35', 'timeout-minutes: 36'),
            'changed_business_step': text.replace('cmake --build', 'echo skipped --build'),
        }
        for kind, value in mutants.items():
            require(value != text, 'inactive workflow negative: ' + name + ':' + kind)
            rejected(name + ':' + kind, lambda value=value: validate_workflow(value, original))
    for path in expected:
        changed = dict(actual); changed[path] = '0' * 40
        rejected('changed-tree:' + path, lambda changed=changed: validate_trees(changed, expected))
    for path in ('src/raster.c', 'extras/apple-reader-display/foreign.c', 'apps/reader/store/001_catalog.sql'):
        rejected('unowned:' + path, lambda path=path: validate_paths([path]))
    output = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'candidate_input_authenticated': True,
              'sdk_source': SDK, 'sdk_version': '3.41.0', 'sdk_abi': 1, 'theme_accepted': False,
              'record_compatibility_delivery': COMPATIBILITY,
              'record_compatibility_scope': 'independent macOS exact-source point-record owner evidence only',
              'legacy_workflows_unchanged': list(WORKFLOWS), 'negative_checks': checks,
              'protected_trees': expected, 'complete_product': False}
    destination = ROOT / 'build/apple-page-theme/guard.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps(output, sort_keys=True))


if __name__ == '__main__':
    main()
