#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Source, protected-tree and path guards for the WebDAV import package.

Run from the checkout root: check_guards.py --fixed <sha> --freeze <sha> --output <dir>.
The positive/negative selftest runs first so a guard that accepts everything
cannot produce a pass.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ALLOWED = re.compile(r'^(apps/reader/cloud-import/|tests/reader_webdav_import/|'
                     r'\.github/workflows/reader-webdav-import\.yml$|docs/READER-WEBDAV-IMPORT\.md$|'
                     r'docs/validation/reader-webdav-import\.json$)')
# The package must stay an adapter: no product SQL, SDK row mutation, thread,
# process or network backend of its own.
FORBIDDEN = [r'sqlite3_', r'\bINSERT\s+INTO\b', r'\bCREATE\s+TABLE\b', r'exr_library_remove',
             r'exr_library_update', r'exr_library_open', r'exr_library_close', r'\bpthread_', r'\bCreateThread\b',
             r'\bthrd_create\b', r'\bsystem\s*\(', r'\bpopen\s*\(', r'\bcurl_', r'\bWinHttp', r'\bNSURLSession\b',
             r'\bsocket\s*\(', r'Authorization']
BOUNDARY = [  # tokens that must exist: both phases are explicit
    (r'exr_webdav_download_file', 'download uses the existing atomic WebDAV download'),
    (r'exr_sideload_import_file', 'import uses the public sideload entry'),
]


def unowned(paths):
    return [p for p in paths if p and not ALLOWED.match(p)]


def selftest():
    good = ['apps/reader/cloud-import/src/cloud_import.c', 'tests/reader_webdav_import/check_cloud_import.py',
            '.github/workflows/reader-webdav-import.yml', 'docs/READER-WEBDAV-IMPORT.md',
            'docs/validation/reader-webdav-import.json']
    bad = ['extras/webdav/src/webdav.cpp', 'extras/sideload/src/sideload.c', 'apps/reader/batch-import/src/batch_import.c',
           'apps/reader/store/001_catalog.sql', 'src/library.c', 'include/exr/library.h', 'docs/README.md',
           'apps/reader/cloud-import-other/x.c', '.github/workflows/reader-webdav.yml',
           'docs/validation/reader-webdav-import-extra.json', 'tests/reader_webdav_import_x/y.py']
    assert unowned(good) == [], unowned(good)
    assert unowned(bad) == bad, unowned(bad)
    sample_ok = 'int x = exr_webdav_download_file(a);'
    sample_bad = ['sqlite3_exec(db);', 'INSERT INTO books VALUES (1);', 'exr_library_remove(l, 1)', 'pthread_create(&t);',
                  'system("rm");', 'curl_easy_init();', 'const char *Authorization;']
    assert not any(re.search(p, sample_ok) for p in FORBIDDEN)
    for text in sample_bad:
        assert any(re.search(p, text) for p in FORBIDDEN), text
    return {'allowed_samples': len(good), 'refused_samples': len(bad), 'forbidden_samples': len(sample_bad)}


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixed', required=True)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = {'selftest': selftest(), 'checks': []}

    def check(name, ok, detail=''):
        report['checks'].append({'name': name, 'ok': bool(ok), 'detail': detail})
        assert ok, (name, detail)

    head = git('rev-parse', 'HEAD').strip()
    check('checkout_is_workflow_sha', head == os.environ.get('GITHUB_SHA', head), head)
    check('fixed_start_is_ancestor', subprocess.run(['git', 'merge-base', '--is-ancestor', args.fixed, 'HEAD']).returncode == 0)
    check('frozen_sdk_tree_unchanged', subprocess.run(
        ['git', 'diff', '--quiet', args.freeze, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures',
         '.github/workflows/native.yml', '.github/workflows/reliability.yml', 'bindings']).returncode == 0)
    changed = [p for p in git('diff', '--name-only', args.fixed, 'HEAD').splitlines() if p]
    check('only_owned_paths_changed', not unowned(changed), unowned(changed))
    check('protected_trees_byte_identical', subprocess.run(
        ['git', 'diff', '--quiet', args.fixed, 'HEAD', '--', 'extras', 'apps/reader/store', 'apps/reader/session',
         'apps/reader/commands', 'apps/reader/revisions', 'apps/reader/sync', 'apps/reader/desktop',
         'apps/reader/desktop-metadata', 'apps/reader/reading-state', 'apps/reader/batch-import']).returncode == 0)
    root = 'apps/reader/cloud-import'
    sources = []
    for base, _, names in os.walk(root):
        for name in names:
            if name.endswith(('.c', '.h')):
                sources.append(os.path.join(base, name))
    check('sources_found', len(sources) >= 2, sources)
    joined = ''
    for path in sources:
        text = open(path, encoding='utf-8').read()
        joined += text
        hits = [p for p in FORBIDDEN if re.search(p, text) and not (p == 'Authorization' and path.endswith('.h'))]
        check('no_forbidden_backend_or_store_symbols:' + path, not hits, hits)
    for pattern, why in BOUNDARY:
        check('required_boundary:' + pattern, re.search(pattern, joined), why)
    check('limits_match_sideload_contract', 'EXR_SIDELOAD_STREAM_LIMIT' in joined and 'EXR_SIDELOAD_MEMORY_LIMIT' in joined)
    os.makedirs(args.output, exist_ok=True)
    report.update({'ok': True, 'head': head, 'changed_paths': changed})
    with open(os.path.join(args.output, 'guards.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print('guards ok:', len(report['checks']), 'checks')


if __name__ == '__main__':
    sys.exit(main())
