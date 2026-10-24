"""Actions-only multi-format and isolated live-cancellation Win32 checks."""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import traceback

from check_ui import SearchApp, U, send, set_text, text, M
from check_ui import BUTTON, QUERY, FIND, NEXT, HITS, OPEN, CANCEL, CLOSE, MESSAGE

REQUIRED = [
    'epub-original-imported', 'epub-four-hits-across-repeated-spine',
    'epub-search-keeps-progress-and-notes', 'epub-independent-found-selects-second-part',
    'epub-repeated-path-keeps-explicit-spine-unit', 'epub-no-hit-is-complete',
    'pdf-text-search-two-independent-pages', 'pdf-independent-found-selects-stable-page',
    'pdf-ambiguous-match-refuses-jump', 'cbz-image-only-text-search-is-unsupported',
    'book-switch-destroys-old-search-dialog', 'new-book-has-empty-query',
    'reflow-ambiguous-match-refuses-jump', 'changed-original-refuses-stale-hit',
    'restored-original-reopens-for-new-search', 'host-restart-discards-transient-query',
    'source-files-unchanged', 'search-does-not-create-product-history',
]
LIFECYCLE = ['review-observer-absent-from-product',
             'cancel-inside-real-f1-control-keeps-previous-batch',
             'late-cancel-discards-completed-unpublished-batch',
             'close-dialog-during-query-discards-late-result',
             'switch-book-during-query-discards-late-result',
             'close-host-during-query-joins-worker',
             'restart-after-live-query-keeps-original-and-history']


class ReviewSearchApp(SearchApp):
    def wait_idle(self):
        self.wait(lambda: self.q(14) == 0, timeout=90)


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.name == 'nt'
    p = argparse.ArgumentParser()
    for name in ('candidate', 'review', 'font', 'fixtures', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve();out.mkdir(parents=True, exist_ok=False)
    fixtures = a.fixtures.resolve()
    spec = importlib.util.spec_from_file_location('search_reading_state_fixtures',
        Path(__file__).resolve().parents[1] / 'reader_reading_state' / 'make_fixtures.py')
    generator = importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    cbz = out / 'Image only.cbz';generator.cbz(cbz)
    other = out / 'Other independent source.txt'
    other.write_text('A different book. Other target.\n' * 12, encoding='utf-8')
    files = [fixtures / 'book.epub', fixtures / 'pages.pdf', fixtures / 'book.txt', cbz, other]
    digests = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    checks = [];problems = [];app = None;phase = 'launch'
    report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  checks=checks, problems=problems, complete_product=False,
                  performance_accepted=False, screen_reader_accepted=False)

    def record(name, condition):
        assert condition, name
        assert name not in checks
        checks.append(name);print(json.dumps({'name': name, 'pass': True}), flush=True)

    def sql(q, values=(), product=False):
        db = Path(str(app.db) + '.product.sqlite') if product else app.db
        with sqlite3.connect(db) as c:
            return c.execute(q, values).fetchall()

    def state():
        return {t: sql('SELECT * FROM ' + t) for t in
                ('notes', 'epub_notes', 'fixed_notes', 'epub_progress', 'book_progress')} | {
                'positions': sql('SELECT id,position FROM books ORDER BY id')}

    def history():
        return tuple(sql('SELECT * FROM ' + t, product=True) for t in ('reader_revisions', 'reader_outbox'))

    def find_dialog():
        app.wait_idle();send(U.GetDlgItem(app.window, BUTTON), 0xF5)
        return app.dialog()

    def query(d, value):
        set_text(U.GetDlgItem(d, QUERY), value);send(U.GetDlgItem(d, FIND), 0xF5)
        app.wait(lambda: U.IsWindowEnabled(U.GetDlgItem(d, FIND)), timeout=90)
        app.wait_idle()
        count = send(U.GetDlgItem(d, HITS), 0x18B)
        report['last_search'] = {'query': value, 'count': count, 'message': text(U.GetDlgItem(d, MESSAGE))}
        return count

    def jump(d, row=0):
        send(U.GetDlgItem(d, HITS), 0x186, row);send(U.GetDlgItem(d, OPEN), 0xF5)
        app.wait(lambda: U.IsWindowEnabled(U.GetDlgItem(d, FIND)), timeout=90);app.wait_idle()
        return text(U.GetDlgItem(d, MESSAGE))

    def close_dialog(d):
        send(U.GetDlgItem(d, CLOSE), 0xF5);app.wait(lambda: not U.IsWindow(d));app.wait_idle()

    def import_book(f, expected_count):
        app.wait_idle();app.import_file(f)
        app.wait(lambda: send(app.control('books'), 0x18B) == expected_count);app.wait_idle()

    def launch(exe, profile, review=False, existing=False):
        result = (ReviewSearchApp if review else SearchApp)(exe.resolve(), a.font.resolve(), profile, existing=existing)
        result.wait_initial_shelf();result.wait_idle()
        return result

    def original_bytes():
        return sql('SELECT id,source FROM books ORDER BY id')

    try:
        app = launch(a.candidate, out / 'profile')
        record('review-observer-absent-from-product', app.q(105) == 0 and app.q(14) == 0)
        for index, f in enumerate(files, 1):
            phase = 'import-' + f.name;import_book(f, index)
        original = original_bytes();initial_history = history()
        record('epub-original-imported', any(hashlib.sha256(blob).hexdigest() == digests[str(files[0])] for _, blob in original))
        phase = 'epub';app.open('reader-search');app.wait_idle();d = find_dialog();before = state()
        record('epub-four-hits-across-repeated-spine', query(d, 'SEARCHTOKEN') == 4)
        record('epub-search-keeps-progress-and-notes', state() == before)
        assert query(d, 'unique-b-only') == 1
        message = jump(d)
        record('epub-independent-found-selects-second-part', '已独立核对' in message and
               sql('SELECT part,path FROM epub_progress') == [(1, 'b.xhtml')])
        assert query(d, 'Repeated spine') == 2
        message = jump(d, 1)
        record('epub-repeated-path-keeps-explicit-spine-unit', '已独立核对' in message and
               sql('SELECT part,path FROM epub_progress') == [(2, 'a.xhtml')])
        record('epub-no-hit-is-complete', query(d, 'ABSENT_EPUB_QUERY') == 0 and
               '没有匹配' in text(U.GetDlgItem(d, MESSAGE)) and not U.IsWindowEnabled(U.GetDlgItem(d, NEXT)))
        phase = 'switch-to-pdf';app.open('pages');app.wait_idle()
        record('book-switch-destroys-old-search-dialog', not U.IsWindow(d))
        d = find_dialog();record('new-book-has-empty-query', text(U.GetDlgItem(d, QUERY)) == '')
        record('pdf-text-search-two-independent-pages', query(d, 'Shared quote across pages.') == 2)
        message = jump(d, 1)
        pdf_id = sql('SELECT id FROM books WHERE source=?', (files[1].read_bytes(),))[0][0]
        record('pdf-independent-found-selects-stable-page', '已独立核对' in message and
               sql('SELECT position FROM books WHERE id=?', (pdf_id,)) == [(3,)])
        assert query(d, 'selection target') == 3
        before = state();message = jump(d)
        record('pdf-ambiguous-match-refuses-jump', '未跳转' in message and state() == before)
        close_dialog(d)
        phase = 'cbz';app.open('Image only');app.wait_idle();d = find_dialog();before = state()
        count = query(d, 'text');after = state()
        report['cbz_changed_state_tables'] = [key for key in before if before[key] != after[key]]
        record('cbz-image-only-text-search-is-unsupported', count == 0 and
               '图像页' in text(U.GetDlgItem(d, MESSAGE)) and '不支持文字查找' in text(U.GetDlgItem(d, MESSAGE)) and
               '没有匹配' not in text(U.GetDlgItem(d, MESSAGE)) and after == before)
        close_dialog(d)
        phase = 'reflow';app.open('book');app.wait_idle();d = find_dialog()
        assert query(d, 'AMBIGUOUS TARGET') == 2
        before = state();message = jump(d)
        record('reflow-ambiguous-match-refuses-jump', '未跳转' in message and state() == before)
        assert query(d, '终点') == 1
        book_id = sql('SELECT id FROM books WHERE source=?', (files[2].read_bytes(),))[0][0]
        saved = files[2].read_bytes();before = state()
        phase = 'source-change'
        sql('UPDATE books SET source=? WHERE id=?', (saved + b'\nchanged', book_id))
        try:
            message = jump(d)
            record('changed-original-refuses-stale-hit', '未跳转' in message and state() == before)
        finally:
            sql('UPDATE books SET source=? WHERE id=?', (saved, book_id))
        close_dialog(d);app.open('book');app.wait_idle();d = find_dialog()
        record('restored-original-reopens-for-new-search', query(d, '终点') == 1 and '已独立核对' in jump(d))
        phase = 'restart';app.close();assert app.process.returncode == 0
        app = launch(a.candidate, out / 'profile', existing=True);app.open('book');app.wait_idle();d = find_dialog()
        record('host-restart-discards-transient-query', text(U.GetDlgItem(d, QUERY)) == '' and send(U.GetDlgItem(d, HITS), 0x18B) == 0)
        close_dialog(d)
        record('source-files-unchanged', all(hashlib.sha256(f.read_bytes()).hexdigest() == digests[str(f)] for f in files) and original_bytes() == original)
        record('search-does-not-create-product-history', history() == initial_history)
        app.close();assert app.process.returncode == 0
        phase = 'live-query';app = launch(a.review, out / 'review', review=True)
        import_book(files[2], 1);import_book(other, 2);app.open('book');app.wait_idle()
        review_original = original_bytes();review_history = history();d = find_dialog()
        assert query(d, 'repeat-phrase') == 4
        before = state()
        # Resume changes only the requested batch; existing four rows remain on cancellation.
        for gate, name in ((4, 'cancel-inside-real-f1-control-keeps-previous-batch'),
                           (5, 'late-cancel-discards-completed-unpublished-batch')):
            phase = name
            # Query the same text again without EN_CHANGE (which intentionally resets results).
            app.gate(gate);send(U.GetDlgItem(d, FIND), 0xF5);app.stage(gate)
            assert U.IsWindowEnabled(U.GetDlgItem(d, CANCEL))
            send(U.GetDlgItem(d, CANCEL), 0xF5);app.release();app.wait_idle()
            record(name, '已取消' in text(U.GetDlgItem(d, MESSAGE)) and
                   send(U.GetDlgItem(d, HITS), 0x18B) == 4 and state() == before and history() == review_history)
        phase = 'close-dialog-in-flight';app.gate(5);send(U.GetDlgItem(d, FIND), 0xF5);app.stage(5)
        send(U.GetDlgItem(d, CLOSE), 0xF5);app.release();app.wait_idle()
        record('close-dialog-during-query-discards-late-result', not U.IsWindow(d) and state() == before)
        d = find_dialog();assert query(d, 'repeat-phrase') == 4
        phase = 'switch-in-flight';app.gate(5);send(U.GetDlgItem(d, FIND), 0xF5);app.stage(5)
        app.open('Other independent source', wait=False);app.release();app.wait_idle()
        record('switch-book-during-query-discards-late-result', not U.IsWindow(d) and
               app.q(10) == sql('SELECT id FROM books WHERE source=?', (other.read_bytes(),))[0][0])
        d = find_dialog();assert query(d, 'Other target') == 12
        phase = 'close-host-in-flight';app.gate(5);send(U.GetDlgItem(d, FIND), 0xF5);app.stage(5)
        U.PostMessageW(app.window, 0x10, 0, 0)
        app.process.wait(timeout=20);app.log.close()
        record('close-host-during-query-joins-worker', app.process.returncode == 0)
        phase = 'reopen-after-live-query';app = launch(a.review, out / 'review', review=True, existing=True)
        app.open('book');app.wait_idle();d = find_dialog()
        record('restart-after-live-query-keeps-original-and-history', query(d, 'repeat-phrase') == 4 and
               original_bytes() == review_original and history() == review_history)
        close_dialog(d)
        assert set(checks) == set(REQUIRED + LIFECYCLE) and len(checks) == len(REQUIRED + LIFECYCLE)
        report['accepted'] = True
    except Exception as e:
        problems.append(phase + ': ' + type(e).__name__ + ': ' + str(e));traceback.print_exc()
        if app and app.process.poll() is None:
            report['native_status'] = app.status()
    finally:
        if app:
            app.close()
        report['count'] = len(checks)
        report['consumer_sha256'] = hashlib.sha256(a.candidate.read_bytes()).hexdigest()
        report['review_sha256'] = hashlib.sha256(a.review.read_bytes()).hexdigest()
        report['inputs'] = digests
        (out / 'formats-and-lifecycle.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True), flush=True)
    if not report['accepted']:
        raise SystemExit('Native Windows search formats/lifecycle checks failed')


if __name__ == '__main__':
    main()
