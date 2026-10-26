# SPDX-License-Identifier: MIT
"""Actions-only regression for the public versus static MSVC map sections."""
import os
from pathlib import Path
import tempfile
from run import windows_static_ownership

assert os.environ.get('GITHUB_ACTIONS') == 'true'
names = ('exr_version', 'rfl_open', 'roe_run', 'reader_jh_open',
         'reader_sync_view_capture', 'reader_annotation_import_run',
         'reader_annotation_export_run', 'reader_catalog_open', 'sqlite3_open_v2')
public = ' Address Publics by Value Rva+Base Lib:Object\n' + ''.join(
    ' 0001:00000000 ' + name + ' 0000000140001000 f provider:one.obj\n' for name in names)
static = (' Static symbols\n'
          ' 0001:00000001 exr_pixel 0000000140001001 f graphics:a.obj\n'
          ' 0001:00000002 exr_pixel 0000000140001002 f render:b.obj\n')
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'host.map'
    path.write_text(public + static, encoding='utf-8')
    assert set(windows_static_ownership(path)) == set(names)
    duplicate = ' 0001:00000003 exr_version 0000000140001003 f duplicate:two.obj\n'
    for invalid in (public + duplicate + static, static):
        path.write_text(invalid, encoding='utf-8')
        try:
            windows_static_ownership(path)
        except AssertionError:
            pass
        else:
            raise AssertionError('invalid public ownership map accepted')
print('PASS public owner uniqueness; local inline duplicates remain local')
