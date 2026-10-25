#!/usr/bin/env python3
"""Path, protected-tree and source guards for the Android import entry, each proven by named positive and
negative cases before it is applied to the real change set."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = 'f43baf9182d75907c0cb5d6f77048f27bca8c950'
ALLOWED = [r'^extras/android-import-entry/', r'^tests/reader_android_import_entry/',
           r'^\.github/workflows/reader-android-import-entry\.yml$', r'^docs/READER-ANDROID-IMPORT-ENTRY\.md$',
           r'^docs/validation/reader-android-import-entry\.json$']
LIB = 'extras/android-import-entry/android/importentry'

# (name, regex) applied to the Java library: the entry must never treat provider data as a path, reach the SDK,
# request storage permissions or spawn processes.
JAVA_FORBIDDEN = [
    ('provider name used as a path', r'\.getPath\(\)|getLastPathSegment\(\)'),
    ('legacy external storage', r'getExternalStorage|WRITE_EXTERNAL_STORAGE|READ_EXTERNAL_STORAGE|getExternalFilesDir'),
    ('process spawn', r'Runtime\.getRuntime\(\)\.exec|ProcessBuilder'),
    ('host SDK reachable from the library', r'System\.loadLibrary|\bnative\s+\w|NativeBridge'),
    ('whole-file read', r'readAllBytes\(\s*\w*[Uu]ri|ByteArrayOutputStream'),
]
JAVA_REQUIRED = [('64 KiB buffer', r'COPY_BUFFER_BYTES\s*=\s*64\s*\*\s*1024'), ('128 MiB ceiling', r'128L\s*<<\s*20'),
                 ('32 MiB ceiling', r'32L\s*<<\s*20'), ('atomic publish', r'ATOMIC_MOVE'), ('fsync before publish', r'getFD\(\)\.sync\(\)')]
C_FORBIDDEN = [('thread creation', r'pthread_create|\bfork\s*\(|\bexec[lv]p?\s*\('),
               ('deleting or moving the host file', r'\bunlink\s*\(|\bremove\s*\(|\brename\s*\(|\brmdir\s*\(')]
MANIFEST_FORBIDDEN = r'<(uses-permission|provider|activity|service|receiver)\b'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True)


def path_violations(paths):
    return [p for p in paths if not any(re.search(a, p) for a in ALLOWED)]


def java_violations(name, text):
    found = [name + ': ' + label for label, rx in JAVA_FORBIDDEN if re.search(rx, text)]
    return found


def required_missing(text):
    return [label for label, rx in JAVA_REQUIRED if not re.search(rx, text)]


def c_violations(name, text):
    return [name + ': ' + label for label, rx in C_FORBIDDEN if re.search(rx, text)]


def self_test():
    cases = []

    def case(label, ok):
        cases.append({'name': label, 'ok': bool(ok)})

    case('path guard accepts every allowed prefix', not path_violations([
        'extras/android-import-entry/CMakeLists.txt', 'tests/reader_android_import_entry/run_device.py',
        '.github/workflows/reader-android-import-entry.yml', 'docs/READER-ANDROID-IMPORT-ENTRY.md',
        'docs/validation/reader-android-import-entry.json']))
    for bad in ('examples/android/app/build.gradle', 'extras/sideload/src/sideload.c', 'extras/android-import-entryX/a',
                'docs/READER-ANDROID-OWNER.md', '.github/workflows/reader-modules.yml', 'tests/reader_android_import_entry_x/a'):
        case('path guard rejects ' + bad, path_violations([bad]) == [bad])
    for label, sample in (('getPath', 'File f = new File(uri.getPath());'), ('external storage', 'Environment.getExternalStorageDirectory()'),
                          ('exec', 'Runtime.getRuntime().exec("cp")'), ('native', 'System.loadLibrary("exreader");'),
                          ('whole file', 'new ByteArrayOutputStream()')):
        case('java guard rejects ' + label, java_violations('x', sample))
    case('java guard accepts a bounded copier', not java_violations('x', 'byte[] b = new byte[COPY_BUFFER_BYTES]; Os.read(fd, b, 0, n);'))
    case('required-constant check flags a missing ceiling', 'atomic publish' in required_missing('COPY_BUFFER_BYTES = 64 * 1024; 128L << 20; 32L << 20;'))
    case('c guard rejects unlink', c_violations('x', 'unlink(path);'))
    case('c guard rejects pthread_create', c_violations('x', 'pthread_create(&t, 0, f, 0);'))
    case('c guard accepts lstat/stat use', not c_violations('x', 'lstat(path, &st);'))
    case('manifest guard rejects a provider', bool(re.search(MANIFEST_FORBIDDEN, '<provider android:name="x"/>')))
    case('manifest guard accepts the empty library manifest', not re.search(MANIFEST_FORBIDDEN, '<manifest xmlns:android="x" />'))
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = {'base': BASE, 'self_tests': self_test(), 'violations': []}
    head = git('rev-parse', 'HEAD').strip()
    results['head'] = head
    if subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', BASE, 'HEAD']).returncode:
        results['violations'].append('HEAD does not descend from the fixed start commit')
    changed = git('diff', '--name-only', BASE, 'HEAD').split()
    results['changed_paths'] = changed
    results['violations'] += ['path outside the allowed set: ' + p for p in path_violations(changed)]
    excludes = [':(exclude)' + e for e in ('extras/android-import-entry', 'tests/reader_android_import_entry',
                '.github/workflows/reader-android-import-entry.yml', 'docs/READER-ANDROID-IMPORT-ENTRY.md',
                'docs/validation/reader-android-import-entry.json')]
    protected = subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', BASE, 'HEAD', '--', '.', *excludes])
    results['protected_tree_unchanged'] = protected.returncode == 0
    if protected.returncode:
        results['violations'].append('protected tree differs from the fixed start commit')
    java_text = ''
    for java in sorted((ROOT / LIB / 'src/main').rglob('*.java')):
        text = java.read_text(encoding='utf-8')
        java_text += text
        results['violations'] += java_violations(java.name, text)
    results['violations'] += ['library lacks: ' + m for m in required_missing(java_text)]
    manifest = (ROOT / LIB / 'src/main/AndroidManifest.xml').read_text(encoding='utf-8')
    if re.search(MANIFEST_FORBIDDEN, manifest):
        results['violations'].append('library manifest declares a component or permission')
    entry_c = (ROOT / 'extras/android-import-entry/src/entry.c').read_text(encoding='utf-8')
    results['violations'] += c_violations('entry.c', entry_c)
    results['violations'] += ['self-test failed: ' + c['name'] for c in results['self_tests'] if not c['ok']]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'guards.json').write_text(json.dumps(results, indent=2))
    print(json.dumps({'violations': results['violations'], 'self_tests': len(results['self_tests'])}, indent=2))
    sys.exit(1 if results['violations'] else 0)


if __name__ == '__main__':
    main()
