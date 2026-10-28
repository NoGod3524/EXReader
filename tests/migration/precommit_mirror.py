#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only existing-target pre-COMMIT publication evidence; old tests unchanged."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import subprocess
import time


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Build/test/fixtures/artifact parsing are GitHub Actions only.')
    import legacy_data as L
    ap = argparse.ArgumentParser()
    ap.add_argument('--tool', required=True)
    ap.add_argument('--old', required=True)
    ap.add_argument('--work', required=True, type=Path)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
    checks = []
    evidence = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': os.environ.get('RUNNER_OS'),
                'scope': 'existing-target v2; new-target v1 unchanged; process crash, not power-loss',
                'checks': checks, 'passed': False}

    def sibling(target, suffix):
        return Path(str(target) + suffix)

    def mirror(target):
        return sibling(target, '.legacy-map.json')

    def pending(target):
        return sibling(target, '.migration-pending.json')

    def record(folder, name, rc, out, err):
        (folder / (name + '.stdout.txt')).write_text(out, encoding='utf-8')
        (folder / (name + '.stderr.txt')).write_text(err, encoding='utf-8')
        return rc, json.loads(out)

    def run(folder, name, command, target, pack=None, extra=(), tool=None):
        cmd = [tool or a.tool, command, '--target', str(target)]
        if pack is not None:
            cmd += ['--pack', str(pack)]
        p = subprocess.run(cmd + list(extra), env=env, capture_output=True, text=True, timeout=45)
        return record(folder, name, p.returncode, p.stdout, p.stderr)

    def make_pack(folder, name, data, notes=()):
        pack = folder / (name + '.exrpack')
        pack.write_bytes(L.build_pack([L.entry(L.book_record(name, name + '.txt'), data)], list(notes)))
        return pack

    def setup(name, legacy=False, existing=True):
        folder = a.work / name
        folder.mkdir()
        target = folder / 'library.sqlite'
        seed, delta = make_pack(folder, 'seed', L.TXT), make_pack(folder, 'delta', L.TXT_OTHER)
        if existing:
            rc, report = run(folder, 'seed', 'migrate', target, seed, tool=a.old if legacy else a.tool)
            assert rc == 0, report
        return folder, target, seed, delta

    def current(target):
        db = sqlite3.connect(target.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            ledger = None
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='exr_migration_ledger'").fetchone():
                row = db.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()
                ledger = row[0] if row else None
            return {'books': db.execute('SELECT id,title,source FROM books ORDER BY id').fetchall(),
                    'notes': db.execute('SELECT id,text FROM notes ORDER BY id').fetchall(), 'ledger': ledger}
        finally:
            db.close()

    def start(target, pack, hook):
        return subprocess.Popen([a.tool, 'migrate', '--pack', str(pack), '--target', str(target),
                                 '--inject', hook], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def wait_marker(process, marker):
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists(), 'rendezvous missing: ' + str(marker)

    def crash(folder, target, pack, hook='precommit-mirror-pause', suffix='.precommit-mirror-ready'):
        p = start(target, pack, hook)
        try:
            wait_marker(p, sibling(target, suffix))
        finally:
            if p.poll() is None:
                p.kill()
            out, err = p.communicate(timeout=10)
            (folder / 'crash.stdout.txt').write_text(out, encoding='utf-8')
            (folder / 'crash.stderr.txt').write_text(err, encoding='utf-8')

    def recover(folder, target, break_lock=True):
        rc, report = run(folder, 'recover', 'recover-mirror', target,
                         extra=('--break-lock',) if break_lock else ())
        assert rc == 0 and not pending(target).exists(), report
        assert report['atomicity']['transaction']['target_commit'] == 'not-attempted', report
        assert not report['atomicity']['rolled_back'], report
        return report

    def assert_artifacts_retired(folder):
        assert not list(folder.glob('library.sqlite.legacy-map.json.before-*'))
        assert not list(folder.glob('library.sqlite.legacy-map.json.staged-*'))
        assert not list(folder.glob('library.sqlite.migration-pending.json'))

    try:
        # This complements, not substitutes for, the unchanged original targeted case.
        folder, target, seed, delta = setup('confirmed-publication-failure')
        db_before, mirror_before, logical = target.read_bytes(), mirror(target).read_bytes(), current(target)
        rc, report = run(folder, 'fault', 'migrate', target, delta, ('--inject', 'sidecar-fail'))
        assert rc == 3 and report['code'] == 'ledger-publish-failed', report
        assert report['atomicity']['rolled_back'] and report['atomicity']['transaction']['target_commit'] == 'not-committed', report
        assert target.read_bytes() == db_before and mirror(target).read_bytes() == mirror_before and current(target) == logical
        assert_artifacts_retired(folder)
        checks.append({'name': 'real-site-publication-failure-explicit-rollback-no-leftovers', 'termination': 'normal'})

        # Real OS refusal at the actual rename/link call, not an injected failure result.
        folder, target, seed, delta = setup('filesystem-publication-refusal')
        db_before, mirror_before = target.read_bytes(), mirror(target).read_bytes()
        p = start(target, delta, 'precommit-publish-pause')
        old_mode, account, restricted, acl_log = stat.S_IMODE(folder.stat().st_mode), None, [], []
        out = err = ''
        try:
            wait_marker(p, sibling(target, '.precommit-publish-ready'))
            intent = json.loads(pending(target).read_bytes())
            assert intent['version'] == 2
            planned = sibling(mirror(target), '.staged-' + intent['artifact_token'])
            if os.name == 'nt':
                who = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], check=True, capture_output=True, text=True)
                sid = next(csv.reader([who.stdout.strip()]))[-1]
                assert sid.startswith('S-1-')
                account = '*' + sid
                for path, rights in ((folder, 'DC'), (planned, 'D'), (mirror(target), 'D')):
                    result = subprocess.run(['icacls', str(path), '/deny', account + ':(' + rights + ')'], check=True, capture_output=True, text=True)
                    acl_log.append(result.stdout + result.stderr)
                    restricted.append(path)
            else:
                # The product waits on existence. Stop it while creating resume,
                # then deny directory writes before allowing the real rename.
                p.send_signal(signal.SIGSTOP)
                _, stopped = os.waitpid(p.pid, os.WUNTRACED)
                assert os.WIFSTOPPED(stopped), 'failed to stop at the filesystem fault boundary'
                sibling(target, '.precommit-publish-ready.resume').touch()
                folder.chmod(old_mode & ~0o222)
                p.send_signal(signal.SIGCONT)
            if os.name == 'nt':
                sibling(target, '.precommit-publish-ready.resume').touch()
            out, err = p.communicate(timeout=15)
        finally:
            if os.name == 'nt' and account:
                for path in reversed(restricted):
                    if path.exists():
                        result = subprocess.run(['icacls', str(path), '/remove:d', account], capture_output=True, text=True)
                        acl_log.append(result.stdout + result.stderr)
                        assert result.returncode == 0, result.stdout + result.stderr
            else:
                folder.chmod(old_mode)
            if p.poll() is None:
                p.kill()
                out, err = p.communicate(timeout=10)
        (folder / 'permission-fixture.txt').write_text('\n'.join(acl_log) or 'POSIX parent directory write permission removed/restored', encoding='utf-8')
        rc, report = record(folder, 'os-refusal', p.returncode, out, err)
        # Parent-directory refusal can also prevent SQLite DELETE-journal
        # finalization. That is an unconfirmed rollback, not a synthetic pass.
        if report['code'] == 'rollback-failed':
            assert rc == 6 and report['result'] == 'inconsistent' and not report['atomicity']['rolled_back'], report
            assert report['atomicity']['transaction']['target_commit'] == 'not-attempted', report
            rollback_observation = 'unconfirmed-rollback-preserved'
        else:
            assert rc == 3 and report['code'] == 'ledger-publish-failed' and report['atomicity']['rolled_back'], report
            assert report['atomicity']['transaction']['target_commit'] == 'not-committed', report
            assert target.read_bytes() == db_before
            rollback_observation = 'SDK-rollback-confirmed'
        assert mirror(target).read_bytes() == mirror_before
        assert pending(target).exists(), 'OS refusal must leave cleanup evidence when owned artifacts cannot be removed'
        recover(folder, target)
        assert target.read_bytes() == db_before and mirror(target).read_bytes() == mirror_before
        assert_artifacts_retired(folder)
        checks.append({'name': 'actual-filesystem-publication-refusal-and-cleanup-retry',
                       'termination': 'normal', 'rollback_observation': rollback_observation})

        for legacy in (False, True):
            folder, target, seed, delta = setup('crash-published-mirror-' + str(legacy), legacy=legacy)
            db_before, mirror_before = target.read_bytes(), mirror(target).read_bytes()
            crash(folder, target, delta)
            intent = json.loads(pending(target).read_bytes())
            preimage = sibling(mirror(target), '.before-' + intent['artifact_token'])
            assert intent['version'] == 2 and preimage.read_bytes() == mirror_before
            assert mirror(target).read_bytes() != mirror_before
            if os.name != 'nt':
                assert stat.S_IMODE(preimage.stat().st_mode) == 0o600
            recover(folder, target)
            assert target.read_bytes() == db_before and mirror(target).read_bytes() == mirror_before
            if legacy:
                assert current(target)['ledger'] is None
            assert_artifacts_retired(folder)
            checks.append({'name': 'precommit-crash-exact-baseline-' + ('legacy' if legacy else 'internal'), 'termination': 'hard-kill'})

        for legacy in (False, True):
            folder, target, seed, delta = setup('recovery-cleanup-crash-' + str(legacy), legacy=legacy)
            db_before, mirror_before = target.read_bytes(), mirror(target).read_bytes()
            crash(folder, target, delta)
            p = subprocess.Popen([a.tool, 'recover-mirror', '--target', str(target), '--break-lock',
                                  '--inject', 'mirror-retire-pause'], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                wait_marker(p, sibling(target, '.mirror-retire-ready'))
                assert pending(target).exists() and not list(folder.glob('library.sqlite.legacy-map.json.before-*'))
                assert mirror(target).read_bytes() == mirror_before
            finally:
                if p.poll() is None:
                    p.kill()
                out, err = p.communicate(timeout=10)
                (folder / 'cleanup-crash.stdout.txt').write_text(out, encoding='utf-8')
                (folder / 'cleanup-crash.stderr.txt').write_text(err, encoding='utf-8')
            recover(folder, target)
            assert target.read_bytes() == db_before and mirror(target).read_bytes() == mirror_before
            assert_artifacts_retired(folder)
            checks.append({'name': 'cleanup-crash-preimage-already-retired-' + str(legacy), 'termination': 'hard-kill'})

        folder, target, seed, delta = setup('cooperative-cancel-after-mirror')
        db_before, mirror_before = target.read_bytes(), mirror(target).read_bytes()
        p = start(target, delta, 'precommit-mirror-pause')
        try:
            wait_marker(p, sibling(target, '.precommit-mirror-ready'))
            if os.name == 'nt':
                p.kill()
                mode = 'windows-hard-kill-not-cooperative-cancellation'
            else:
                p.send_signal(signal.SIGTERM)
                mode = 'posix-cooperative-SIGTERM'
            out, err = p.communicate(timeout=10)
            (folder / 'cancel.stdout.txt').write_text(out, encoding='utf-8')
            (folder / 'cancel.stderr.txt').write_text(err, encoding='utf-8')
            if os.name == 'nt':
                recover(folder, target)
            else:
                report = json.loads(out)
                assert p.returncode == 4 and report['atomicity']['rolled_back'], report
                assert report['atomicity']['transaction']['target_commit'] == 'not-committed', report
        finally:
            if p.poll() is None:
                p.kill()
                p.communicate(timeout=10)
        assert target.read_bytes() == db_before and mirror(target).read_bytes() == mirror_before
        assert_artifacts_retired(folder)
        checks.append({'name': 'cancel-after-mirror-before-COMMIT', 'termination': mode})

        folder, target, seed, delta = setup('confirmed-rollback-restores-absence')
        mirror(target).unlink()
        before = target.read_bytes()
        rc, report = run(folder, 'cancel', 'migrate', target, delta, ('--inject', 'precommit-cancel'))
        assert rc == 4 and report['atomicity']['rolled_back'], report
        assert report['atomicity']['transaction']['target_commit'] == 'not-committed', report
        assert target.read_bytes() == before and not mirror(target).exists()
        assert_artifacts_retired(folder)
        checks.append({'name': 'confirmed-rollback-removes-only-planned-mirror-restores-absence', 'termination': 'test-hook-cooperative-cancel'})

        folder, target, seed, delta = setup('foreign-planned-stage')
        before = target.read_bytes(), mirror(target).read_bytes()
        p = start(target, delta, 'precommit-publish-pause')
        try:
            wait_marker(p, sibling(target, '.precommit-publish-ready'))
            intent = json.loads(pending(target).read_bytes())
            planned = sibling(mirror(target), '.staged-' + intent['artifact_token'])
            replacement = folder / 'foreign-stage.json'
            shutil.copyfile(planned, replacement)
            os.replace(replacement, planned)
            foreign_bytes, foreign_id = planned.read_bytes(), planned.stat().st_ino
            sibling(target, '.precommit-publish-ready.resume').touch()
            out, err = p.communicate(timeout=15)
            rc, report = record(folder, 'refuse-stage', p.returncode, out, err)
            assert rc != 0 and report['atomicity']['transaction']['target_commit'] == 'not-committed', report
            assert (target.read_bytes(), mirror(target).read_bytes()) == before
            assert planned.read_bytes() == foreign_bytes and planned.stat().st_ino == foreign_id and pending(target).exists()
        finally:
            if p.poll() is None:
                p.kill()
                p.communicate(timeout=10)
        checks.append({'name': 'foreign-same-content-stage-never-published-or-deleted', 'termination': 'normal'})

        for conflict in ('missing-preimage', 'foreign-preimage', 'foreign-mirror'):
            folder, target, seed, delta = setup(conflict, legacy=conflict != 'foreign-mirror')
            mirror_before = mirror(target).read_bytes()
            crash(folder, target, delta)
            intent = json.loads(pending(target).read_bytes())
            preimage = sibling(mirror(target), '.before-' + intent['artifact_token'])
            if conflict == 'missing-preimage':
                preimage.rename(folder / 'retained-preimage.json')
            else:
                selected = mirror(target) if conflict == 'foreign-mirror' else preimage
                replacement = folder / 'foreign.json'
                shutil.copyfile(selected, replacement)
                os.replace(replacement, selected)
            external, journal = mirror(target).read_bytes(), pending(target).read_bytes()
            rc, report = run(folder, 'refuse', 'recover-mirror', target, extra=('--break-lock',))
            assert rc != 0 and mirror(target).read_bytes() == external and pending(target).read_bytes() == journal, report
            assert external != mirror_before
            checks.append({'name': 'fail-closed-' + conflict, 'termination': 'hard-kill'})

        folder, target, seed, delta = setup('commit-busy-unknown')
        before = target.read_bytes(), mirror(target).read_bytes()
        p = start(target, delta, 'precommit-mirror-pause')
        reader = None
        try:
            wait_marker(p, sibling(target, '.precommit-mirror-ready'))
            reader = sqlite3.connect(target)
            reader.execute('BEGIN')
            reader.execute('SELECT count(*) FROM books').fetchone()
            sibling(target, '.precommit-mirror-ready.resume').touch()
            out, err = p.communicate(timeout=35)
            rc, report = record(folder, 'busy', p.returncode, out, err)
            assert rc != 0 and report['atomicity']['transaction']['target_commit'] == 'unknown', report
            assert not report['atomicity']['rolled_back'] and pending(target).exists(), report
        finally:
            if reader is not None:
                reader.close()
            if p.poll() is None:
                p.kill()
                p.communicate(timeout=10)
        recover(folder, target)
        assert (target.read_bytes(), mirror(target).read_bytes()) == before
        checks.append({'name': 'COMMIT-error-remains-unknown-current-state-recovery', 'termination': 'normal'})

        folder, target, seed, delta = setup('equal-hash-real-commit', existing=False)
        pack = make_pack(folder, 'note-book', L.TXT,
                         [L.note_record('note', 'note-book', 'lantern keeper', 'kept comment')])
        rc, report = run(folder, 'seed-note', 'migrate', target, pack)
        assert rc == 0, report
        with sqlite3.connect(target) as db:
            db.execute('DELETE FROM notes')
        before = current(target)
        assert not before['notes']
        crash(folder, target, pack, 'commit-pause', '.commit-ready')
        after = current(target)
        intent = json.loads(pending(target).read_bytes())
        assert intent['version'] == 2 and intent['before_sha'] == intent['after_sha']
        assert before['ledger'] == after['ledger'] and len(after['notes']) == 1
        recover(folder, target)
        assert current(target) == after
        checks.append({'name': 'v2-equal-hash-never-infers-no-COMMIT', 'termination': 'hard-kill'})

        folder, target, seed, delta = setup('new-target-still-v1', existing=False)
        rc, report = run(folder, 'fault', 'migrate', target, delta, ('--inject', 'sidecar-fail'))
        assert rc == 3 and report['atomicity']['transaction']['target_commit'] == 'committed', report
        assert not report['atomicity']['rolled_back'] and json.loads(pending(target).read_bytes())['version'] == 1
        committed = current(target)
        recover(folder, target)
        assert current(target) == committed and mirror(target).read_bytes() == committed['ledger']
        checks.append({'name': 'new-target-v1-no-precommit-orphan-mirror', 'termination': 'normal'})
        evidence['passed'] = True
    finally:
        (a.work / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(evidence))


if __name__ == '__main__':
    main()
