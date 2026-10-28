#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only safety matrix over frozen reviewed v2 product sources."""
import argparse
import csv
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

OLD_SDK_REF = 'c2d23c29a3b2096c2236fdb414dcd1e66d3243b4'
SOURCES = {
    'extras/migration/CMakeLists.txt': 'b3ce74a1ad235859cf2656ea99c09a2d8447fc365484a20bedd77eeba5df4ab9',
    'extras/migration/src/lm_main.c': '2c36cb0d8c4102b35e11f45419820de5154ec98f5819694567ca3e239814b5ff',
    'extras/migration/src/lm_mirror.c': '3275bafb28e3767921ca1756f612abbd2192ac80651a887952767791db5d976a',
    'extras/migration/src/lm_mirror.h': 'dccc5374b27f6614a7872cc584a952c11acf767200a8aa68ae1cc24f5c7b6be3',
}


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('All execution, fixtures and artifact parsing belong in GitHub Actions.')
    import legacy_data as L
    ap = argparse.ArgumentParser()
    ap.add_argument('--tool', required=True)
    ap.add_argument('--old-tool', required=True)
    ap.add_argument('--work', required=True, type=Path)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
    results = []
    evidence = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': os.environ.get('RUNNER_OS'),
                'old_sdk_ref': OLD_SDK_REF, 'product_sources': SOURCES, 'cases': results, 'passed': False,
                'contract': 'process-crash/current-state safety; ledger hash is never historical COMMIT proof'}

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
            (folder / 'exception.txt').write_text(entry['error'], encoding='utf-8')
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

    try:
        for path, digest in SOURCES.items():
            assert sha(path) == digest, 'reviewed product source drift: ' + path
        evidence['tool_sha256'], evidence['old_tool_sha256'] = sha(a.tool), sha(a.old_tool)
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
        evidence['passed'] = len(results) == 15 and all(case['passed'] for case in results)
    finally:
        (a.work / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(evidence))
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
