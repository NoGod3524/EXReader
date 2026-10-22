#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only migration review regressions; original 65 cases run separately."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import legacy_data as L
from run_cases import Ctx, Result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool', required=True)
    parser.add_argument('--editor', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    args.output.mkdir(parents=True, exist_ok=False)
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        assert condition, name

    def seeded(name, fixed=False):
        context = Ctx(args.tool, str(args.output), name)
        book = L.entry(L.book_record('book', 'book.pdf' if fixed else 'book.txt'), L.pdf() if fixed else L.TXT)
        if fixed:
            _, notes = L.dataset()
            note = next(n.copy() for n in notes if n['bookId'] == 'b-pdf' and n.get('note') == 'second page')
            note.update(id='note', bookId='book')
        else:
            note = L.note_record('note', 'book', 'lantern keeper', 'original comment')
        pack = context.pack([book], [note])
        target = context.path('library.sqlite')
        assert context.migrate(pack, target).code == 0
        return context, book, note, pack, target

    c, book, note, pack, target = seeded('pack-note-change')
    changed = dict(note, note='changed pack comment')
    changed_pack = c.pack([book], [changed], name='changed.exrpack')
    result = c.tool_run('verify', '--pack', changed_pack, '--target', target)
    check('verify rejects same note identity with changed pack content', result.code == 3 and bool(result.entries('verify-note-content')))

    for mode in ('reflow-text', 'fixed-text', 'fixed-range'):
        c, _, _, pack, target = seeded(mode, mode.startswith('fixed'))
        subprocess.run([args.editor, target, mode], check=True)
        before = (c.sha(target), c.sha(target + '.legacy-map.json'))
        result = c.tool_run('verify', '--pack', pack, '--target', target)
        check('verify rejects public API edit: ' + mode, result.code == 3 and result.codename == 'verify-failed')
        check('verification preserves edited library and ledger: ' + mode,
              before == (c.sha(target), c.sha(target + '.legacy-map.json')))

    c, _, _, pack, target = seeded('read-missing-target')
    Path(target).unlink()
    result = c.tool_run('verify', '--pack', pack, '--target', target)
    check('verify does not create missing target', result.code != 0 and not Path(target).exists())
    result = c.tool_run('dump', '--target', c.path('missing.sqlite'))
    check('dump does not create missing target', result.code != 0 and not Path(c.path('missing.sqlite')).exists())

    c, _, _, pack, target = seeded('late-cancel')
    before = (c.sha(target), c.sha(target + '.legacy-map.json'))
    result = c.migrate(pack, target, inject='publish-cancel')
    check('late cancellation refuses publication', result.code == 4 and before == (c.sha(target), c.sha(target + '.legacy-map.json')))

    for mutation in ('ledger-content', 'ledger-created', 'target-created'):
        c, _, _, pack, target = seeded('concurrent-' + mutation)
        ledger = Path(target + '.legacy-map.json')
        if mutation == 'ledger-created':
            ledger.unlink()
        elif mutation == 'target-created':
            Path(target).unlink()
            ledger.unlink()
        before_target = c.sha(target)
        env = dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1')
        log_path = Path(c.path('process.log'))
        with log_path.open('wb') as log:
            process = subprocess.Popen([args.tool, 'migrate', '--pack', pack, '--target', target,
                                        '--inject', 'publish-pause'], stdout=log, stderr=subprocess.STDOUT, env=env)
            try:
                ready = Path(target + '.review-ready')
                end = time.monotonic() + 30
                while not ready.exists() and process.poll() is None and time.monotonic() < end:
                    time.sleep(.02)
                assert ready.exists(), 'missing publication synchronization'
                if mutation == 'ledger-content':
                    ledger.write_bytes(ledger.read_bytes() + b'\n ')
                elif mutation == 'ledger-created':
                    ledger.write_text('{"external":true}', encoding='utf-8')
                else:
                    Path(target).write_bytes(b'external writer content')
                expected = (c.sha(target), c.sha(str(ledger)))
                Path(target + '.review-resume').write_text('resume', encoding='utf-8')
                process.wait(timeout=30)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        result = Result(process.returncode, log_path.read_text(encoding='utf-8'), '')
        check('publication preserves concurrent change: ' + mutation,
              result.code == 3 and result.codename in ('target-changed', 'ledger-changed') and
              expected == (c.sha(target), c.sha(str(ledger))))
        check('no stage or lock left: ' + mutation,
              not any('.migrating-' in p.name or p.name.endswith('.migrate-lock') for p in Path(c.dir).iterdir()))

    report = {'schema': 1, 'passed': True, 'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'checks': checks,
              'tool_sha256': hashlib.sha256(Path(args.tool).read_bytes()).hexdigest(),
              'editor_sha256': hashlib.sha256(Path(args.editor).read_bytes()).hexdigest()}
    (args.output / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'checks': len(checks), 'source_sha': report['source_sha']}))


if __name__ == '__main__':
    main()
