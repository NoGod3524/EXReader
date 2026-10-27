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
         '.github/workflows/reader-d26-accessibility.yml', 'apps/reader/desktop/gtk_feature_integration.cmake', 'examples/linux/reading.h', 'examples/linux/wave3_backend.inc', 'examples/linux/wave3_ui.inc', 'tests/reader_d26_accessibility/identity_current.py', 'tests/reader_d26_accessibility/tools_current.py',
         'src/chapter_reader.c', 'tests/bounded_txt_scan/view.c', '.github/workflows/sdk-txt-anchor-resolve.yml', '.github/workflows/reader-d24-apple-large-type.yml',
         'examples/reader.c', 'apps/reader/desktop/windows_search.inc', 'apps/reader/desktop/windows_txt_search.inc', 'apps/reader/desktop/windows_wave3.inc', 'tests/windows_host/txt/check_progress.py', '.github/workflows/windows-wave3-txt-progress.yml')
def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()
head = git('rev-parse', 'HEAD')
subprocess.check_call(['git', 'merge-base', '--is-ancestor', SEED, head])
names = git('diff', '--name-only', SEED, head).splitlines()
extra_paths = [
    '.github/workflows/android-real-original-save.yml',
    'tests/android_real_original_save/device.sh',
    'tests/android_real_original_save/java/org/exreader/host/OriginalSaveUiTest.java',
    'tests/android_real_original_save/run_ui.py',
    'tests/android_real_original_save/test.init.gradle',
    'tests/reader_d26_accessibility/README.md',
    'tests/reader_d26_accessibility/current_expectations.py',
    'tests/reader_d26_accessibility/g13_current.py',
    'docs/reader-total-progress/README.md',
    'docs/reader-total-progress/catalog.json',
    'docs/reader-total-progress/android-font-reader.md',
    'docs/reader-total-progress/linux-annotation-export.md',
    'docs/reader-total-progress/android-original-save.md',
]
assert all(name.startswith(OWNED) or name in extra_paths for name in names), names
for reference, paths in [
    ('e24527faed81110ea4626d56013469487c606cb4', extra_paths[:5]),
    ('ac8d65c02c0e4d2ae2b8e76ac7797d634dce9267', extra_paths[5:8]),
    ('3b66f138a383662477433b42fece97b9582b4219', extra_paths[8:]),
]:
    subprocess.run(['git', 'diff', '--exit-code', reference, 'HEAD', '--', *paths], check=True)
subprocess.run(['git', 'diff', '--exit-code', '642bb8efe124fdd301410f0b3e8e17292d6a5069', 'HEAD', '--', *['examples/reader.c', 'apps/reader/desktop/windows_search.inc', 'apps/reader/desktop/windows_txt_search.inc', 'apps/reader/desktop/windows_wave3.inc', 'tests/windows_host/txt/check_progress.py', '.github/workflows/windows-wave3-txt-progress.yml']], check=True)
subprocess.run(['git', 'diff', '--exit-code', 'cc75214cb5e6dce389625e33399e1b120aedf4c4', 'HEAD', '--', *['apps/reader/desktop/gtk_feature_integration.cmake', 'examples/linux/reading.h', 'examples/linux/wave3_backend.inc', 'examples/linux/wave3_ui.inc', 'tests/reader_d26_accessibility/identity_current.py', 'tests/reader_d26_accessibility/tools_current.py']], check=True)
subprocess.run(['git', 'diff', '--exit-code', '642bb8efe124fdd301410f0b3e8e17292d6a5069', 'HEAD', '--', 'src/chapter_reader.c', 'tests/bounded_txt_scan/view.c'], check=True)
subprocess.run(['git', 'diff', '--exit-code', '9715391a129b343f343810243080c2cc6ecdfdf0', 'HEAD', '--', '.github/workflows/reader-d24-apple-large-type.yml', '.github/workflows/reader-d26-accessibility.yml', '.github/workflows/sdk-txt-anchor-resolve.yml'], check=True)
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
