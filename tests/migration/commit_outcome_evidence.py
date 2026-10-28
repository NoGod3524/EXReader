#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only evidence for process-local commit knowledge, not crash recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time

BASELINE = 'e771f3c5d1567412f26184ad304730b7c640235d'


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('This evidence probe runs only in GitHub Actions.')
    import legacy_data as L
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool', required=True)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
    checks = []
    evidence = {'source_sha': os.environ['GITHUB_SHA'], 'baseline_sha': BASELINE,
                'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                'platform': os.environ.get('RUNNER_OS'), 'checks': checks,
                'scope': 'commit knowledge reporting only; not the original 65/31/17 gate',
                'passed': False}

    def pack(folder, name, data):
        path = folder / (name + '.exrpack')
        path.write_bytes(L.build_pack([L.entry(L.book_record(name, name + '.txt'), data)], []))
        return path

    def record(folder, name, rc, out, err):
        (folder / (name + '.stdout.txt')).write_text(out, encoding='utf-8')
        (folder / (name + '.stderr.txt')).write_text(err, encoding='utf-8')
        report = json.loads(out)
        return rc, report

    def run(folder, name, tool, source, target, *extra):
        p = subprocess.run([tool, 'migrate', '--pack', str(source), '--target', str(target), *extra],
                           env=env, capture_output=True, text=True, timeout=45)
        return record(folder, name, p.returncode, p.stdout, p.stderr)

    def setup(name, tool, existing):
        folder = args.work / name
        folder.mkdir()
        target = folder / 'library.sqlite'
        if existing:
            seed = pack(folder, 'seed', L.TXT)
            rc, report = run(folder, 'seed', tool, seed, target)
            assert rc == 0, report
        return folder, target, pack(folder, 'delta', L.TXT_OTHER)

    def snapshot(target):
        assert target.is_file(), target
        db = sqlite3.connect(target.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            books = db.execute('SELECT id,title,source FROM books ORDER BY id').fetchall()
            ledger = db.execute('SELECT data FROM exr_migration_ledger WHERE id=1').fetchone()[0]
            return books, ledger
        finally:
            db.close()

    def start(tool, source, target, hook):
        return subprocess.Popen([tool, 'migrate', '--pack', str(source), '--target', str(target),
                                 '--inject', hook], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def wait_marker(process, marker):
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists(), 'rendezvous missing: ' + str(marker)

    def finish(folder, name, process):
        out, err = process.communicate(timeout=35)
        return record(folder, name, process.returncode, out, err)

    def stop(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)

    def commit_report(report, target, stage):
        assert report['atomicity']['transaction'] == {
            'target_commit': target, 'private_stage_commit': stage}, report

    def interrupted_commit(name, tool, existing, baseline=False):
        folder, target, source = setup(name, tool, existing)
        before = snapshot(target) if existing else None
        process = start(tool, source, target, 'commit-pause')
        try:
            wait_marker(process, Path(str(target) + '.commit-ready'))
            # POSIX reaches the existing cooperative SIGTERM handler. Windows
            # exercises the unchanged 20-second acknowledgement timeout instead.
            if os.name != 'nt':
                process.send_signal(signal.SIGTERM)
            rc, report = finish(folder, 'interrupted', process)
        finally:
            stop(process)
        after = snapshot(target)
        assert len(after[0]) == (2 if existing else 1), after[0]
        assert before is None or after != before
        assert rc == 3 and report['result'] == 'failed' and report['code'] == 'review-hook-timeout', report
        assert report['atomicity']['rolled_back'] is False, report
        if baseline:
            assert 'transaction' not in report['atomicity'], report
        else:
            commit_report(report, 'committed', 'not-attempted' if existing else 'committed')
        checks.append({'case': name, 'passed': True, 'legacy_result_preserved': report['result'],
                       'termination_mode': 'cooperative-SIGTERM' if os.name != 'nt' else 'acknowledgement-timeout',
                       'target_books': len(after[0]), 'ledger_sha256': hashlib.sha256(after[1]).hexdigest(),
                       'transaction': report['atomicity'].get('transaction')})

    try:
        interrupted_commit('baseline-postcommit-existing', args.baseline, True, baseline=True)
        for existing in (False, True):
            suffix = 'existing' if existing else 'new'
            interrupted_commit('candidate-postcommit-' + suffix, args.tool, existing)
            folder, target, source = setup('precommit-cancel-' + suffix, args.tool, existing)
            before = snapshot(target) if existing else None
            rc, report = run(folder, 'cancel', args.tool, source, target, '--inject', 'publish-cancel')
            assert rc == 4 and report['result'] == 'cancelled', report
            commit_report(report, 'not-committed' if existing else 'not-attempted',
                          'not-attempted' if existing else 'not-committed')
            assert snapshot(target) == before if existing else not target.exists()
            checks.append({'case': 'precommit-cancel-' + suffix, 'passed': True})

        folder, target, source = setup('private-stage-publication-conflict', args.tool, False)
        process = start(args.tool, source, target, 'writer-pause')
        competitor = b'An unrelated target must not be replaced or removed.\n'
        try:
            wait_marker(process, Path(str(target) + '.writer-ready'))
            with target.open('xb') as output:
                output.write(competitor)
            Path(str(target) + '.writer-resume').write_text('resume', encoding='utf-8')
            rc, report = finish(folder, 'conflict', process)
        finally:
            stop(process)
        assert rc == 3 and report['code'] == 'publish-failed', report
        assert target.read_bytes() == competitor
        commit_report(report, 'unknown', 'committed')
        checks.append({'case': 'private-stage-publication-conflict', 'passed': True})

        folder, target, source = setup('commit-return-error', args.tool, True)
        before = snapshot(target)
        process = start(args.tool, source, target, 'writer-pause')
        reader = None
        try:
            wait_marker(process, Path(str(target) + '.writer-ready'))
            reader = sqlite3.connect(target.resolve().as_uri() + '?mode=ro', uri=True)
            assert reader.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
            reader.execute('BEGIN')
            reader.execute('SELECT count(*) FROM books').fetchone()
            Path(str(target) + '.writer-resume').write_text('resume', encoding='utf-8')
            rc, report = finish(folder, 'busy-commit', process)
        finally:
            if reader is not None:
                reader.rollback()
                reader.close()
            stop(process)
        assert rc == 3 and report['code'] == 'sdk-error' and 'committing migration' in report['message'], report
        commit_report(report, 'unknown', 'not-attempted')
        assert snapshot(target) == before, 'independent read must confirm this particular rollback'
        checks.append({'case': 'commit-return-error', 'passed': True,
                       'note': 'rollback independently observed; error alone still reports unknown'})
        evidence['passed'] = True
    finally:
        (args.work / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(evidence), flush=True)


if __name__ == '__main__':
    main()
