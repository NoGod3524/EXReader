"""Actions-only actual SendInput and native UI Automation search checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback

from check_ui import SearchApp, U, send, text, M
from check_ui import QUERY, FIND, NEXT, HITS, OPEN, CANCEL, CLOSE, MESSAGE
from check_formats import ReviewSearchApp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_windows_account'))
import check_a11y_ui as A

REQUIRED = ['ctrl-f-opens-native-search', 'initial-focus-is-named-query',
            'native-query-value-pattern', 'enter-searches-focused-query',
            'results-expose-selection-items', 'completed-next-and-cancel-disabled',
            'all-actions-have-native-accessible-names', 'tab-reaches-every-enabled-action',
            'shift-tab-returns-to-previous-control', 'uia-select-and-invoke-locate',
            'escape-closes-and-returns-reading-focus', 'reopen-clears-transient-query',
            'empty-enter-refuses-query', 'real-escape-cancels-live-query',
            'second-escape-closes-after-cancel', 'keyboard-does-not-write-notes-or-history']


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    p = argparse.ArgumentParser()
    for name in ('candidate', 'review', 'font', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args();out = args.output.resolve();out.mkdir(parents=True, exist_ok=False)
    source = out / 'Keyboard search sample.txt'
    source.write_text('First unique context. KEYTOKEN first.\n' + 'reading filler\n' * 220 +
                      'Second unique context. KEYTOKEN second.\n' + 'other filler\n' * 220 +
                      'Last unique context. KEYTOKEN final.\n', encoding='utf-8')
    checks = [];problems = [];app = None;phase = 'launch'
    report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], checks=checks, problems=problems,
                  transport='SendInput+UIAutomation', screen_reader_accepted=False, complete_product=False)

    def record(name, condition):
        assert condition, name
        assert name not in checks
        checks.append(name);print(json.dumps({'name': name, 'pass': True}), flush=True)

    def element(hwnd):
        return A.auto.ControlFromHandle(hwnd)

    def foreground(hwnd):
        def ready():
            A.USER32.BringWindowToTop(hwnd);A.USER32.SetForegroundWindow(hwnd)
            return A.USER32.GetForegroundWindow() == hwnd
        app.wait(ready, timeout=10)

    def setup(exe, profile, review=False):
        nonlocal app
        app = (ReviewSearchApp if review else SearchApp)(exe.resolve(), args.font.resolve(), profile)
        app.wait_initial_shelf();app.wait_idle();app.import_file(source)
        app.wait(lambda: send(app.control('books'), 0x18B) == 1);app.wait_idle()
        app.open('Keyboard search sample');app.wait_idle();foreground(app.window)

    def immutable():
        with sqlite3.connect(app.db) as db:
            notes = tuple(db.execute('SELECT * FROM ' + t).fetchall() for t in ('notes', 'epub_notes', 'fixed_notes'))
        with sqlite3.connect(str(app.db) + '.product.sqlite') as db:
            history = tuple(db.execute('SELECT * FROM ' + t).fetchall() for t in ('reader_revisions', 'reader_outbox'))
        return notes, history

    try:
        setup(args.candidate, out / 'profile');before = immutable()
        phase = 'ctrl-f';A.tap(ord('F'), (A.VK_CONTROL,));d = app.dialog()
        record('ctrl-f-opens-native-search', bool(d) and U.IsWindowVisible(d))
        q = U.GetDlgItem(d, QUERY);app.wait(lambda: A.focus_of(app.process.pid) == q)
        query = element(q)
        record('initial-focus-is-named-query', '查找文字' in (query.Name or '') and query.IsKeyboardFocusable)
        query.GetValuePattern().SetValue('KEYTOKEN')
        record('native-query-value-pattern', query.GetValuePattern().Value == 'KEYTOKEN')
        phase = 'keyboard-search';A.tap(0x0D)
        app.wait(lambda: send(U.GetDlgItem(d, HITS), 0x18B) == 3 and U.IsWindowEnabled(U.GetDlgItem(d, FIND)))
        app.wait_idle()
        record('enter-searches-focused-query', '已查找完毕' in text(U.GetDlgItem(d, MESSAGE)))
        rows = element(U.GetDlgItem(d, HITS));items = rows.GetChildren()
        record('results-expose-selection-items', '书内查找结果' in (rows.Name or '') and len(items) == 3 and
               all(item.Name and item.GetSelectionItemPattern() for item in items))
        record('completed-next-and-cancel-disabled', not element(U.GetDlgItem(d, NEXT)).IsEnabled and
               not element(U.GetDlgItem(d, CANCEL)).IsEnabled)
        names = {identifier: element(U.GetDlgItem(d, identifier)).Name for identifier in
                 (FIND, NEXT, OPEN, CANCEL, CLOSE)}
        record('all-actions-have-native-accessible-names', all(names.values()))
        report['accessible_names'] = {str(k): v for k, v in names.items()}
        query.SetFocus();app.wait(lambda: A.focus_of(app.process.pid) == q)
        phase = 'tab-cycle';visited = []
        for identifier in (FIND, HITS, OPEN, CLOSE, QUERY):
            A.tap(A.VK_TAB);expected = U.GetDlgItem(d, identifier)
            app.wait(lambda: A.focus_of(app.process.pid) == expected)
            visited.append(identifier)
        record('tab-reaches-every-enabled-action', visited == [FIND, HITS, OPEN, CLOSE, QUERY])
        A.tap(A.VK_TAB, (A.VK_SHIFT,));app.wait(lambda: A.focus_of(app.process.pid) == U.GetDlgItem(d, CLOSE))
        record('shift-tab-returns-to-previous-control', A.focus_of(app.process.pid) == U.GetDlgItem(d, CLOSE))
        phase = 'uia-locate';items[-1].GetSelectionItemPattern().Select()
        element(U.GetDlgItem(d, OPEN)).GetInvokePattern().Invoke()
        app.wait(lambda: '已独立核对' in text(U.GetDlgItem(d, MESSAGE)));app.wait_idle()
        record('uia-select-and-invoke-locate', send(U.GetDlgItem(d, HITS), 0x188) == 2)
        M.screenshot(d, out / 'search-accessible.bmp')
        phase = 'escape';A.tap(A.VK_ESCAPE);app.wait(lambda: not U.IsWindow(d))
        app.wait(lambda: A.focus_of(app.process.pid) == app.control('page'))
        record('escape-closes-and-returns-reading-focus', A.focus_of(app.process.pid) == app.control('page'))
        A.tap(ord('F'), (A.VK_CONTROL,));d = app.dialog()
        record('reopen-clears-transient-query', text(U.GetDlgItem(d, QUERY)) == '' and send(U.GetDlgItem(d, HITS), 0x18B) == 0)
        A.tap(0x0D)
        app.wait(lambda: '4096' in text(U.GetDlgItem(d, MESSAGE)))
        record('empty-enter-refuses-query', send(U.GetDlgItem(d, HITS), 0x18B) == 0)
        A.tap(A.VK_ESCAPE);app.wait(lambda: not U.IsWindow(d))
        record('keyboard-does-not-write-notes-or-history', immutable() == before)
        app.close();assert app.process.returncode == 0
        phase = 'review-live-escape';setup(args.review, out / 'review', review=True)
        A.tap(ord('F'), (A.VK_CONTROL,));d = app.dialog()
        element(U.GetDlgItem(d, QUERY)).GetValuePattern().SetValue('KEYTOKEN')
        app.gate(4);A.tap(0x0D);app.stage(4)
        foreground(d);A.tap(A.VK_ESCAPE);app.release();app.wait_idle()
        record('real-escape-cancels-live-query', U.IsWindow(d) and '已取消' in text(U.GetDlgItem(d, MESSAGE)))
        A.tap(A.VK_ESCAPE);app.wait(lambda: not U.IsWindow(d))
        record('second-escape-closes-after-cancel', not U.IsWindow(d))
        assert set(checks) == set(REQUIRED) and len(checks) == len(REQUIRED)
        report['accepted'] = True
    except Exception as e:
        problems.append(phase + ': ' + type(e).__name__ + ': ' + str(e));traceback.print_exc()
    finally:
        if app:
            app.close()
        report['count'] = len(checks)
        report['consumer_sha256'] = hashlib.sha256(args.candidate.read_bytes()).hexdigest()
        report['review_sha256'] = hashlib.sha256(args.review.read_bytes()).hexdigest()
        (out / 'keyboard-uia.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True), flush=True)
    if not report['accepted']:
        raise SystemExit('Native search keyboard/UI Automation checks failed')


if __name__ == '__main__':
    main()
