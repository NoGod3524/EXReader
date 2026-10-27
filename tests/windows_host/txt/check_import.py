"""Actions-only native shelf coverage for product-owned TXT originals."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
import check_ui as ui
sys.path.insert(0, str(ROOT / 'tests/reader_perf_windows'))
from perf_windows import make_txt_fixture


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
                  scope='native shelf and picker; TXT reading is not implemented', accepted=False)
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
        with catalog() as db:
            sdk_before = db.execute('SELECT book_key,sdk_book_id FROM reader_local_books').fetchall()
        assert len(sdk_before) == 1 and sdk_before[0][1] > 0, sdk_before
        sdk_line = rows()[0]
        ui.picker(app, fixture)
        assert '阅读功能尚未完成' in app.status(), app.status()
        app.wait(lambda: selected() >= 0 and selected() < len(rows()) and '阅读尚未支持' in rows()[selected()], timeout=60)
        original_line = rows()[selected()]
        assert rows().count(original_line) == 1, rows()
        app.click('open'); app.wait_idle()
        assert '阅读功能尚未完成' in app.status(), app.status()
        report['checks'].append('large original appears selected and opening reports incomplete reader')
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
