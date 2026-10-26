"""Actions-only ownership and provenance guard for the C11 Android wave3 integration."""
import json
import os
from pathlib import Path
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true'
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK_APPROVED = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
OWNED = (
    'examples/android/app/src/main/java/org/exreader/host/',
    'examples/android/app/src/main/cpp/',
    'examples/android/app/src/main/res/',
    'examples/android/app/build.gradle',
    'examples/android/gradle.properties',
    'tests/reader_wave3_c11/',
    '.github/workflows/reader-wave3-c11.yml',
    '.github/workflows/reader-wave3-c11-java.yml',
    'docs/reader-wave3-c11/',
    'HANDOFF-RESULT-C11.md',
)
# The reviewed modules, the frozen SDK and every earlier test or budget stay exactly the seed's bytes.
FROZEN = ('apps/reader', 'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures', 'extras',
          'tests/reader_android_search', 'tests/reader_android_navigation', 'tests/reader_android_reading',
          'tests/reader_android_preferences', 'tests/reader_android_host_import', 'tests/reader_host_session_android',
          'tests/reader_android_raw3', 'tests/android_host', 'examples/android/app/src/androidTest',
          'examples/android/app/src/debug', 'examples/android/app/src/main/AndroidManifest.xml',
          '.github/workflows/native.yml', '.github/workflows/reliability.yml')


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


head = git('rev-parse', 'HEAD')
subprocess.check_call(['git', 'merge-base', '--is-ancestor', SEED, head])
names = [name for name in git('diff', '--name-only', SEED, head).splitlines() if name]
foreign = [name for name in names if not name.startswith(OWNED)]
if foreign:
    print('paths outside the C11 ownership boundary:', foreign)
    sys.exit(1)
subprocess.check_call(['git', 'diff', '--exit-code', SEED, head, '--', *FROZEN])
# Recorded, not enforced here: the seed's SDK sources against the approved candidate they were reviewed with.
sdk_difference = subprocess.run(['git', 'diff', '--stat', SDK_APPROVED, head, '--', 'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings'],
                                capture_output=True, text=True).stdout.strip().splitlines()
tree = git('rev-parse', 'HEAD^{tree}')
out = Path('build/wave3')
out.mkdir(parents=True, exist_ok=True)
modules = {name: git('rev-parse', 'HEAD:apps/reader/' + name) for name in
           ('annotation-import', 'annotation-export', 'font-library', 'original-export', 'jump-history', 'sync-status-view', 'reading-state', 'revisions')}
summary = {'seed': SEED, 'sdk_approved': SDK_APPROVED, 'source_sha': head, 'tree': tree, 'changed_paths': names, 'module_trees': modules, 'sdk_difference_from_approved': sdk_difference,
           'run_id': os.environ.get('GITHUB_RUN_ID'), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}
(out / 'guard.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
(out / 'source.txt').write_text(head + '\n', encoding='utf-8')
print(json.dumps(summary, indent=2, sort_keys=True))
