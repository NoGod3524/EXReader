# SPDX-License-Identifier: MIT
"""Actions-only source admission for two exact Android path-access candidates."""
import json
import os
from pathlib import Path
import subprocess

BASE = '7752663d285ce9d47621b12a4e902d4da4f5cb6d'
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
BLOBS = {
    'apps/reader/font-library/src/library.cpp': '4743c2eb9de510a322c3a55baa82f6bfb9f9a23d',
    'apps/reader/original-export/src/original_export.cpp': 'c18f721bc1fc3b65fd6a20d8f18c57d7e3d93514',
}
OWNED = {'tests/reader_android_path_access/guard.py',
         '.github/workflows/reader-android-path-access.yml',
         'docs/reader-android-path-access/README.md'}


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def tree(ref):
    result = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-rz', ref]).split(b'\0'):
        if row:
            metadata, name = row.split(b'\t', 1)
            result[name.decode()] = tuple(metadata.decode().split())
    return result


def inspect(actual, base):
    problems = []
    for name in set(actual) | set(base):
        value = actual.get(name)
        if name in BLOBS:
            if value != ('100644', 'blob', BLOBS[name]):
                problems.append(name)
        elif name in OWNED:
            if not value or value[:2] != ('100644', 'blob'):
                problems.append(name)
        elif value != base.get(name):
            problems.append(name)
    return sorted(problems)


assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
head = git('rev-parse', 'HEAD')
assert head == os.environ['GITHUB_SHA']
subprocess.check_call(['git', 'merge-base', '--is-ancestor', BASE, head])
actual, base = tree(head), tree(BASE)
assert not inspect(actual, base), inspect(actual, base)
# Exercise each prohibited source mutation without changing files or the Git tree.
for name in list(BLOBS) + ['src/library.c', 'tests/reader_wave3_c11/guard.py',
                            'tests/reader_wave3_c11/report.py',
                            'examples/android/app/src/main/java/org/exreader/host/MainActivity.java']:
    changed = dict(actual)
    changed[name] = ('100644', 'blob', '0' * 40)
    assert name in inspect(changed, base), name
modules = {name: git('rev-parse', 'HEAD:apps/reader/' + name) for name in
           ('annotation-import', 'annotation-export', 'font-library', 'original-export',
            'jump-history', 'sync-status-view', 'reading-state', 'revisions')}
summary = {'seed': SEED, 'source_base': BASE, 'source_sha': head,
           'sdk_approved': 'edddc463c06ed5731195cdb8f06b2df6dff7699e',
           'tree': git('rev-parse', 'HEAD^{tree}'), 'module_trees': modules,
           'candidate_module_blobs': BLOBS,
           'changed_paths': sorted(name for name in set(actual) | set(base)
                                   if actual.get(name) != base.get(name)),
           'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT']}
out = Path('build/wave3')
out.mkdir(parents=True, exist_ok=True)
(out / 'guard.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
(out / 'source.txt').write_text(head + '\n', encoding='utf-8')
print(json.dumps(summary))
