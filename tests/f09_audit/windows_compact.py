"""F09 Windows: keyboard and UI Automation audit of the compact product host.

The shared-source Windows host (F06 recipe) is the compact shell: a menu bar
(书库/阅读/视图/设置), search, 继续阅读/打开/导入, the shelf list and a reading
view. The retained tests/reader_a11y_windows audit targets the earlier full
panel (an import path field), so it cannot evaluate this shell; it still runs
unchanged. This audit drives the compact shell only with real keyboard input
(uiautomation.SendKeys -> SendInput) and reads it only through UI Automation.

Each check records element, expected, actual and evidence. A phase that cannot
run is recorded as a failed check, never skipped. Actions only.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import uiautomation as auto

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f09/windows-compact'
checks = []
trace = []


def check(cid, element, expected, actual, passed, severity='blocking'):
    checks.append({'id': cid, 'element': element, 'expected': expected, 'actual': actual,
                   'status': 'pass' if passed else 'fail', 'severity': severity})
    print(('PASS ' if passed else 'FAIL ') + cid + ' ' + str(actual)[:160], flush=True)
    return passed


def keys(text, note):
    trace.append({'t': round(time.time(), 3), 'keys': text, 'note': note, 'focus': focused_name()})
    auto.SendKeys(text, interval=0.05, waitTime=0.4)


def focused_name():
    try:
        c = auto.GetFocusedControl()
        return (c.ControlTypeName, c.Name, c.ClassName) if c else None
    except Exception:
        return None


def shot(window, name):
    try:
        window.CaptureToImage(str(OUT / ('%s.png' % name)))
    except Exception as error:
        trace.append({'shot_failed': name, 'error': str(error)})


def wait(predicate, seconds=30, step=0.3):
    end = time.time() + seconds
    while time.time() < end:
        try:
            value = predicate()
            if value:
                return value
        except Exception:
            pass
        time.sleep(step)
    return None


def list_items(window):
    lst = window.ListControl(searchDepth=3)
    if not lst.Exists(3):
        return None, []
    return lst, [i for i in lst.GetChildren() if i.ControlTypeName == 'ListItemControl']


def tab_cycle(window, limit=40):
    """Real Tab presses from the current focus until a stop repeats."""
    stops = []
    for _ in range(limit):
        keys('{Tab}', 'tab cycle')
        f = auto.GetFocusedControl()
        key = (f.ControlTypeName, f.Name, f.AutomationId) if f else None
        if key in stops:
            return stops, True
        stops.append(key)
    return stops, False


def main(exe, book):
    OUT.mkdir(parents=True, exist_ok=True)
    data = OUT / 'host-data'
    data.mkdir(exist_ok=True)
    process = subprocess.Popen([str(exe), '--data', str(data)], cwd=str(Path(exe).parent))
    window = None
    try:
        window = auto.WindowControl(searchDepth=1, Name='EXReader')
        if not window.Exists(60):
            check('W-00', 'main window', 'a top-level window named EXReader', 'absent', False)
            return
        window.SetActive()
        time.sleep(2)
        shot(window, '00-empty-shelf')

        # W-01 menu bar names and access keys
        bar = window.MenuBarControl(searchDepth=2)
        names = [m.Name for m in bar.GetChildren()] if bar.Exists(3) else []
        check('W-01', 'menu bar', '书库/阅读/视图 present, each with an access key',
              names, all(any(n.startswith(label) and '(' in n for n in names) for label in ('书库', '阅读', '视图')))

        # W-02 empty state guides the actual import path
        status = wait(lambda: next((t.Name for t in window.GetChildren()
                                    if t.ControlTypeName == 'TextControl' and '书架为空' in t.Name), None), 10)
        check('W-02', 'status text', 'empty-shelf guidance names Ctrl+O / the Import button, not a path field',
              status, bool(status) and 'Ctrl+O' in status and '输入文件路径' not in status)

        # W-03 keyboard import through the system file chooser
        keys('{Ctrl}o', 'import')
        dialog = wait(lambda: auto.WindowControl(searchDepth=2, ClassName='#32770').Exists(0) and
                      auto.WindowControl(searchDepth=2, ClassName='#32770'), 20)
        check('W-03a', 'import dialog', 'Ctrl+O opens the system file chooser', bool(dialog), bool(dialog))
        if dialog:
            shot(dialog, '01-import-dialog')
            keys('{Esc}', 'cancel chooser')
            back = wait(lambda: auto.GetFocusedControl() and
                        auto.GetFocusedControl().GetTopLevelControl().Name == 'EXReader', 10)
            check('W-03b', 'focus after cancel', 'Escape closes the chooser, focus back in EXReader',
                  focused_name(), bool(back))
            keys('{Ctrl}o', 'import again')
            dialog = wait(lambda: auto.WindowControl(searchDepth=2, ClassName='#32770').Exists(0) and
                          auto.WindowControl(searchDepth=2, ClassName='#32770'), 20)
            if dialog:
                auto.SetClipboardText(str(book))
                keys('{Ctrl}v', 'paste path')
                keys('{Enter}', 'confirm path')
        lst, rows = None, []
        found = wait(lambda: list_items(window)[1], 90)
        lst, rows = list_items(window)
        check('W-03c', 'shelf list', 'the imported book becomes a named shelf row',
              [r.Name for r in rows], bool(rows) and all(r.Name.strip() for r in rows))
        shot(window, '02-shelf-loaded')

        # W-04 Tab cycle: every enabled stop named, no trap
        stops, closed = tab_cycle(window)
        unnamed = [s for s in stops if s and not (s[1] or '').strip()]
        check('W-04', 'shelf Tab cycle', 'Tab returns to a visited stop; every stop has a name',
              {'stops': stops, 'closed': closed}, closed and not unnamed)

        # W-05 open the book from the keyboard
        if lst and lst.Exists(1):
            lst.SetFocus()
            keys('{Home}{Enter}', 'open selected book')
        page = wait(lambda: window.Control(searchDepth=3, ClassName='EXReaderPage').Exists(0) and
                    window.Control(searchDepth=3, ClassName='EXReaderPage'), 60)
        check('W-05', 'reading view', 'Enter on a shelf row opens the reading view', bool(page), bool(page))
        time.sleep(2)
        shot(window, '03-reader')

        # W-06 the page is readable through UI Automation
        readable = None
        if page:
            for getter in ('GetTextPattern', 'GetValuePattern', 'GetLegacyIAccessiblePattern'):
                try:
                    pattern = getattr(page, getter)()
                    text = (pattern.DocumentRange.GetText(500) if getter == 'GetTextPattern'
                            else getattr(pattern, 'Value', '') or '')
                    if text and text.strip():
                        readable = (getter, text[:120])
                        break
                except Exception:
                    continue
        check('W-06', 'EXReaderPage', 'page text readable through a Text or Value pattern',
              readable or {'name': page.Name if page else None}, bool(readable))

        # W-07 page turn from the keyboard changes the announced position
        label_before = page.Name if page else None
        keys('{PageDown}', 'next page')
        changed = wait(lambda: page and page.Name != label_before, 15)
        check('W-07', 'reading position', 'PageDown moves to the next page and the name reflects it',
              {'before': label_before, 'after': page.Name if page else None}, bool(changed))

        # W-08 reading menu from the keyboard: font size changes
        keys('{Alt}r', 'reading menu')
        menu = wait(lambda: auto.MenuControl(searchDepth=2).Exists(0) and auto.MenuControl(searchDepth=2), 10)
        items = [i.Name for i in menu.GetChildren()] if menu else []
        check('W-08a', 'reading menu', 'Alt+R opens the reading menu with named items',
              items, bool(items) and all(n.strip() for n in items))
        keys('{Esc}{Esc}', 'close menu')

        # W-09 annotation from the keyboard: select page, add a note
        keys('{Ctrl}a', 'select page')
        keys('{Alt}r', 'reading menu')
        time.sleep(0.6)
        menu = auto.MenuControl(searchDepth=2)
        entry = None
        if menu.Exists(3):
            entry = next((i for i in menu.GetChildren() if i.Name.startswith('标注编辑')), None)
        if entry:
            # Reach the item from the keyboard: arrow down to it and press Enter.
            names = [i.Name for i in menu.GetChildren()]
            index = names.index(entry.Name)
            keys('{Down}' * (index + 1) + '{Enter}', 'annotation editor')
        note = wait(lambda: auto.GetFocusedControl() and auto.GetFocusedControl().ControlTypeName == 'EditControl'
                    and auto.GetFocusedControl(), 15)
        check('W-09a', 'annotation editor', '标注编辑 puts focus in a named comment field',
              focused_name(), bool(note) and bool((note.Name or '').strip()))
        if note:
            keys('f09 keyboard note', 'type note')
            keys('{Alt}t', 'add note (access key)')
        notes = wait(lambda: next((l for l in window.GetChildren() if l.ControlTypeName == 'ListControl'
                                   and l.Name.startswith('标注')), None), 15)
        rows = [i.Name for i in notes.GetChildren()] if notes else []
        check('W-09b', 'annotation list', 'the saved note is listed with its text',
              rows, any('f09 keyboard note' in r for r in rows))
        shot(window, '04-annotation')

        # W-10 back to the shelf from the keyboard, focus lands on the shelf
        keys('{Alt}{Left}', 'back to shelf')
        landed = wait(lambda: auto.GetFocusedControl() and auto.GetFocusedControl().ControlTypeName in
                      ('ListControl', 'ListItemControl'), 15)
        check('W-10', 'focus after Alt+Left', 'focus returns to the shelf list', focused_name(), bool(landed))
        shot(window, '05-back-to-shelf')
    finally:
        try:
            if window and window.Exists(1):
                window.SetActive()
                keys('{Alt}{F4}', 'close')
            code = process.wait(30)
        except Exception:
            process.kill()
            code = None
        check('W-11', 'process', 'Alt+F4 closes the host with exit code 0', code, code == 0)
        blocking = [c for c in checks if c['status'] == 'fail' and c['severity'] == 'blocking']
        report = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
                  'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'host': str(exe), 'transport': 'SendInput',
                  'checks': checks, 'blocking_failures': len(blocking), 'accepted': not blocking,
                  'screen_reader_verified': False}
        (OUT / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        (OUT / 'key-trace.json').write_text(json.dumps(trace, indent=1, ensure_ascii=False, default=str) + '\n',
                                            encoding='utf-8')


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    main(Path(sys.argv[1]), Path(sys.argv[2]))
