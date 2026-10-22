#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""H11: independent real GTK input, installed SDK and bounded state evidence; Actions only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from check_linux_host import Session, command

SDK = '2f26847684b54006ca812c35477ceae43719e7d4'
TREES = ('src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures',
         '.github/workflows/native.yml', '.github/workflows/reliability.yml', 'bindings')


def fixture(path, missing=False, large=False):
    """Independent routes: short A/B, one long chapter, and repeated A spine entry."""
    container = '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>'
    package = ('<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:title>H11 native bounded</dc:title></metadata><manifest>'
               '<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>'
               '<item id="b" href="b.xhtml" media-type="application/xhtml+xml"/>'
               '<item id="c" href="c.xhtml" media-type="application/xhtml+xml"/></manifest>'
               '<spine><itemref idref="a"/><itemref idref="b"/><itemref idref="c"/><itemref idref="a"/></spine></package>')
    if large:
        package = package.replace('<spine><itemref idref="a"/><itemref idref="b"/><itemref idref="c"/>',
                                  '<spine><itemref idref="c"/><itemref idref="a"/><itemref idref="b"/>')
    body = lambda value: '<html xmlns="http://www.w3.org/1999/xhtml"><body>'+value+'</body></html>'
    a = body('<p>ALPHA. Native GTK chapter zero. Unicode 中文 café 😀 with its own exact quote.</p>')
    b = body('<p>BETA. Independent chapter one. This annotation has an unambiguous chapter route.</p>')
    count = 300000 if large else 10000
    c = body(''.join('<p>Unique row %06d. Bounded reading retains a small window and native page text. '
                     'UTF-8 中文 café 😀 distinct ending %06d.</p>' % (i, i) for i in range(count)))
    with zipfile.ZipFile(path, 'w') as book:
        for name, value in [('mimetype', 'application/epub+zip'), ('META-INF/container.xml', container),
                            ('OPS/book.opf', package), ('OPS/a.xhtml', a),
                            *([] if missing else [('OPS/b.xhtml', b)]), ('OPS/c.xhtml', c)]:
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            book.writestr(item, value.encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve()
    assert not output.exists(); output.mkdir(parents=True)
    binary = (args.payload/'bin/exreader-linux').resolve(); font = (args.payload/'Reader.otf').resolve()
    checks, records, trees = [], {}, {}
    source = os.environ['GITHUB_SHA']
    host = Session(binary, font, output)

    def require(condition, name, detail=None):
        checks.append({'name': name, 'passed': bool(condition), 'observed': detail})
        if not condition:
            raise AssertionError(name)
        print('H11 PASS '+name, flush=True)

    def stable(name):
        state = host.wait(lambda s: not s['saving'])
        records[name] = state
        require(state['error'] == 0 and not state['save_failed'], name, state)
        return state

    def turn(key, predicate):
        before = host.read()['sequence']; host.key(key)
        return host.wait(lambda s: s['sequence'] > before and predicate(s), timeout=60)

    def select_copy():
        host.key('F7', 'ctrl+a', 'ctrl+c')
        return command('xclip', '-selection', 'clipboard', '-o')

    def raw_wait(predicate, timeout=10):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            assert host.process.poll() is None
            state = host.read()
            if state and predicate(state): return state
            time.sleep(.005)
        raise TimeoutError('H11 raw state timeout: '+repr(host.read()))

    report = {'schema': 1, 'accepted': False, 'source_sha': source, 'sdk_candidate': SDK,
              'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'checks': checks, 'states': records, 'sdk_trees': trees, 'kind': 'real-GTK-X11-input'}
    try:
        require(subprocess.run(['git', 'merge-base', '--is-ancestor', SDK, source], cwd=ROOT).returncode == 0,
                'frozen SDK is ancestor')
        for path in TREES:
            baseline = command('git', '-C', ROOT, 'rev-parse', SDK+':'+path)
            current = command('git', '-C', ROOT, 'rev-parse', source+':'+path)
            trees[path] = {'baseline': baseline, 'host': current}
            require(current == baseline, 'unchanged SDK '+path)
        book, missing, huge = output/'routes.epub', output/'missing.epub', output/'huge.epub'
        fixture(book); fixture(missing, missing=True); fixture(huge, large=True)
        report['identities'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (binary, font, book, missing, huge)}
        manifest = json.loads((args.payload.parent/'build.json').read_text())
        require(manifest['source_sha'] == source and manifest['sdk_version'] == '3.40.0' and manifest['abi'] == 1
                and manifest['files']['bin/exreader-linux'] == report['identities'][str(binary)]
                and manifest['files']['Reader.otf'] == report['identities'][str(font)],
                'same source SDK program and font package identity')
        host.launch(); host.dialog(book)
        first = stable('first page')
        require(first['bounded'] == 1 and first['part'] == 0 and first['snapshot_bytes'] == 0,
                'new EPUB defaults to bounded source')
        require('ALPHA' in select_copy(), 'native selectable first chapter text')
        turn('F4', lambda s: s['part'] == 1)
        require('BETA' in select_copy(), 'cross chapter forward and native clipboard')
        host.key('F11'); host.paste('H11 beta note'); host.key('F7', 'ctrl+a', 'F8')
        note = host.wait(lambda s: s['notes'] == 1 and s['selection_end'] > s['selection_start'])
        with sqlite3.connect(output/'profile/library.sqlite') as db:
            stored = db.execute('SELECT part,path,start,end,exact FROM epub_notes').fetchone()
        require(stored[0] == 1 and stored[1] == 'OPS/b.xhtml' and stored[2] == 0 and stored[3] == note['selection_end']
                and 'BETA' in stored[4], 'chapter local note independently persisted')
        turn('F4', lambda s: s['part'] == 2)
        beginning = stable('long chapter first frame')
        require(beginning['projection_bytes'] > 1000000 and beginning['workspace_bytes'] <= 64*1024*1024
                and beginning['snapshot_bytes'] == 0 and beginning['index_bytes'] < 64*1024*1024,
                'long chapter bounded metrics', beginning)
        for i in range(65):
            page = host.read()['page']; turn('F4', lambda s: s['page'] == page+1 and s['part'] == 2)
        advanced = stable('long chapter after 65 native turns')
        require(advanced['start'] > 16384 and advanced['windows_evicted'] > 0 and advanced['snapshot_bytes'] == 0,
                'real page turns cross bounded window and evict', advanced)
        turn('F5', lambda s: s['font'] == 26)
        require(host.read()['position'] == advanced['position'], 'font change keeps exact chapter offset')
        turn('F6', lambda s: s['font'] == 24)
        host.key('F9', 'Home', 'Return')
        jumped = host.wait(lambda s: s['part'] == 1 and s['selected'] > 0)
        require('BETA' in select_copy() and jumped['notes'] == 1, 'note jumps across evicted chapter and selects quote')
        turn('F3', lambda s: s['part'] == 0)
        require('ALPHA' in select_copy(), 'previous crosses chapter boundary')
        turn('F4', lambda s: s['part'] == 1)
        saved = stable('before actual process reopen'); pid = host.process.pid
        command('import', '-window', host.window, output/'before-reopen.png')
        book.unlink(); host.close(); host.launch()
        restored = stable('after actual process reopen')
        restored_pid = host.process.pid
        require(host.process.pid != pid and all(restored[k] == saved[k] for k in ('book', 'part', 'position', 'start', 'font', 'notes')),
                'new process restores exact source independent chapter and note')
        require('BETA' in select_copy(), 'reopened page native text')
        # Exercise a repeated physical resource through the third spine position
        # using a small independent routing fixture generated by the same cloud step.
        small = output/'small.epub'
        fixture(small)
        with zipfile.ZipFile(small) as original:
            entries = [(item, original.read(item.filename)) for item in original.infolist()]
        with zipfile.ZipFile(small, 'w') as rewritten:
            for item, data in entries:
                if item.filename == 'OPS/c.xhtml':
                    data = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>GAMMA short distinct route.</p></body></html>'
                rewritten.writestr(item, data)
        host.dialog(small); second = stable('small repeated route open')
        for expected in (1, 2, 3): turn('F4', lambda s: s['part'] == expected)
        require('ALPHA' in select_copy() and host.read()['part'] == 3, 'repeated resource keeps distinct spine position')
        duplicate = stable('repeated route before restart'); host.close(); host.launch()
        repeated = stable('repeated route after restart')
        require(repeated['part'] == 3 and repeated['position'] == duplicate['position'], 'repeated route survives process reopen')
        host.dialog(missing); broken = stable('missing chapter first frame')
        turn('F4', lambda s: s['error'] != 0)
        rejected = host.read()
        require(rejected['book'] == broken['book'] and rejected['part'] == 0 and rejected['start'] == broken['start'],
                'missing chapter fails without replacing accepted frame')
        # Real production worker: import is accepted through the native chooser;
        # observe GTK dispatch while its large source is still processing.
        host.key('F1')
        dialog = command('xdotool', 'search', '--sync', '--onlyvisible', '--name', '^Import book$').splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', dialog); host.key('ctrl+l'); host.paste(str(huge))
        command('xdotool', 'key', '--clearmodifiers', 'Return')
        time.sleep(.15)
        if subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '^Import book$'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            command('xdotool', 'key', '--clearmodifiers', 'Return')
        running = raw_wait(lambda s: s['busy'] and not s['saving'])
        sent = time.monotonic(); command('xdotool', 'key', '--clearmodifiers', 'F2')
        responding = raw_wait(lambda s: s['sequence'] > running['sequence'] and s['reader_visible'] == 0 and s['busy'])
        elapsed = (time.monotonic()-sent)*1000
        require(elapsed < 2000 and responding['book'] == broken['book'], 'GTK dispatches real input while worker is busy',
                {'input_response_ms': elapsed, 'state': responding})
        command('xdotool', 'key', '--clearmodifiers', 'Escape')
        cancelled = raw_wait(lambda s: not s['busy'] and s['error'] == 9)
        time.sleep(1)
        settled = host.read()
        require(all(settled[k] == broken[k] for k in ('book', 'part', 'start', 'position'))
                and settled['generation'] > running['generation'] and settled['error'] == cancelled['error'],
                'real cancellation rejects stale result and keeps accepted position', settled)
        # Retry a valid book via the real shelf after cancellation drains.
        host.key('F2', 'End', 'Return')
        retry = stable('book switch after cancellation')
        require(retry['book'] != broken['book'], 'worker accepts subsequent book without stale overwrite')
        command('import', '-window', host.window, output/'after-cancel.png')
        host.close()
        report['measurements'] = {'long_native_turns': 65, 'projection_bytes': beginning['projection_bytes'],
                                  'index_bytes': advanced['index_bytes'], 'peak_parse_workspace_bytes': advanced['workspace_bytes'],
                                  'explicit_snapshot_bytes': advanced['snapshot_bytes'], 'windows_evicted': advanced['windows_evicted'],
                                  'input_response_ms': elapsed, 'cancel_code': cancelled['error'],
                                  'original_pid': pid, 'reopened_pid': restored_pid, 'screenshots': 2}
        report['accepted'] = True
    finally:
        if host.process and host.process.poll() is None:
            host.process.send_signal(signal.SIGTERM); host.process.wait(timeout=10)
        if host.log: host.log.close()
        report['files'] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in output.rglob('*') if p.is_file() and p.name != 'bounded-ui.json'}
        (output/'bounded-ui.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
        if not report['accepted']:
            print('H11 STATE '+repr(host.read()), flush=True)
            print((output/'application.log').read_text(errors='replace')[-10000:], flush=True)
    print(json.dumps({'H11_accepted': report['accepted'], 'checks': len(checks), 'source_sha': source,
                      'sdk_candidate': SDK, 'run_id': report['run_id'], 'run_attempt': report['run_attempt'],
                      'measurements': report['measurements']}, sort_keys=True))


if __name__ == '__main__':
    main()
