"""F09 Android keyboard: the shared-source host driven by hardware keys only.

Runs on the emulator after android_flow.py (Sample.epub on the shelf). Every
input is a key event (adb `input keyevent`: TAB, DPAD, ENTER, ESCAPE); focus
is read from the live UI Automator hierarchy (focused="true"). Checks: the
shelf Tab cycle has named stops and no trap; a book row is reached and Enter
opens the reader; the reader More menu is reached and opened by keyboard and
its "选择本页" entry runs; Escape/Back returns to the shelf with focus kept in
it. Writes build/f09/android-keyboard.json. Actions only.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f09'
PKG = 'org.exreader.host'
trace = []
checks = []


def adb(*args, check=True):
    return subprocess.run(['adb', *args], check=check, capture_output=True, text=True, encoding='utf-8',
                          errors='replace').stdout


def tree():
    adb('shell', 'uiautomator', 'dump', '/sdcard/f09k.xml')
    return ET.fromstring(adb('exec-out', 'cat', '/sdcard/f09k.xml'))


def focused(root=None):
    root = tree() if root is None else root
    node = next((n for n in root.iter('node') if n.get('focused') == 'true'), None)
    if node is None:
        return None
    rid = (node.get('resource-id') or '').split('/')[-1]
    name = node.get('text') or node.get('content-desc') or ''
    if not name:
        # A row or container is announced by the text it contains.
        name = ' '.join(t for t in (c.get('text') or c.get('content-desc') for c in node.iter('node')) if t)
    return {'id': rid, 'class': node.get('class'), 'name': name.strip()}


def key(code, note):
    adb('shell', 'input', 'keyevent', code)
    time.sleep(0.8)
    trace.append({'key': code, 'note': note, 'focus': focused()})
    return trace[-1]['focus']


def has(rid, root=None):
    root = tree() if root is None else root
    return any((n.get('resource-id') or '').endswith('/' + rid) for n in root.iter('node'))


def wait_for(rid, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if has(rid):
            return True
        time.sleep(0.7)
    return False


def check(cid, expected, actual, passed):
    checks.append({'id': cid, 'expected': expected, 'actual': actual, 'status': 'pass' if passed else 'fail'})


def main():
    result = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'transport': 'adb input keyevent'}
    try:
        adb('shell', 'am', 'force-stop', PKG)
        adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1')
        time.sleep(5)
        # The host may reopen the last book; Escape is the keyboard way back.
        if not wait_for('book_list', 10):
            key('KEYCODE_ESCAPE', 'leave the reopened book')
        check('K-00', 'the shelf is shown', None, wait_for('book_list', 30))

        # K-01 Tab cycle on the shelf: named stops, returns to a visited stop.
        stops, closed = [], False
        for _ in range(30):
            now = key('KEYCODE_TAB', 'shelf tab')
            ident = now and (now['id'], now['name'])
            if ident and ident in stops:
                closed = True
                break
            stops.append(ident)
        unnamed = [s for s in stops if not s or not s[1]]
        check('K-01', 'Tab moves through named shelf stops and cycles without a trap',
              {'stops': stops, 'closed': closed}, closed and not unnamed)

        # K-02 reach a book row by keyboard and open it with Enter.
        row = None
        for _ in range(30):
            now = focused()
            if now and 'Sample' in now['name'] and now['id'] != 'shelf_search':
                row = now
                break
            key('KEYCODE_TAB', 'seek book row')
        if row is None:
            # Into the list, the arrow keys move between rows.
            for _ in range(10):
                now = key('KEYCODE_DPAD_DOWN', 'row down')
                if now and 'Sample' in now['name']:
                    row = now
                    break
        if row:
            key('KEYCODE_ENTER', 'open book')
        opened = wait_for('reader_more', 40)
        check('K-02', 'a book row is reached by keyboard and Enter opens the reader', row, bool(row) and opened)

        # K-03 the reader More menu by keyboard; its 选择本页 entry runs.
        more = None
        for _ in range(25):
            now = focused()
            if now and now['id'] == 'reader_more':
                more = now
                break
            key('KEYCODE_TAB', 'seek reader More')
        menu_items, selected = [], False
        if more:
            key('KEYCODE_ENTER', 'open reader More')
            time.sleep(1)
            root = tree()
            menu_items = [n.get('text') for n in root.iter('node')
                          if n.get('resource-id') == 'android:id/title' and n.get('text')]
            for _ in range(12):
                now = focused()
                if now and now['name'].startswith('选择本页'):
                    key('KEYCODE_ENTER', 'run 选择本页')
                    selected = wait_for('selection_bar', 10)
                    break
                key('KEYCODE_DPAD_DOWN', 'menu down')
        check('K-03', 'Tab reaches reader More, Enter opens it, arrows reach 选择本页 and Enter selects the page',
              {'more': more, 'menu': menu_items}, bool(more) and selected)

        # K-04 Escape leaves selection and the reader; focus stays in the shelf.
        for _ in range(3):
            if wait_for('book_list', 2):
                break
            key('KEYCODE_ESCAPE', 'back')
        back = wait_for('book_list', 15)
        landing = focused()
        check('K-04', 'Escape returns to the shelf and keyboard focus is inside it', landing,
              back and bool(landing))
    except Exception as error:
        check('K-ERR', 'the lane runs to completion', repr(error), False)
    result['checks'] = checks
    result['trace'] = trace
    result['accepted'] = bool(checks) and all(c['status'] == 'pass' for c in checks)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'android-keyboard.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n',
                                               encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('accepted', 'checks')}, ensure_ascii=False)[:3000], flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    main()
