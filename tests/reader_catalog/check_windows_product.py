# SPDX-License-Identifier: MIT
"""Actual cloud Windows product: published identities, repair, refusal and profile locks."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_windows_host import fields, digest, source_identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--original-evidence', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    package = args.package.resolve()
    original_folder = args.original_evidence.resolve()
    original_path = original_folder / 'wp13-windows-evidence.json'
    original = json.loads(original_path.read_text(encoding='utf-8'))
    assert original['passed'] is True and original['source_sha'] == source_identity()
    assert original['counts'] == {'steps': 158, 'passed': 158, 'failed': 0}
    assert original['identities_unchanged'] is True
    output = args.output.resolve()
    output.mkdir()
    profile = output / 'profile'
    # All original driver phases exited normally. Preserve their sealed files.
    shutil.copytree(original_folder / 'data', profile)
    catalog = profile / 'library.sqlite.product.sqlite'
    checks = []
    expected = {}
    for path, kind, mode in ((package / 'Sample-positive.epub', 'epub', 'epub_chapter'),
                              (args.fixtures / 'Pages.pdf', 'pdf', 'fixed_page'),
                              (args.fixtures / 'Extra-Book.epub', 'epub', None)):
        expected[kind + ':' + digest(path)] = (path.stat().st_size, mode)
    with sqlite3.connect(catalog) as db:
        assert db.execute('PRAGMA application_id').fetchone()[0] == 1163416144
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        rows = db.execute('SELECT b.book_key,b.source_bytes,l.location_kind,l.sdk_book_id FROM reader_books b LEFT JOIN reader_local_books l USING(book_key)').fetchall()
        assert len(rows) == 3 and {key: (size, mode) for key, size, mode, _ in rows} == expected
        final_ids = {int(book['id']) for book in original['shelf']['C']['after_restart']}
        assert {sdk_id for _, _, _, sdk_id in rows if sdk_id is not None} == final_ids
        checks.append('real_ui_publication_has_verified_original_keys_sizes_modes_and_sdk_ids')
        keys = {row[0] for row in rows}
        for file in ('Cancel-Big.epub', 'Stale-Book.epub'):
            assert 'epub:' + digest(args.fixtures / file) not in keys
        checks.append('cancelled_and_superseded_imports_have_no_global_or_local_product_rows')
        extra_key = 'epub:' + digest(args.fixtures / 'Extra-Book.epub')
        assert db.execute('SELECT count(*) FROM reader_books WHERE book_key=?', (extra_key,)).fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM reader_local_books WHERE book_key=?', (extra_key,)).fetchone()[0] == 0
        checks.append('actual_delete_removes_only_local_mapping_and_retains_global_metadata')
        db.execute('DELETE FROM reader_local_books')
        db.execute("UPDATE reader_books SET title='User catalog metadata'")
    script = output / 'observe.script'
    script.write_text('wait_idle\nstate|product\nquit\n', encoding='utf-8')
    executable = package / 'EXReader.exe'
    executable_sha = digest(executable)
    env = dict(os.environ, EXREADER_HOST_ACCEPTANCE='1')
    process_records = []

    def launch_args(folder, data=profile, library=None):
        return [str(executable), '--drive', str(script), '--evidence', str(folder),
                '--data', str(data), '--library', str(library or (data / 'library.sqlite')),
                '--phase', '4']

    def observe(name):
        folder = output / name
        folder.mkdir()
        with (folder / 'stdout.log').open('wb') as log:
            process = subprocess.Popen(launch_args(folder), stdout=log, stderr=subprocess.STDOUT, env=env)
            try:
                assert process.wait(timeout=120) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=20)
        lines = (folder / 'drive.log').read_text(encoding='utf-8').splitlines()
        assert fields(';'.join(lines[0].split('\t')[1:])) == {'phase': '4', 'engine': '3.40.0', 'pid': str(process.pid)}
        steps = [line.split('\t') for line in lines if line.startswith('STEP\t')]
        assert [(row[1], row[2], row[3]) for row in steps] == [('1', 'wait_idle', 'PASS'), ('2', 'state', 'PASS'), ('3', 'quit', 'PASS')]
        done = [line.split('\t') for line in lines if line.startswith('DONE\t')]
        assert len(done) == 1 and done[0][1:] == ['3', 'eof', 'PASS', 'script finished']
        states = [line.split('\t') for line in lines if line.startswith('STATE\t')]
        assert len(states) == 1 and states[0][2:4] == ['product', 'PASS']
        state = fields(states[0][4])
        prior = original['states']['C']['after_restart']
        assert all(state[key] == prior[key] for key in ('book_id', 'font', 'offset', 'title'))
        process_records.append({'id': name, 'pid': process.pid, 'exit_code': process.returncode, 'state': state})
        return state

    state = observe('repair')
    assert state['product_pending'] == '0'
    with sqlite3.connect(catalog) as db:
        assert db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM reader_books WHERE title='User catalog metadata'").fetchone()[0] == 3
        db.execute('DELETE FROM reader_local_books')
        db.execute("CREATE TRIGGER reject_mapping BEFORE INSERT ON reader_local_books BEGIN SELECT RAISE(ABORT,'injected product write failure');END")
    checks.append('actual_startup_repairs_missing_mappings_and_preserves_user_metadata')
    state = observe('product-write-refusal')
    assert state['product_pending'] == '1' and '书架信息待恢复' in state['status']
    with sqlite3.connect(catalog) as db:
        assert db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0] == 0
        db.execute('DROP TRIGGER reject_mapping')
    checks.append('catalog_write_failure_retains_readable_sdk_book_and_visible_pending_state')
    state = observe('retry-after-restart')
    assert state['product_pending'] == '0'
    with sqlite3.connect(catalog) as db:
        assert db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0] == 2
    checks.append('next_real_startup_repairs_failed_product_write_without_reimport')

    user32 = ctypes.windll.user32
    user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetDlgItem.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowEnabled.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    owner = None
    with (output / 'owner.log').open('wb') as log:
        try:
            owner = subprocess.Popen([str(executable), '--data', str(profile), '--font', str(package / 'Reader.otf')],
                                     stdout=log, stderr=subprocess.STDOUT, env=env)
            end = time.monotonic() + 90
            window = None
            while window is None:
                windows = []

                @callback_type
                def visit(hwnd, unused):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == owner.pid and user32.IsWindowVisible(hwnd) and user32.GetDlgItem(hwnd, 117):
                        windows.append(hwnd)
                    return True

                user32.EnumWindows(visit, 0)
                if windows and not user32.IsWindowEnabled(user32.GetDlgItem(windows[0], 117)):
                    window = windows[0]
                else:
                    assert owner.poll() is None and time.monotonic() < end, 'Owner did not become idle'
                    time.sleep(.1)
            before_settings = (profile / 'host.ini').read_bytes()
            other_library = output / 'other-library.sqlite'
            for name, data, library in (('same-profile-different-sdk', profile, other_library),
                                         ('same-sdk-different-profile', output / 'other-profile', profile / 'library.sqlite')):
                folder = output / name
                folder.mkdir()
                result = subprocess.run(launch_args(folder, data, library), capture_output=True, env=env, timeout=30)
                (folder / 'stdout.log').write_bytes(result.stdout + result.stderr)
                assert result.returncode == 2 and not (folder / 'drive.log').exists()
                assert (profile / 'host.ini').read_bytes() == before_settings
                assert owner.poll() is None
                checks.append(name.replace('-', '_') + '_is_refused_before_profile_writes')
            assert not other_library.exists() and not (output / 'other-profile/host.ini').exists()
            checks.append('refused_instances_do_not_create_other_sdk_or_overwrite_owner_settings')
            assert user32.PostMessageW(window, 0x0010, 0, 0)
            assert owner.wait(timeout=30) == 0
            owner = None
        finally:
            if owner is not None and owner.poll() is None:
                owner.kill()
                owner.wait(timeout=20)
    state = observe('owner-normal-restart')
    assert state['product_pending'] == '0'
    checks.append('owner_normal_restart_retains_accepted_reading_state_after_refusals')
    assert len(checks) == 10 and digest(executable) == executable_sha
    report = {'accepted': True, 'source_sha': source_identity(), 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'processes': process_records,
              'original_ui_steps': 158, 'original_report_sha256': digest(original_path),
              'program_sha256': executable_sha, 'complete_product': False,
              'files': {str(path.relative_to(output)): digest(path) for path in sorted(output.rglob('*')) if path.is_file()}}
    (output / 'product-result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': True, 'checks': len(checks), 'source_sha': report['source_sha']}))


if __name__ == '__main__':
    main()
