"""Actions-only task boundary; historical C11 guard is preserved, not retargeted."""
import json
import os
import subprocess
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true'
SEED = 'c45ac1a7508842f071e3d892635fdd9af444ae90'
OWNED = ('tests/android_font_reader/', '.github/workflows/reader-android-font-reader.yml',
         'docs/android-font-reader/', 'examples/android/app/src/main/java/org/exreader/host/MainActivity.java',
         'tests/reader_d21_apple_receive/guard.py', 'tests/reader_android_receive_d22/guard.py',
         'tests/reader_d25_real_formats/run.py', '.github/workflows/reader-d23-relay.yml',
         'examples/reader.c', 'apps/reader/desktop/windows_search.inc', 'apps/reader/desktop/windows_txt_search.inc', 'apps/reader/desktop/windows_wave3.inc', 'tests/windows_host/txt/check_progress.py', '.github/workflows/windows-wave3-txt-progress.yml')
def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()
head = git('rev-parse', 'HEAD')
subprocess.check_call(['git', 'merge-base', '--is-ancestor', SEED, head])
names = git('diff', '--name-only', SEED, head).splitlines()
assert all(name.startswith(OWNED) for name in names), names
subprocess.run(['git', 'diff', '--exit-code', '7ee9f9b93cbc1cb1dbf485bb138c2cf4e2de3691', 'HEAD', '--', *['examples/reader.c', 'apps/reader/desktop/windows_search.inc', 'apps/reader/desktop/windows_txt_search.inc', 'apps/reader/desktop/windows_wave3.inc', 'tests/windows_host/txt/check_progress.py', '.github/workflows/windows-wave3-txt-progress.yml']], check=True)
# The whitelist freezes ALL other paths, including SDK, budgets and old suites.
modules = {name: git('rev-parse', 'HEAD:apps/reader/' + name) for name in
           ('annotation-import', 'annotation-export', 'font-library', 'original-export', 'jump-history', 'sync-status-view', 'reading-state', 'revisions')}
summary = {'seed': SEED, 'source_sha': head, 'tree': git('rev-parse', 'HEAD^{tree}'),
           'changed_paths': names, 'module_trees': modules,
           'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
           'historical_guard_preserved': 'tests/reader_wave3_c11/guard.py',
           'scope': 'all non-owned paths identical to current common candidate'}
out = Path('build/wave3'); out.mkdir(parents=True, exist_ok=True)
(out/'guard.json').write_text(json.dumps(summary, indent=2)+'\n')
(out/'source.txt').write_text(head+'\n')
print(json.dumps(summary, indent=2))
