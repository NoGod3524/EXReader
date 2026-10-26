# SPDX-License-Identifier: MIT
"""Owner admission: the original Team24 Apple guard rules, the seed frozen set,
and exactly one shared tool blob that root approved for non-UTF8 link maps."""
import json
import os
from pathlib import Path
import subprocess

SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
BRANCH_START = '8ebef083aa17272c5019c8f778c03ace78e9ea96'
ROOT_COMMIT = '9979001fba4df9fceaed3ffc89d6d9e0bcc16337'
ROOT_BRANCH = 'codex/team24-composition'
TOOL = 'tools/check_apple_product.py'
RUN_UI = 'tests/reader_team24_apple/run_ui.py'
ORIGINAL_GUARD = 'tests/reader_team24_apple/guard.py'
ROOT_TOOL_BLOB = 'ed7f62597e01d4e045f679369805d27abc20b7bc'
SEED_TOOL_BLOB = 'c08a4b5990e660ab4b603094d3e947d521224a20'
ORIGINAL_GUARD_BLOB = '9fad8c90dd00b7bd54c38675b2db4232166908ee'
APPROVED_OLD = '    mapping = Path(link_map).read_text()'
APPROVED_NEW = "    mapping = Path(link_map).read_text(encoding='utf-8', errors='surrogateescape')"
MAP_READ = "mapping.read_text(encoding='utf-8', errors='surrogateescape')"
PREFIXES = ('examples/apple/', 'apps/reader/apple-feature-integration/',
            'tests/reader_team24_apple/', 'docs/handoffs/team24-apple')
WORKFLOW = '.github/workflows/team24-apple.yml'
FROZEN = ('src/', 'include/', 'bindings/', 'cmake/', 'tools/', 'tests/apple_host/',
          'tests/fixtures/', 'tests/reader_a11y_apple/', 'CMakeLists.txt')


def admit_paths(paths):
    """Original owner prefixes, plus the one shared tool this package may carry."""
    return all(path.startswith(PREFIXES) or path in (WORKFLOW, TOOL) for path in paths)


def frozen_changes(paths):
    """Every changed path in the original frozen set except the pinned shared tool."""
    return [path for path in paths if path.startswith(FROZEN) and path != TOOL]


def admit_tool_blob(blob):
    """The shared checker must be byte-identical to the root approved blob."""
    return blob == ROOT_TOOL_BLOB


def admit_tool_lines(removed, added):
    """The only admitted checker edit is the explicit utf-8/surrogateescape decode."""
    return removed == [APPROVED_OLD] and added == [APPROVED_NEW]


def changed_lines(diff_text):
    removed, added = [], []
    for line in diff_text.splitlines():
        if line[:3] in ('---', '+++', '@@ ') or line.startswith(('diff ', 'index ')):
            continue
        if line.startswith('-'):
            removed.append(line[1:])
        elif line.startswith('+'):
            added.append(line[1:])
    return removed, added


def self_test():
    """Negative controls: every widened or narrowed admission must be rejected."""
    controls = 0
    assert admit_paths(['examples/apple/HostModel.swift', TOOL, WORKFLOW,
                        'docs/handoffs/team24-apple-DSF-A01.md'])
    controls += 1
    for bad in ('src/library.c', 'tools/apple_swift.py', 'CMakeLists.txt',
                'tests/apple_host/make_xcodeproj.rb', 'tests/fixtures/Sample.epub',
                'tests/reader_a11y_apple/run.py', 'docs/handoffs/other.md',
                'apps/reader/search/src/search.cpp'):
        assert not admit_paths([bad]), bad
        controls += 1
    for value, expected in ((['src/a.c'], ['src/a.c']), ([TOOL], []),
                            (['tools/apple_swift.py'], ['tools/apple_swift.py']),
                            (['examples/apple/HostModel.swift'], []),
                            (['tests/apple_host/EXReaderHostUITests.swift'],
                             ['tests/apple_host/EXReaderHostUITests.swift'])):
        assert frozen_changes(value) == expected, (value, frozen_changes(value))
        controls += 1
    assert not admit_paths(['examples/apple/x.swift', 'docs/handoffs/other.md'])
    controls += 1
    assert admit_tool_blob(ROOT_TOOL_BLOB)
    controls += 1
    for bad in (SEED_TOOL_BLOB, '', ROOT_TOOL_BLOB[:-1], ROOT_TOOL_BLOB.upper(), 'f' * 40):
        assert not admit_tool_blob(bad), bad
        controls += 1
    assert admit_tool_lines([APPROVED_OLD], [APPROVED_NEW])
    controls += 1
    for removed, added in (([APPROVED_OLD], [APPROVED_NEW.replace('surrogateescape', 'ignore')]),
                           ([APPROVED_OLD], [APPROVED_NEW.replace('surrogateescape', 'replace')]),
                           ([APPROVED_OLD], [APPROVED_NEW, 'x']),
                           ([APPROVED_OLD, 'y'], [APPROVED_NEW]),
                           ([], [APPROVED_NEW]),
                           ([APPROVED_OLD], []),
                           ([APPROVED_OLD], [APPROVED_NEW.replace("encoding='utf-8', ", '')])):
        assert not admit_tool_lines(removed, added), (removed, added)
        controls += 1
    assert changed_lines('--- a\n+++ b\n@@ -1 +1 @@\n-' + APPROVED_OLD + '\n+' + APPROVED_NEW) == (
        [APPROVED_OLD], [APPROVED_NEW])
    controls += 1
    assert changed_lines('@@ -1 +1 @@\n-' + APPROVED_OLD + '\n+' + APPROVED_NEW + '\n+z') == (
        [APPROVED_OLD], [APPROVED_NEW, 'z'])
    controls += 1
    return controls


def git(*args):
    return subprocess.check_output(['git', *args], text=True)


def present(rev):
    return subprocess.run(['git', 'cat-file', '-e', rev + '^{commit}'],
                          capture_output=True).returncode == 0


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = os.environ['GITHUB_SHA']
    assert git('rev-parse', 'HEAD').strip() == source
    for ancestor in (SEED, BRANCH_START):
        subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, 'HEAD'], check=True)
    if not present(ROOT_COMMIT):
        subprocess.run(['git', 'fetch', '--no-tags', 'origin', ROOT_BRANCH], check=False)
    assert present(ROOT_COMMIT), 'approved root commit unavailable from origin ' + ROOT_BRANCH
    root_blob = git('rev-parse', ROOT_COMMIT + ':' + TOOL).strip()
    assert root_blob == ROOT_TOOL_BLOB, root_blob
    head_blob = git('rev-parse', 'HEAD:' + TOOL).strip()
    seed_blob = git('rev-parse', SEED + ':' + TOOL).strip()
    assert seed_blob == SEED_TOOL_BLOB, seed_blob
    assert admit_tool_blob(head_blob), head_blob
    assert git('rev-parse', 'HEAD:' + ORIGINAL_GUARD).strip() == ORIGINAL_GUARD_BLOB
    paths = git('diff', '--name-only', SEED, 'HEAD').splitlines()
    assert admit_paths(paths), [path for path in paths if not admit_paths([path])]
    frozen = frozen_changes(paths)
    assert not frozen, frozen
    removed, added = changed_lines(git('diff', '-U0', SEED, 'HEAD', '--', TOOL))
    assert admit_tool_lines(removed, added), (removed, added)
    tool_text = Path(TOOL).read_text(encoding='utf-8')
    ui_text = Path(RUN_UI).read_text(encoding='utf-8')
    assert MAP_READ in ui_text and 'mapping.read_text()' not in ui_text
    for text, name in ((tool_text, TOOL), (ui_text, RUN_UI)):
        assert "errors='ignore'" not in text and 'errors="ignore"' not in text, name
    report = {'seed': SEED, 'branch_start': BRANCH_START, 'source_sha': source,
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'changed_paths': paths, 'original_guard_blob': ORIGINAL_GUARD_BLOB,
              'shared_tool': {'path': TOOL, 'root_commit': ROOT_COMMIT, 'root_branch': ROOT_BRANCH,
                              'root_blob': root_blob, 'seed_blob': seed_blob, 'head_blob': head_blob,
                              'decode': APPROVED_NEW.strip()},
              'frozen_paths_checked': list(FROZEN), 'negative_controls': self_test(),
              'accepted': True}
    out = Path('build/team24-apple-guard.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('source_sha', 'changed_paths', 'shared_tool',
                                                   'negative_controls', 'accepted')}, indent=2))


if __name__ == '__main__':
    main()
