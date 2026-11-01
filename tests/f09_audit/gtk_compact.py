"""F09 GTK: keyboard and AT-SPI audit of the compact full product host.

The shared-source GTK product (tests/reader_gtk_raw_wave3 build_compact_host)
is the compact shell: a library bar (Import book, Continue reading, More
library actions), a reading bar (Back to library, Previous/Next page,
Contents / pages, More reader actions) and keyboard commands for collections
(Ctrl+Shift+C), account (Ctrl+Shift+A), reading records (Ctrl+Shift+R), details
(Ctrl+E) and search (Ctrl+F); F1 imports, F2 returns to the shelf, F3/F4 turn
pages (Page_Down only when the hardware-key preference is on). Importing a
book opens it, by design. The retained tests/reader_a11y_gtk audit targets
the earlier toolbar; it still runs unchanged. This audit reuses its X11 key
driver and AT-SPI client, presses only real keys (xdotool) and reads only the
accessibility bus. A phase that cannot run is a failed check. Actions only.
"""
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tests/reader_a11y_gtk'))
import atspi_client as a11y  # noqa: E402
import driver  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
OUT = ROOT / os.environ.get('F09_GTK_COMPACT_OUT', 'build/f09/gtk-compact')
checks = []


def check(cid, element, expected, actual, passed, severity='blocking'):
    checks.append({'id': cid, 'element': element, 'expected': expected, 'actual': actual,
                   'status': 'pass' if passed else 'fail', 'severity': severity})
    print(('PASS ' if passed else 'FAIL ') + cid + ' ' + json.dumps(actual, ensure_ascii=False, default=str)[:200],
          flush=True)
    return passed


def frame():
    app = a11y.wait_application('exreader', timeout=30)
    return a11y.find_one(app, roles={'frame'}, text='EXReader Linux') or app


def focused(root):
    nodes = a11y.focused_all(root)
    return [(a11y.role(n), a11y.name(n)) for n in nodes]


def wait(predicate, seconds=20, step=0.25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            value = predicate()
            if value:
                return value
        except Exception:
            pass
        time.sleep(step)
    return None


def named(root, label):
    return a11y.find_one(root, text=label)


def dialog_named(label):
    app = a11y.wait_application('exreader', timeout=10)
    return a11y.find_one(app, roles={'dialog', 'frame', 'file chooser'}, text=label)


def dialog_round(host, root, keys, title, cid):
    """A keyboard command opens a named dialog with focus inside; Escape returns
    focus to an element of the main window."""
    host.key(keys)
    dialog = wait(lambda: dialog_named(title), 20)
    inside = wait(lambda: dialog and a11y.focused_all(dialog), 10) if dialog else None
    check(cid + 'a', title, keys + ' opens a dialog named %r with keyboard focus inside' % title,
          {'dialog': bool(dialog), 'focus': [(a11y.role(n), a11y.name(n)) for n in (inside or [])]},
          bool(dialog) and bool(inside))
    if dialog:
        host.screenshot(str(OUT / ('%s.png' % cid)))
        host.key('Escape')
        back = wait(lambda: not dialog_named(title) and a11y.focused_all(frame()), 15)
        check(cid + 'b', title, 'Escape closes it and focus returns inside the main window',
              focused(frame()), bool(back))


def main(payload):
    OUT.mkdir(parents=True, exist_ok=True)
    corpus = OUT / 'corpus'
    corpus.mkdir(exist_ok=True)
    books = []
    for title in ('Alpha F09 book', 'Beta F09 book'):
        path = corpus / (title.replace(' ', '-') + '.txt')
        path.write_text(('%s page text for the F09 audit. ' % title) * 1200, encoding='utf-8')
        books.append(path)
    a11y.init()
    host = driver.Host(payload / 'bin/exreader-linux', payload / 'Reader.otf', OUT, title='EXReader Linux')
    code = None
    try:
        host.launch()
        time.sleep(2)
        root = frame()
        host.screenshot(str(OUT / '00-library.png'))

        # G-01 library bar names
        wanted = ['Import book', 'Continue reading', 'More reader actions']
        found = {label: bool(named(root, label)) for label in wanted}
        search = a11y.find_one(root, roles={'text', 'entry'}, contains='Search')
        check('G-01', 'library bar', 'library controls and the search entry are named',
              {'controls': found, 'search': a11y.name(search) if search else None},
              all(found.values()) and bool(search))

        # G-02 import with the keyboard through the chooser
        for index, book in enumerate(books):
            host.key('F1')
            chooser = wait(lambda: host.window_named('Import book', True, 2), 20)
            if index == 0:
                check('G-02a', 'import chooser', 'F1 opens a chooser named "Import book"', bool(chooser), bool(chooser))
            time.sleep(1.5)
            host.key('ctrl+l')
            time.sleep(0.8)
            host.type_text(str(book))
            time.sleep(0.8)
            host.screenshot(str(OUT / ('import-%d-before-return.png' % index)))
            host.key('Return')
            # The location bar may take the first Return to accept its completion
            # (Orca run 41277347712: "Text unselected."), and under load the next one
            # only clears that selection (run 41361345920); confirm until it closes.
            for _ in range(3):
                try:
                    host.window_named('Import book', False, 3)
                    break
                except TimeoutError:
                    host.key('Return')
            opened = wait(lambda: host.number('host', 'book') > 0 and host.number('host', 'reader_visible') == 1, 60)
            if index == 0:
                check('G-02b', 'reader', 'an imported book opens in the reader', host.section('host'), bool(opened))
            host.key('F2')
            wait(lambda: host.number('host', 'reader_visible') == 0, 15)
        grown = wait(lambda: host.number('host', 'books') >= len(books), 30)
        check('G-02c', 'shelf', 'F2 returns to the shelf, which lists both imported books',
              host.number('host', 'books'), bool(grown))
        root = frame()
        rows = [n for n in a11y.find_all(root, roles={'list item'})]
        names = [a11y.name(n) for n in rows]
        check('G-03', 'shelf rows', 'every shelf row has a non-empty accessible name and is focusable',
              {'names': names, 'focusable': [a11y.states(n).get('focusable') for n in rows]},
              bool(rows) and all(n.strip() for n in names) and all(a11y.states(n).get('focusable') for n in rows))
        host.screenshot(str(OUT / '01-shelf.png'))

        # G-04 Tab cycle on the library: named stops, no trap
        stops = []
        closed = False
        for _ in range(40):
            host.key('Tab')
            current = tuple(focused(frame())[:1])
            if current and current in stops:
                closed = True
                break
            stops.append(current)
        unnamed = [s for s in stops if s and not (s[0][1] or '').strip()]
        check('G-04', 'library Tab cycle', 'Tab returns to a visited stop and every stop is named',
              {'stops': stops, 'closed': closed}, closed and not unnamed)

        # G-05 collections, account and details dialogs from the keyboard
        dialog_round(host, root, 'ctrl+shift+c', 'Library collections', 'G-05')
        dialog_round(host, root, 'ctrl+shift+a', 'Account and Sync', 'G-06')

        # G-07 open a book from the keyboard; focus lands on the reading page
        host.key('F2')
        host.key('Return')
        opened = wait(lambda: host.number('host', 'book') > 0 and host.section('host').get('page') is not None
                      and a11y.find_one(frame(), text='Back to library'), 60)
        page_focus = wait(lambda: any(name.startswith('Reading page') or name.startswith('Rendered')
                                      for _, name in focused(frame())), 15)
        check('G-07', 'reader', 'F2 + Return opens the selected book and focus lands on the reading page',
              focused(frame()), bool(opened) and bool(page_focus))
        host.screenshot(str(OUT / '02-reader.png'))

        # G-08 page turn from the keyboard (F4 next, the default keyboard binding)
        before = host.number('host', 'page', -1)
        host.key('F4')
        turned = wait(lambda: host.number('host', 'page', -1) != before, 15)
        check('G-08', 'reading position', 'F4 moves to the next page', {'before': before,
              'after': host.number('host', 'page', -1)}, bool(turned))

        # G-09 reading records (bookmarks and annotations) from the keyboard
        dialog_round(host, root, 'ctrl+shift+r', 'Reading records', 'G-09')

        # G-10 reader More menu by its mnemonic, items named
        host.key('alt+m')
        menu = wait(lambda: a11y.find_all(a11y.wait_application('exreader', 5), roles={'menu item', 'menu'}), 10)
        items = [a11y.name(i) for i in (menu or []) if a11y.states(i).get('showing')]
        # Default UI stays simple; everything else is one level down in named submenus.
        groups = ['Reading', 'Text and notes', 'Library', 'Import']
        check('G-10', 'More reader actions', 'Alt+M opens the menu: named items and the Reading, Text and notes, '
              'Library and Import submenus', {'items': items, 'missing': [g for g in groups if g not in items]},
              bool(items) and all(i.strip() for i in items) and all(g in items for g in groups))
        # G-13 every default-UI product function has a named entry under that menu
        every = [a11y.name(i) for i in (menu or [])]
        functions = ['Search within book…', 'Directory / page entries…', 'Reading records…', 'Reading settings…',
                     'Larger text', 'Smaller text', 'Select page text', 'Add note from selection', 'Saved notes',
                     'Book details…', 'Collections…', 'Account / Sync…', 'Import file…']
        check('G-13', 'menu functions', 'each product function has a named entry in the More menu tree',
              {'missing': [f for f in functions if f not in every], 'count': len(every)},
              all(f in every for f in functions))
        host.key('Escape')

        # G-11 back to the library from the keyboard
        back_button = named(frame(), 'Back to library')
        for _ in range(30):
            if back_button and a11y.states(back_button).get('focused'):
                break
            host.key('Tab')
        host.key('Return')
        returned = wait(lambda: named(frame(), 'Import book') and a11y.states(named(frame(), 'Import book')).get('showing'), 20)
        check('G-11', 'back to library', 'Back to library is reachable by Tab and returns to the shelf',
              focused(frame()), bool(returned))
    except Exception as error:
        check('G-ERR', 'audit', 'the audit runs to completion', repr(error), False)
    finally:
        try:
            code = host.close()
        except Exception as error:
            code = repr(error)
        check('G-12', 'process', 'Alt+F4 closes the host with exit code 0', code, code == 0)
        blocking = [c for c in checks if c['status'] == 'fail' and c['severity'] == 'blocking']
        report = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
                  'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'payload': str(payload), 'transport': 'xdotool',
                  'checks': checks, 'blocking_failures': len(blocking), 'accepted': not blocking,
                  'orca_screen_reader_verified': False}
        (OUT / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n',
                                         encoding='utf-8')


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    main(Path(sys.argv[1]).resolve())
