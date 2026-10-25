# SPDX-License-Identifier: MIT
"""Actions-only guard for GTK host wiring over fixed reviewed packages."""
import os
import subprocess


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


assert os.environ.get('GITHUB_ACTIONS') == 'true'
assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
base = 'e4356a6e13223469fdf3b2f3d5171a6e99ab10a6'
j03 = '5988ee7fed3cfbf823f0ff55ffc1906a5166d145'
owned = '2df6040666635bcd7b0349b035b8f4885757fdd0'
navigation_driver = '600ef981fb44acd91dca618850a25d1725de18f7'
navigation_path = 'tests/reader_gtk_navigation/check_ui.py'
for ancestor in (base, j03, owned, navigation_driver):
    subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, 'HEAD'], check=True)
subprocess.run(['git', 'diff', '--exit-code', '9854061be331fe603a1822d9b2b36ee357154927', 'HEAD', '--',
                'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tests/fixtures', '.github/workflows/native.yml', '.github/workflows/reliability.yml'], check=True)
subprocess.run(['git', 'diff', '--exit-code', j03, 'HEAD', '--', 'extras/desktop-drop', 'tests/reader_desktop_drop',
                '.github/workflows/reader-desktop-drop.yml', 'docs/READER-DESKTOP-DROP.md', 'docs/validation/reader-desktop-drop.json'], check=True)
subprocess.run(['git', 'diff', '--exit-code', owned, 'HEAD', '--', 'tests/reader_gtk_batch_import'], check=True)
assert git('rev-parse', 'HEAD:' + navigation_path) == '4b3bb47191d9e3bce3a80b75b9266f5a618ac9a9'
subprocess.run(['git', 'diff', '--exit-code', navigation_driver, 'HEAD', '--', 'tests/reader_gtk_navigation'], check=True)
allowed = ('examples/linux/', 'tests/reader_gtk_drop_import/')
exact = {'apps/reader/desktop/CMakeLists.txt', '.github/workflows/reader-gtk-drop-import.yml',
         'docs/READER-GTK-DROP-IMPORT.md', 'docs/validation/reader-gtk-drop-import.json', navigation_path}
dependencies = {'apps/reader/desktop/CMakeLists.txt', 'examples/linux/reading.h', 'examples/linux/batch_import_backend.inc',
                'examples/linux/batch_import_ui.inc', 'tests/reader_gtk_batch_import/owner_faults.c', 'tests/reader_gtk_batch_import/check_evidence.py'}
merge_base = '3e5db2279941e02c230a00c010564a79c5b5cc4a'
for path in git('diff', '--name-only', merge_base, 'HEAD').splitlines():
    assert path.startswith(allowed) or path in exact or path in dependencies, path
for path in ('apps/reader/store', 'apps/reader/revisions', 'apps/reader/commands', 'apps/reader/session', 'apps/reader/sync',
             'apps/reader/search', 'apps/reader/navigation', 'apps/reader/reading-state', 'apps/reader/reading-commands',
             'apps/reader/annotation-view', 'apps/reader/batch-import', 'apps/reader/preferences', 'extras/sideload',
             'tests/reader_gtk_search', 'tests/reader_gtk_reading_records', 'tests/linux_host', 'tools'):
    assert not git('diff', '--name-only', base, 'HEAD', '--', path), path
print('GTK_DROP_GUARD fixed SDK/schema/modules, reviewed J03 and host-only wiring passed')
