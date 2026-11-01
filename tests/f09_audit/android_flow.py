"""F09 Android: annotation reached without a precise text touch.

Runs on the emulator after the retained audit (which leaves Sample.epub
imported). Every step is a real input event (adb `input tap`/`input text`) on a
control found in the live UI Automator hierarchy; no internal API is called.
Path: open the book from the shelf, reader More -> "选择本页", the selection bar
appears, Annotate, type a comment, save, the notes count reads (1), the notes
panel lists the comment. Writes build/f09/android-flow.json. Actions only.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f09'
PKG = 'org.exreader.host'
steps = []


def adb(*args, check=True):
    return subprocess.run(['adb', *args], check=check, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout


def tree():
    adb('shell', 'uiautomator', 'dump', '/sdcard/f09.xml')
    return ET.fromstring(adb('exec-out', 'cat', '/sdcard/f09.xml'))


def find(node, rid=None, text=None):
    for n in node.iter('node'):
        if rid and n.get('resource-id') == PKG + ':id/' + rid and n.get('enabled') == 'true':
            return n
        if text and (n.get('text') == text or n.get('content-desc') == text):
            return n
    return None


def wait(rid=None, text=None, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        n = find(tree(), rid, text)
        if n is not None:
            return n
        time.sleep(0.7)
    return None


def tap(n, label):
    left, top, right, bottom = map(int, re.findall(r'\d+', n.get('bounds')))
    adb('shell', 'input', 'tap', str((left + right) // 2), str((top + bottom) // 2))
    steps.append('tap ' + label)
    time.sleep(1.0)


def step(rid=None, text=None, label=None):
    n = wait(rid, text)
    if n is None:
        raise RuntimeError('missing ' + (label or rid or text))
    tap(n, label or rid or text)
    return n


def main():
    result = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'passed': False}
    try:
        adb('shell', 'am', 'force-stop', PKG)
        adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1')
        time.sleep(4)
        shelf = wait('book_list', seconds=40)
        if shelf is None:
            raise RuntimeError('shelf did not appear')
        # ListView rows are plain text views: the list handles their clicks, so
        # they are not marked clickable themselves.
        rows = [n for n in shelf.iter('node') if n is not shelf and n.get('bounds')]
        if not rows:
            raise RuntimeError('no book on the shelf')
        tap(rows[0], 'first book')
        if wait('reader_more', seconds=40) is None:
            raise RuntimeError('reader did not open')
        time.sleep(2)
        step('reader_more', label='reader More')
        step(text='选择本页', label='选择本页')
        bar = wait('selection_bar', seconds=10)
        result['selection_bar_shown'] = bar is not None
        if bar is None:
            raise RuntimeError('selection bar did not appear after 选择本页')
        step('annotate_button', label='Annotate')
        field = wait(text=None, rid='note_comment', seconds=10)
        if field is None:
            edits = [n for n in tree().iter('node') if n.get('class') == 'android.widget.EditText']
            field = edits[0] if edits else None
        if field is None:
            raise RuntimeError('annotation comment field missing')
        tap(field, 'comment field')
        adb('shell', 'input', 'text', 'f09%snote')
        steps.append('type comment')
        time.sleep(0.8)
        root = tree()
        save = None
        for n in root.iter('node'):
            if n.get('class') == 'android.widget.Button' and n.get('text', '').lower() in ('save', 'ok', '保存', '确定', 'add'):
                save = n
        if save is None:
            raise RuntimeError('annotation dialog has no save button')
        tap(save, 'save annotation')
        notes = wait('notes_button', seconds=15)
        result['notes_label'] = notes.get('text') if notes is not None else None
        if notes is None or '(1)' not in notes.get('text', ''):
            raise RuntimeError('notes count did not become (1): %r' % result['notes_label'])
        tap(notes, 'notes')
        listed = wait(text='f09 note', seconds=10)
        if listed is None:
            listed = next((n for n in tree().iter('node') if 'f09 note' in (n.get('text') or '')), None)
        result['note_listed'] = listed is not None
        if listed is None:
            raise RuntimeError('saved note is not listed')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
    result['steps'] = steps
    try:
        adb('shell', 'screencap', '-p', '/sdcard/f09-flow.png')
        (OUT / 'android-flow.png').write_bytes(subprocess.run(['adb', 'exec-out', 'cat', '/sdcard/f09-flow.png'],
                                                             capture_output=True).stdout)
        (OUT / 'android-flow-last.xml').write_text(adb('exec-out', 'cat', '/sdcard/f09.xml', check=False), encoding='utf-8')
    except Exception:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'android-flow.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    main()
