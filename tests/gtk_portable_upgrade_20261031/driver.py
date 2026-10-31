# SPDX-License-Identifier: MIT
"""K03 real Linux portable A -> B update matrix on the GTK host.

Every product launch goes through the package's own no-argument Start-EXReader.sh, from an unrelated
working directory, with an isolated XDG_DATA_HOME locating the default profile g_get_user_data_dir()/exreader.
Input is real X11 keyboard/mouse through xdotool plus AT-SPI reads; nothing writes the profile except the
product. Databases are inspected only after the writer exited, and only on scratch copies; the untouched
copy of every snapshot is kept as evidence. stdbuf -oL only line-buffers the host's own STATUS stdout.

Each matrix item is recorded as passed / failed / blocked with raw observations; a failure is never
converted into a pass and later items still run where their prerequisites hold.
usage: driver.py --install install.json --fixtures DIR --root DIR --evidence DIR
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
sys.path.insert(0, str(TOOLS))
import atspi_client as bus  # noqa: E402  (copied from the retained 67e2f8c4 client by the workflow)

BUSY_MESSAGE = 'Reading operation in progress'
LOCK_MESSAGE = 'This local library is already in use or cannot be locked'
NOTE_A = 'K03 旧包批注 café'
NOTE_B = 'K03 新包批注 नमस्ते'
NOTE_K = 'K03 kill 前批注'
SHELF = 'K03 书架 😀'
FONT = '25.5'


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def command(*args, timeout=30):
    return subprocess.check_output([str(a) for a in args], text=True, timeout=timeout).strip()


def tree(path):
    if not path.exists():
        return {}
    return {p.relative_to(path).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
            for p in sorted(path.rglob('*')) if p.is_file() and not p.is_symlink()}


class Evidence:
    def __init__(self, folder):
        self.dir = folder
        self.checks, self.processes, self.snapshots, self.notes = [], [], {}, []
        self.counter = 0

    def name(self, stem, suffix):
        self.counter += 1
        return self.dir / f'{self.counter:03d}-{stem}{suffix}'

    def record(self, item, name, status, observed=None, detail=''):
        value = dict(item=item, name=name, status=status, observed=observed, detail=detail)
        self.checks.append(value)
        print('K03-CHECK ' + json.dumps(value, ensure_ascii=False, default=str)[:4000], flush=True)
        return status == 'passed'


class Host:
    """One product process launched through the package's own no-argument launcher."""

    def __init__(self, ev, label, install, xdg, cwd):
        self.ev, self.label, self.install, self.xdg, self.cwd = ev, label, Path(install), Path(xdg), Path(cwd)
        self.launcher = self.install / 'EXReader-Linux/Start-EXReader.sh'
        self.entry = self.install / 'EXReader-Linux/bin/exreader-linux'
        self.process = self.window = self.app = None
        self.rec = None

    @property
    def profile(self):
        return self.xdg / 'data/exreader'

    def env(self):
        env = dict(os.environ, XDG_DATA_HOME=str(self.xdg / 'data'), XDG_CONFIG_HOME=str(self.xdg / 'config'),
                   XDG_CACHE_HOME=str(self.xdg / 'cache'), GTK_A11Y='atspi')
        for key in ('NO_AT_BRIDGE', 'GTK_MODULES'):
            env.pop(key, None)
        return env

    def launch(self, expect_window=True, timeout=40):
        for sub in ('data', 'config', 'cache'):
            (self.xdg / sub).mkdir(parents=True, exist_ok=True)
        self.log_path = self.ev.name(self.label, '.log')
        self.log = self.log_path.open('wb')
        argv = ['stdbuf', '-oL', '-eL', '/bin/sh', str(self.launcher)]
        self.process = subprocess.Popen(argv, cwd=self.cwd, env=self.env(), stdout=self.log, stderr=subprocess.STDOUT)
        self.rec = dict(label=self.label, argv=argv, cwd=str(self.cwd), xdg_data_home=str(self.xdg / 'data'),
                        pid=self.process.pid, launcher_sha256=sha(self.launcher), started=time.time(),
                        log=self.log_path.name, exit=None, killed_by_test=False)
        self.ev.processes.append(self.rec)
        if not expect_window:
            return
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.process.poll() is not None:
                self.rec['exit'] = self.process.returncode
                raise RuntimeError(f'{self.label}: exited {self.process.returncode} before mapping a window')
            found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(self.process.pid)],
                                   text=True, capture_output=True, timeout=5)
            for candidate in found.stdout.split():
                try:
                    if command('xdotool', 'getwindowname', candidate) == 'EXReader Linux':
                        self.window = candidate
                except subprocess.CalledProcessError:
                    pass
            if self.window:
                break
            time.sleep(.1)
        if not self.window:
            raise TimeoutError(f'{self.label}: window not mapped')
        pid = self.process.pid
        exe = os.readlink(f'/proc/{pid}/exe')
        self.rec.update(exe=exe, exe_sha256=sha(exe), proc_cwd=os.readlink(f'/proc/{pid}/cwd'),
                        cmdline=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1], window=self.window)
        self.rec['cmdline'] = [part.decode(errors='replace') for part in self.rec['cmdline']]
        self.activate()
        self.idle()

    def activate(self):
        command('xdotool', 'windowactivate', '--sync', self.window)

    def statuses(self):
        self.log.flush()
        lines = self.log_path.read_text(errors='replace').splitlines()
        out = []
        for line in lines:
            if not line.startswith('STATUS '):
                continue
            head, _, message = line[len('STATUS '):].partition(' message=')
            value = dict(message=message)
            for field in head.split():
                key, _, number = field.partition('=')
                try:
                    value[key] = int(number)
                except ValueError:
                    value[key] = number
            out.append(value)
        return out

    def last(self):
        values = self.statuses()
        return values[-1] if values else {}

    def wait(self, predicate, since=0, timeout=40):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError(f'{self.label}: host exited {self.process.returncode}')
            values = self.statuses()[since:]
            if values and predicate(values[-1]):
                return self.idle()
            time.sleep(.1)
        raise TimeoutError(f'{self.label}: status not reached; last={self.last()!r}')

    def lines(self):
        self.log.flush()
        return self.log_path.read_bytes().count(b'
')

    def idle(self, quiet=1.5, timeout=40):
        """Quiet stdout for `quiet` seconds. The STATUS busy/saving fields are not an idle signal: after a
        frame the host commits the position and clears busy without printing another STATUS line."""
        end = time.monotonic() + timeout
        count, stable = -1, time.monotonic()
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError(f'{self.label}: host exited {self.process.returncode}')
            now = self.lines()
            if now != count:
                count, stable = now, time.monotonic()
            elif time.monotonic() - stable >= quiet:
                return self.last()
            time.sleep(.1)
        raise TimeoutError(f'{self.label}: output never settled; last={self.last()!r}')

    def key(self, *keys):
        for value in keys:
            for attempt in range(6):
                before = len(self.statuses())
                command('xdotool', 'key', '--clearmodifiers', value)
                time.sleep(.15)
                if value not in ('F3', 'F4', 'F8', 'F10', 'Return'):
                    break
                self.idle()
                # The host rejects reading work while a commit runs; repeat the same user key.
                if not any(s.get('message', '').startswith(BUSY_MESSAGE) for s in self.statuses()[before:]):
                    break
                time.sleep(1)

    def paste(self, text):
        subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode(), check=True, timeout=10)
        self.key('ctrl+v')

    def dialog_window(self, title, present=True, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--all', '--pid', str(self.process.pid),
                                    '--name', '^' + title + '$'], text=True, capture_output=True, timeout=5)
            ids = found.stdout.split()
            if bool(ids) == present:
                if present:
                    command('xdotool', 'windowactivate', '--sync', ids[-1])
                    return ids[-1]
                return None
            time.sleep(.1)
        raise TimeoutError(f'{self.label}: dialog {title!r} visibility != {present}')

    def import_book(self, path):
        before, previous = len(self.statuses()), self.last().get('book', 0)
        self.activate()
        self.key('F1')
        self.dialog_window('Import book')
        self.key('ctrl+l')
        self.paste(str(path))
        self.key('Return')
        time.sleep(.4)
        still = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '^Import book$'],
                               capture_output=True, timeout=5)
        if still.returncode == 0:
            self.key('Return')
        self.dialog_window('Import book', present=False)
        self.wait(lambda s: s.get('book', 0) not in (0, previous), since=before, timeout=60)
        return self.idle()

    def note(self, text):
        before = len(self.statuses())
        self.activate()
        self.key('F11')
        self.paste(text)
        self.key('F7', 'ctrl+a', 'F8')
        self.idle()
        return self.statuses()[before:]

    def accessible(self):
        """The registered AT-SPI application for exactly this PID."""
        end = time.monotonic() + 40
        while time.monotonic() < end:
            for app in bus.applications():
                if bus._safe(lambda: app.get_process_id()) == self.process.pid:
                    self.app = app
                    return app
            time.sleep(.2)
        raise TimeoutError(f'{self.label}: not on the accessibility bus')

    def atspi_dump(self, stem):
        app = self.accessible()
        path = self.ev.name(f'{self.label}-{stem}-atspi', '.txt')
        lines = []
        for node in bus.walk(app, max_depth=16):
            lines.append(json.dumps(dict(role=bus.role(node), name=bus.name(node),
                                         showing=bool(bus.states(node).get('showing'))), ensure_ascii=False))
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return path, lines

    def label_text(self):
        app = self.accessible()
        names = [bus.name(n) for n in bus.walk(app, max_depth=8) if bus.role(n) == 'label' and bus.states(n).get('showing')]
        return names

    def shelf_rows(self):
        app = self.accessible()
        shelf = bus.find_one(app, text='Bookshelf')
        if shelf is None:
            return None
        return [bus.name(child) for child in bus.children(shelf)]

    def screenshot(self, stem, window=None):
        path = self.ev.name(f'{self.label}-{stem}', '.png')
        command('import', '-window', window or self.window, str(path))
        return path.name

    def close(self, timeout=40):
        if self.process.poll() is None:
            self.activate()
            command('xdotool', 'key', '--clearmodifiers', 'alt+F4')
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.rec['close_timeout'] = True
                raise
        self.finish()
        return self.process.returncode

    def kill(self):
        """SIGKILL only to the PID this test launched."""
        assert self.process.poll() is None
        os.kill(self.process.pid, signal.SIGKILL)
        self.process.wait(timeout=20)
        self.rec['killed_by_test'] = True
        self.finish()
        return self.process.returncode

    def finish(self):
        self.rec['exit'] = self.process.returncode
        self.rec['ended'] = time.time()
        self.rec['status_lines'] = len(self.statuses())
        self.log.close()


def inspect(ev, label, profile):
    """Copy the closed profile twice: an untouched evidence copy and a scratch copy for read queries."""
    keep = ev.dir / 'profiles' / label
    scratch = Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'k03-scratch' / label
    for target in (keep, scratch):
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(profile, target)
    result = dict(label=label, files=tree(keep))
    library = scratch / 'library.sqlite'
    if library.is_file():
        with sqlite3.connect(library) as db:  # scratch copy only
            q = lambda sql: db.execute(sql).fetchall()
            tables = [r[0] for r in q("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            result['user_version'] = q('PRAGMA user_version')[0][0]
            result['integrity'] = q('PRAGMA integrity_check')[0][0]
            result['tables'] = {t: q(f'SELECT count(*) FROM "{t}"')[0][0] for t in tables}
            result['books'] = [dict(id=r[0], format=r[1], title=r[2], position=r[3], text_size=r[4],
                                    source_sha256=hashlib.sha256(r[5] or b'').hexdigest(), source_bytes=len(r[5] or b''))
                               for r in q('SELECT id,format,title,position,text_size,source FROM books ORDER BY id')]
            result['notes'] = [list(r) for r in q('SELECT book_id,start,end,text FROM notes ORDER BY id')] if 'notes' in tables else []
            result['epub_notes'] = ([list(r) for r in q('SELECT book_id,part,start,end,text FROM epub_notes ORDER BY id')]
                                    if 'epub_notes' in tables else [])
            result['fixed_notes'] = ([list(r) for r in q('SELECT book_id,page,start,end,text FROM fixed_notes ORDER BY id')]
                                     if 'fixed_notes' in tables else [])
            result['epub_progress'] = ([list(r) for r in q('SELECT book_id,part,position FROM epub_progress ORDER BY book_id')]
                                       if 'epub_progress' in tables else [])
            result['ledger'] = [list(r) for r in q('SELECT * FROM exr_migration_ledger')] if 'exr_migration_ledger' in tables else []
    catalog = scratch / 'library.sqlite.product.sqlite'
    if catalog.is_file():
        with sqlite3.connect(catalog) as db:  # scratch copy only
            q = lambda sql: db.execute(sql).fetchall()
            tables = [r[0] for r in q("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            result['catalog_tables'] = {t: q(f'SELECT count(*) FROM "{t}"')[0][0] for t in tables}
            if 'reader_shelves' in tables:
                result['shelves'] = [list(r) for r in q('SELECT name,ordinal FROM reader_shelves ORDER BY name')]
            if 'reader_book_shelves' in tables:
                result['memberships'] = q('SELECT count(*) FROM reader_book_shelves')[0][0]
            if 'reader_books' in tables:
                result['catalog_books'] = sorted(r[0] for r in q('SELECT book_key FROM reader_books'))
    for name in ('reader.ini', 'preferences.json'):
        if (scratch / name).is_file():
            result[name] = (scratch / name).read_text(errors='replace')
    ev.snapshots[label] = result
    return result


def all_notes(snap):
    return [tuple(n) for key in ('notes', 'epub_notes', 'fixed_notes') for n in snap.get(key, [])]


def main():
    parser = argparse.ArgumentParser()
    for name in ('install', 'fixtures', 'root', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    install = json.loads(args.install.read_text())
    a_dir, b_dir = Path(install['a']['install']), Path(install['b']['install'])
    root, ev = args.root.resolve(), Evidence(args.evidence.resolve())
    ev.dir.mkdir(parents=True, exist_ok=True)
    unrelated = root / '无关 工作 目录'
    unrelated.mkdir(parents=True, exist_ok=True)
    fixtures = args.fixtures.resolve()
    books = {'pdf': fixtures / 'Pages 页面.pdf', 'txt': fixtures / 'Notes 笔记.txt', 'epub': fixtures / '示例 Portable.epub'}
    book_sha = {k: sha(p) for k, p in books.items()}
    main_xdg = root / 'xdg 主 profile'
    report = dict(schema='k03-linux-portable-upgrade/1', source_sha=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  a_entry_sha256=install['a']['entry_sha256'], b_entry_sha256=install['b']['entry_sha256'],
                  fixtures={k: dict(path=str(p), sha256=book_sha[k]) for k, p in books.items()},
                  checks=ev.checks, processes=ev.processes, snapshots=ev.snapshots, notes=ev.notes)
    program_before = {'A': tree(a_dir), 'B': tree(b_dir)}
    state = {}

    def item(number, name, fn, needs=()):
        missing = [n for n in needs if not state.get(n)]
        if missing:
            ev.record(number, name, 'blocked', detail=f'prerequisite(s) not passed: {missing}')
            state[number] = False
            return
        started = len(ev.processes)
        try:
            observed = fn()
            state[number] = ev.record(number, name, 'passed', observed)
        except Exception as error:  # every failure keeps its raw observation
            ev.record(number, name, 'failed', detail=f'{type(error).__name__}: {error}')
            state[number] = False
            # Stop only processes this failed item launched; earlier ones end at teardown.
            for proc in ev.processes[started:]:
                if proc.get('exit') is None:
                    pid = proc['pid']
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        continue
                    os.kill(pid, signal.SIGKILL)  # only PIDs launched by this test
                    proc['killed_after_failure'] = True

    hosts = {}

    def first_run():
        host = hosts['A1'] = Host(ev, 'A1-first', a_dir, main_xdg, unrelated)
        assert not main_xdg.exists(), 'user environment is not clean'
        host.launch()
        rec = host.rec
        assert rec['exe_sha256'] == install['a']['entry_sha256'], 'A process is not the authenticated A entry'
        assert rec['cmdline'][1:] == [], f'A launched with arguments {rec["cmdline"]}'
        assert rec['proc_cwd'] == str(unrelated)
        return dict(pid=rec['pid'], exe=rec['exe'], cmdline=rec['cmdline'], cwd=rec['proc_cwd'],
                    labels=host.label_text(), screenshot=host.screenshot('empty'))

    def build_profile():
        host = hosts['A1']
        observed = {}
        for kind in ('pdf', 'txt', 'epub'):
            observed[kind] = host.import_book(books[kind])
        epub_id = observed['epub']['book']
        host.key('F4')
        host.key('F4')
        position = host.idle()
        assert position.get('book') == epub_id and position.get('page', 0) >= 1, position
        observed['position'] = position
        observed['note_status'] = host.note(NOTE_A)
        # Settings: the real preferences dialog, one non-default value.
        host.activate()
        host.key('ctrl+comma')
        host.dialog_window('Reading settings')
        app = host.accessible()
        target = None
        for _ in range(100):
            target = bus.find_one(app, text='Font size', roles={'spin button', 'text'})
            if target:
                break
            time.sleep(.1)
        assert target is not None, 'Font size control not exposed'
        rect = bus.extents(target)
        command('xdotool', 'mousemove', '--sync', rect['x'] + rect['width'] // 2, rect['y'] + rect['height'] // 2)
        command('xdotool', 'click', '1')
        host.key('ctrl+a')
        host.paste(FONT)
        host.key('Tab', 'alt+s')
        host.idle()
        observed['settings_screenshot'] = host.screenshot('settings', command('xdotool', 'getactivewindow'))
        host.key('Escape')
        host.dialog_window('Reading settings', present=False)
        # Organization: one shelf with the open book as a member, through the native organizer.
        host.activate()
        host.key('F2')
        host.idle()
        host.key('ctrl+shift+c')
        host.dialog_window('Library collections')
        host.key('alt+n')
        host.dialog_window('Collection details')
        host.key('alt+n', 'ctrl+a')
        host.paste(SHELF)
        host.key('alt+p', 'ctrl+a')
        host.paste('3')
        host.key('Return')
        host.dialog_window('Collection details', present=False)
        host.dialog_window('Library collections')
        host.key('alt+a')
        try:
            host.dialog_window('Book classification', timeout=15)
            host.key('Return')
            host.dialog_window('Book classification', present=False)
            observed['membership_dialog'] = True
        except TimeoutError:
            observed['membership_dialog'] = False
        observed['collections_screenshot'] = host.screenshot('collections', command('xdotool', 'getactivewindow'))
        host.key('alt+F4')
        host.dialog_window('Library collections', present=False)
        host.activate()
        # Return to the EPUB reading page so the last-open book is the annotated EPUB.
        observed['rows_before_close'] = host.shelf_rows()
        observed['labels'] = host.label_text()
        observed['screenshot'] = host.screenshot('profile-built')
        final = host.idle()
        assert final.get('book') == epub_id, f'last open book is not the annotated EPUB: {final}'
        state['epub_id'] = epub_id
        # The font change repaginates; resume is compared with the last state before close.
        state['a_position'] = final
        observed['final'] = final
        return observed

    def close_and_backup():
        host = hosts['A1']
        code = host.close()
        assert code == 0, f'A exited {code}'
        snap = inspect(ev, 'after-A', host.profile)
        sources = {b['source_sha256'] for b in snap['books']}
        assert snap['integrity'] == 'ok' and len(snap['books']) == 3, snap.get('books')
        assert {book_sha['txt'], book_sha['epub']} <= sources, 'EPUB/TXT original bytes not in the library'
        assert any(NOTE_A == n[-1] for n in all_notes(snap)), 'A note not persisted'
        assert re.search(r'25\.50*(?![0-9])', snap.get('preferences.json', '')), 'font setting not persisted'
        assert snap.get('shelves') and any(s[0] == SHELF for s in snap['shelves']), 'shelf not persisted'
        backup = root / 'K03 备份 before-update'
        shutil.copytree(host.profile, backup / 'exreader')
        assert tree(backup / 'exreader') == tree(host.profile), 'backup differs from the closed profile'
        state['backup'] = backup
        state['after_a'] = snap
        return dict(exit=code, user_version=snap['user_version'], tables=snap['tables'], books=snap['books'],
                    notes=all_notes(snap), shelves=snap.get('shelves'), memberships=snap.get('memberships'),
                    pdf_source_in_library=book_sha['pdf'] in sources,
                    backup_files=len(tree(backup / 'exreader')))

    def b_opens_profile():
        host = hosts['B1'] = Host(ev, 'B1-update', b_dir, main_xdg, unrelated)
        host.launch()
        rec = host.rec
        assert rec['exe_sha256'] == install['b']['entry_sha256'] and rec['exe'].startswith(str(b_dir)), rec['exe']
        assert rec['cmdline'][1:] == []
        resumed = host.idle()
        dump, lines = host.atspi_dump('opened')
        rows = host.shelf_rows()
        assert resumed.get('book') == state['epub_id'], f'B did not reopen the last book: {resumed}'
        assert resumed.get('page') == state['a_position'].get('page'), f'position {resumed} != {state["a_position"]}'
        assert rows is None or len(rows) == 3, rows
        return dict(pid=rec['pid'], resumed=resumed, shelf_rows=rows, atspi=dump.name, labels=host.label_text(),
                    screenshot=host.screenshot('opened'))

    def b_edits():
        host = hosts['B1']
        host.key('F4')
        moved = host.idle()
        statuses = host.note(NOTE_B)
        code = host.close()
        assert code == 0
        snap = inspect(ev, 'after-B-edit', host.profile)
        before = state['after_a']
        assert [b['source_sha256'] for b in snap['books']] == [b['source_sha256'] for b in before['books']], 'books changed'
        assert [b['id'] for b in snap['books']] == [b['id'] for b in before['books']], 'book identities changed'
        notes = all_notes(snap)
        assert set(all_notes(before)) <= set(notes) and any(n[-1] == NOTE_B for n in notes), notes
        assert snap.get('shelves') == before.get('shelves') and snap.get('memberships') == before.get('memberships')
        assert re.search(r'25\.50*(?![0-9])', snap.get('preferences.json', ''))
        reopen = hosts['B2'] = Host(ev, 'B2-reopen', b_dir, main_xdg, unrelated)
        reopen.launch()
        resumed = reopen.idle()
        assert reopen.rec['pid'] != hosts['B1'].rec['pid'] and reopen.rec['exe_sha256'] == install['b']['entry_sha256']
        assert resumed.get('book') == state['epub_id'], resumed
        rows = reopen.shelf_rows()
        assert rows is None or len(rows) == 3, f'duplicate import after reopen: {rows}'
        state['after_b'] = snap
        return dict(moved=moved, note_status=statuses[-3:], notes=notes, reopen_pid=reopen.rec['pid'],
                    resumed=resumed, rows=rows, screenshot=reopen.screenshot('reopened'))

    def paths_and_dependencies():
        for label, folder in (('A', a_dir), ('B', b_dir)):
            assert ' ' in str(folder) and any(ord(c) > 127 for c in str(folder)), folder
        ldd = {label: install[label]['ldd'] for label in ('a', 'b')}
        for label, lines in ldd.items():
            assert not any('not found' in l or os.environ['GITHUB_WORKSPACE'] in l for l in lines), label
        changed = {}
        for label, folder in (('A', a_dir), ('B', b_dir)):
            now = tree(folder)
            changed[label] = sorted(k for k in set(now) | set(program_before[label]) if now.get(k) != program_before[label].get(k))
        assert not any(changed.values()), f'program directories changed: {changed}'
        cwd_files = tree(unrelated)
        assert not cwd_files, f'data written to the unrelated working directory: {cwd_files}'
        assert all(p['proc_cwd'] == str(unrelated) for p in ev.processes if 'proc_cwd' in p)
        return dict(programs={'A': str(a_dir), 'B': str(b_dir)}, cwd=str(unrelated), profile=str(main_xdg / 'data/exreader'),
                    font_from_package=True)

    def concurrent_lock():
        writer = hosts['B2']
        before = writer.idle()
        second = hosts['A2'] = Host(ev, 'A2-concurrent', a_dir, main_xdg, unrelated)
        second.launch()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not any(LOCK_MESSAGE in s.get('message', '') for s in second.statuses()):
            time.sleep(.1)
        refused = [s for s in second.statuses() if LOCK_MESSAGE in s.get('message', '')]
        labels = second.label_text()
        shot = second.screenshot('lock-refused')
        assert refused, f'second writer was not refused: {second.statuses()[-3:]}'
        assert any(LOCK_MESSAGE in l for l in labels), f'refusal not visible: {labels}'
        second.close()
        writer.activate()
        after = writer.idle()
        code = writer.close()
        assert code == 0
        snap = inspect(ev, 'after-lock', writer.profile)
        assert snap['books'] == state['after_b']['books'] and set(all_notes(snap)) == set(all_notes(state['after_b']))
        return dict(refused=refused[-1], labels=labels, screenshot=shot, writer_before=before, writer_after=after,
                    second_exit=second.rec['exit'])

    def damaged_b():
        broken = root / 'K03 程序 目录' / 'B 损坏 副本'
        shutil.copytree(b_dir, broken, symlinks=True)
        # A missing program file; an empty one would be run by sh as an empty script.
        (broken / 'EXReader-Linux/bin/exreader-linux').unlink()
        profile_before = tree(main_xdg / 'data/exreader')
        host = Host(ev, 'B-damaged', broken, main_xdg, unrelated)
        try:
            host.launch(expect_window=False)
            host.process.wait(timeout=30)
        finally:
            host.finish()
        assert host.rec['exit'] != 0, 'damaged copy started'
        assert tree(main_xdg / 'data/exreader') == profile_before, 'profile changed by failed start'
        assert tree(a_dir) == program_before['A'] and tree(b_dir) == program_before['B']
        good = Host(ev, 'B3-after-damaged', b_dir, main_xdg, unrelated)
        good.launch()
        resumed = good.idle()
        assert resumed.get('book') == state['epub_id']
        assert good.close() == 0
        return dict(damaged_exit=host.rec['exit'], recovered=resumed, signature_verifier_claimed=False)

    def kill_and_reopen():
        host = Host(ev, 'B4-kill', b_dir, main_xdg, unrelated)
        host.launch()
        host.key('F4')
        confirmed = host.note(NOTE_K)
        host.key('F4')
        unconfirmed = host.last()
        code = host.kill()
        assert code == -signal.SIGKILL
        reopen = Host(ev, 'B5-after-kill', b_dir, main_xdg, unrelated)
        reopen.launch()
        resumed = reopen.idle()
        assert reopen.close() == 0
        snap = inspect(ev, 'after-kill', reopen.profile)
        assert snap['integrity'] == 'ok' and [b['source_sha256'] for b in snap['books']] == \
            [b['source_sha256'] for b in state['after_b']['books']]
        notes = all_notes(snap)
        ev.notes.append(dict(kill_note_persisted=any(n[-1] == NOTE_K for n in notes),
                             unconfirmed_page_turn=unconfirmed, resumed=resumed))
        assert set(all_notes(state['after_b'])) <= set(notes), 'confirmed notes lost after SIGKILL'
        state['after_kill'] = snap
        return dict(exit=code, confirmed_note_status=confirmed[-2:], kill_note_persisted=any(n[-1] == NOTE_K for n in notes),
                    unconfirmed_after_kill=unconfirmed, resumed=resumed, power_loss_claimed=False)

    def restore_backup():
        restored = root / 'xdg 恢复 restore'
        (restored / 'data').mkdir(parents=True)
        shutil.copytree(state['backup'] / 'exreader', restored / 'data/exreader')
        host = Host(ev, 'A3-restore', a_dir, restored, unrelated)
        host.launch()
        resumed = host.idle()
        assert host.rec['exe_sha256'] == install['a']['entry_sha256']
        assert resumed.get('book') == state['epub_id'] and resumed.get('page') == state['a_position'].get('page'), resumed
        rows = host.shelf_rows()
        shot = host.screenshot('restored')
        assert host.close() == 0
        snap = inspect(ev, 'after-restore', restored / 'data/exreader')
        before = state['after_a']
        assert snap['books'] == before['books'] and set(all_notes(snap)) == set(all_notes(before)), 'restore differs'
        assert tree(main_xdg / 'data/exreader'), 'failed/updated profile must be kept as evidence'
        return dict(resumed=resumed, rows=rows, screenshot=shot, books=len(snap['books']), notes=all_notes(snap))

    def repeat_flow():
        xdg = root / 'xdg 重复 repeat'
        a = Host(ev, 'R-A', a_dir, xdg, unrelated)
        a.launch()
        a.import_book(books['txt'])
        assert a.close() == 0
        first = inspect(ev, 'repeat-after-A', a.profile)
        results = []
        for index in range(2):
            b = Host(ev, f'R-B{index + 1}', b_dir, xdg, unrelated)
            b.launch()
            results.append(b.idle())
            assert b.close() == 0
            snap = inspect(ev, f'repeat-after-B{index + 1}', b.profile)
            assert snap['books'] == first['books'], f'duplicate or changed books on pass {index + 1}'
        return dict(books=first['books'], statuses=results)

    def separation():
        profile_before = tree(main_xdg / 'data/exreader')
        moved = root / 'K03 程序 目录' / 'B 移动后 位置'
        shutil.move(str(b_dir), str(moved))
        shutil.rmtree(root / 'K03 程序 目录' / 'B 损坏 副本')
        assert tree(main_xdg / 'data/exreader') == profile_before, 'moving/removing program dirs changed the profile'
        host = Host(ev, 'B6-moved', moved, main_xdg, unrelated)
        host.launch()
        resumed = host.idle()
        assert host.rec['exe'].startswith(str(moved)) and resumed.get('book') == state['epub_id']
        rows = host.shelf_rows()
        assert host.close() == 0
        shutil.move(str(moved), str(b_dir))
        return dict(moved_to=str(moved), resumed=resumed, rows=rows, uninstall_performed=False)

    try:
        assert bus.init()[0], 'AT-SPI unavailable'
        item(1, 'A first run in a clean user environment via the no-argument launcher', first_run)
        item(2, 'A builds the old profile through the real UI', build_profile, needs=(1,))
        item(3, 'A closes; complete closed-state backup', close_and_backup, needs=(2,))
        item(4, 'B opens the same profile from another path', b_opens_profile, needs=(3,))
        item(5, 'B edits, closes and reopens without duplicates', b_edits, needs=(4,))
        item(6, 'program paths with spaces/non-ASCII, unrelated CWD, packaged dependencies', paths_and_dependencies, needs=(5,))
        item(7, 'A and B on one profile: second writer refused by the profile lock', concurrent_lock, needs=(5,))
        item(8, 'damaged B copy fails without touching A, B or the profile', damaged_b, needs=(5,))
        item(9, 'B SIGKILLed by PID then reopened', kill_and_reopen, needs=(5,))
        item(10, 'pre-update backup restored into a new directory and opened by the original A', restore_backup, needs=(3,))
        item(11, 'repeated A -> B on an independent profile', repeat_flow, needs=(1,))
        item(12, 'moving/removing synthetic program directories keeps the profile', separation, needs=(5,))
        ev.record('downgrade', 'B-modified profile handed back to A', 'not-run',
                  detail='no downgrade contract exists; not promised. Backup restore with the original A is item 10.')
        ev.record('schema', 'cross-schema migration', 'not-run',
                  detail='A and B record their actual library user_version; no older-schema source was authorized.')
    finally:
        for proc in ev.processes:
            if proc.get('exit') is None:
                try:
                    os.kill(proc['pid'], signal.SIGKILL)
                    proc['killed_at_teardown'] = True
                except OSError:
                    pass
        try:
            (ev.dir / 'xwininfo.txt').write_text(command('xwininfo', '-root', '-tree'))
        except Exception:
            pass
        report['summary'] = {s: sum(c['status'] == s for c in ev.checks) for s in ('passed', 'failed', 'blocked', 'not-run')}
        report['passed'] = all(state.get(n) for n in range(1, 13))
        report['files'] = {p.relative_to(ev.dir).as_posix(): sha(p) for p in sorted(ev.dir.rglob('*'))
                           if p.is_file() and p.name != 'report.json'}
        (ev.dir / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n')
        print('K03-RESULT ' + json.dumps(dict(passed=report['passed'], summary=report['summary'])), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
