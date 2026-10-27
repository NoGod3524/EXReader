"""Actions-only native shelf coverage for product-owned TXT originals."""
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
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


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    exe, font, out, pdf = map(lambda x: Path(x).resolve(), sys.argv[1:5])
    out.mkdir(parents=True, exist_ok=False)
    fixture = make_txt_fixture(out, 0)
    expected = '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
    def digest(path):
        with path.open('rb') as f:
            return hashlib.file_digest(f, 'sha256').hexdigest()
    assert fixture.stat().st_size == 16792975 and digest(fixture) == expected
    report = dict(source_sha=os.environ['GITHUB_SHA'], host_sha256=digest(exe), checks=[],
                  scope='native shelf, verified TXT page turns and SDK book; restart position remains unimplemented', accepted=False)
    app = None
    try:
        profile = out / 'profile'
        app = ui.P.App(exe, font, profile)
        app.wait_idle()
        def rows():
            books = app.control('books')
            result = []
            for i in range(ui.send(books, 0x18B)):
                buf = C.create_unicode_buffer(1024)
                ui.send(books, 0x189, i, C.addressof(buf))
                result.append(buf.value)
            return result
        def selected():
            return ui.send(app.control('books'), 0x188)
        def catalog():
            return sqlite3.connect(str(app.db) + '.product.sqlite')
        ui.picker(app, pdf)
        app.wait(lambda: len(rows()) == 1, timeout=60)
        def sdk_rows():
            with catalog() as db:
                return db.execute('SELECT book_key,sdk_book_id FROM reader_local_books').fetchall()
        sdk_before = app.wait(lambda: sdk_rows() or None, timeout=60)
        assert len(sdk_before) == 1 and sdk_before[0][1] > 0, sdk_before
        sdk_line = rows()[0]
        ui.picker(app, fixture)
        assert '阅读功能尚未完成' in app.status(), app.status()
        app.wait(lambda: selected() >= 0 and selected() < len(rows()) and fixture.name in rows()[selected()], timeout=60)
        original_line = rows()[selected()]
        assert rows().count(original_line) == 1, rows()
        app.click('open'); app.wait_idle()
        app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=120)
        assert '阅读位置保存尚未实现' in app.status(), app.status()
        automation = Uia()
        assert automation.available, automation.error
        page = automation.control(app.control('page'))
        value = page.GetValuePattern().Value
        assert value and 'Perf Import 0000' in value and 'line 0000' in value, value
        assert ui.P.U.IsWindowEnabled(app.control('next'))
        first = value
        app.click('next'); app.wait_idle()
        second = automation.control(app.control('page')).GetValuePattern().Value
        assert second and second != first, second
        # This fixture has unique consecutive line numbers in its first 512 lines.
        source_text = fixture.read_text(encoding='utf-8')
        assert first in source_text and second in source_text
        assert source_text.index(second) >= source_text.index(first) + len(first)
        ui.P.M.screenshot(app.window, out / 'txt-second-page.bmp')
        app.click('prev'); app.wait_idle()
        back = automation.control(app.control('page')).GetValuePattern().Value
        assert back == first, back
        report['checks'].append('native next and previous show distinct consecutive source text and restore first page')
        ui.P.M.screenshot(app.window, out / 'txt-first-page.bmp')
        report['page_excerpt'] = value[:300]
        report['checks'].append('selected 16792975-byte original renders first page with expected UI Automation text and screenshot')
        original = Path(str(app.db) + '.originals') / (expected + '.txt')
        assert original.stat().st_size == 16792975 and digest(original) == expected
        with catalog() as db:
            assert db.execute('SELECT book_key,state FROM reader_originals').fetchall() == [('txt:' + expected, 'ready')]
            assert db.execute('SELECT book_key,sdk_book_id FROM reader_local_books').fetchall() == sdk_before
        report['checks'].append('stable content key and unchanged SDK identity')
        app.close(); app = None
        app = ui.P.App(exe, font, profile, existing=True)
        app.wait_idle()
        app.wait(lambda: original_line in rows(), timeout=60)
        ui.picker(app, fixture)
        assert 'TXT 原书已存在' in app.status(), app.status()
        app.wait(lambda: selected() >= 0 and selected() < len(rows()) and rows()[selected()] == original_line, timeout=60)
        assert rows().count(original_line) == 1, rows()
        with catalog() as db:
            assert db.execute('SELECT book_key,state FROM reader_originals').fetchall() == [('txt:' + expected, 'ready')]
            assert db.execute('SELECT book_key,sdk_book_id FROM reader_local_books').fetchall() == sdk_before
        assert digest(original) == expected and digest(fixture) == expected
        report['checks'].append('restart and duplicate retain one selected stable row')
        # Search uses the same native bounded shelf query for both types.
        search = ui.U.GetDlgItem(app.window, 126)
        ui.P.set_text(search, fixture.name)
        app.wait(lambda: rows() == [original_line], timeout=60)
        ui.P.set_text(search, '')
        app.wait(lambda: len(rows()) == 2 and sdk_line in rows(), timeout=60)
        ui.send(app.control('books'), 0x186, rows().index(sdk_line))
        app.click('open'); app.wait_idle()
        app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=60)
        report['checks'].append('filter and SDK selection/open remain functional')
        report['accepted'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if app: app.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    assert report['accepted']


if __name__ == '__main__':
    main()
