#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only safety matrix over frozen reviewed v2 product sources."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import time
import traceback

OLD_SDK_REF = 'c2d23c29a3b2096c2236fdb414dcd1e66d3243b4'
SOURCES = {
    'extras/migration/CMakeLists.txt': 'b3ce74a1ad235859cf2656ea99c09a2d8447fc365484a20bedd77eeba5df4ab9',
    'extras/migration/src/lm_main.c': 'dc8136ab8127033d24f8843109423d5d262b1bfe742134b078cd43f82ddb523e',
    'extras/migration/src/lm_mirror.c': '9e11dab71c01c7539af4fa711badc3e0c0ed728d97444a296270fd354bc6f9cc',
    'extras/migration/src/lm_mirror.h': 'e913b5e9b776c2563d2c77558845c6f63882845961624fde090df59ea64da6c9',
}


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('All execution, fixtures and artifact parsing belong in GitHub Actions.')
    import legacy_data as L
    ap = argparse.ArgumentParser()
    ap.add_argument('--tool', required=True)
    ap.add_argument('--old-tool', required=True)
    ap.add_argument('--observer', required=True)
    ap.add_argument('--work', required=True, type=Path)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
    results = []
    evidence = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': os.environ.get('RUNNER_OS'),
                'old_sdk_ref': OLD_SDK_REF, 'product_sources': SOURCES, 'cases': results, 'passed': False,
                'contract': 'process-crash/current-state safety; ledger hash is never historical COMMIT proof'}
    evidence['rollback_observation_contract'] = {
        'sdk_only_error_observability': 'not available: full ROLLBACK drops lower-layer I/O status',
        'diagnostic_boundary': 'unchanged installed SDK plus public SQLite error logging; no substituted returns',
        'wal_io_fault_platforms': ['Windows'],
        'wal_io_fault_gap': 'Linux/macOS ordinary permission controls do not calibrate existing-handle WAL reads',
        'full_candidate_acceptance': False,
        'pending_product_risk': 'SDK OK alone currently permits mirror evidence retirement; mitigation not implemented',
    }

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def sibling(target, suffix):
        return Path(str(target) + suffix)

    def mirror(target):
        return sibling(target, '.legacy-map.json')

    def pending(target):
        return sibling(target, '.migration-pending.json')

    def connection(target, readonly=False, timeout=0):
        return sqlite3.connect(target.resolve().as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=timeout)

    def state(db):
        ledger = None
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='exr_migration_ledger'").fetchone():
            row = db.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()
            ledger = row[0] if row else None
        return (db.execute('PRAGMA user_version').fetchone()[0],
                db.execute('SELECT id,title,source FROM books ORDER BY id').fetchall(),
                db.execute('SELECT id,text FROM notes ORDER BY id').fetchall(), ledger)

    def read_state(target):
        db = connection(target, readonly=True)
        try:
            return state(db)
        finally:
            db.close()

    def record(folder, name, p):
        (folder / (name + '.stdout.txt')).write_text(p.stdout, encoding='utf-8')
        (folder / (name + '.stderr.txt')).write_text(p.stderr, encoding='utf-8')
        return p.returncode, json.loads(p.stdout)

    def run(folder, name, command, target, pack=None, extra=(), tool=None):
        cmd = [tool or a.tool, command, '--target', str(target)]
        if pack is not None:
            cmd += ['--pack', str(pack)]
        p = subprocess.run(cmd + list(extra), capture_output=True, text=True, env=env, timeout=45)
        return record(folder, name, p)

    def seed(folder, schema=7):
        target = folder / 'library.sqlite'
        first, delta = folder / 'seed.exrpack', folder / 'delta.exrpack'
        first.write_bytes(L.build_pack([L.entry(L.book_record('seed', 'seed.txt'), L.TXT)],
                                       [L.note_record('seed-note', 'seed', 'lantern keeper', 'retained note')]))
        delta.write_bytes(L.build_pack([L.entry(L.book_record('delta', 'delta.txt'), L.TXT_OTHER)], []))
        rc, report = run(folder, 'seed', 'migrate', target, first, tool=a.old_tool if schema == 6 else a.tool)
        assert rc == 0 and read_state(target)[0] == schema, report
        return target, first, delta

    def wait_marker(p, marker):
        deadline = time.monotonic() + 20
        while not marker.exists() and p.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists(), 'rendezvous missing: ' + str(marker)

    def start(target, pack, hook, tool=None, command='migrate', extra=()):
        cmd = [tool or a.tool, command, '--target', str(target)]
        if pack is not None:
            cmd += ['--pack', str(pack)]
        return subprocess.Popen(cmd + ['--inject', hook] + list(extra), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def finish(folder, name, p, timeout=35):
        out, err = p.communicate(timeout=timeout)
        return record(folder, name, subprocess.CompletedProcess(p.args, p.returncode, out, err))

    def crash(folder, name, target, pack, hook, suffix):
        # A prior hard kill leaves its test rendezvous. Never treat that stale
        # file as evidence that the next process reached the same boundary.
        sibling(target, suffix).unlink(missing_ok=True)
        p = start(target, pack, hook)
        try:
            wait_marker(p, sibling(target, suffix))
        finally:
            if p.poll() is None:
                p.kill()
            out, err = p.communicate(timeout=10)
            (folder / (name + '.stdout.txt')).write_text(out, encoding='utf-8')
            (folder / (name + '.stderr.txt')).write_text(err, encoding='utf-8')

    def recover(folder, name, target, break_lock=True):
        rc, report = run(folder, name, 'recover-mirror', target,
                         extra=('--break-lock',) if break_lock else ())
        assert rc == 0, report
        assert report['atomicity']['transaction']['target_commit'] == 'not-attempted' and not report['atomicity']['rolled_back'], report
        assert not pending(target).exists(), report
        return report

    def windows_hold_against_delete(path):
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        # Permit reads/writes but no DELETE opens. This is a real OS sharing
        # refusal, independent of a runner administrator's backup privileges.
        handle = api.CreateFileW(str(path), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
        invalid = ctypes.c_void_p(-1).value
        assert handle != invalid, ctypes.get_last_error()
        try:
            deletion = api.CreateFileW(str(path), 0x00010000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
            error = ctypes.get_last_error()
            if deletion != invalid:
                api.CloseHandle(deletion)
            assert deletion == invalid and error == 32, ('delete-sharing control', error)
        except Exception:
            api.CloseHandle(handle)
            raise
        return api, handle

    def execute(name, function):
        folder = a.work / name
        folder.mkdir()
        entry = {'name': name, 'passed': False}
        results.append(entry)
        try:
            detail = function(folder)
            if detail:
                entry.update(detail)
            entry['passed'] = True
        except Exception:
            entry['error'] = traceback.format_exc()
            try:
                (folder / 'exception.txt').write_text(entry['error'], encoding='utf-8')
            except OSError:
                # A failed permission-restoration fixture must not erase its
                # original failure or prevent subsequent independent cases.
                (a.work / (name + '.exception.txt')).write_text(entry['error'], encoding='utf-8')
        print(json.dumps(entry), flush=True)

    def matrix_case(folder, schema, mode):
        target, first, delta = seed(folder, schema)
        anchor = connection(target)
        try:
            assert anchor.execute('PRAGMA journal_mode=' + mode).fetchone()[0].lower() == mode
            anchor.execute('PRAGMA wal_autocheckpoint=0')
            anchor.execute("UPDATE books SET title='ordinary-before-owner' WHERE id=1")
            anchor.commit()
            if mode == 'wal':
                assert sibling(target, '-wal').is_file() and sibling(target, '-wal').stat().st_size > 0
            before, original_mirror = state(anchor), mirror(target).read_bytes()
            for hook in ('publish-cancel', 'precommit-cancel'):
                rc, report = run(folder, hook, 'migrate', target, delta, ('--inject', hook))
                assert rc == 4 and report['result'] == 'cancelled' and report['code'] == 'cancelled', report
                assert report['atomicity']['transaction'] == {
                    'target_commit': 'not-committed', 'private_stage_commit': 'not-attempted'}, report
                # The earlier legacy hook never set rolled_back; preserve that
                # field while checking the additive explicit-rollback knowledge.
                assert report['atomicity']['rolled_back'] == (hook == 'precommit-cancel'), report
                assert state(anchor) == before and mirror(target).read_bytes() == original_mirror
                assert not pending(target).exists()
                assert not list(folder.glob('library.sqlite.legacy-map.json.before-*'))
                assert not list(folder.glob('library.sqlite.legacy-map.json.staged-*'))
            rc, report = run(folder, 'precommit-publication-failure', 'migrate', target, delta, ('--inject', 'sidecar-fail'))
            assert rc == 3 and report['code'] == 'ledger-publish-failed' and report['atomicity']['rolled_back'], report
            assert report['atomicity']['transaction']['target_commit'] == 'not-committed', report
            assert state(anchor) == before and mirror(target).read_bytes() == original_mirror and not pending(target).exists()

            crash(folder, 'precommit-crash', target, delta, 'precommit-mirror-pause', '.precommit-mirror-ready')
            assert pending(target).exists()
            # No read-only hot-journal recovery is demanded before the tool opens its owner.
            recover(folder, 'precommit-recover', target)
            assert state(anchor) == before and mirror(target).read_bytes() == original_mirror

            # Active migration owns the SQLite writer lock, including schema upgrade.
            p = start(target, delta, 'intent-pause')
            try:
                wait_marker(p, sibling(target, '.intent-ready'))
                try:
                    anchor.execute("UPDATE books SET title='must-not-commit' WHERE id=1")
                    anchor.commit()
                    raise AssertionError('ordinary writer committed while migration owner was held')
                except sqlite3.OperationalError as error:
                    assert 'locked' in str(error).lower() or 'busy' in str(error).lower(), error
                    anchor.rollback()
                sibling(target, '.intent-ready.resume').touch()
                rc, report = finish(folder, 'owner-excludes-writer', p)
                assert rc == 0, report
            finally:
                if p.poll() is None:
                    p.kill(); p.communicate(timeout=10)
            assert state(anchor)[0] == 7 and len(state(anchor)[1]) == 2

            crash(folder, 'committed-crash', target, delta, 'commit-pause', '.commit-ready')
            anchor.execute("UPDATE books SET title='ordinary-after-COMMIT' WHERE id=1")
            anchor.commit()
            committed = state(anchor)
            recover(folder, 'preserve-ordinary-writer', target)
            assert state(anchor) == committed and mirror(target).read_bytes() == committed[3]

            crash(folder, 'busy-recovery-seed', target, delta, 'commit-pause', '.commit-ready')
            intent_bytes, mirror_bytes = pending(target).read_bytes(), mirror(target).read_bytes()
            anchor.execute('BEGIN IMMEDIATE')
            anchor.execute("UPDATE books SET title='writer-holds-owner' WHERE id=1")
            rc, report = run(folder, 'recovery-busy', 'recover-mirror', target, extra=('--break-lock',))
            assert rc == 5 and report['code'] == 'target-busy', report
            assert pending(target).read_bytes() == intent_bytes and mirror(target).read_bytes() == mirror_bytes
            anchor.commit()
            latest = state(anchor)
            recover(folder, 'busy-recovery-retry', target)
            assert state(anchor) == latest and mirror(target).read_bytes() == latest[3]
            return {'actual_initial_schema': schema, 'journal_mode': mode, 'ordinary_writers_preserved': True,
                    'before_and_after_mirror_publication_cancellation': 'explicit-rollback-confirmed',
                    'recovery_report_has_no_historical_commit_claim': True}
        finally:
            anchor.close()

    def interrupted_committed_target(folder, existing):
        if existing:
            target, _, delta = seed(folder)
        else:
            target, delta = folder / 'library.sqlite', folder / 'delta.exrpack'
            delta.write_bytes(L.build_pack([L.entry(L.book_record('delta', 'delta.txt'), L.TXT_OTHER)], []))
            rc, report = run(folder, 'new-target-precommit-cancel', 'migrate', target, delta,
                             ('--inject', 'publish-cancel'))
            assert rc == 4 and report['result'] == 'cancelled' and not target.exists(), report
            assert not report['atomicity']['rolled_back'] and report['atomicity']['transaction'] == {
                'target_commit': 'not-attempted', 'private_stage_commit': 'not-committed'}, report
            assert not mirror(target).exists() and not pending(target).exists()
        p = start(target, delta, 'commit-pause')
        try:
            wait_marker(p, sibling(target, '.commit-ready'))
            if os.name != 'nt':
                p.send_signal(signal.SIGTERM)
            rc, report = finish(folder, 'postcommit-interruption', p)
        finally:
            if p.poll() is None:
                p.kill(); p.communicate(timeout=10)
        # An acknowledgement interruption is a failed command, not a failed DB COMMIT.
        assert rc == 3 and report['result'] == 'failed' and report['code'] == 'review-hook-timeout', report
        assert not report['atomicity']['rolled_back'] and report['atomicity']['transaction'] == {
            'target_commit': 'committed',
            'private_stage_commit': 'not-attempted' if existing else 'committed'}, report
        committed = read_state(target)
        assert len(committed[1]) == (2 if existing else 1) and pending(target).exists()
        assert json.loads(pending(target).read_bytes())['version'] == (2 if existing else 1)
        recover(folder, 'postcommit-recovery', target, break_lock=False)
        assert read_state(target) == committed and mirror(target).read_bytes() == committed[3]
        return {'target': 'existing-v2' if existing else 'new-v1', 'target_commit': 'committed',
                'termination': 'POSIX cooperative SIGTERM' if os.name != 'nt' else 'Windows acknowledgement timeout',
                'legacy_failed_command_result_preserved': True}

    def foreign_new_target_before_commit(folder):
        target, pack = folder / 'library.sqlite', folder / 'delta.exrpack'
        pack.write_bytes(L.build_pack([L.entry(L.book_record('delta', 'delta.txt'), L.TXT_OTHER)], []))
        p = start(target, pack, 'writer-pause')
        foreign = b'An unrelated target must not be replaced or removed.\n'
        try:
            wait_marker(p, sibling(target, '.writer-ready'))
            with target.open('xb') as output:
                output.write(foreign)
            foreign_id = target.stat().st_ino
            sibling(target, '.writer-resume').touch()
            rc, report = finish(folder, 'foreign-target-early-refusal', p)
        finally:
            if p.poll() is None:
                p.kill(); p.communicate(timeout=10)
        assert rc == 3 and report['result'] == 'failed' and report['code'] == 'target-changed', report
        assert report['atomicity']['transaction'] == {
            'target_commit': 'not-attempted', 'private_stage_commit': 'not-attempted'}, report
        assert not report['atomicity']['rolled_back'], report
        assert target.read_bytes() == foreign and target.stat().st_ino == foreign_id
        assert not pending(target).exists() and not mirror(target).exists()
        assert not list(folder.glob('library.sqlite.migrating-*'))
        return {'foreign_target_bytes_and_identity_preserved': True,
                'v2_refusal_before_any_commit_attempt': True,
                'historical_publication_conflict_assertion': 'retained-in-inherited-probe-not-v2-acceptance'}

    def commit_error_unknown(folder):
        target, _, delta = seed(folder)
        before, external = read_state(target), mirror(target).read_bytes()
        p = start(target, delta, 'precommit-mirror-pause')
        reader = None
        try:
            wait_marker(p, sibling(target, '.precommit-mirror-ready'))
            reader = connection(target, readonly=True)
            assert reader.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
            reader.execute('BEGIN')
            reader.execute('SELECT count(*) FROM books').fetchone()
            sibling(target, '.precommit-mirror-ready.resume').touch()
            rc, report = finish(folder, 'commit-busy', p)
            assert rc == 3 and report['code'] == 'sdk-error' and 'committing migration' in report['message'], report
            assert not report['atomicity']['rolled_back'] and report['atomicity']['transaction'] == {
                'target_commit': 'unknown', 'private_stage_commit': 'not-attempted'}, report
            assert pending(target).exists()
        finally:
            if reader is not None:
                reader.close()
            if p.poll() is None:
                p.kill(); p.communicate(timeout=10)
        # A separate current-state observation is not retroactive commit knowledge.
        assert read_state(target) == before
        recover(folder, 'commit-error-recovery', target, break_lock=False)
        assert read_state(target) == before and mirror(target).read_bytes() == external
        return {'target_commit': 'unknown', 'rollback_observed_independently': True,
                'recovery_report_has_no_historical_commit_claim': True}

    def equal_ledger_real_commit(folder):
        target, first, _ = seed(folder)
        writer = connection(target)
        try:
            writer.execute('DELETE FROM notes')
            writer.commit()
        finally:
            writer.close()
        before = read_state(target)
        assert not before[2]
        crash(folder, 'equal-ledger-commit', target, first, 'commit-pause', '.commit-ready')
        after = read_state(target)
        intent = json.loads(pending(target).read_bytes())
        assert intent['before_sha'] == intent['after_sha'] and before[3] == after[3]
        assert len(after[2]) == 1 and after != before
        recover(folder, 'equal-ledger-recovery', target)
        assert read_state(target) == after and mirror(target).read_bytes() == after[3]
        return {'equal_ledger_bytes_with_real_note_restoration': True,
                'recovery_report_has_no_historical_commit_claim': True}

    def shared_owner(folder, holder_old):
        target, first, delta = seed(folder, 6)
        p = start(target, delta, 'publish-pause' if holder_old else 'intent-pause',
                  tool=a.old_tool if holder_old else a.tool)
        suffix = '.review-ready' if holder_old else '.intent-ready'
        resume = '.review-resume' if holder_old else '.intent-ready.resume'
        try:
            wait_marker(p, sibling(target, suffix))
            lock = sibling(target, '.migrate-lock')
            lock_bytes, lock_id = lock.read_bytes(), lock.stat().st_ino
            rc, report = run(folder, 'contender', 'migrate', target, first, tool=a.tool if holder_old else a.old_tool)
            assert rc == 5 and report['code'] == 'target-busy', report
            assert lock.read_bytes() == lock_bytes and lock.stat().st_ino == lock_id
            sibling(target, resume).touch()
            rc, report = finish(folder, 'holder', p)
            assert rc == 0 and not lock.exists(), report
            return {'holder': 'actual-sdk-3.40' if holder_old else 'reviewed-v2', 'no-break-lock-while-live': True}
        finally:
            if p.poll() is None:
                p.kill(); p.communicate(timeout=10)

    def foreign_target(folder):
        target, first, delta = seed(folder)
        crash(folder, 'committed-crash', target, delta, 'commit-pause', '.commit-ready')
        foreign_folder = folder / 'foreign-owner'
        foreign_folder.mkdir()
        foreign, _, _ = seed(foreign_folder, 6)
        os.replace(foreign, target)
        foreign_bytes, external, intent = target.read_bytes(), mirror(target).read_bytes(), pending(target).read_bytes()
        rc, report = run(folder, 'foreign-owner-refused', 'recover-mirror', target, extra=('--break-lock',))
        assert rc != 0 and report['code'] == 'mirror-recovery-conflict', report
        assert target.read_bytes() == foreign_bytes and read_state(target)[0] == 6
        assert mirror(target).read_bytes() == external and pending(target).read_bytes() == intent
        retained = folder / 'retained-foreign.sqlite'
        target.rename(retained)
        rc, report = run(folder, 'absent-target-refused', 'recover-mirror', target)
        assert rc != 0 and not target.exists() and retained.read_bytes() == foreign_bytes and pending(target).read_bytes() == intent, report
        return {'foreign_schema6_not_upgraded': True, 'absent_target_not_created': True}

    def preimage_read_refusal(folder):
        target, first, delta = seed(folder, 6)
        before, external = read_state(target), mirror(target).read_bytes()
        crash(folder, 'legacy-precommit-crash', target, delta, 'precommit-mirror-pause', '.precommit-mirror-ready')
        intent = json.loads(pending(target).read_bytes())
        preimage = sibling(mirror(target), '.before-' + intent['artifact_token'])
        planned, pending_bytes = mirror(target).read_bytes(), pending(target).read_bytes()
        account, retained, victim = None, folder / 'retained-preimage.json', folder / 'foreign-victim.json'
        if os.name != 'nt':
            preimage.rename(retained)
            victim.write_bytes(b'foreign content must remain')
            preimage.symlink_to(victim.resolve())
        else:
            who = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], check=True, capture_output=True, text=True)
            sid = next(csv.reader([who.stdout.strip()]))[-1]
            assert sid.startswith('S-1-')
            account = '*' + sid
            acl = subprocess.run(['icacls', str(preimage), '/deny', account + ':(R)'], check=True, capture_output=True, text=True)
            (folder / 'acl-deny.txt').write_text(acl.stdout + acl.stderr, encoding='utf-8')
        try:
            if account:
                try:
                    with preimage.open('rb') as file:
                        file.read(1)
                except PermissionError:
                    pass
                else:
                    raise AssertionError('read ACL did not deny an ordinary file open')
            rc, report = run(folder, 'preimage-read-refused', 'recover-mirror', target, extra=('--break-lock',))
            assert rc != 0 and pending(target).read_bytes() == pending_bytes and mirror(target).read_bytes() == planned, report
            assert read_state(target) == before
            if os.name != 'nt':
                assert preimage.is_symlink() and victim.read_bytes() == b'foreign content must remain'
        finally:
            if account:
                restored = []
                # A failing product may already have renamed the denied owned
                # preimage into the mirror. Restore access there too so failure
                # artifacts remain readable; never erase the failed assertion.
                for path in (preimage, mirror(target)):
                    # Do not gate restoration on an access-sensitive exists()
                    # query. Attempt both owned names before checking either.
                    acl = subprocess.run(['icacls', str(path), '/remove:d', account], capture_output=True, text=True)
                    restored.append((path, acl))
                (folder / 'acl-restore.txt').write_text('\n'.join(
                    str(path) + '\n' + acl.stdout + acl.stderr for path, acl in restored), encoding='utf-8')
                for path, acl in restored:
                    try:
                        path.lstat()
                    except FileNotFoundError:
                        continue
                    assert acl.returncode == 0, (path, acl.stdout, acl.stderr)
                    with path.open('rb') as file:
                        file.read(1)
            else:
                preimage.unlink()
                retained.rename(preimage)
        recover(folder, 'preimage-access-restored', target)
        assert read_state(target) == before and mirror(target).read_bytes() == external
        return {'fixture': 'Windows read ACL' if account else 'POSIX preimage symlink', 'foreign_content_preserved': True}

    def special_mirror(folder):
        target, first, delta = seed(folder)
        before = target.read_bytes()
        retained = folder / 'retained-mirror.json'
        mirror(target).rename(retained)
        foreign_dir = folder / 'foreign-directory'
        foreign_dir.mkdir()
        victim = foreign_dir / 'keep.txt'
        victim.write_text('untouched', encoding='utf-8')
        kind = 'POSIX FIFO'
        try:
            if os.name == 'nt':
                kind = 'Windows directory junction'
                p = subprocess.run(['cmd', '/c', 'mklink', '/J', str(mirror(target)), str(foreign_dir)], capture_output=True, text=True)
                (folder / 'junction.txt').write_text(p.stdout + p.stderr, encoding='utf-8')
                assert p.returncode == 0, (p.stdout, p.stderr)
                assert os.lstat(mirror(target)).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
            else:
                os.mkfifo(mirror(target))
            for command in ('migrate', 'verify', 'dump'):
                rc, report = run(folder, command + '-special', command, target, first if command != 'dump' else None)
                assert rc == (3 if command == 'migrate' else 2) and report['code'] == 'ledger-unreadable', report
                assert target.read_bytes() == before and victim.read_text(encoding='utf-8') == 'untouched'
        finally:
            if os.name == 'nt':
                if mirror(target).exists():
                    os.rmdir(mirror(target))
            elif mirror(target).exists():
                mirror(target).unlink()
            retained.rename(mirror(target))
        return {'fixture': kind, 'no_blocking_special_file_read': True}

    def real_cleanup_failure(folder):
        target, first, delta = seed(folder)
        crash(folder, 'committed-crash', target, delta, 'commit-pause', '.commit-ready')
        committed = read_state(target)
        p = start(target, None, 'mirror-retire-pause', command='recover-mirror', extra=('--break-lock',))
        old_mode, blocker, out, err = stat.S_IMODE(folder.stat().st_mode), None, '', ''
        try:
            wait_marker(p, sibling(target, '.mirror-retire-ready'))
            assert not list(folder.glob('library.sqlite.legacy-map.json.before-*'))
            writer = connection(target)
            try:
                writer.execute("UPDATE books SET title='ordinary-write-after-recovery-owner-release' WHERE id=1")
                writer.commit()
                committed = state(writer)
            finally:
                writer.close()
            if os.name == 'nt':
                blocker = windows_hold_against_delete(pending(target))
                sibling(target, '.mirror-retire-ready.resume').touch()
            else:
                p.send_signal(signal.SIGSTOP)
                _, stopped = os.waitpid(p.pid, os.WUNTRACED)
                assert os.WIFSTOPPED(stopped)
                sibling(target, '.mirror-retire-ready.resume').touch()
                folder.chmod(old_mode & ~0o222)
                p.send_signal(signal.SIGCONT)
            out, err = p.communicate(timeout=15)
        finally:
            if blocker:
                api, handle = blocker
                assert api.CloseHandle(handle), 'cannot release delete-sharing fixture'
            elif os.name != 'nt':
                folder.chmod(old_mode)
            if p.poll() is None:
                p.kill(); out, err = p.communicate(timeout=10)
        rc, report = record(folder, 'real-cleanup-refusal', subprocess.CompletedProcess(p.args, p.returncode, out, err))
        assert rc == 0 and report['code'] == 'mirror-cleanup-pending' and report['atomicity']['mirror']['pending'], report
        assert report['atomicity']['transaction']['target_commit'] == 'not-attempted' and not report['atomicity']['rolled_back'], report
        assert pending(target).exists() and read_state(target) == committed and mirror(target).read_bytes() == committed[3]
        recover(folder, 'real-cleanup-retry', target)
        assert read_state(target) == committed
        return {'real_intent_unlink_failure': True, 'database_owner_released_before_permission_fault': True,
                'fixture': 'Windows no-delete-share handle' if os.name == 'nt' else 'POSIX directory write denial',
                'ordinary_write_after_owner_release_preserved': True}

    # Additive transaction-candidate acceptance. The original fifteen cases and
    # unchanged 65-scenario companion remain intact, including its four failures.
    def candidate_anchor(target, mode):
        db = connection(target)
        try:
            assert db.execute('PRAGMA journal_mode=' + mode).fetchone()[0].lower() == mode
            db.execute('PRAGMA wal_autocheckpoint=0')
            if mode == 'wal':
                # Keep a real WAL connection alive for every WAL variant.
                db.execute("UPDATE books SET title=title || ' [WAL control]' WHERE id=1")
                db.commit()
                assert sibling(target, '-wal').is_file() and sibling(target, '-wal').stat().st_size > 0
            return db
        except Exception:
            db.close()
            raise

    def file_identity(path):
        info = path.stat()
        assert stat.S_ISREG(info.st_mode)
        return info.st_dev, info.st_ino

    def content_rows(db):
        # Retain every original column/byte value, not only a count or title.
        # Schema 6 -> 7 may add columns; existing columns must remain equal.
        result = {}
        for table in ('books', 'notes'):
            cursor = db.execute('SELECT * FROM ' + table + ' ORDER BY id')
            names = [column[0] for column in cursor.description]
            result[table] = [dict(zip(names, row)) for row in cursor.fetchall()]
        return result

    def original_rows_preserved(before, after):
        for table, rows in before.items():
            current = {row['id']: row for row in after[table]}
            for row in rows:
                assert row['id'] in current, ('missing original row', table, row['id'])
                for column, value in row.items():
                    assert current[row['id']].get(column) == value, ('changed original value', table, row['id'], column)

    def no_owned_residue(folder, target):
        assert not pending(target).exists()
        assert not sibling(target, '.migrate-lock').exists()
        for suffix in ('.migrating-*', '.pre-*', '.legacy-map.json.before-*', '.legacy-map.json.staged-*'):
            assert not list(folder.glob(target.name + suffix)), suffix

    def candidate_lineage(folder, schema, mode):
        target, first, _ = seed(folder, schema)
        anchor = candidate_anchor(target, mode)
        try:
            before, rows, identity = state(anchor), content_rows(anchor), file_identity(target)
            has_internal_lineage = before[3] is not None
            assert has_internal_lineage == (schema == 7)
            # schema 6 was made by the actual old SDK: removing its external
            # ledger truly removes lineage. schema 7 retains internal lineage.
            mirror(target).unlink()
            rc, report = run(folder, 'rebuild-missing-mirror', 'migrate', target, first)
            assert rc == 0, report
            assert report['counts']['books_created'] == 0, report
            assert report['counts']['notes_created'] == 0, report
            expected = 'already-migrated' if has_internal_lineage else 'adopted-existing'
            wrong = 'adopted-existing' if has_internal_lineage else 'already-migrated'
            seed_entries = [entry['code'] for entry in report['entries'] if entry.get('legacy_id') == 'seed']
            assert expected in seed_entries and wrong not in seed_entries, report
            after = state(anchor)
            assert after[0] == 7 and len(after[1]) == len(before[1]) and len(after[2]) == len(before[2])
            original_rows_preserved(rows, content_rows(anchor))
            assert file_identity(target) == identity
            assert mirror(target).read_bytes() == after[3]
            if has_internal_lineage:
                assert after[3] == before[3], 'retained internal lineage must not be relabeled'
            no_owned_residue(folder, target)
            return {'actual_initial_schema': schema, 'journal_mode': mode,
                    'internal_lineage_survived_external_loss': has_internal_lineage,
                    'truthful_event': expected, 'no_duplicate_books_or_notes': True,
                    'all_original_book_and_note_columns_preserved': True}
        finally:
            anchor.close()

    def candidate_existing_content(folder, schema, mode):
        target, _, delta = seed(folder, schema)
        anchor = candidate_anchor(target, mode)
        try:
            rows, identity = content_rows(anchor), file_identity(target)
            p = start(target, delta, 'intent-pause')
            try:
                wait_marker(p, sibling(target, '.intent-ready'))
                try:
                    anchor.execute("UPDATE books SET title='must-not-win-against-owner' WHERE id=1")
                    anchor.commit()
                    raise AssertionError('ordinary write bypassed the transaction owner')
                except sqlite3.OperationalError as error:
                    assert 'locked' in str(error).lower() or 'busy' in str(error).lower(), error
                    anchor.rollback()
                sibling(target, '.intent-ready.resume').touch()
                rc, report = finish(folder, 'existing-in-place-commit', p)
            finally:
                if p.poll() is None:
                    p.kill(); p.communicate(timeout=10)
            assert rc == 0, report
            assert report['atomicity']['stage'] == 'none', report
            assert report['atomicity']['transaction'] == {
                'target_commit': 'committed', 'private_stage_commit': 'not-attempted'}, report
            assert file_identity(target) == identity
            original_rows_preserved(rows, content_rows(anchor))
            assert len(state(anchor)[1]) == len(rows['books']) + 1
            anchor.execute("UPDATE books SET title='ordinary-after-successful-migration' WHERE id=1")
            anchor.commit()
            latest = state(anchor)
            recover(folder, 'idempotent-recovery-preserves-later-write', target)
            assert state(anchor) == latest and file_identity(target) == identity
            no_owned_residue(folder, target)
            return {'actual_initial_schema': schema, 'journal_mode': mode,
                    'existing_file_identity_preserved': True, 'database_stage': 'none',
                    'all_original_book_and_note_columns_preserved': True,
                    'live_owner_exclusion_and_later_ordinary_write_preserved': True}
        finally:
            anchor.close()

    def candidate_partial_write(folder, schema, mode):
        target, _, _ = seed(folder, schema)
        partial = folder / 'two-imports.exrpack'
        partial.write_bytes(L.build_pack([
            L.entry(L.book_record('first-new', 'first-new.txt'), L.TXT_OTHER),
            L.entry(L.book_record('second-new', 'second-new.txt'), L.TXT_OTHER + b'\nA distinct second original.\n'),
        ], []))
        anchor = candidate_anchor(target, mode)
        try:
            before, rows, identity = state(anchor), content_rows(anchor), file_identity(target)
            mirror_before = mirror(target).read_bytes()
            db_before = target.read_bytes() if mode == 'delete' else None
            rc, report = run(folder, 'second-import-write-failure', 'migrate', target, partial,
                             ('--inject', 'write-fail@1'))
            # Separate assertions expose each old composite predicate directly.
            assert rc == 3, ('exit code', rc, report)
            assert report['result'] == 'failed', ('result', report)
            assert report['code'] == 'injected-write-fail', ('error code', report)
            assert report['counts']['books_created'] == 1, 'first import must really have succeeded before fault'
            assert report['atomicity']['stage'] == 'none', report
            assert report['atomicity']['transaction'] == {
                'target_commit': 'not-attempted', 'private_stage_commit': 'not-attempted'}, report
            # Close-triggered cleanup is not a process-local explicit-rollback
            # acknowledgement. Independently observe current state instead.
            assert not report['atomicity']['rolled_back'], report
            assert state(anchor) == before and content_rows(anchor) == rows
            assert mirror(target).read_bytes() == mirror_before and file_identity(target) == identity
            if mode == 'delete':
                assert target.read_bytes() == db_before
            no_owned_residue(folder, target)
            return {'actual_initial_schema': schema, 'journal_mode': mode,
                    'exit_code': rc, 'error_code': report['code'], 'uncommitted_import_count': 1,
                    'database_stage': 'none', 'target_commit': 'not-attempted',
                    'independent_current_state_rollback_observed': True,
                    'original_mirror_and_all_rows_preserved': True}
        finally:
            anchor.close()

    def candidate_product_rollback_observation(folder, schema):
        target, _, delta = seed(folder, schema)
        anchor = candidate_anchor(target, 'delete')
        before, rows = state(anchor), content_rows(anchor)
        anchor.close()
        original_mirror, identity = mirror(target).read_bytes(), file_identity(target)
        journal = sibling(target, '-journal')
        calibration = folder / 'owned-delete-calibration.txt'
        calibration.write_text('owned disposable deletion calibration', encoding='utf-8')
        p = start(target, delta, 'precommit-mirror-pause')
        blocker, old_mode, out, err = None, stat.S_IMODE(folder.stat().st_mode), '', ''
        fault = {'mode': 'delete', 'actual_initial_schema': schema, 'calibrated': False}
        def journal_observation():
            try:
                with journal.open('rb') as file:
                    header = file.read(32)
                return {'present': True, 'size': journal.stat().st_size, 'first_32_bytes_hex': header.hex()}
            except FileNotFoundError:
                return {'present': False}
        try:
            wait_marker(p, sibling(target, '.precommit-mirror-ready'))
            assert journal.is_file() and journal.stat().st_size > 0, 'real SQLite rollback journal required'
            fault['journal_before_refusal'] = journal_observation()
            intent_bytes, published_mirror = pending(target).read_bytes(), mirror(target).read_bytes()
            intent = json.loads(intent_bytes)
            preimage = sibling(mirror(target), '.before-' + intent['artifact_token'])
            preimage_bytes = preimage.read_bytes()
            assert intent['version'] == 2 and preimage_bytes == original_mirror
            assert published_mirror != original_mirror
            if os.name == 'nt':
                blocker = windows_hold_against_delete(journal)
                fault.update({'calibrated': True, 'mechanism': 'journal no-delete-share handle',
                              'control_error': 32, 'termination': 'real acknowledgement timeout'})
                # Do not resume: the existing hook times out and invokes the
                # real SDK rollback. No injected rollback return is substituted.
            else:
                p.send_signal(signal.SIGSTOP)
                _, stopped = os.waitpid(p.pid, os.WUNTRACED)
                assert os.WIFSTOPPED(stopped)
                folder.chmod(old_mode & ~0o222)
                try:
                    calibration.unlink()
                    raise AssertionError('directory deletion refusal did not calibrate')
                except PermissionError as error:
                    fault.update({'calibrated': True, 'mechanism': 'journal parent-directory write denial',
                                  'control_errno': error.errno, 'termination': 'cooperative SIGTERM'})
                p.send_signal(signal.SIGTERM)
                p.send_signal(signal.SIGCONT)
            out, err = p.communicate(timeout=40)
        finally:
            cleanup_errors = []
            if blocker:
                api, handle = blocker
                try:
                    if not api.CloseHandle(handle):
                        cleanup_errors.append('cannot release journal refusal fixture')
                except Exception as error:
                    cleanup_errors.append('journal handle release: ' + repr(error))
            elif os.name != 'nt':
                try:
                    folder.chmod(old_mode)
                except Exception as error:
                    cleanup_errors.append('directory permission restore: ' + repr(error))
            if p.poll() is None:
                try:
                    p.kill()
                except Exception as error:
                    cleanup_errors.append('child kill: ' + repr(error))
                try:
                    out, err = p.communicate(timeout=10)
                except Exception as error:
                    cleanup_errors.append('child wait: ' + repr(error))
            for name, content in (('product-rollback-observation.stdout.txt', out),
                                  ('product-rollback-observation.stderr.txt', err)):
                try:
                    (folder / name).write_text(content, encoding='utf-8')
                except Exception as error:
                    cleanup_errors.append(name + ': ' + repr(error))
                    try:
                        (a.work / (folder.name + '-' + name)).write_text(content, encoding='utf-8')
                    except Exception as fallback_error:
                        cleanup_errors.append('fallback ' + name + ': ' + repr(fallback_error))
            try:
                fault['journal_after_process_exit'] = journal_observation()
            except Exception as error:
                cleanup_errors.append('journal observation: ' + repr(error))
                fault['journal_after_process_exit'] = {'observation_error': repr(error)}
            fault['cleanup_errors'] = cleanup_errors
            try:
                (folder / 'rollback-fault-calibration.json').write_text(json.dumps(fault, indent=2) + '\n', encoding='utf-8')
            except Exception as error:
                cleanup_errors.append('calibration evidence: ' + repr(error))
                (a.work / (folder.name + '-rollback-fault-calibration.json')).write_text(
                    json.dumps(fault, indent=2) + '\n', encoding='utf-8')
            assert not cleanup_errors, cleanup_errors
        rc, report = record(folder, 'product-rollback-observation', subprocess.CompletedProcess(p.args, p.returncode, out, err))
        # A real OS refusal is not automatically a non-OK SDK result. Record
        # the uninstrumented product's actual disposition without upgrading it
        # into retained-evidence or failed-rollback coverage.
        assert fault['calibrated'], fault
        assert rc != 0 and report['result'] != 'success', report
        assert report['atomicity']['transaction']['target_commit'] in ('not-attempted', 'not-committed'), report
        assert report['atomicity']['transaction']['private_stage_commit'] == 'not-attempted', report
        disposition = {
            'exit_code': rc, 'result': report['result'], 'code': report['code'],
            'reported_rolled_back': report['atomicity']['rolled_back'],
            'exact_intent_retained': pending(target).exists() and pending(target).read_bytes() == intent_bytes,
            'exact_published_mirror_retained': mirror(target).read_bytes() == published_mirror,
            'exact_preimage_path_retained': preimage.exists() and preimage.read_bytes() == preimage_bytes,
            'mirror_is_original': mirror(target).read_bytes() == original_mirror,
        }
        if report['code'] == 'rollback-failed':
            assert rc == 6 and report['result'] == 'inconsistent' and not disposition['reported_rolled_back'], report
            assert disposition['exact_intent_retained'] and disposition['exact_published_mirror_retained'] and disposition['exact_preimage_path_retained'], disposition
        (folder / 'product-evidence-disposition.json').write_text(json.dumps(disposition, indent=2) + '\n')
        assert file_identity(target) == identity
        assert not list(folder.glob(target.name + '.pre-*')), 'external mirror evidence is not a DB preimage'
        # Restore only the OS fault. Let a fresh product owner perform SQLite
        # recovery; never hand-delete/patch the database or its journal.
        recover(folder, 'fresh-owner-after-rollback-observation', target)
        after = connection(target, readonly=True)
        try:
            assert state(after) == before and content_rows(after) == rows
            assert after.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        finally:
            after.close()
        assert mirror(target).read_bytes() == original_mirror and file_identity(target) == identity
        writer = connection(target)
        try:
            writer.execute("UPDATE books SET title='ordinary-after-error-recovery' WHERE id=1")
            writer.commit()
            latest = state(writer)
        finally:
            writer.close()
        recover(folder, 'repeat-recovery-preserves-later-write', target)
        assert read_state(target) == latest
        no_owned_residue(folder, target)
        return dict(fault, product_disposition=disposition,
                    sdk_finish_error_inferred=False, internal_io_attribution='separate diagnostic consumer only',
                    fresh_owner_recovered_original_rows=True, later_ordinary_write_preserved=True,
                    historical_commit_claim=False)

    def full_fixture_rows(db):
        result = {'schema_objects': db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(),
                  'tables': {}}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            columns = tuple(row[1] for row in db.execute('PRAGMA table_info(' + quoted + ')'))
            # Fixture records are small; repr sorting is solely canonical test
            # comparison, never a production receipt or historical COMMIT proof.
            result['tables'][name] = (columns, sorted(db.execute('SELECT * FROM ' + quoted).fetchall(), key=repr))
        return result

    def sqlite_os_log_path(message):
        # Exact pinned os_win.c/os_unix.c logger format, not path substrings.
        # Synthetic parser controls below are not actual fault calibration.
        match = re.fullmatch(r'os_(win|unix)\.c:\d+: \((\d+)\) ([A-Za-z0-9_]+)\((.*?)\) - [^\r\n]*', message)
        if not match:
            return None
        platform, native_error, operation, path = match.groups()
        path = path.replace('\\', '/') if platform == 'win' else path
        if platform == 'win':
            path = path.casefold()
        return platform, int(native_error), operation, path

    def sqlite_log_path_controls():
        checked = 0
        for platform, path, operation in (('win', 'C:/owned/library.sqlite', 'winRead'),
                                          ('unix', '/owned/library.sqlite-journal', 'unlink')):
            expected = path.casefold() if platform == 'win' else path
            def message(candidate):
                return 'os_%s.c:123: (33) %s(%s) - control only' % (platform, operation, candidate)
            assert sqlite_os_log_path(message(path))[3] == expected
            checked += 1
            for suffix in ('-wal', '-journal', '-other', '.before-token'):
                assert sqlite_os_log_path(message(path + suffix))[3] != expected
                checked += 1
            assert sqlite_os_log_path('unstructured unrelated ' + path) is None
            checked += 1
        return {'synthetic_parser_controls': checked, 'exact_filename_equality': True,
                'actual_fault_calibration': False}

    def windows_hold_read_range(path, size):
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        class Overlapped(ctypes.Structure):
            _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                        ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
        api.LockFileEx.restype = wintypes.BOOL
        api.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.DWORD, ctypes.POINTER(Overlapped)]
        api.UnlockFileEx.restype = wintypes.BOOL
        api.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        api.ReadFile.restype = wintypes.BOOL
        api.CloseHandle.argtypes, api.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
        invalid, handle, control = ctypes.c_void_p(-1).value, None, None
        overlap, locked = Overlapped(), False
        try:
            handle = api.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
            assert handle != invalid, ctypes.get_last_error()
            assert api.LockFileEx(handle, 3, 0, size, 0, ctypes.byref(overlap)), ctypes.get_last_error()
            locked = True
            control = api.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
            assert control != invalid, ctypes.get_last_error()
            buffer, count = ctypes.create_string_buffer(size), wintypes.DWORD()
            ok = api.ReadFile(control, buffer, size, ctypes.byref(count), None)
            error = ctypes.get_last_error()
            assert not ok and error == 33, ('exact page-1 ReadFile control', bool(ok), error)
        except Exception:
            if locked:
                api.UnlockFileEx(handle, 0, size, 0, ctypes.byref(overlap))
            if handle not in (None, invalid):
                api.CloseHandle(handle)
            raise
        finally:
            if control not in (None, invalid):
                api.CloseHandle(control)
        def release():
            unlocked = api.UnlockFileEx(handle, 0, size, 0, ctypes.byref(overlap))
            error = ctypes.get_last_error()
            closed = api.CloseHandle(handle)
            assert unlocked and closed, ('release page-1 refusal', bool(unlocked), bool(closed), error)
        return release

    def diagnostic_rollback(folder, schema, mode, refuse):
        target = folder / 'library.sqlite'
        if schema == 6:
            target, _, _ = seed(folder, 6)
        else:
            seed_result = subprocess.run([a.observer, 'seed', str(target)], capture_output=True, text=True, env=env, timeout=30)
            (folder / 'diagnostic-seed.stdout.txt').write_text(seed_result.stdout)
            (folder / 'diagnostic-seed.stderr.txt').write_text(seed_result.stderr)
            assert seed_result.returncode == 0, seed_result.stderr
        anchor = connection(target)
        try:
            assert anchor.execute('PRAGMA journal_mode=' + mode).fetchone()[0].lower() == mode
            assert anchor.execute('PRAGMA user_version').fetchone()[0] == schema
            assert not anchor.execute("SELECT 1 FROM sqlite_master WHERE name='exr_migration_ledger'").fetchone()
            anchor.execute('PRAGMA wal_autocheckpoint=0')
            if mode == 'wal':
                anchor.execute("UPDATE books SET title=title || ' [WAL diagnostic baseline]' WHERE id=1")
                anchor.commit()
                assert anchor.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0
                assert sibling(target, '-wal').stat().st_size == 0
            baseline, baseline_rows, identity = state(anchor), full_fixture_rows(anchor), file_identity(target)
            page_size = anchor.execute('PRAGMA page_size').fetchone()[0]
            old_mode = stat.S_IMODE(folder.stat().st_mode)
            control = folder / 'owned-unlink-control'
            control.write_text('owned disposable unlink control')
        except Exception:
            anchor.close()
            raise
        # Marker/report live OUTSIDE the directory made non-writable by the
        # DELETE control; no publication permission is confused with SDK I/O.
        ready = a.work / (folder.name + '.observer-ready')
        report_path = a.work / (folder.name + '.observer-result.json')
        try:
            p = subprocess.Popen([a.observer, 'observe', str(target), str(ready), str(report_path)],
                                 env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception:
            anchor.close()
            raise
        release, out, err, report = None, '', '', None
        calibration = {'mode': mode, 'refusal_requested': refuse, 'calibrated': False,
                       'actual_initial_schema': schema, 'page_size': page_size,
                       'page1_committed_location': 'main database; WAL checkpointed before SDK open'}
        def journal_state():
            path = sibling(target, '-journal')
            try:
                with path.open('rb') as f:
                    prefix = f.read(32)
                return {'present': True, 'size': path.stat().st_size, 'prefix_hex': prefix.hex()}
            except FileNotFoundError:
                return {'present': False}
        try:
            wait_marker(p, ready)
            if mode == 'delete':
                calibration['journal_before'] = journal_state()
                assert calibration['journal_before']['present'] and calibration['journal_before']['size'] > 0
            if refuse and mode == 'wal':
                assert os.name == 'nt', 'WAL physical read-error fixture is Windows only'
                release = windows_hold_read_range(target, page_size)
                calibration.update(calibrated=True, native_error=33, mechanism='exact main DB page-1 mandatory read refusal')
            elif refuse and os.name == 'nt':
                api, handle = windows_hold_against_delete(sibling(target, '-journal'))
                def release_delete():
                    assert api.CloseHandle(handle), 'release journal refusal handle'
                release = release_delete
                calibration.update(calibrated=True, native_error=32, mechanism='exact journal no-delete-share handle')
            elif refuse:
                folder.chmod(old_mode & ~0o222)
                release = lambda: folder.chmod(old_mode)
                try:
                    control.unlink()
                    raise AssertionError('owned deletion refusal did not calibrate')
                except PermissionError as error:
                    calibration.update(calibrated=True, native_error=error.errno, mechanism='journal parent directory deletion refusal')
            else:
                calibration.update(calibrated=True, mechanism='no-fault negative control')
            p.stdin.write('R'); p.stdin.flush()
            wait_marker(p, report_path)
            report = json.loads(report_path.read_text())
            calibration['sdk_finish_observation'] = report
        finally:
            cleanup_errors = []
            if release:
                try:
                    release()
                except Exception as error:
                    cleanup_errors.append('fault release: ' + repr(error))
            try:
                if p.poll() is None:
                    p.stdin.write('C'); p.stdin.flush()
                out, err = p.communicate(timeout=20)
            except Exception as error:
                cleanup_errors.append('observer close/wait: ' + repr(error))
                try:
                    p.kill()
                except Exception as error:
                    cleanup_errors.append('observer kill: ' + repr(error))
                try:
                    out, err = p.communicate(timeout=10)
                except Exception as error:
                    cleanup_errors.append('observer final wait: ' + repr(error))
            try:
                anchor.close()
            except Exception as error:
                cleanup_errors.append('anchor close: ' + repr(error))
            for name, value in (('observer.stdout.txt', out), ('observer.stderr.txt', err)):
                try:
                    (folder / name).write_text(value, encoding='utf-8')
                except Exception as error:
                    cleanup_errors.append(name + ': ' + repr(error))
                    try:
                        (a.work / (folder.name + '-' + name)).write_text(value, encoding='utf-8')
                    except Exception as fallback_error:
                        cleanup_errors.append('fallback ' + name + ': ' + repr(fallback_error))
            calibration['cleanup_errors'] = cleanup_errors
            try:
                calibration['journal_after'] = journal_state()
            except Exception as error:
                calibration['journal_after'] = {'observation_error': repr(error)}
            try:
                (a.work / (folder.name + '-calibration.json')).write_text(json.dumps(calibration, indent=2) + '\n')
            except Exception as error:
                cleanup_errors.append('calibration write: ' + repr(error))
            assert not cleanup_errors, cleanup_errors
        assert p.returncode == 0 and report is not None, (p.returncode, out, err)
        assert report['sqlite_version'] == '3.54.0' and report['diagnostic_mmap_disabled'], report
        if refuse:
            key = 'finish_read_events' if mode == 'wal' else 'finish_delete_events'
            assert report[key] > 0 and report['finish_io_events'] > 0, report
            code = report['read_error_code' if mode == 'wal' else 'delete_error_code']
            expected_path = str((target if mode == 'wal' else sibling(target, '-journal')).resolve())
            if os.name == 'nt':
                expected_path = expected_path.replace('\\', '/').casefold()
            expected_operation = 'winRead' if mode == 'wal' else ('winDelete' if os.name == 'nt' else 'unlink')
            events = [json.loads(line) for line in err.splitlines() if line.startswith('{')]
            matched = []
            for event in events:
                location = sqlite_os_log_path(event['message'])
                if (event['phase'] == 'sdk-finish' and event['sqlite_code'] == code and location
                        and location[2] == expected_operation and location[3] == expected_path):
                    matched.append(event)
            assert matched, ('no actual SDK finish I/O event for exact owned path', expected_path, events)
            calibration['matched_finish_io_events'] = matched
        else:
            assert report['sdk_ok'] and report['finish_io_events'] == 0, report
        # Actual status is evidence, not predetermined. A swallowed I/O error
        # with SDK OK is an observability limitation, never "SDK rollback failed".
        calibration['classification'] = ('internal-io-error-sdk-ok' if report['sdk_ok'] else 'internal-io-error-sdk-non-ok') if refuse else 'clean-rollback-control'
        # A fresh actual SDK migration owner is the first connection after the
        # old owner/anchor close. Its schema-6 upgrade is inside a transaction
        # ended by real rollback, not an ordinary open that commits an upgrade.
        recovery = subprocess.run([a.observer, 'recover', str(target)], capture_output=True, text=True, env=env, timeout=30)
        (folder / 'fresh-sdk-recovery.stdout.txt').write_text(recovery.stdout)
        (folder / 'fresh-sdk-recovery.stderr.txt').write_text(recovery.stderr)
        assert recovery.returncode == 0, (recovery.returncode, recovery.stdout, recovery.stderr)
        recovery_events = [json.loads(line) for line in recovery.stderr.splitlines() if line.startswith('{')]
        assert not [event for event in recovery_events if (event['sqlite_code'] & 255) == 10], recovery_events
        # Independent fixture SQL verifies the persisted schema and every row;
        # this does not pretend the frozen SDK exposes an integrity-check API.
        fresh = connection(target)
        try:
            assert fresh.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert state(fresh) == baseline and full_fixture_rows(fresh) == baseline_rows
            fresh.execute("UPDATE books SET title='ordinary-after-diagnostic-recovery' WHERE id=1")
            fresh.commit()
            latest = full_fixture_rows(fresh)
        finally:
            fresh.close()
        fresh = connection(target, readonly=True)
        try:
            assert full_fixture_rows(fresh) == latest
        finally:
            fresh.close()
        assert file_identity(target) == identity
        calibration.update(fresh_recovery_exact=True, later_ordinary_write_preserved=True,
                           fresh_sdk_recovery_succeeded=True, verification_sqlite_version=sqlite3.sqlite_version,
                           real_sdk_return_error=not report['sdk_ok'], product_mirror_lifecycle_proved=False)
        (a.work / (folder.name + '-calibration.json')).write_text(json.dumps(calibration, indent=2) + '\n')
        return calibration

    def candidate_rollback_observation(folder, schema):
        result = {'observations': [], 'full_candidate_acceptance': False}
        def observe(name, function):
            child = folder / name
            child.mkdir()
            item = {'name': name, 'passed': False}
            result['observations'].append(item)
            try:
                item['details'] = function(child)
                item['passed'] = True
            except Exception:
                item['error'] = traceback.format_exc()
                # Save outside a potentially inaccessible fault directory.
                (a.work / (name + '-observation-error.txt')).write_text(item['error'])
        observe('product-schema%d-delete' % schema,
                lambda child: candidate_product_rollback_observation(child, schema))
        for mode in (('delete', 'wal') if os.name == 'nt' else ('delete',)):
            for refuse in (False, True):
                observe('diagnostic-schema%d-%s-%s' % (schema, mode, 'fault' if refuse else 'control'),
                        lambda child, m=mode, f=refuse: diagnostic_rollback(child, schema, m, f))
        result['wal_fault_scope'] = 'Windows; see individually recorded observation outcomes' if os.name == 'nt' else 'not covered on this platform'
        (folder / 'observations.json').write_text(json.dumps(result, indent=2) + '\n')
        assert all(item['passed'] for item in result['observations']), result
        return result

    try:
        evidence['sqlite_log_attribution_controls'] = sqlite_log_path_controls()
        for path, digest in SOURCES.items():
            assert sha(path) == digest, 'reviewed product source drift: ' + path
        evidence['tool_sha256'], evidence['old_tool_sha256'] = sha(a.tool), sha(a.old_tool)
        evidence['observer_sha256'] = sha(a.observer)
        evidence['observer_sources_sha256'] = {path: sha(path) for path in (
            'tests/migration/rollback_observe_20261028/CMakeLists.txt',
            'tests/migration/rollback_observe_20261028/observe.c')}
        old_version = subprocess.run([a.old_tool, '--version'], check=True, capture_output=True, text=True).stdout
        (a.work / 'old-sdk-version.txt').write_text(old_version, encoding='utf-8')
        assert '3.40' in old_version, old_version
        for schema in (6, 7):
            for mode in ('delete', 'wal'):
                execute('schema%d-%s' % (schema, mode), lambda folder, s=schema, m=mode: matrix_case(folder, s, m))
        for existing in (False, True):
            execute('postcommit-interrupted-' + ('existing' if existing else 'new'),
                    lambda folder, e=existing: interrupted_committed_target(folder, e))
        execute('foreign-new-target-before-commit', foreign_new_target_before_commit)
        execute('commit-error-unknown', commit_error_unknown)
        execute('equal-ledger-real-commit', equal_ledger_real_commit)
        execute('shared-lock-actual-old-holder', lambda folder: shared_owner(folder, True))
        execute('shared-lock-v2-holder', lambda folder: shared_owner(folder, False))
        execute('foreign-owner-and-absent-target', foreign_target)
        execute('preimage-access-refusal', preimage_read_refusal)
        execute('special-mirror-path', special_mirror)
        execute('real-intent-cleanup-failure', real_cleanup_failure)
        for schema in (6, 7):
            for mode in ('delete', 'wal'):
                for group, function in (
                    ('candidate-lineage', candidate_lineage),
                    ('candidate-existing-content', candidate_existing_content),
                    ('candidate-partial-write', candidate_partial_write),
                ):
                    execute('%s-schema%d-%s' % (group, schema, mode),
                            lambda folder, f=function, s=schema, m=mode: f(folder, s, m))
            execute('candidate-rollback-observation-schema%d' % schema,
                    lambda folder, s=schema: candidate_rollback_observation(folder, s))
        evidence['passed'] = len(results) == 29 and all(case['passed'] for case in results)
    finally:
        (a.work / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(evidence))
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
