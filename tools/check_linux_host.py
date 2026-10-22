#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Twenty real GTK/X11 user-operation checks; run only on a cloud Linux runner."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time

from PIL import Image
from run_benchmarks import make_epub


def command(*args, **kwargs):
    return subprocess.check_output([str(x) for x in args], text=True, timeout=30, **kwargs).strip()


class Session:
    def __init__(self, binary, font, folder):
        self.binary, self.font, self.folder = binary, font, folder
        self.observe = folder/'state.ini'
        self.process = None
        self.log = None

    def launch(self):
        self.observe.unlink(missing_ok=True)
        self.log = (self.folder/'application.log').open('ab')
        self.process = subprocess.Popen([str(self.binary), str(self.font), str(self.folder/'profile'),
                                         str(self.observe)], stdout=self.log, stderr=subprocess.STDOUT)
        self.wait(lambda s: s['visible'] == 1)
        end = time.monotonic()+30
        self.window = None
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError('Host exited before mapping its window; see application.log')
            result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(self.process.pid)],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
            if result.returncode == 0:
                for candidate in result.stdout.splitlines():
                    if command('xdotool', 'getwindowname', candidate) == 'EXReader Linux':
                        self.window = candidate
                        break
            if self.window:
                break
            time.sleep(.1)
        if not self.window:
            raise TimeoutError('Host window was not mapped; see window-tree.txt and application.log')
        command('xdotool', 'windowactivate', '--sync', self.window)

    def read(self):
        parser = configparser.ConfigParser()
        if not parser.read(self.observe):
            return {}
        return {key: int(value) for key, value in parser['host'].items()}

    def wait(self, predicate, timeout=30):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError('Host exited; see application.log')
            state = self.read()
            if state and not state.get('busy', 0) and predicate(state):
                return state
            time.sleep(.1)
        raise TimeoutError('UI did not reach expected state: '+repr(self.read()))

    def key(self, *keys):
        command('xdotool', 'key', '--clearmodifiers', *keys)
        time.sleep(.15)

    def paste(self, value):
        subprocess.run(['xclip', '-selection', 'clipboard'], input=value.encode(), check=True)
        self.key('ctrl+v')

    def dialog(self, path=None):
        before = self.read()['sequence']
        self.key('F1')
        command('xdotool', 'search', '--sync', '--onlyvisible', '--name', '^Import book$')
        if path is None:
            self.key('Escape')
        else:
            self.key('ctrl+l')
            self.paste(str(path))
            self.key('Return')
        self.wait(lambda s: s['sequence'] > before)
        end = time.monotonic()+30
        while time.monotonic() < end:
            result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '^Import book$'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if result.returncode == 1:
                return
            time.sleep(.1)
        raise TimeoutError('Native import dialog did not close')

    def close(self):
        if self.process:
            if self.process.poll() is None:
                command('xdotool', 'windowactivate', '--sync', self.window)
                self.key('alt+F4')
                self.process.wait(timeout=20)
            if self.process.returncode != 0:
                raise RuntimeError('Host close failed')
        if self.log:
            self.log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('Choose a new evidence directory')
    output.mkdir(parents=True)
    # Wait for the desktop session before mapping a real client. Openbox starts
    # asynchronously in the workflow; showing GTK before it owns the root races.
    end = time.monotonic()+30
    while time.monotonic() < end:
        ready = command('xprop', '-root', '_NET_SUPPORTING_WM_CHECK')
        if 'window id #' in ready and '0x0' not in ready:
            break
        time.sleep(.1)
    else:
        raise TimeoutError('Window manager did not become ready')
    corpus = output/'corpus'
    corpus.mkdir()
    book = corpus/'示例 reader.epub'
    make_epub(book, 2, 12000)
    other = corpus/'Z unicode.txt'
    other.write_text(('中文、café, नमस्ते. Portable library shelf.\n'*80), encoding='utf-8')
    invalid = corpus/'invalid.epub'
    invalid.write_bytes(b'not an epub')
    oversized = corpus/'large.txt'
    with oversized.open('wb') as file:
        file.truncate(8*1024*1024+1)
    host = Session((args.payload/'bin/exreader-linux').resolve(), (args.payload/'Reader.otf').resolve(), output)
    checks = []

    def checked(name, result, detail=None):
        if not result:
            raise AssertionError(name)
        checks.append({'name': name, 'pass': True, 'observed': detail or host.read()})
        print('PASS '+name, flush=True)

    report = {'schema': 1, 'passed': False, 'checks': checks, 'kind': 'real-x11-input',
              'display': os.environ.get('DISPLAY'), 'sdk_version': '3.40.0',
              'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    try:
        host.launch()
        checked('01 empty shelf launch', host.read()['books'] == 0)
        host.dialog()
        checked('02 cancel initial import', host.read()['books'] == 0 and host.read()['book'] == 0)
        host.dialog(book)
        state = host.wait(lambda s: s['books'] == 1 and s['book'] > 0 and s['end'] > 0)
        first = state['book']
        checked('03 unicode path EPUB import and open', state['error'] == 0 and state['page'] == 0)
        command('import', '-window', host.window, str(output/'reader.png'))
        image = Image.open(output/'reader.png').convert('RGB')
        colors = image.getcolors(image.width*image.height)
        ink = sum(1 for r, g, b in image.crop((50, 120, 500, 650)).getdata() if max(r, g, b) < 200)
        checked('04 real mapped GTK window and rendered page', colors is not None and len(colors) > 100 and ink > 1000,
                {'width': image.width, 'height': image.height, 'colors': len(colors) if colors else 0, 'page_ink_pixels': ink})
        host.key('F4')
        checked('05 next page', host.wait(lambda s: s['page'] == 1)['start'] > 0)
        host.key('F3')
        checked('06 previous page', host.wait(lambda s: s['page'] == 0)['start'] == 0)
        host.key('F3')
        checked('07 first page boundary preserves frame', host.read()['page'] == 0 and host.read()['error'] == 1)
        host.key('F5')
        checked('08 increase font and repaginate', host.wait(lambda s: s['font'] == 26)['error'] == 0)
        host.key('F6')
        checked('09 decrease font and repaginate', host.wait(lambda s: s['font'] == 24)['error'] == 0)
        host.key('F7', 'ctrl+a')
        checked('10 native text selection', host.wait(lambda s: s['selected'] > 0)['selected'] > 10)
        host.key('F11')
        host.paste('Cloud UI note: 中文 café')
        host.key('F7', 'ctrl+a', 'F8')
        state = host.wait(lambda s: s['notes'] == 1)
        with sqlite3.connect(output/'profile/library.sqlite') as db:
            table, quote = ('epub_notes', 'exact') if state.get('bounded') else ('notes', 'anchor_exact')
            note = db.execute(f'SELECT start,end,text,{quote} FROM {table}').fetchone()
        checked('11 selected range and Unicode comment stored',
                state['selection_end'] > state['selection_start'] and note[0] == state['selection_start']
                and note[1] == state['selection_end'] and note[2] == 'Cloud UI note: 中文 café' and bool(note[3]))
        host.key('F4', 'F4', 'F9', 'Home', 'Return')
        checked('12 note activation navigates and selects', host.wait(lambda s: s['page'] == 0 and s['selected'] > 0)['notes'] == 1)
        # Persist a nondefault value: restoring defaults must fail this check.
        host.key('F5')
        host.wait(lambda s: s['font'] == 26 and s['error'] == 0)
        host.key('F4', 'F4')
        saved = host.wait(lambda s: s['page'] == 2)
        report['restart_expected'] = saved
        book.unlink()
        host.close()
        host.launch()
        restored = host.wait(lambda s: s['book'] == first and s['page'] == 2)
        checked('13 graceful restart restores source progress font notes',
                restored['start'] == saved['start'] and restored['notes'] == 1
                and saved['font'] != 24 and restored['font'] == saved['font'])
        command('xdotool', 'windowminimize', host.window)
        time.sleep(.3)
        command('xdotool', 'windowmap', host.window)
        command('xdotool', 'windowactivate', '--sync', host.window)
        command('xdotool', 'windowsize', '--sync', host.window, '1200', '900')
        time.sleep(.3)
        geometry = command('xdotool', 'getwindowgeometry', '--shell', host.window)
        checked('14 minimize restore resize retains reading location',
                host.read()['start'] == saved['start'] and 'WIDTH=1200' in geometry and 'HEIGHT=900' in geometry)
        host.dialog()
        checked('15 cancel import preserves open page', host.read()['book'] == first and host.read()['start'] == saved['start'])
        make_epub(book, 2, 12000)
        host.dialog(book)
        state = host.wait(lambda s: s['error'] == 0 and s['book'] == first)
        checked('16 exact duplicate import retains row notes progress', state['books'] == 1 and state['notes'] == 1 and state['page'] == 2)
        host.dialog(other)
        second = host.wait(lambda s: s['books'] == 2 and s['book'] != first)['book']
        host.key('F11')
        host.paste('Unicode byte range')
        host.key('F7', 'ctrl+Home', 'shift+Right', 'shift+Right', 'shift+Right', 'F8')
        unicode_state = host.wait(lambda s: s['notes'] == 1 and s['selection_end'] > 0)
        with sqlite3.connect(output/'profile/library.sqlite') as db:
            unicode_note = db.execute('SELECT start,end,anchor_exact FROM notes WHERE book_id=?', (second,)).fetchone()
        unicode_range = unicode_state['selection_start'] == 0 and unicode_state['selection_end'] == 9 and unicode_note == (0, 9, '中文、')
        host.key('F2', 'Home', 'Down', 'Return')
        checked('17 Unicode byte-range selection and native shelf switching',
                unicode_range and second != first and host.wait(lambda s: s['book'] == first)['page'] == 2)
        prior = host.read()
        host.dialog(oversized)
        state = host.wait(lambda s: s['error'] == 6)
        checked('18 over limit import leaves library and reader intact',
                state['books'] == 2 and state['book'] == first and state['start'] == prior['start'])
        host.dialog(invalid)
        state = host.wait(lambda s: s['error'] != 0 and s['error'] != 6)
        checked('19 invalid EPUB fails without replacing active book',
                state['books'] == 2 and state['book'] == first and state['start'] == prior['start'])
        host.key('F9', 'Home', 'F10')
        host.wait(lambda s: s['notes'] == 0 and s['error'] == 0)
        host.close()
        host.launch()
        state = host.wait(lambda s: s['book'] == first)
        checked('20 note deletion persists across close and relaunch', state['notes'] == 0 and state['books'] == 2)
        host.close()
        report['passed'] = len(checks) == 20
    finally:
        (output/'window-tree.txt').write_text(command('xwininfo', '-root', '-tree'))
        if len(checks) != 20:
            print('Window inventory: '+(output/'window-tree.txt').read_text(), flush=True)
            print('Host diagnostics: '+(output/'application.log').read_text(errors='replace'), flush=True)
        if host.process and host.process.poll() is None:
            host.process.send_signal(signal.SIGTERM)
            host.process.wait(timeout=10)
        if host.log:
            host.log.close()
        report['files'] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'report.json'}
        (output/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    if not report['passed']:
        raise RuntimeError('Linux host acceptance incomplete')
    print(json.dumps({'acceptance': 'wp13-linux', 'passed': True, 'checks': len(checks),
                      'names': [case['name'] for case in checks], 'source_sha': report['source_sha'],
                      'run_id': report['run_id'], 'report_sha256': hashlib.sha256((output/'report.json').read_bytes()).hexdigest(),
                      'screenshot_sha256': report['files']['reader.png']}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
