"""Actions-only native acceptance for product TXT reading positions.

The real Win32 host (EXReaderProduct.exe) is driven through its own controls and
UI Automation: a 16,792,975-byte product original, page turns, close and restart,
a font-size relayout, a second book identity, a refused write while the product
database is write-locked, and the existing SDK book path. Nothing here weakens an
assertion: every step either produces the declared observation or reports a
failure with the host status text and the retained record.
"""
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
spec = importlib.util.spec_from_file_location("compact_ui", ROOT / "tests/reader_windows_compact/check_ui.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
sys.path.insert(0, str(ROOT / 'tests/reader_perf_windows'))
from perf_windows import make_txt_fixture
sys.path.insert(0, str(ROOT / 'tests/reader_a11y_windows'))
from uia_layer import Uia

FONT_INC = 114
FONT_DEC = 113


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def rows(app):
    books = app.control('books')
    found = []
    for index in range(ui.send(books, 0x18B)):
        buffer = C.create_unicode_buffer(2048)
        ui.send(books, 0x189, index, C.addressof(buffer))
        found.append(buffer.value)
    return found


def page_text(app, automation):
    return automation.control(app.control('page')).GetValuePattern().Value or ''


def first_line(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[0] if lines else ''


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    exe, font, out, pdf = map(lambda value: Path(value).resolve(), sys.argv[1:5])
    out.mkdir(parents=True, exist_ok=False)
    fixture = make_txt_fixture(out, 0)
    expected = '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
    assert fixture.stat().st_size == 16792975 and digest(fixture) == expected
    # A second, independent identity: same shape, different bytes and size.
    isolated = out / 'Isolated.txt'
    lines = ['Isolated Book %04d keeps its own reading position line %04d.' % (index, index) for index in range(1200)]
    isolated.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    report = dict(source_sha=os.environ['GITHUB_SHA'], host_sha256=digest(exe), checks=[],
                  scope='native Windows host: product TXT position save/restore, relayout, identity isolation, refused write and SDK book regression',
                  accepted=False)
    app = None

    def record(name, detail=''):
        report['checks'].append(dict(name=name, passed=True, detail=str(detail)))
        print('CHECK ' + name + ' :: ' + str(detail), flush=True)

    def progress_heads(key):
        with sqlite3.connect(str(app.db) + '.product.sqlite', timeout=20) as db:
            found = db.execute('SELECT revision_id, body_json, body_sha256 FROM reader_revisions '
                               "WHERE entity_kind='progress' AND entity_key=?", (key,)).fetchall()
        parents = {parent for _, body, _ in found for parent in json.loads(body)['parents']}
        return {row[0]: row[2] for row in found if row[0] not in parents}, len(found)

    def select_row(fragment):
        found = rows(app)
        index = [n for n, line in enumerate(found) if fragment in line]
        assert index, (fragment, found)
        ui.send(app.control('books'), 0x186, index[0])
        return index[0]

    def open_row(fragment):
        select_row(fragment)
        app.click('open')
        app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=240)
        app.wait_idle()

    def press_font_increase():
        ui.send(ui.U.GetDlgItem(app.window, FONT_INC), 0xF5)  # BM_CLICK

    try:
        profile = out / 'profile'
        app = ui.P.App(exe, font, profile)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error

        ui.picker(app, pdf)
        app.wait(lambda: len(rows(app)) == 1, timeout=180)
        ui.picker(app, fixture)
        assert 'TXT 原书已保存' in app.status(), app.status()
        app.wait(lambda: len(rows(app)) == 2, timeout=300)
        record('native TXT import adds one product original after the SDK book', app.status())

        open_row(fixture.name)
        assert 'Perf Import 0000' in page_text(app, automation), page_text(app, automation)[:200]
        record('shelf selection opens the 16792975-byte original at its first page')

        seen = [first_line(page_text(app, automation))]
        for _ in range(6):
            app.click('next')
            app.wait_idle()
            current = first_line(page_text(app, automation))
            assert current and current not in seen, (current, seen)
            assert current > seen[-1], (current, seen[-1])
            seen.append(current)
        record('six forward page turns show consecutive source content', seen[-1])

        before_font = page_text(app, automation)
        press_font_increase()
        app.wait_idle()
        after_font = page_text(app, automation)
        marker = first_line(before_font)
        assert marker and marker in after_font, (marker, after_font[:300])
        position_line = first_line(after_font)
        record('font increase relayouts and keeps the content position', marker)

        heads, count = progress_heads('txt:' + expected)
        assert count >= 1 and heads, (count, heads)
        record('product progress history exists for the content identity',
               'revisions=%d heads=%d' % (count, len(heads)))

        app.close(); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 2, timeout=180)
        open_row(fixture.name)
        restored = page_text(app, automation)
        assert '已按内容位置恢复' in app.status(), app.status()
        assert first_line(restored) == position_line, (first_line(restored), position_line)
        record('close and restart restore the same content position', position_line)

        ui.picker(app, isolated)
        app.wait(lambda: len(rows(app)) == 3, timeout=300)
        open_row(isolated.name)
        isolated_text = page_text(app, automation)
        assert 'Isolated Book 0000' in isolated_text, isolated_text[:200]
        assert '还没有保存过阅读位置' in app.status(), app.status()
        record('a different book identity starts at its own first page', app.status())

        app.close(); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 3, timeout=180)
        open_row(isolated.name)
        assert 'Isolated Book 0000' in page_text(app, automation), page_text(app, automation)[:200]
        open_row(fixture.name)
        assert first_line(page_text(app, automation)) == position_line, page_text(app, automation)[:200]
        record('restart keeps both content identities independent')

        heads_before, count_before = progress_heads('txt:' + expected)
        lock = sqlite3.connect(str(app.db) + '.product.sqlite', isolation_level=None, timeout=0.2)
        lock.execute('PRAGMA busy_timeout=200')
        locked = False
        for _ in range(60):
            try:
                lock.execute('BEGIN EXCLUSIVE')
                locked = True
                break
            except sqlite3.OperationalError:
                time.sleep(0.2)
        assert locked, 'could not hold the product database write lock'
        press_font_increase()
        app.wait_idle()
        app.wait(lambda: '阅读位置未保存' in app.status(), timeout=120)
        refused = app.status()
        # A refused write must not trap the exit either: the window still closes.
        app.close(); app = None
        lock.execute('ROLLBACK')
        lock.close()
        heads_after, count_after = progress_heads('txt:' + expected)
        assert heads_after == heads_before, (heads_before, heads_after)
        assert count_after == count_before, (count_before, count_after)
        record('a refused write keeps the retained record and still exits', refused)

        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 3, timeout=180)
        open_row(fixture.name)
        assert first_line(page_text(app, automation)) == position_line, page_text(app, automation)[:200]
        record('restart after the refused write restores the durable position', position_line)

        open_row(pdf.name)
        sdk_first = page_text(app, automation)
        app.click('next')
        app.wait_idle()
        sdk_second = page_text(app, automation)
        app.close(); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        automation = Uia()
        assert automation.available, automation.error
        app.wait(lambda: len(rows(app)) == 3, timeout=180)
        open_row(pdf.name)
        sdk_restored = page_text(app, automation)
        if sdk_second and sdk_second != sdk_first:
            assert sdk_restored == sdk_second, (sdk_restored[:120], sdk_second[:120])
            record('existing SDK fixed-page book restores its own position', sdk_restored[:80])
        else:
            assert sdk_restored == sdk_first, (sdk_restored[:120], sdk_first[:120])
            record('existing SDK fixed-page book reopens with its single page', sdk_restored[:80])
        report['accepted'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if app:
            try:
                app.close()
            except Exception:
                pass
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    # The runner console is cp1252: report the outcome as ASCII only, and keep the
    # full record in report.json for the artifact.
    summary = dict(accepted=report['accepted'], checks=[row['name'] for row in report['checks']],
                   error=(report.get('error') or '').splitlines()[-1:] or None)
    print(json.dumps(summary, ensure_ascii=True), flush=True)
    assert report['accepted'], 'TXT position host acceptance failed; see report.json'


if __name__ == '__main__':
    main()
