"""Actions-only admission of the composed Android font reader source."""
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
base = '0ec6d3aa34297f30e016af9f1cb2416ed79709f2'
candidate = '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'
seed = 'c45ac1a7508842f071e3d892635fdd9af444ae90'

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

head = git('rev-parse', 'HEAD')
assert head == os.environ['GITHUB_SHA']
subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], check=True)
changed = git('diff', '--name-only', base, head).splitlines()
assert set(changed) == {'.github/workflows/reader-android-font-reader.yml',
                        'tests/android_font_reader/common_guard.py'}, changed
subprocess.run(['git', 'diff', '--exit-code', candidate, 'HEAD', '--',
                'src', 'include', 'cmake', 'CMakeLists.txt'], check=True)
modules = {name: git('rev-parse', 'HEAD:apps/reader/' + name) for name in
           ('annotation-import', 'annotation-export', 'font-library', 'original-export',
            'jump-history', 'sync-status-view', 'reading-state', 'revisions')}
summary = {'seed': seed, 'composition_base': base, 'source_sha': head,
           'tree': git('rev-parse', 'HEAD^{tree}'), 'changed_paths': changed,
           'module_trees': modules, 'sdk_tree_matches': candidate,
           'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
           'historical_guard_preserved': 'tests/reader_wave3_c11/guard.py',
           'scope': 'exact composed source, original Android font and C11 tests unchanged'}
out = Path('build/wave3')
out.mkdir(parents=True, exist_ok=True)
(out / 'guard.json').write_text(json.dumps(summary, indent=2) + '\n')
(out / 'source.txt').write_text(head + '\n')
print(json.dumps(summary, indent=2))
