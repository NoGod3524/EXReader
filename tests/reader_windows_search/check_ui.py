"""Actions-only initial native UI checks. Cancellation/lifecycle grants remain pending."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows_host'))
import check_metadata_ui as M
from check_metadata_ui import U, ENUM, send, set_text, text

BUTTON, QUERY, FIND, NEXT, HITS, OPEN, CANCEL, CLOSE, MESSAGE = range(170, 179)
REQUIRED = ['native-secondary-entry', 'query-has-no-sdk-local-row-id', 'exactly-32-results',
            'empty-final-batch-preserves-results', 'first-miss-is-empty', 'unicode-query',
            'utf8-query-limit', 'new-query-restarts-cursor', 'search-does-not-write-notes-or-history',
            'search-does-not-move-reading-progress', 'independently-resolved-jump-moves-progress',
            'closed-dialog-is-destroyed', 'original-bytes-unchanged']


class SearchApp(M.MetadataApp):
    def dialog(self):
        def find():
            windows = []
            @ENUM
            def visit(window, unused):
                pid = W.DWORD();U.GetWindowThreadProcessId(window, C.byref(pid))
                if pid.value == self.process.pid and U.IsWindowVisible(window) and U.GetDlgItem(window, QUERY):
                    windows.append(window)
                return True
            U.EnumWindows(visit, 0)
            assert len(windows) <= 1
            return windows[0] if windows else None
        return self.wait(find)


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.name == 'nt'
    parser = argparse.ArgumentParser()
    for name in ('candidate', 'font', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    source = output / 'Native search sample.txt'
    original = ''.join('paragraph%03d ' % i + ('filler text ' * 120) + ' BATCHHIT %03d\n' % i for i in range(32))
    original += '尾声中文🙂仅一次。 TARGET_AT_END\n'
    source.write_text(original, encoding='utf-8')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    app = None;checks = [];problems = []
    report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], checks=checks, problems=problems,
                  scope='initial Win32 TXT native search controls only', complete_product=False,
                  cancellation_accepted=False, epub_accepted=False, pdf_accepted=False, performance_accepted=False)
    def record(name, condition):
        assert condition, name
        assert name not in checks
        checks.append(name);print(json.dumps({'name': name, 'pass': True}), flush=True)
    def snapshot():
        with sqlite3.connect(app.db) as db:
            progress = db.execute('SELECT position FROM books').fetchall()
            notes = db.execute('SELECT * FROM notes').fetchall()
        product = Path(str(app.db) + '.product.sqlite')
        with sqlite3.connect(product) as db:
            revisions = db.execute('SELECT * FROM reader_revisions').fetchall()
            outbox = db.execute('SELECT * FROM reader_outbox').fetchall()
        return progress, notes, revisions, outbox
    def query(dialog, value):
        set_text(U.GetDlgItem(dialog, QUERY), value)
        send(U.GetDlgItem(dialog, FIND), 0xF5)
        app.wait(lambda: U.IsWindowEnabled(U.GetDlgItem(dialog, FIND)), timeout=90)
        return send(U.GetDlgItem(dialog, HITS), 0x18B)
    phase = 'launch'
    try:
        app = SearchApp(args.candidate.resolve(), args.font.resolve(), output / 'profile')
        phase = 'import'
        app.import_file(source)
        phase = 'wait-imported-row'
        app.wait(lambda: send(app.control('books'), 0x18B) == 1);app.wait_idle()
        phase = 'open-imported-book'
        app.open('Native search sample');app.wait_idle()
        phase = 'snapshot-before-search'
        before = snapshot()
        record('native-secondary-entry', bool(U.GetDlgItem(app.window, BUTTON)))
        send(U.GetDlgItem(app.window, BUTTON), 0xF5);dialog = app.dialog()
        record('query-has-no-sdk-local-row-id', text(U.GetDlgItem(dialog, QUERY)) == '')
        record('exactly-32-results', query(dialog, 'BATCHHIT') == 32 and U.IsWindowEnabled(U.GetDlgItem(dialog, NEXT)))
        send(U.GetDlgItem(dialog, NEXT), 0xF5)
        app.wait(lambda: U.IsWindowEnabled(U.GetDlgItem(dialog, FIND)))
        record('empty-final-batch-preserves-results', send(U.GetDlgItem(dialog, HITS), 0x18B) == 32 and
               not U.IsWindowEnabled(U.GetDlgItem(dialog, NEXT)) and '已查找完毕' in text(U.GetDlgItem(dialog, MESSAGE)))
        record('first-miss-is-empty', query(dialog, 'UNSEEN_QUERY') == 0 and '没有匹配' in text(U.GetDlgItem(dialog, MESSAGE)))
        record('unicode-query', query(dialog, '中文🙂') == 1)
        record('utf8-query-limit', query(dialog, '汉' * 2048) == 0 and '4096' in text(U.GetDlgItem(dialog, MESSAGE)))
        record('new-query-restarts-cursor', query(dialog, 'TARGET_AT_END') == 1)
        after = snapshot()
        record('search-does-not-write-notes-or-history', before[1:] == after[1:])
        record('search-does-not-move-reading-progress', before[0] == after[0])
        M.screenshot(dialog, output / 'search-native.bmp')
        send(U.GetDlgItem(dialog, OPEN), 0xF5)
        app.wait(lambda: U.IsWindowEnabled(U.GetDlgItem(dialog, FIND)), timeout=90);app.wait_idle()
        record('independently-resolved-jump-moves-progress', '已独立核对' in text(U.GetDlgItem(dialog, MESSAGE)) and snapshot()[0] != before[0])
        send(U.GetDlgItem(dialog, CLOSE), 0xF5)
        app.wait(lambda: not U.IsWindow(dialog));record('closed-dialog-is-destroyed', not U.IsWindow(dialog))
        record('original-bytes-unchanged', hashlib.sha256(source.read_bytes()).hexdigest() == digest)
        assert set(checks) == set(REQUIRED) and len(checks) == len(REQUIRED)
        report['accepted'] = True
    except Exception as error:
        problems.append(phase + ': ' + type(error).__name__ + ': ' + str(error))
        traceback.print_exc()
        if app:
            report['native_status'] = app.status()
            report['import_path'] = text(app.control('path'))
            report['shelf_rows'] = send(app.control('books'), 0x18B)
            print(json.dumps({'native_status': report['native_status'],
                              'import_path': report['import_path'],
                              'shelf_rows': report['shelf_rows']}, ensure_ascii=True), flush=True)
    finally:
        if app:
            app.close()
        report['count'] = len(checks)
        report['consumer_sha256'] = hashlib.sha256(args.candidate.read_bytes()).hexdigest()
        (output / 'search-ui.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True), flush=True)
    if not report['accepted']:
        raise SystemExit('Native search UI initial checks failed')


if __name__ == '__main__':
    main()
