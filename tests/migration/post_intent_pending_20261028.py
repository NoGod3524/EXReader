#!/usr/bin/env python3
"""Actions-only, additive v3 pending-policy tests. No historical test is replaced."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import subprocess
import time
import traceback


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Builds, tests, fixtures and artifact parsing belong in Actions only.')
    import legacy_data as L
    ap = argparse.ArgumentParser()
    ap.add_argument('--tool', required=True)
    ap.add_argument('--old-tool', required=True)
    ap.add_argument('--v2-tool', required=True)
    ap.add_argument('--work', required=True, type=Path)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
    cases = []
    evidence = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                    attempt=os.environ['GITHUB_RUN_ATTEMPT'], platform=os.environ['RUNNER_OS'],
                    cases=cases, passed=False, full_p0_acceptance=False,
                    scope='existing-target post-intent; no full recovery verifier or SQLite observer',
                    gaps=['pre-intent rollback', 'old 3.40 explicit --break-lock bypass',
                          'non-OK SDK rollback return', 'automatic full recovery'])

    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def sibling(target, suffix):
        return Path(str(target) + suffix)

    def connect(target, mode='rw'):
        return sqlite3.connect(target.resolve().as_uri() + '?mode=' + mode, uri=True, timeout=0)

    def identity(path):
        s = path.stat()
        return s.st_dev, s.st_ino

    def content(target):
        db = connect(target, 'ro')
        try:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            tables = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            rows = []
            for name, sql in tables:
                quoted = '"' + name.replace('"', '""') + '"'
                columns = db.execute('PRAGMA table_info(' + quoted + ')').fetchall()
                data = sorted(db.execute('SELECT * FROM ' + quoted).fetchall(), key=repr)
                rows.append((name, sql, columns, data))
            return db.execute('PRAGMA user_version').fetchone()[0], rows
        finally:
            db.close()

    def record(folder, name, p, require_json=True):
        (folder / (name + '.stdout.txt')).write_text(p.stdout, encoding='utf-8')
        (folder / (name + '.stderr.txt')).write_text(p.stderr, encoding='utf-8')
        return p.returncode, json.loads(p.stdout) if require_json else None

    def run(folder, name, command, target, pack=None, extra=(), tool=None):
        cmd = [tool or a.tool, command, '--target', str(target)]
        if pack is not None:
            cmd += ['--pack', str(pack)]
        return record(folder, name, subprocess.run(cmd + list(extra), env=env,
                      capture_output=True, text=True, timeout=45))

    def seed(folder, schema, mode):
        target = folder / 'library.sqlite'
        first, delta = folder / 'seed.exrpack', folder / 'delta.exrpack'
        first.write_bytes(L.build_pack([L.entry(L.book_record('seed', 'seed.txt'), L.TXT)],
                                       [L.note_record('seed-note', 'seed', 'lantern keeper', 'retained note')]))
        delta.write_bytes(L.build_pack([L.entry(L.book_record('delta', 'delta.txt'), L.TXT_OTHER)], []))
        rc, report = run(folder, 'seed', 'migrate', target, first, tool=a.old_tool if schema == 6 else a.tool)
        assert rc == 0 and content(target)[0] == schema, report
        anchor = connect(target)
        assert anchor.execute('PRAGMA journal_mode=' + mode).fetchone()[0].lower() == mode
        anchor.execute('PRAGMA wal_autocheckpoint=0')
        if mode == 'wal':
            anchor.execute("UPDATE books SET title=title || ' [live WAL]' WHERE id=1")
            anchor.commit()
            assert sibling(target, '-wal').stat().st_size > 0
        return target, first, delta, anchor

    def start(target, pack, hook):
        return subprocess.Popen([a.tool, 'migrate', '--target', str(target), '--pack', str(pack),
                                 '--inject', hook], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def wait_marker(p, marker):
        until = time.monotonic() + 25
        while not marker.exists() and p.poll() is None and time.monotonic() < until:
            time.sleep(.02)
        assert marker.exists(), ('missing rendezvous', str(marker), p.poll())

    def collect(folder, name, p, timeout=35, require_json=True):
        out, err = p.communicate(timeout=timeout)
        return record(folder, name, subprocess.CompletedProcess(p.args, p.returncode, out, err), require_json)

    def stop_save(folder, name, p):
        if p.poll() is None:
            p.kill()
        out, err = p.communicate(timeout=10)
        (folder / (name + '.cleanup.stdout.txt')).write_text(out, encoding='utf-8')
        (folder / (name + '.cleanup.stderr.txt')).write_text(err, encoding='utf-8')

    def retained(target):
        pending = sibling(target, '.migration-pending.json')
        intent = json.loads(pending.read_text())
        assert intent['version'] == 3
        paths = [pending, sibling(target, '.legacy-map.json'), sibling(target, '.migrate-lock')]
        if intent['mirror_present']:
            paths.append(sibling(target, '.legacy-map.json.before-' + intent['artifact_token']))
        staged = sibling(target, '.legacy-map.json.staged-' + intent['artifact_token'])
        if staged.exists():
            paths.append(staged)
        return {str(path): (identity(path), digest(path)) for path in paths}

    def pending_refusals(folder, target, first):
        before = retained(target)
        database_before = content(target), identity(target)
        rc, report = run(folder, 'verify-policy-retained', 'verify', target, first)
        # A schema-6 read may refuse its schema, while schema 7 can verify the
        # touched items. Neither outcome clears the observed retirement policy.
        assert report['atomicity']['recovery']['automatic_retirement_blocked'], report
        assert not report['atomicity']['recovery']['full_recovery_accepted'], report
        assert retained(target) == before
        assert (content(target), identity(target)) == database_before
        for name, cmd, pack, extra in (
                ('recover', 'recover-mirror', None, ()),
                ('recover-break', 'recover-mirror', None, ('--break-lock',)),
                ('retry-migration', 'migrate', first, ('--break-lock',)),
                ('retry-dry-run', 'migrate', first, ('--dry-run', '--break-lock'))):
            rc, report = run(folder, name, cmd, target, pack, extra)
            assert rc == 5 and report['code'] == 'recovery-unverified', report
            assert report['atomicity']['recovery']['automatic_retirement_blocked'], report
            assert not report['atomicity']['recovery']['full_recovery_accepted'], report
            assert report['atomicity']['recovery']['io_observation'] == 'not-installed'
            assert retained(target) == before
            assert (content(target), identity(target)) == database_before
        rc, report = run(folder, 'actual340-default', 'migrate', target, first, tool=a.old_tool)
        assert rc == 5 and report['code'] == 'target-busy', report
        assert retained(target) == before
        assert (content(target), identity(target)) == database_before
        # Actual old candidate format refusal is tested on an isolated copy.
        # Its --break-lock is NOT allowed to erase the original barrier.
        isolated = folder / 'old-v2-format-control'
        isolated.mkdir()
        copy_target = isolated / 'library.sqlite'
        shutil.copyfile(target, copy_target)
        shutil.copyfile(sibling(target, '.migration-pending.json'), sibling(copy_target, '.migration-pending.json'))
        rc, report = run(isolated, 'v2-refuses-v3', 'recover-mirror', copy_target, tool=a.v2_tool)
        assert rc != 0 and report['code'] == 'mirror-intent-invalid', report
        assert sibling(copy_target, '.migration-pending.json').exists()
        assert retained(target) == before
        assert (content(target), identity(target)) == database_before
        return {'actual340_rejection': 'shared lock, NOT v3 format recognition',
                'v2_candidate_format_rejection': True, 'explicit_old_break_lock_protected': False}

    def normal(folder, schema, mode):
        target, first, delta, anchor = seed(folder, schema, mode)
        p = None
        try:
            original_id = identity(target)
            dry_baseline = content(target)
            rc, dry = run(folder, 'early-dry-run-observation', 'migrate', target, delta, ('--dry-run',))
            assert rc == 0 and dry['result'] == 'dry-run', dry
            assert dry['atomicity']['recovery']['rollback_requested'] is None, dry
            assert dry['atomicity']['recovery']['sdk_status'] is None, dry
            assert content(target) == dry_baseline and identity(target) == original_id
            p = start(target, delta, 'mirror-pause')
            marker = sibling(target, '.mirror-ready')
            wait_marker(p, marker)
            assert json.loads(sibling(target, '.migration-pending.json').read_text())['version'] == 3
            # The original owner must be closed; this committed ordinary write
            # happens before artifact retirement, not after the whole command.
            anchor.execute("UPDATE books SET title='ordinary-after-commit-before-cleanup' WHERE id=1")
            anchor.commit()
            sibling(target, '.mirror-ready.resume').touch()
            rc, report = collect(folder, 'normal', p)
            assert rc == 0 and report['atomicity']['transaction']['target_commit'] == 'committed', report
            assert report['atomicity']['mirror']['state'] == 'commit-planned-mirror-matched', report
            assert not sibling(target, '.migration-pending.json').exists()
            assert not sibling(target, '.migrate-lock').exists()
            assert identity(target) == original_id
            assert anchor.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == 'ordinary-after-commit-before-cleanup'
            rc, again = run(folder, 'idempotent', 'migrate', target, delta)
            assert rc == 0 and not sibling(target, '.migration-pending.json').exists(), again
            assert anchor.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == 'ordinary-after-commit-before-cleanup'
            return {'same_process_commit': True, 'ordinary_write_before_cleanup_preserved': True,
                    'unchanged_baseline_mirror_noop_allowed': True, 'full_recovery_accepted': False}
        finally:
            if p is not None:
                stop_save(folder, 'normal', p)
            anchor.close()

    def abort(folder, schema, mode, crash_hook=None):
        target, first, delta, anchor = seed(folder, schema, mode)
        p = None
        try:
            baseline, original_id = content(target), identity(target)
            original_mirror = digest(sibling(target, '.legacy-map.json'))
            if crash_hook:
                hook, suffix = crash_hook
                p = start(target, delta, hook)
                wait_marker(p, sibling(target, suffix))
                before = retained(target)
                p.kill()
                collect(folder, 'hard-crash', p, require_json=False)
                assert retained(target) == before
                report = None
            else:
                rc, report = run(folder, 'cancel', 'migrate', target, delta, ('--inject', 'precommit-cancel'))
                assert rc == 4 and report['atomicity']['rolled_back'], report
                observation = report['atomicity']['recovery']
                assert observation['rollback_requested'] and observation['sdk_status'] == 0, observation
                assert observation['logical_state'] == 'unverified' and observation['automatic_retirement_blocked']
                assert report['atomicity']['lock'] == 'retained-pending'
            assert content(target) == baseline and identity(target) == original_id
            intent = json.loads(sibling(target, '.migration-pending.json').read_text())
            assert digest(sibling(target, '.legacy-map.json.before-' + intent['artifact_token'])) == original_mirror
            compatibility = pending_refusals(folder, target, first)
            anchor.execute("UPDATE books SET title='ordinary-while-recovery-pending' WHERE id=1")
            anchor.commit()
            later = content(target)
            rc, report = run(folder, 'reopen-after-writer', 'recover-mirror', target, extra=('--break-lock',))
            assert rc == 5 and report['code'] == 'recovery-unverified', report
            assert content(target) == later and identity(target) == original_id
            return dict(compatibility, original_rows_preserved=True, later_write_preserved=True,
                        no_database_restore=True, automatic_recovery_completed=False)
        finally:
            if p is not None:
                stop_save(folder, 'abort', p)
            anchor.close()

    def hold_delete(path):
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.CloseHandle.argtypes, api.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
        bad = ctypes.c_void_p(-1).value
        handle = api.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
        assert handle != bad, ctypes.get_last_error()
        control = api.CreateFileW(str(path), 0x10000, 7, None, 3, 0x80, None)
        error = ctypes.get_last_error()
        if control != bad:
            api.CloseHandle(control)
        if control != bad or error != 32:
            api.CloseHandle(handle)
            raise AssertionError(('native journal deletion refusal', error))
        def release():
            assert api.CloseHandle(handle), 'release native handle'
        return release

    def physical_fault(folder, schema):
        target, first, delta, anchor = seed(folder, schema, 'delete')
        baseline = content(target)
        old_mode = stat.S_IMODE(folder.stat().st_mode)
        control = folder / 'owned-unlink-control'
        control.write_text('disposable owned control')
        p, release, cleanup_errors = None, None, []
        calibration = {'schema': schema, 'product_io_logger': 'not-installed'}
        try:
            p = start(target, delta, 'precommit-mirror-pause')
            wait_marker(p, sibling(target, '.precommit-mirror-ready'))
            before = retained(target)
            journal = sibling(target, '-journal')
            assert journal.stat().st_size > 0
            if os.name == 'nt':
                release = hold_delete(journal)
                calibration.update(native_error=32, mechanism='exact journal no-delete-share')
                # Let the real existing hook time out, not simulated SIGTERM.
            else:
                folder.chmod(old_mode & ~0o222)
                release = lambda: folder.chmod(old_mode)
                try:
                    control.unlink()
                    raise AssertionError('native unlink refusal did not calibrate')
                except PermissionError as error:
                    calibration.update(native_error=error.errno, mechanism='parent directory write refusal')
                p.send_signal(signal.SIGTERM)
            out, err = p.communicate(timeout=35)
            calibration['exit_code'] = p.returncode
            calibration['report'] = json.loads(out)
        finally:
            if release:
                try:
                    release()
                except Exception as error:
                    cleanup_errors.append('fault release: ' + repr(error))
            if p is not None:
                try:
                    if p.poll() is None:
                        p.kill()
                    tail_out, tail_err = p.communicate(timeout=10)
                    out, err = locals().get('out', tail_out), locals().get('err', tail_err)
                except Exception as error:
                    cleanup_errors.append('child cleanup: ' + repr(error))
            try:
                anchor.close()
            except Exception as error:
                cleanup_errors.append('anchor close: ' + repr(error))
            for suffix, data in [('stdout.txt', locals().get('out', '')), ('stderr.txt', locals().get('err', ''))]:
                try:
                    (a.work / (folder.name + '.' + suffix)).write_text(data, encoding='utf-8')
                except Exception as error:
                    cleanup_errors.append('evidence write: ' + repr(error))
            calibration['cleanup_errors'] = cleanup_errors
            (a.work / (folder.name + '.calibration.json')).write_text(json.dumps(calibration, indent=2) + '\n')
        assert not cleanup_errors, cleanup_errors
        report = calibration['report']
        assert report['atomicity']['recovery']['rollback_requested'], report
        assert report['atomicity']['recovery']['automatic_retirement_blocked'], report
        assert retained(target) == before
        assert content(target) == baseline
        assert report['atomicity']['recovery']['io_observation'] == 'not-installed'
        return dict(calibration, native_refusal_measured=True, exact_evidence_retained=True,
                    current_fixture_parity=True, internal_product_io_attributed=False)

    def foreign_cleanup(folder, kind, late=False):
        target, first, delta, anchor = seed(folder, 7, 'wal')
        p = None
        try:
            hook, suffix = ('mirror-retire-pause', '.mirror-retire-ready') if late else ('mirror-pause', '.mirror-ready')
            p = start(target, delta, hook)
            wait_marker(p, sibling(target, suffix))
            token = json.loads(sibling(target, '.migration-pending.json').read_text())['artifact_token']
            path = sibling(target, {'lock': '.migrate-lock', 'mirror': '.legacy-map.json',
                                    'intent': '.migration-pending.json',
                                    'preimage': '.legacy-map.json.before-' + token}[kind])
            replacement = folder / 'foreign-replacement'
            replacement.write_bytes(b'foreign-nonce\n' if kind == 'lock' else path.read_bytes())
            os.replace(replacement, path)
            foreign = identity(path), digest(path)
            sibling(target, suffix + '.resume').touch()
            rc, report = collect(folder, 'foreign', p)
            assert (identity(path), digest(path)) == foreign
            if kind != 'lock':
                assert rc != 0 and sibling(target, '.migration-pending.json').exists(), report
            else:
                assert any(x['code'] == 'migration-lock-changed' for x in report['entries']), report
            return {'foreign_identity_and_bytes_untouched': True, 'kind': kind, 'late_retirement_boundary': late}
        finally:
            if p is not None:
                stop_save(folder, 'foreign', p)
            anchor.close()

    def malformed(folder):
        target, first, delta, anchor = seed(folder, 6, 'delete')
        try:
            pending, lock = sibling(target, '.migration-pending.json'), sibling(target, '.migrate-lock')
            pending.write_bytes(b'{"version":3,')
            lock.write_text('foreign-unchanged\n')
            before = content(target), identity(target), digest(pending), identity(lock), digest(lock)
            rc, report = run(folder, 'partial-intent', 'migrate', target, delta, ('--break-lock',))
            assert rc != 0 and report['code'] == 'mirror-intent-invalid', report
            assert (content(target), identity(target), digest(pending), identity(lock), digest(lock)) == before
            return {'partial_intent_fail_closed_before_open': True, 'foreign_lock_not_removed': True}
        finally:
            anchor.close()

    def execute(name, function):
        folder = a.work / name
        folder.mkdir()
        item = {'name': name, 'passed': False}
        cases.append(item)
        try:
            item['details'] = function(folder)
            item['passed'] = True
        except Exception:
            item['error'] = traceback.format_exc()
            (a.work / (name + '.error.txt')).write_text(item['error'], encoding='utf-8')
        print(json.dumps(item), flush=True)

    for schema in (6, 7):
        for mode in ('delete', 'wal'):
            execute('commit-schema%d-%s' % (schema, mode), lambda f, s=schema, m=mode: normal(f, s, m))
            execute('cancel-schema%d-%s' % (schema, mode), lambda f, s=schema, m=mode: abort(f, s, m))
            for hook, suffix in [('intent-pause', '.intent-ready'), ('precommit-mirror-pause', '.precommit-mirror-ready')]:
                execute('%s-schema%d-%s' % (hook, schema, mode),
                        lambda f, s=schema, m=mode, h=hook, x=suffix: abort(f, s, m, (h, x)))
        execute('native-delete-refusal-schema%d' % schema, lambda f, s=schema: physical_fault(f, s))
    for kind in ('lock', 'mirror', 'intent', 'preimage'):
        execute('foreign-' + kind, lambda f, k=kind: foreign_cleanup(f, k))
    execute('foreign-mirror-final-retirement', lambda f: foreign_cleanup(f, 'mirror', True))
    execute('foreign-intent-final-retirement', lambda f: foreign_cleanup(f, 'intent', True))
    execute('partial-v3-intent', malformed)
    evidence['passed'] = len(cases) == 25 and all(case['passed'] for case in cases)
    evidence['executables_sha256'] = {name: digest(path) for name, path in
                                    [('candidate', a.tool), ('actual_sdk340', a.old_tool), ('tested_v2', a.v2_tool)]}
    (a.work / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence))
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
