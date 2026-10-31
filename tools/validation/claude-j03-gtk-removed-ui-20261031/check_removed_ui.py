# SPDX-License-Identifier: MIT
"""J03: real GTK 'Removed books' dialog paging/selection/restore. Actions only.

Drives the unchanged packaged GTK host with real X11 input and reads the dialog
through AT-SPI. Fixtures: tombstoned books seeded through the installed typed
command API (scenario A, no restores) and two really imported then really
deleted books plus synthetic tombstones (scenario B).
"""
import argparse, hashlib, json, os, re, sqlite3, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests/reader_a11y_gtk'))
from check_linux_host import Session, command  # noqa: E402
import atspi_client as bus  # noqa: E402

KEY = re.compile(r'txt:[0-9a-f]{64}')
report = {'accepted': False, 'scope': 'GTK Removed books dialog UI only; not a product acceptance',
          'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
          'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'checks': [], 'steps': [],
          'differs_from_c07': 'C07 evidence is installed-API paging; this drives dialog buttons and reads widgets',
          'sdk_changed': False, 'production_files_changed': False}


def record(name, ok, observed=None):
    row = {'name': name, 'pass': bool(ok), 'observed': observed}
    report['checks'].append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
    assert ok, row


def text_of(node):
    value = bus.accessible_text(node)
    return value['text'] if isinstance(value, dict) else (value or '')


class Ui:
    def __init__(self, payload, folder):
        self.folder = folder
        folder.mkdir(parents=True)
        self.host = Session((payload / 'bin/exreader-linux').resolve(), (payload / 'Reader.otf').resolve(), folder)
        self.catalog = folder / 'profile/library.sqlite.product.sqlite'
        self.app = None
        self.shots = 0

    def launch(self):
        self.host.launch()
        self.app = bus.wait_application('exreader-linux')

    def close(self):
        self.host.close()

    def sql(self, q, v=()):
        with sqlite3.connect(self.catalog) as db:
            return db.execute(q, v).fetchall()

    def shot(self, label):
        self.shots += 1
        name = '%02d-%s.png' % (self.shots, label)
        subprocess.run(['import', '-window', 'root', str(self.folder / name)], timeout=20, check=False)
        return name

    def window(self, title, present=True, timeout=35):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            assert self.host.process.poll() is None, 'host exited'
            r = subprocess.run(['xdotool', 'search', '--onlyvisible', '--all', '--pid', str(self.host.process.pid),
                                '--name', '^' + title + '$'], text=True, capture_output=True, timeout=5)
            seen = bool(r.stdout.strip()) or (present and self.atspi_has(title))
            if seen == present:
                if present and r.stdout.strip():
                    command('xdotool', 'windowactivate', '--sync', r.stdout.splitlines()[-1])
                return
            time.sleep(.1)
        self.diagnose('window-' + title)
        raise TimeoutError('window state differs: ' + title)

    def atspi_has(self, title):
        for n in bus.walk(self.app):
            if bus.name(n) == title and bus.role(n) in ('dialog', 'frame', 'window') and bus.states(n).get('showing'):
                return True
        return False

    def diagnose(self, label):
        listing = subprocess.run(['wmctrl', '-lpG'], text=True, capture_output=True, timeout=10).stdout
        ids = subprocess.run(['xdotool', 'search', '--all', '--pid', str(self.host.process.pid), '--name', '.'],
                             text=True, capture_output=True, timeout=10).stdout.split()
        names = []
        for i in ids[:60]:
            r = subprocess.run(['xdotool', 'getwindowname', i], text=True, capture_output=True, timeout=5)
            names.append(i + ':' + r.stdout.strip())
        tops = [bus.role(n) + ':' + bus.name(n) + ':' + str(bool(bus.states(n).get('showing'))) for n in bus.children(self.app)]
        report.setdefault('diagnostics', []).append({'label': label, 'wmctrl': listing, 'x_windows': names,
                                                      'atspi_top_level': tops, 'host_state': self.host.read()})
        subprocess.run(['import', '-window', 'root', str(self.folder / ('diag-' + label.replace(' ', '_') + '.png'))], timeout=20, check=False)

    def dialog_node(self):
        for n in bus.walk(self.app):
            if bus.name(n) == 'Removed books' and bus.role(n) in ('dialog', 'frame', 'window') and bus.states(n).get('showing'):
                return n
        return None

    def rows(self):
        """Ordered unique book keys currently held by the dialog list, plus selected keys."""
        d = self.dialog_node()
        assert d is not None, 'Removed books dialog not on the accessibility tree'
        found, selected, titles = {}, [], {}
        for n in bus.walk(d):
            if bus.role(n) != 'label':
                continue
            text = bus.name(n) + '\n' + text_of(n)
            m = KEY.search(text)
            if m and bus.states(n).get('visible', True):
                box = bus.extents(n) or {'y': 0}
                found.setdefault(m.group(0), box['y'])
                titles[m.group(0)] = text.split('\n')[0]
        for n in bus.walk(d):
            if bus.role(n) == 'list item' and bus.states(n).get('selected'):
                for c in bus.walk(n):
                    m = KEY.search(bus.name(c) + '\n' + text_of(c))
                    if m:
                        selected.append(m.group(0)); break
        return list(found), selected, titles

    def button(self, name):
        d = self.dialog_node()
        for n in bus.walk(d):
            if bus.role(n) == 'push button' and bus.name(n).replace('_', '') == name:
                return n
        raise AssertionError('button missing: ' + name)

    def enabled(self, name):
        st = bus.states(self.button(name))
        return bool(st.get('sensitive') or st.get('enabled'))

    def click(self, name):
        node = self.button(name)
        box = bus.extents(node)
        assert box and box['width'] > 0 and box['x'] >= 0 and box['y'] >= 0, (name, box)
        command('xdotool', 'mousemove', '--sync', str(box['x'] + box['width'] // 2), str(box['y'] + box['height'] // 2))
        command('xdotool', 'click', '1')
        time.sleep(.3)

    def wait_rows(self, predicate, label, timeout=40):
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            assert self.host.process.poll() is None, 'host exited'
            self.host.wait(lambda s: True, timeout=30)
            keys, _, _ = self.rows()
            last = keys
            if predicate(keys):
                return keys
            time.sleep(.2)
        raise TimeoutError(label + ' last=' + repr(last and len(last)))

    def open_removed(self):
        command('xdotool', 'windowactivate', '--sync', self.host.window)
        self.host.key('ctrl+shift+d')
        self.window('Removed books')

    def activate_first(self):
        """Activate the first row by real input; try double-click, then focused Home+Return, then Return. Records which worked."""
        d = self.dialog_node()
        items = [n for n in bus.walk(d) if bus.role(n) == 'list item']
        box = bus.extents(items[0]) if items else None
        assert box and box['x'] >= 0 and box['width'] > 0, 'no list row extents'
        point = (str(box['x'] + box['width'] // 2), str(box['y'] + box['height'] // 2))
        log = {'row_box': box, 'tried': []}
        report.setdefault('activation', []).append(log)

        def landed():
            try:
                self.window('Book details', timeout=8)
                return True
            except TimeoutError:
                return False

        command('xdotool', 'mousemove', '--sync', *point)
        command('xdotool', 'click', '--repeat', '2', '--delay', '120', '1')
        log['tried'].append('double_click')
        if landed():
            log['worked'] = 'double_click'; return
        if self.dialog_node() is not None:
            command('xdotool', 'click', '1')
            time.sleep(.3)
            self.host.key('Home', 'Return')
            log['tried'].append('click_home_return')
            if landed():
                log['worked'] = 'click_home_return'; return
        self.diagnose('activation-failed')
        raise TimeoutError('no activation method opened Book details')

    def step(self, name, **data):
        row = dict(name=name, **data)
        report['steps'].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)


def seed(exe, db, rows, folder):
    tsv = folder / 'seed.tsv'
    tsv.write_text(''.join(k + '\t' + t + '\n' for k, t in rows), encoding='utf-8')
    out = subprocess.run([str(exe), str(db), str(tsv)], capture_output=True, text=True, timeout=300)
    (folder / 'seed.log').write_text(out.stdout + out.stderr)
    assert out.returncode == 0, out.stderr


def deleted_keys(ui):
    return sorted(k for k, in ui.sql('SELECT book_key FROM reader_books WHERE deleted=1'))


def scenario_a(args, out):
    ui = Ui(args.payload, out / 'A-paging')
    ui.launch(); ui.host.wait(lambda s: True); ui.close()
    assert ui.catalog.exists(), 'product catalog missing after first launch'
    rows = [('txt:%064x' % i, 'J03 Removed %03d' % i) for i in range(1, 52)]
    seed(args.seed, ui.catalog, rows, ui.folder)
    keys = [k for k, _ in rows]
    record('A.fixture_51_unique_tombstones', deleted_keys(ui) == sorted(keys) and len(set(keys)) == 51, {'count': 51})
    ui.launch()
    try:
        ui.host.wait(lambda s: s['books'] == 0)
        ui.open_removed()
        first = ui.wait_rows(lambda k: len(k) > 0, 'first page')
        ui.shot('removed-page-1')
        record('A.open_shows_50_expected_ids_in_order', first == keys[:50], {'rows': len(first), 'first': first[:2], 'last': first[-1]})
        record('A.first_page_buttons', ui.enabled('Next page'), {'next_enabled': True})
        ui.step('page1', keys=first, first_enabled=ui.enabled('First page'), next_enabled=ui.enabled('Next page'))
        ui.click('Next page')
        second = ui.wait_rows(lambda k: k != first, 'next page')
        ui.shot('removed-page-2')
        record('A.next_shows_exactly_the_1_remaining_id', second == keys[50:], {'rows': len(second), 'keys': second})
        record('A.last_page_next_disabled', not ui.enabled('Next page'), {'next_enabled': ui.enabled('Next page')})
        ui.step('page2', keys=second, first_enabled=ui.enabled('First page'), next_enabled=ui.enabled('Next page'))
        ui.click('First page')
        again = ui.wait_rows(lambda k: len(k) == 50, 'first page again')
        ui.shot('removed-page-1-again')
        record('A.first_returns_same_50_ids_same_order', again == first, {'rows': len(again)})
        ui.step('page1-again', keys=again)
        record('A.no_state_change_from_paging', deleted_keys(ui) == sorted(keys), {'tombstones': 51})
        ui.host.key('Escape')
    finally:
        try:
            ui.close()
        except Exception as e:
            report.setdefault('close_errors', []).append(repr(e))
    return ui


def make_book(path, tag):
    path.write_bytes((tag + ' native removed-book restore fixture.\n').encode() * 200)
    return 'txt:' + hashlib.sha256(path.read_bytes()).hexdigest()


def scenario_b(args, out):
    ui = Ui(args.payload, out / 'B-select-restore')
    books = ui.folder / 'books'; books.mkdir()
    pa, pb = books / 'J03 real A.txt', books / 'J03 real B.txt'
    ka, kb = make_book(pa, 'A'), make_book(pb, 'B')
    ka, kb = sorted([ka, kb]); pa, pb = (pa, pb) if make_book(pa, 'A') == ka else (pb, pa)
    ui.launch()
    try:
        for path in (pa, pb):
            ui.host.dialog(path)
            ui.host.wait(lambda s: s['books'] == 1 and s['book'] > 0)
            command('xdotool', 'windowactivate', '--sync', ui.host.window)
            ui.host.key('F2', 'ctrl+e'); ui.window('Book details')
            ui.host.key('alt+d'); ui.window('Confirm book operation')
            ui.host.key('alt+o'); ui.window('Confirm book operation', False); ui.window('Book details', False)
            ui.host.wait(lambda s: s['books'] == 0 and not s['error'], timeout=60)
    finally:
        ui.close()
    record('B.two_real_imports_were_really_deleted_in_ui', deleted_keys(ui) == sorted([ka, kb]), {'keys': [ka, kb]})
    lo, hi = int(ka[4:], 16), int(kb[4:], 16)
    seeds = [('txt:%064x' % (lo + (i + 1) * (hi - lo) // 50), 'J03 Synthetic %02d' % (i + 1)) for i in range(49)]
    assert len({k for k, _ in seeds} | {ka, kb}) == 51
    seed(args.seed, ui.catalog, seeds, ui.folder)
    ordered = sorted([ka, kb] + [k for k, _ in seeds])
    record('B.fixture_51_tombstones_real_first_and_last', deleted_keys(ui) == ordered and ordered[0] == ka and ordered[50] == kb,
           {'first': ordered[0] == ka, 'last': ordered[50] == kb})
    revisions0 = ui.sql('SELECT count(*) FROM reader_revisions')[0][0]
    ui.launch()
    try:
        command('xdotool', 'windowactivate', '--sync', ui.host.window)
        ui.host.key('F2')
        ui.host.wait(lambda s: s['books'] == 0)
        # End-page selection: restore the record on page 2.
        ui.open_removed()
        p1 = ui.wait_rows(lambda k: len(k) > 0, 'B page 1')
        record('B.page1_has_50_with_first_real', p1 == ordered[:50], {'rows': len(p1)})
        ui.click('Next page')
        p2 = ui.wait_rows(lambda k: k != p1, 'B page 2')
        record('B.page2_is_exactly_the_last_real_id', p2 == [kb], {'keys': p2})
        _, sel_before, _ = ui.rows()
        ui.activate_first(); ui.window('Book details')
        ui.shot('b-details-page2-row')
        ui.host.key('alt+r'); ui.window('Confirm book operation')
        ui.host.key('alt+o'); ui.window('Confirm book operation', False); ui.window('Book details', False)
        ui.host.wait(lambda s: s['books'] == 1 and not s['error'], timeout=60)
        after = deleted_keys(ui)
        record('B.restore_from_page2_changes_only_that_id', after == sorted(set(ordered) - {kb}),
               {'tombstones': len(after), 'restored': kb, 'selected_before': sel_before})
        record('B.restore_adds_exactly_one_revision',
               ui.sql('SELECT count(*) FROM reader_revisions')[0][0] == revisions0 + 1, {})
        # Reopen: counts and pagination follow the record ids, not old row numbers.
        ui.open_removed()
        r1 = ui.wait_rows(lambda k: len(k) > 0, 'after restore page 1')
        expected = sorted(set(ordered) - {kb})
        record('B.reopen_shows_50_ids_no_stale_row', r1 == expected and not ui.enabled('Next page'),
               {'rows': len(r1), 'next_enabled': ui.enabled('Next page')})
        # First-page selection: restore the first record by id.
        _, sel0, _ = ui.rows()
        ui.activate_first(); ui.window('Book details')
        ui.host.key('alt+r'); ui.window('Confirm book operation')
        ui.host.key('alt+o'); ui.window('Confirm book operation', False); ui.window('Book details', False)
        ui.host.wait(lambda s: s['books'] == 2 and not s['error'], timeout=60)
        after2 = deleted_keys(ui)
        record('B.restore_from_page1_changes_only_that_id', after2 == sorted(set(expected) - {ka}),
               {'tombstones': len(after2), 'restored': ka})
        ui.open_removed()
        r2 = ui.wait_rows(lambda k: len(k) > 0, 'final page')
        record('B.final_removed_list_is_49_synthetic_ids', r2 == sorted(set(expected) - {ka}), {'rows': len(r2)})
        # Synthetic row has no retained original: product must refuse without writing.
        rev_before = ui.sql('SELECT count(*) FROM reader_revisions')[0][0]
        ui.activate_first(); ui.window('Book details')
        ui.host.key('alt+r')
        time.sleep(1.5)
        ui.shot('b-synthetic-restore-attempt')
        confirm = subprocess.run(['xdotool', 'search', '--onlyvisible', '--all', '--pid', str(ui.host.process.pid),
                                  '--name', '^Confirm book operation$'], text=True, capture_output=True, timeout=5).stdout.strip()
        if confirm:
            ui.host.key('alt+o'); time.sleep(2)
        wins = subprocess.run(['wmctrl', '-l'], text=True, capture_output=True, timeout=10).stdout
        report['synthetic_restore_observation'] = {'confirm_dialog_shown': bool(confirm), 'windows': wins,
            'host_state': ui.host.read()}
        record('B.synthetic_without_original_not_restored_no_write',
               deleted_keys(ui) == r2 and ui.sql('SELECT count(*) FROM reader_revisions')[0][0] == rev_before,
               report['synthetic_restore_observation'])
    finally:
        try:
            ui.close()
        except Exception as e:
            report.setdefault('close_errors', []).append(repr(e))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--payload', type=Path, required=True)
    p.add_argument('--seed', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    for n in ('NO_AT_BRIDGE', 'GTK_MODULES', 'AT_SPI_BUS_ADDRESS'):
        os.environ.pop(n, None)
    os.environ['GTK_A11Y'] = 'atspi'
    out = args.output.resolve(); out.mkdir(parents=True)
    assert bus.init()[0]
    try:
        scenario_a(args, out)
        scenario_b(args, out)
        report['accepted'] = True
    except Exception as failure:
        report['failure'] = repr(failure)
        subprocess.run(['import', '-window', 'root', str(out / 'failure-desktop.png')], timeout=20, check=False)
        w = subprocess.run(['wmctrl', '-lpG'], text=True, capture_output=True, timeout=10)
        (out / 'failure-windows.txt').write_text(w.stdout + w.stderr)
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        bus.exit_bus()


if __name__ == '__main__':
    main()
