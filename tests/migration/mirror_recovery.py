#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only mirror/pending recovery evidence. Never a replacement for old gates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import time


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('All fixtures, executions and artifact parsing belong in GitHub Actions.')
    import legacy_data as L
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool', required=True)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
    checks = []
    evidence = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': os.environ.get('RUNNER_OS'),
                'scope': 'process-crash mirror convergence, not power-loss or historical commit proof',
                'checks': checks, 'passed': False}

    def sibling(target, suffix):
        return Path(str(target) + suffix)

    def mirror(target):
        return sibling(target, '.legacy-map.json')

    def pending(target):
        return sibling(target, '.migration-pending.json')

    def snapshot(target):
        db = sqlite3.connect(target.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            return {'books': db.execute('SELECT id,title,source FROM books ORDER BY id').fetchall(),
                    'notes': db.execute('SELECT id,text FROM notes ORDER BY id').fetchall(),
                    'ledger': db.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0]}
        finally:
            db.close()

    def write_pack(folder, name, data, notes=()):
        pack = folder / (name + '.exrpack')
        pack.write_bytes(L.build_pack([L.entry(L.book_record(name, name + '.txt'), data)], list(notes)))
        return pack

    def record(folder, name, process):
        (folder / (name + '.stdout.txt')).write_text(process.stdout, encoding='utf-8')
        (folder / (name + '.stderr.txt')).write_text(process.stderr, encoding='utf-8')
        return process.returncode, json.loads(process.stdout)

    def run(folder, name, command, target, pack=None, extra=()):
        cmd = [args.tool, command, '--target', str(target)]
        if pack is not None:
            cmd += ['--pack', str(pack)]
        p = subprocess.run(cmd + list(extra), env=env, capture_output=True, text=True, timeout=45)
        return record(folder, name, p)

    def setup(name, existing=True):
        folder = args.work / name
        folder.mkdir()
        target = folder / 'library.sqlite'
        seed = write_pack(folder, 'seed', L.TXT)
        delta = write_pack(folder, 'delta', L.TXT_OTHER)
        if existing:
            rc, report = run(folder, 'seed', 'migrate', target, seed)
            assert rc == 0, report
            assert mirror(target).read_bytes() == snapshot(target)['ledger']
            assert not pending(target).exists()
        return folder, target, seed, delta

    def start(target, pack, hook):
        return subprocess.Popen([args.tool, 'migrate', '--pack', str(pack), '--target', str(target),
                                 '--inject', hook], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def wait_marker(process, marker):
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists(), 'missing rendezvous: ' + str(marker)

    def hard_crash(folder, target, pack, hook, suffix):
        process = start(target, pack, hook)
        try:
            wait_marker(process, sibling(target, suffix))
        finally:
            if process.poll() is None:
                process.kill()
            out, err = process.communicate(timeout=10)
            (folder / ('crash-' + hook + '.stdout.txt')).write_text(out, encoding='utf-8')
            (folder / ('crash-' + hook + '.stderr.txt')).write_text(err, encoding='utf-8')
        return process.returncode

    def recover(folder, target, label='recover', break_lock=False):
        rc, report = run(folder, label, 'recover-mirror', target,
                         extra=('--break-lock',) if break_lock else ())
        assert rc == 0, report
        assert report['atomicity']['transaction']['target_commit'] == 'not-attempted', report
        assert not report['atomicity']['rolled_back'], report
        assert not pending(target).exists()
        return report

    try:
        folder, target, seed, delta = setup('normal-and-missing-mirror')
        original = mirror(target).read_bytes()
        original_id = mirror(target).stat().st_ino
        rc, report = run(folder, 'rerun', 'migrate', target, seed)
        assert rc == 0 and mirror(target).read_bytes() == original, report
        assert mirror(target).stat().st_ino == original_id, 'equal mirror was unnecessarily replaced'
        mirror(target).unlink()
        rc, report = run(folder, 'missing-mirror', 'migrate', target, seed)
        assert rc == 0 and mirror(target).read_bytes() == original, report
        assert not any(e['code'] == 'adopted-existing' for e in report['entries']), report
        checks.append({'name': 'real-mirror-idempotence-and-loss-rebuild', 'termination': 'normal'})

        folder, target, seed, delta = setup('preexisting-divergence')
        before = snapshot(target)
        changed = json.loads(mirror(target).read_bytes())
        changed['external_edit'] = 'must not become an overwriteable baseline'
        mirror(target).write_text(json.dumps(changed), encoding='utf-8')
        foreign = mirror(target).read_bytes()
        rc, report = run(folder, 'refuse', 'migrate', target, delta)
        assert rc != 0 and report['code'] == 'mirror-diverged', report
        assert snapshot(target) == before and mirror(target).read_bytes() == foreign
        rc, report = run(folder, 'verify', 'verify', target, seed)
        assert rc == 3 and report['code'] == 'verify-failed', report
        checks.append({'name': 'preexisting-valid-envelope-divergence-refused', 'termination': 'normal'})

        folder, target, seed, delta = setup('real-mirror-failure-and-writer')
        original = mirror(target).read_bytes()
        rc, report = run(folder, 'publication-failure', 'migrate', target, delta, ('--inject', 'sidecar-fail'))
        assert rc == 3 and report['code'] == 'ledger-publish-failed', report
        assert report['atomicity']['transaction']['target_commit'] == 'committed', report
        assert not report['atomicity']['rolled_back'] and pending(target).exists(), report
        assert mirror(target).read_bytes() == original
        owned_before = {p.name: p.read_bytes() for p in folder.iterdir() if p.name.startswith('library.sqlite')}
        rc, report = run(folder, 'dry-run-pending', 'migrate', target, delta, ('--dry-run',))
        assert rc == 5 and report['code'] == 'mirror-recovery-required', report
        assert {p.name: p.read_bytes() for p in folder.iterdir() if p.name.startswith('library.sqlite')} == owned_before
        rc, report = run(folder, 'verify-pending', 'verify', target, delta)
        assert rc == 0 and report['atomicity']['mirror']['pending'], report
        with sqlite3.connect(target) as db:
            db.execute("UPDATE books SET title='ordinary writer preserved' WHERE id=(SELECT min(id) FROM books)")
        before = snapshot(target)
        recover(folder, target)
        assert snapshot(target) == before and mirror(target).read_bytes() == before['ledger']
        checks.append({'name': 'real-publication-failure-dry-run-no-write-and-recovery-preserves-writer', 'termination': 'normal'})

        for existing in (True, False):
            folder, target, seed, delta = setup('precommit-crash-' + str(existing), existing)
            before = snapshot(target) if existing else None
            hard_crash(folder, target, delta, 'intent-pause', '.intent-ready')
            assert pending(target).exists()
            stages = list(folder.glob('library.sqlite.migrating-*'))
            if not existing:
                assert not target.exists() and stages
            report = recover(folder, target, break_lock=True)
            if existing:
                assert snapshot(target) == before
            else:
                assert not target.exists() and all(p.exists() for p in stages)
                assert report['atomicity']['mirror']['state'] == 'no-authoritative-target'
                rc, report = run(folder, 'explicit-fresh-migration', 'migrate', target, delta)
                assert rc == 0 and all(p.exists() for p in stages), report
            checks.append({'name': 'intent-precommit-crash-' + str(existing), 'termination': 'hard-kill'})

        for hook, suffix in (('commit-pause', '.commit-ready'), ('mirror-pause', '.mirror-ready')):
            folder, target, seed, delta = setup('postcommit-' + hook)
            hard_crash(folder, target, delta, hook, suffix)
            before = snapshot(target)
            assert len(before['books']) == 2 and pending(target).exists()
            mirror_id = mirror(target).stat().st_ino
            rc, report = run(folder, 'verify-with-stale-lock', 'verify', target, delta)
            assert rc == 0 and report['atomicity']['mirror']['pending'], report
            recover(folder, target, break_lock=True)
            assert snapshot(target) == before and mirror(target).read_bytes() == before['ledger']
            if hook == 'mirror-pause':
                assert mirror(target).stat().st_ino == mirror_id, 'converged mirror changed on retry'
            checks.append({'name': 'crash-' + hook, 'termination': 'hard-kill'})

        folder, target, seed, delta = setup('prepared-cancel')
        before = snapshot(target)
        process = start(target, delta, 'intent-pause')
        try:
            wait_marker(process, sibling(target, '.intent-ready'))
            if os.name == 'nt':
                process.kill()
                mode = 'windows-hard-kill-not-cooperative-cancellation'
            else:
                process.send_signal(signal.SIGTERM)
                mode = 'posix-cooperative-SIGTERM'
            out, err = process.communicate(timeout=10)
            (folder / 'cancel.stdout.txt').write_text(out, encoding='utf-8')
            (folder / 'cancel.stderr.txt').write_text(err, encoding='utf-8')
            if os.name != 'nt':
                report = json.loads(out)
                assert process.returncode == 4 and report['atomicity']['transaction']['target_commit'] == 'not-committed', report
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
        assert pending(target).exists()
        if os.name != 'nt':
            assert snapshot(target) == before
        recover(folder, target, break_lock=os.name == 'nt')
        assert snapshot(target) == before
        checks.append({'name': 'cancellation-after-intent-prepare', 'termination': mode})

        folder, target, seed, delta = setup('cancel-mirror-prepublish')
        old_mirror = mirror(target).read_bytes()
        process = start(target, delta, 'mirror-prepublish-pause')
        try:
            wait_marker(process, sibling(target, '.mirror-prepublish-ready'))
            committed = snapshot(target)
            assert len(committed['books']) == 2 and mirror(target).read_bytes() == old_mirror
            if os.name == 'nt':
                process.kill()
                mode = 'windows-hard-kill-not-cooperative-cancellation'
            else:
                process.send_signal(signal.SIGTERM)
                mode = 'posix-cooperative-SIGTERM'
            out, err = process.communicate(timeout=10)
            (folder / 'cancel.stdout.txt').write_text(out, encoding='utf-8')
            (folder / 'cancel.stderr.txt').write_text(err, encoding='utf-8')
            if os.name != 'nt':
                report = json.loads(out)
                assert process.returncode == 4 and report['atomicity']['transaction']['target_commit'] == 'committed', report
                assert not report['atomicity']['rolled_back'], report
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
        assert pending(target).exists() and mirror(target).read_bytes() == old_mirror
        recover(folder, target, break_lock=os.name == 'nt')
        assert snapshot(target) == committed and mirror(target).read_bytes() == committed['ledger']
        checks.append({'name': 'cancellation-after-mirror-stage-fsync-before-publication', 'termination': mode})

        for timing, hook, ready, resume in (
                ('before-intent', 'publish-pause', '.review-ready', '.review-resume'),
                ('after-intent', 'intent-pause', '.intent-ready', '.intent-ready.resume')):
            folder, target, seed, delta = setup('foreign-new-target-' + timing, False)
            process = start(target, delta, hook)
            try:
                wait_marker(process, sibling(target, ready))
                target.write_bytes(b'foreign destination must survive')
                sibling(target, resume).write_text('resume', encoding='utf-8')
                out, err = process.communicate(timeout=15)
                (folder / 'foreign.stdout.txt').write_text(out, encoding='utf-8')
                (folder / 'foreign.stderr.txt').write_text(err, encoding='utf-8')
                report = json.loads(out)
                assert process.returncode == 3 and target.read_bytes() == b'foreign destination must survive', report
                if timing == 'before-intent':
                    assert report['code'] == 'target-changed' and not pending(target).exists(), report
                    assert not list(folder.glob('library.sqlite.migrating-*'))
                else:
                    assert report['code'] == 'publish-failed' and pending(target).exists(), report
                    assert report['atomicity']['transaction'] == {'target_commit': 'unknown', 'private_stage_commit': 'committed'}, report
                    rc, report = run(folder, 'refuse-foreign-recovery', 'recover-mirror', target)
                    assert rc != 0 and target.read_bytes() == b'foreign destination must survive', report
                    assert pending(target).exists() and list(folder.glob('library.sqlite.migrating-*'))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)
            checks.append({'name': 'foreign-new-target-' + timing, 'termination': 'normal'})

        folder, target, seed, delta = setup('missing-private-stage', False)
        hard_crash(folder, target, delta, 'intent-pause', '.intent-ready')
        intent = json.loads(pending(target).read_bytes())
        stage = sibling(target, '.migrating-' + intent['stage_token'])
        retained = folder / 'manually-retained-stage.sqlite'
        stage.rename(retained)
        rc, report = run(folder, 'refuse-missing-stage', 'recover-mirror', target, extra=('--break-lock',))
        assert rc != 0 and not target.exists() and retained.exists() and pending(target).exists(), report
        checks.append({'name': 'missing-stage-never-creates-target', 'termination': 'hard-kill'})

        folder, target, seed, delta = setup('equal-ledger-real-db-change', False)
        note_pack = write_pack(folder, 'note-book', L.TXT,
                               [L.note_record('note', 'note-book', 'lantern keeper', 'kept comment')])
        rc, report = run(folder, 'seed-note', 'migrate', target, note_pack)
        assert rc == 0, report
        with sqlite3.connect(target) as db:
            db.execute('DELETE FROM notes')
        before = snapshot(target)
        assert not before['notes']
        hard_crash(folder, target, note_pack, 'commit-pause', '.commit-ready')
        after = snapshot(target)
        assert after['ledger'] == before['ledger'] and len(after['notes']) == 1
        intent = json.loads(pending(target).read_bytes())
        assert intent['before_sha'] == intent['after_sha'] == hashlib.sha256(after['ledger']).hexdigest()
        recover(folder, target, break_lock=True)
        assert snapshot(target) == after
        checks.append({'name': 'equal-ledger-hash-does-not-prove-no-db-commit', 'termination': 'hard-kill'})

        for conflict in ('third-ledger', 'foreign-target', 'invalid-intent', 'unknown-version'):
            folder, target, seed, delta = setup('conflict-' + conflict)
            rc, report = run(folder, 'publication-failure', 'migrate', target, delta, ('--inject', 'sidecar-fail'))
            assert rc == 3 and pending(target).exists(), report
            if conflict == 'third-ledger':
                with sqlite3.connect(target) as db:
                    changed = json.loads(db.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0])
                    changed['independent_ledger_write'] = True
                    db.execute('UPDATE exr_migration_ledger SET data=? WHERE id=1', (json.dumps(changed).encode(),))
            elif conflict == 'foreign-target':
                replacement = folder / 'foreign.sqlite'
                shutil.copyfile(target, replacement)
                os.replace(replacement, target)
            elif conflict == 'invalid-intent':
                pending(target).write_bytes(b'{"format":')
            else:
                changed = json.loads(pending(target).read_bytes())
                changed['version'] = 999
                pending(target).write_text(json.dumps(changed), encoding='utf-8')
            before, external, intent_bytes = snapshot(target), mirror(target).read_bytes(), pending(target).read_bytes()
            rc, report = run(folder, 'refuse-recovery', 'recover-mirror', target)
            assert rc != 0, report
            assert snapshot(target) == before and mirror(target).read_bytes() == external
            assert pending(target).read_bytes() == intent_bytes
            checks.append({'name': 'fail-closed-' + conflict, 'termination': 'normal'})

        evidence['passed'] = True
    finally:
        (args.work / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(evidence))


if __name__ == '__main__':
    main()
